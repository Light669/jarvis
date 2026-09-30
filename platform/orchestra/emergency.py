"""Arrêt d'urgence : gèle tous les agents et coupe tout accès externe."""
from __future__ import annotations

import threading
import time

from orchestra.models import Actor, now_iso


class EmergencyService:
    def __init__(self, p):
        self.p = p
        self._flag = threading.Event()
        if p.db.get_state("emergency", "0") == "1":
            self._flag.set()  # l'arrêt survit à un redémarrage

    @property
    def active(self) -> bool:
        return self._flag.is_set()

    def stop(self, actor: Actor, raison: str = "arrêt d'urgence") -> dict:
        self.p.perms.require(actor, "emergency.stop")
        t0 = time.monotonic()
        self._flag.set()
        self.p.db.set_state("emergency", "1")
        self.p.db.set_state("emergency_since", now_iso())
        killed = 0
        runtime = getattr(self.p, "runtime", None)
        if runtime:
            killed = runtime.freeze_all()
        frozen = self.p.db.query("SELECT id FROM agents WHERE activite IN ('travail','attente')")
        for a in frozen:
            self.p.agents.set_activity(a["id"], "gele", "arrêt d'urgence")
        elapsed = time.monotonic() - t0
        self.p.audit.record("urgence", "arret_urgence", agent_id=actor.id, niveau=actor.niveau, resultat=raison,
                            gravite="critique", details={"duree_s": round(elapsed, 3), "conteneurs_arretes": killed})
        self.p.alerts.raise_("arret_urgence", f"Arrêt d'urgence déclenché par {actor.nom or actor.id} : {raison}", gravite="critique")
        self.p.bus.publish("emergency", active=True, raison=raison)
        return {"active": True, "duree_s": round(elapsed, 3), "conteneurs_arretes": killed}

    def resume(self, actor: Actor) -> dict:
        self.p.perms.require(actor, "emergency.resume")
        self._flag.clear()
        self.p.db.set_state("emergency", "0")
        self.p.db.execute("UPDATE agents SET activite='inactif', activite_detail='' WHERE activite='gele'")
        self.p.audit.record("urgence", "reprise", agent_id=actor.id, niveau=actor.niveau, gravite="attention")
        self.p.bus.publish("emergency", active=False)
        return {"active": False}

    def wait(self, timeout: float) -> bool:
        return self._flag.wait(timeout)
