"""Alertes : base + journal + événement temps réel (le notifier Windows s'y abonne)."""
from __future__ import annotations

import time

from orchestra.audit import AuditLog
from orchestra.db import Database
from orchestra.events import EventBus
from orchestra.models import now_iso

GRAVITES = ("info", "attention", "grave", "critique")


class AlertService:
    def __init__(self, db: Database, audit: AuditLog, bus: EventBus, dedup_seconds: float = 60):
        self.db, self.audit, self.bus = db, audit, bus
        self.dedup_seconds = dedup_seconds
        self._last: dict[tuple[str, str | None, str], float] = {}

    def raise_(self, type_: str, message: str, *, gravite: str = "attention", agent_id: str | None = None) -> int | None:
        key = (type_, agent_id, message)
        t = time.monotonic()
        if t - self._last.get(key, -1e9) < self.dedup_seconds:
            return None
        self._last[key] = t
        message = self.audit.redactor.full(message)
        cur = self.db.execute(
            "INSERT INTO alerts(horodatage,gravite,type,message,agent_id) VALUES(?,?,?,?,?)",
            (now_iso(), gravite, type_, message, agent_id),
        )
        alert_id = cur.lastrowid
        self.audit.record("alerte", type_, agent_id=agent_id, resultat=message, gravite=gravite,
                          details={"alerte_id": alert_id})
        self.bus.publish("alert", id=alert_id, gravite=gravite, alerte=type_, message=message, agent_id=agent_id)
        return alert_id

    def list(self, only_unread: bool = False, limit: int = 100) -> list[dict]:
        where = "WHERE lue=0" if only_unread else ""
        return self.db.query(f"SELECT * FROM alerts {where} ORDER BY id DESC LIMIT ?", (limit,))

    def mark_read(self, alert_id: int) -> None:
        self.db.execute("UPDATE alerts SET lue=1 WHERE id=?", (alert_id,))
