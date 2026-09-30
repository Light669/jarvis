"""API FastAPI : 127.0.0.1 uniquement, jeton local obligatoire, WebSocket temps réel."""
from __future__ import annotations

import asyncio
import hmac
import os
import secrets
import signal
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from orchestra.models import OWNER, OrchestraError
from orchestra.platform import Platform

DASHBOARD_DIST = Path(__file__).resolve().parents[2] / "dashboard" / "dist"


def _ensure_token(p: Platform) -> str:
    token = os.environ.get("ORCHESTRA_TOKEN") or p.env.get("ORCHESTRA_TOKEN")
    if token:
        return token
    token = secrets.token_hex(32)
    env_path = p.root / ".env"
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = [l for l in text.splitlines() if not l.startswith("ORCHESTRA_TOKEN=")] + [f"ORCHESTRA_TOKEN={token}"]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    p.env["ORCHESTRA_TOKEN"] = token
    p.redactor.literals.insert(0, token)
    return token


def create_app(root: Path | None = None, platform: Platform | None = None, background: bool = True) -> FastAPI:
    p = platform or Platform(root)  # type: ignore[arg-type]
    token = _ensure_token(p)
    if token not in p.redactor.literals:
        p.redactor.literals.insert(0, token)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        p.audit.record("systeme", "demarrage_api", agent_id=OWNER.id, niveau="proprietaire")
        tasks = []
        if background and hasattr(p, "start_background"):
            tasks = p.start_background()
        yield
        for t in tasks:
            t.cancel()
        p.audit.record("systeme", "arret_api", agent_id=OWNER.id, niveau="proprietaire")
        if platform is None:
            p.close()

    app = FastAPI(title="Orchestra", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.platform = p

    # --------------------------------------------------------------- sécurité
    def check_token(given: str | None) -> bool:
        return bool(given) and hmac.compare_digest(given.encode(), token.encode())

    def auth(request: Request) -> None:
        h = request.headers.get("authorization", "")
        given = h[7:] if h.lower().startswith("bearer ") else request.headers.get("x-orchestra-token")
        if not check_token(given):
            p.audit.record("tableau_de_bord", "acces_refuse", cible=request.url.path, resultat="jeton invalide",
                           gravite="attention", details={"client": request.client.host if request.client else None})
            raise OrchestraError("jeton invalide")

    @app.exception_handler(OrchestraError)
    async def _err(request: Request, exc: OrchestraError):
        status = 401 if str(exc) == "jeton invalide" else exc.status
        return JSONResponse({"detail": str(exc)}, status_code=status)

    @app.middleware("http")
    async def _log_actions(request: Request, call_next):
        if request.client and request.client.host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            return JSONResponse({"detail": "accès local uniquement"}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith("/api/") and request.method != "GET":
            p.audit.record("tableau_de_bord", f"{request.method} {request.url.path}", agent_id=OWNER.id,
                           niveau="proprietaire", resultat=str(response.status_code),
                           gravite="info" if response.status_code < 400 else "attention")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    # --------------------------------------------------------------- routes
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "emergency": p.db.get_state("emergency", "0") == "1"}

    from orchestra.api import routes

    routes.register(app, p, auth)

    @app.post("/api/system/shutdown", dependencies=[Depends(auth)])
    async def shutdown() -> dict[str, Any]:
        p.audit.record("systeme", "arret_demande", agent_id=OWNER.id, niveau="proprietaire")
        loop = asyncio.get_running_loop()
        loop.call_later(0.5, lambda: os.kill(os.getpid(), signal.SIGINT))
        return {"ok": True}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        if not check_token(websocket.query_params.get("token")):
            p.audit.record("tableau_de_bord", "connexion_ws_refusee", resultat="jeton invalide", gravite="attention")
            await websocket.close(code=4401)
            return
        await websocket.accept()
        p.audit.record("tableau_de_bord", "connexion", agent_id=OWNER.id, niveau="proprietaire", cible="websocket")
        q = p.bus.subscribe()
        try:
            while True:
                event = await q.get()
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            p.bus.unsubscribe(q)

    # --------------------------------------------------------------- tableau de bord statique
    if DASHBOARD_DIST.exists():
        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            f = (DASHBOARD_DIST / path).resolve()
            if path and f.is_file() and DASHBOARD_DIST in f.parents:
                return FileResponse(f)
            return FileResponse(DASHBOARD_DIST / "index.html")

    return app
