"""Routes REST du tableau de bord. Toutes les actions sont faites au nom du Propriétaire."""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import Depends, FastAPI, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from orchestra.models import OWNER, OrchestraError


class AgentIn(BaseModel):
    nom: str
    niveau: str = "salarie"
    parent_id: str | None = None
    statut: str = "actif"
    modele: str | None = None
    role: str = ""
    contexte: str = ""
    instructions: str = ""
    objectif: str = ""
    kpi: list[str] = []
    outils: list[str] = []
    skills: list[str] = []
    interdits: str = ""
    budget_jour_eur: float | None = None
    budget_mois_eur: float | None = None


class AgentPatch(BaseModel):
    nom: str | None = None
    parent_id: str | None = None
    modele: str | None = None
    role: str | None = None
    contexte: str | None = None
    instructions: str | None = None
    objectif: str | None = None
    kpi: list[str] | None = None
    outils: list[str] | None = None
    skills: list[str] | None = None
    interdits: str | None = None
    journal: str | None = None
    budget_jour_eur: float | None = None
    budget_mois_eur: float | None = None
    raison: str | None = None


class Reason(BaseModel):
    raison: str = ""
    new_parent_id: str | None = None


def register(app: FastAPI, p, auth) -> None:
    dep = [Depends(auth)]

    # ------------------------------------------------------------------ agents
    @app.get("/api/agents", dependencies=dep)
    def list_agents(include_archived: bool = True) -> list[dict]:
        return p.agents.list(include_archived)

    @app.post("/api/agents", dependencies=dep)
    def create_agent(body: AgentIn) -> dict:
        data = body.model_dump()
        if data["budget_jour_eur"] is None:
            data.pop("budget_jour_eur")
        return p.agents.create(OWNER, data)

    @app.get("/api/agents/{agent_id}", dependencies=dep)
    def get_agent(agent_id: str) -> dict:
        return p.agents.get(agent_id)

    @app.patch("/api/agents/{agent_id}", dependencies=dep)
    def patch_agent(agent_id: str, body: AgentPatch) -> dict:
        changes = body.model_dump(exclude_unset=True)
        raison = changes.pop("raison", None) or "modification par le Propriétaire"
        return p.agents.update(OWNER, agent_id, changes, raison)

    @app.post("/api/agents/{agent_id}/{action}", dependencies=dep)
    def agent_action(agent_id: str, action: str, body: Reason | None = None) -> dict:
        body = body or Reason()
        if action in ("pause", "resume", "activate", "archive"):
            statut = {"pause": "pause", "resume": "actif", "activate": "actif", "archive": "archive"}[action]
            return p.agents.set_status(OWNER, agent_id, statut, body.raison)
        if action == "promote":
            return p.agents.promote(OWNER, agent_id, body.new_parent_id, body.raison or "promotion par le Propriétaire")
        if action == "demote":
            return p.agents.demote(OWNER, agent_id, body.new_parent_id, body.raison or "rétrogradation par le Propriétaire")
        raise OrchestraError(f"action inconnue : {action}")

    @app.get("/api/agents/{agent_id}/versions", dependencies=dep)
    def versions(agent_id: str) -> list[dict]:
        return p.agents.versions(agent_id)

    @app.post("/api/agents/{agent_id}/restore/{version}", dependencies=dep)
    def restore(agent_id: str, version: int) -> dict:
        return p.agents.restore_version(OWNER, agent_id, version)

    # ------------------------------------------------------------------ logs
    def _logs_query(q: str | None, agent_id: str | None, niveau: str | None, type_evenement: str | None,
                    gravite: str | None, since: str | None, until: str | None, limit: int, offset: int) -> list[dict]:
        where, params = [], []
        if q:
            terms = " ".join(f'"{t}"' for t in re.findall(r"[\w\-]+", q, flags=re.UNICODE))
            if terms:
                where.append("seq IN (SELECT rowid FROM log_fts WHERE log_fts MATCH ?)")
                params.append(terms)
        for col, val in (("agent_id", agent_id), ("niveau", niveau), ("type_evenement", type_evenement), ("gravite", gravite)):
            if val:
                where.append(f"{col}=?")
                params.append(val)
        if since:
            where.append("horodatage>=?")
            params.append(since)
        if until:
            where.append("horodatage<=?")
            params.append(until + "￿" if len(until) == 10 else until)
        sql = "SELECT * FROM log_index" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY seq DESC LIMIT ? OFFSET ?"
        rows = p.db.query(sql, (*params, limit, offset))
        for r in rows:
            r.pop("ligne", None)
        return rows

    @app.get("/api/logs", dependencies=dep)
    def logs(q: str | None = None, agent_id: str | None = None, niveau: str | None = None,
             type_evenement: str | None = None, gravite: str | None = None, since: str | None = None,
             until: str | None = None, limit: int = Query(200, le=5000), offset: int = 0) -> list[dict]:
        return _logs_query(q, agent_id, niveau, type_evenement, gravite, since, until, limit, offset)

    @app.get("/api/logs/export.csv", dependencies=dep)
    def logs_csv(q: str | None = None, agent_id: str | None = None, niveau: str | None = None,
                 type_evenement: str | None = None, gravite: str | None = None, since: str | None = None,
                 until: str | None = None):
        rows = _logs_query(q, agent_id, niveau, type_evenement, gravite, since, until, 100000, 0)
        buf = io.StringIO()
        cols = ["seq", "horodatage", "agent_id", "niveau", "type_evenement", "action", "cible", "resultat",
                "gravite", "cout_tokens", "cout_eur", "correlation_id"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(rows)
        p.audit.record("tableau_de_bord", "export_logs_csv", agent_id=OWNER.id, niveau="proprietaire", details={"lignes": len(rows)})
        return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=orchestra-logs.csv"})

    @app.get("/api/logs/verify", dependencies=dep)
    def verify() -> dict[str, Any]:
        rep = p.verify_logs()
        if not rep.ok:
            p.alerts.raise_("integrite_logs", "Intégrité des logs compromise : " + "; ".join(rep.errors[:3]), gravite="critique")
        return {"ok": rep.ok, "fichiers": rep.files, "lignes": rep.lines, "erreurs": rep.errors}

    # ------------------------------------------------------------------ alertes
    @app.get("/api/alerts", dependencies=dep)
    def alerts(only_unread: bool = False) -> list[dict]:
        return p.alerts.list(only_unread)

    @app.post("/api/alerts/{alert_id}/read", dependencies=dep)
    def alert_read(alert_id: int) -> dict:
        p.alerts.mark_read(alert_id)
        return {"ok": True}

    @app.get("/api/events/recent", dependencies=dep)
    def recent_events() -> list[dict]:
        return list(p.bus.recent)[-200:]

    for extra in getattr(p, "route_registrars", []):
        extra(app, p, dep)
