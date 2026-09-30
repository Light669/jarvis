"""Conteneur des services de la plateforme (un seul objet partagé par l'API et les tests)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

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
from orchestra.improvement import ImprovementService
from orchestra.messaging import MessagingService
from orchestra.redact import Redactor
from orchestra.scribe.scribe import Scribe
from orchestra.scribe.writer import VaultWriter
from orchestra.simulation import SimulationService
from orchestra.skills import SkillService
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
        self.alerts = AlertService(self.db, self.audit, self.bus, email_cfg=self.cfg.alerts.email, env=self.env)
        self.perms = Permissions(self.db, self.audit, self.alerts)
        self.agents = AgentService(self)
        self.emergency = EmergencyService(self)
        self.budget = BudgetService(self)
        self.gateway = LLMGateway(self)
        self.runtime = Runtime(self)
        self.writer = VaultWriter(self)
        self.messaging = MessagingService(self)
        self.scribe = Scribe(self)
        self.skills = SkillService(self)
        self.improvement = ImprovementService(self)
        self.simulation = SimulationService(self)
        self.route_registrars: list = []

    # ------------------------------------------------------------------ tâches de fond
    def background_jobs(self) -> list[tuple[float, str, Callable[[], object]]]:
        return [
            (60, "escalade_demandes", self.messaging.escalate_overdue),
            (4, "simulation", self.simulation.tick),
            (300, "commit_coffre", lambda: self.git.commit("Synchronisation périodique du coffre")),
            (600, "rapports_amelioration", self.improvement.scheduled),
            (3600, "verification_integrite", self.check_integrity),
            (3600, "test_arret_urgence", self.emergency.scheduled_self_test),
        ]

    def start_background(self) -> list[asyncio.Task]:
        loop = asyncio.get_running_loop()

        async def every(seconds: float, name: str, fn: Callable[[], object]) -> None:
            while True:
                await asyncio.sleep(seconds)
                try:
                    await asyncio.to_thread(fn)
                except Exception as e:  # une tâche de fond ne doit jamais arrêter la plateforme
                    self.audit.record("systeme", "erreur_tache_fond", resultat=f"{name}: {e}", gravite="grave")
                    self.alerts.raise_("erreur_grave", f"Tâche de fond {name} en erreur : {e}", gravite="grave")

        self.scribe.reindex()
        self.scribe.start()
        self.check_integrity()
        return [loop.create_task(every(s, n, f)) for s, n, f in self.background_jobs()]

    def stop_background(self) -> None:
        self.scribe.stop()
        self.git.commit("Arrêt de la plateforme")

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

    def check_integrity(self):
        rep = self.verify_logs()
        if not rep.ok:
            self.alerts.raise_("integrite_logs", "Intégrité des logs compromise : " + "; ".join(rep.errors[:3]), gravite="critique")
        return rep

    def verify_logs(self):
        head = self.db.get_state("audit_head")
        return verify_chain(self.logs_dir, tuple(json.loads(head)) if head else None)

    def close(self) -> None:
        self.scribe.stop()
        self.git.flush()
        self.db.close()
