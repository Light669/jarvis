"""Commandes en ligne : init, serve, verify-logs, scan-secrets."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def find_root() -> Path:
    env = os.environ.get("ORCHESTRA_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for p in [here, *here.parents]:
        if (p / "config.yaml").exists() and (p / "platform").exists():
            return p
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestra", description="Plateforme Orchestra")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="Crée le coffre, la base et les dossiers")
    sub.add_parser("serve", help="Lance l'API, le Scribe et le planificateur")
    sub.add_parser("verify-logs", help="Vérifie l'intégrité de la chaîne de hash des logs")
    sub.add_parser("scan-secrets", help="Recherche de secrets dans logs/ et Cerveau/")
    args = parser.parse_args(argv)
    root = find_root()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    if args.cmd == "init":
        from orchestra.platform import Platform

        p = Platform(root)
        p.close()
        print(f"Orchestra initialisé dans {root}")
        return 0

    if args.cmd == "serve":
        import uvicorn

        from orchestra.api.app import create_app
        from orchestra.config import load_config

        cfg = load_config(root)
        app = create_app(root)
        uvicorn.run(app, host=cfg.server.host, port=cfg.server.port, log_level="info")
        return 0

    if args.cmd == "verify-logs":
        from orchestra.audit import verify_chain
        from orchestra.config import load_config

        cfg = load_config(root)
        report = verify_chain(root / cfg.paths.logs)
        if report.ok:
            print(f"Intégrité OK : {report.lines} lignes dans {report.files} fichiers")
            return 0
        print("INTÉGRITÉ COMPROMISE :")
        for err in report.errors:
            print(f"  - {err}")
        return 2

    if args.cmd == "scan-secrets":
        from orchestra.config import load_config, load_env
        from orchestra.redact import scan_paths

        cfg = load_config(root)
        hits = scan_paths([root / cfg.paths.logs, root / cfg.paths.vault], load_env(root))
        if not hits:
            print("Aucun secret détecté dans logs/ et le coffre.")
            return 0
        for h in hits:
            print(f"SECRET POSSIBLE : {h}")
        return 3
    return 1
