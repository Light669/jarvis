"""Conteneur des services de la plateforme (un seul objet partagé par l'API et les tests)."""
from __future__ import annotations

import json
from pathlib import Path

from orchestra.agents import AgentService
from orchestra.alerts import AlertService
from orchestra.audit import AuditLog, verify_chain
from orchestra.budget import BudgetService
from orchestra.emergency import EmergencyService
from orchestra.gateway import LLMGateway
from orchestra.runtime.runner import Runtime
from orchestra.config import load_config, load_env
from orchestra.db import Database
from orchestra.events import EventBus
from orchestra.permissions import Permissions
from orchestra.redact import Redactor
from orchestra.vault import VaultGit, init_vault


class Platform:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.cfg = load_config(self.root)
        self.env = load_env(self.root)
        self.vault_dir = self.root / self.cfg.paths.vault
        self.data_dir = self.root / self.cfg.paths.data
        self.logs_dir = self.root / self.cfg.paths.logs
        for d in (self.data_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        init_vault(self.vault_dir)
        self.git = VaultGit(self.vault_dir)
        self.git.ensure_repo()

        self.redactor = Redactor(self.env)
        self.db = Database(self.data_dir / "orchestra.db")
        self.bus = EventBus()
        self.audit = AuditLog(self.logs_dir, self.redactor)
        self.audit.listeners.append(self._index_log)
        self.alerts = AlertService(self.db, self.audit, self.bus)
        self.perms = Permissions(self.db, self.audit, self.alerts)
        self.agents = AgentService(self)
        self.emergency = EmergencyService(self)
        self.budget = BudgetService(self)
        self.gateway = LLMGateway(self)
        self.runtime = Runtime(self)
        self.route_registrars: list = []

    # ------------------------------------------------------------------ logs
    def _index_log(self, entry: dict) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO log_index(seq,horodatage,agent_id,niveau,type_evenement,action,cible,resultat,gravite,"
            "cout_tokens,cout_eur,correlation_id,ligne) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (entry["seq"], entry["horodatage"], entry["agent_id"], entry["niveau"], entry["type_evenement"],
             entry["action"], entry["cible"], entry["resultat"], entry["gravite"], entry["cout_tokens"],
             entry["cout_eur"], entry["correlation_id"], json.dumps(entry, ensure_ascii=False)),
        )
        text = " ".join(str(x) for x in (entry["type_evenement"], entry["action"], entry["cible"] or "",
                                          entry["resultat"], entry["agent_id"] or "",
                                          json.dumps(entry["details"], ensure_ascii=False)))
        self.db.execute("INSERT INTO log_fts(rowid, texte) VALUES(?,?)", (entry["seq"], text))
        self.db.set_state("audit_head", json.dumps([entry["seq"], entry["hash"]]))
        self.bus.publish("log", entry={k: entry[k] for k in ("seq", "horodatage", "agent_id", "type_evenement",
                                                           "action", "cible", "resultat", "gravite")})

    def verify_logs(self):
        head = self.db.get_state("audit_head")
        return verify_chain(self.logs_dir, tuple(json.loads(head)) if head else None)

    def close(self) -> None:
        self.db.close()
