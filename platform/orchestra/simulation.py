"""Mode simulation du MVP : fait vivre l'organisation de démonstration.

Toutes les actions passent par les VRAIS services (permissions, messagerie, runtime, skills, journal) :
la simulation ne fait que choisir quoi faire. Elle n'agit que sur les agents au modèle `demo/…`,
jamais pendant un arrêt d'urgence, et peut être mise en pause depuis le tableau de bord.
"""
from __future__ import annotations

import random

from orchestra.models import OrchestraError, agent_actor, system

SIM = system("simulation")

CONSIGNES = {
    "chef": ["Faire le point hebdomadaire avec les responsables", "Arbitrer le budget du mois", "Préparer le rapport pour le Propriétaire"],
    "responsable": ["Planifier la semaine de l'équipe", "Relire le travail des salariés", "Prioriser les demandes en attente"],
    "salarie": ["Qualifier 5 prospects BTP à Lyon", "Rédiger 3 brouillons de relance", "Monter une vidéo verticale de 30 s",
                "Analyser les statistiques de la semaine", "Mettre à jour la liste des clients"],
    "apprenti": ["Préparer une liste de 10 entreprises", "Vérifier les numéros SIREN", "Classer les notes de la semaine"],
}
SUJETS = [("Point rapide", "Où en es-tu sur ta tâche ?"), ("Liste partagée", "Je t'envoie la liste mise à jour."),
          ("Question", "As-tu le modèle de devis ?"), ("Bravo", "Beau travail sur le dernier livrable.")]


class SimulationService:
    def __init__(self, p, seed: int | None = None):
        self.p = p
        self.rng = random.Random(seed)

    @property
    def active(self) -> bool:
        return self.p.db.get_state("simulation", "0") == "1"

    def set_active(self, value: bool) -> dict:
        self.p.db.set_state("simulation", "1" if value else "0")
        self.p.audit.record("systeme", "simulation_" + ("activee" if value else "arretee"), agent_id="proprietaire", niveau="proprietaire")
        self.p.bus.publish("simulation", active=value)
        return {"active": value}

    def _agents(self) -> list[dict]:
        return [a for a in self.p.agents.list(include_archived=False) if a["statut"] == "actif" and a["modele"].startswith("demo/")]

    def tick(self) -> str | None:
        if not self.active or self.p.emergency.active:
            return None
        agents = self._agents()
        if not agents:
            return None
        r = self.rng.random()
        try:
            if r < 0.40:
                return self._task(agents)
            if r < 0.60:
                return self._message(agents)
            if r < 0.72:
                return self._request(agents)
            if r < 0.80:
                return self._decide()
            if r < 0.94:
                return self._validate()
            if r < 0.97:
                return self._forbidden(agents)
            return self._skill(agents)
        except OrchestraError as e:  # un refus fait partie du spectacle : il est déjà journalisé
            return f"refus : {e}"

    # ------------------------------------------------------------------ actions
    def _task(self, agents: list[dict]) -> str | None:
        idle = [a for a in agents if a["activite"] not in ("travail",)]
        if not idle:
            return None
        a = self.rng.choice(idle)
        t = self.p.runtime.assign(SIM, a["id"], self.rng.choice(CONSIGNES[a["niveau"]]))
        return f"tâche {t['id']} → {a['nom']}"

    def _message(self, agents: list[dict]) -> str | None:
        a = self.rng.choice(agents)
        ok = [b for b in agents if b["id"] != a["id"] and self.p.perms.can_message(a, b)]
        if not ok:
            return None
        b = self.rng.choice(ok)
        sujet, corps = self.rng.choice(SUJETS)
        self.p.messaging.send(agent_actor(a), b["id"], sujet, corps)
        return f"message {a['nom']} → {b['nom']}"

    def _request(self, agents: list[dict]) -> str | None:
        cand = [a for a in agents if a["niveau"] in ("salarie", "apprenti") and a["parent_id"]]
        if not cand or len(self.p.messaging.pending()) >= 4:
            return None
        a = self.rng.choice(cand)
        kind, sujet, why = self.rng.choice([("aide", "Besoin d'aide", "Bloqué sur un cas client"),
                                            ("validation", "Validation du livrable", "Livrable prêt à relire")])
        self.p.messaging.request(agent_actor(a), kind, sujet, why, "Gagner du temps")
        return f"demande de {a['nom']}"

    def _decide(self) -> str | None:
        pending = [r for r in self.p.messaging.pending() if r["a"].startswith("agent-") and r["type"] in ("aide", "validation")]
        if not pending:
            return None
        r = self.rng.choice(pending)
        dec = self.p.agents.get(r["a"])
        accept = self.rng.random() < 0.75
        self.p.messaging.decide(agent_actor(dec), r["id"], accept, "OK, on avance" if accept else "Voir avec ton pair d'abord")
        return f"demande {'acceptée' if accept else 'refusée'} par {dec['nom']}"

    def _validate(self) -> str | None:
        rows = self.p.db.query("SELECT t.* FROM tasks t JOIN agents a ON a.id=t.agent_id WHERE t.statut='terminee' AND t.succes IS NULL "
                               "AND a.modele LIKE 'demo/%' AND a.parent_id IS NOT NULL LIMIT 20")
        if not rows:
            return None
        t = self.rng.choice(rows)
        a = self.p.agents.get(t["agent_id"])
        ok = self.rng.random() < 0.85
        self.p.runtime.validate(agent_actor(self.p.agents.get(a["parent_id"])), t["id"], ok, None if ok else "qualité insuffisante")
        return f"tâche {'validée' if ok else 'en échec'} ({a['nom']})"

    def _forbidden(self, agents: list[dict]) -> str | None:
        """Un apprenti tente de sortir de son périmètre : le code refuse, la carte montre le refus."""
        apprentis = [a for a in agents if a["niveau"] == "apprenti"]
        targets = [a for a in agents if a["niveau"] == "responsable"]
        if not apprentis or not targets:
            return None
        a, b = self.rng.choice(apprentis), self.rng.choice(targets)
        self.p.messaging.send(agent_actor(a), b["id"], "Je veux parler au responsable", "Sans passer par mon référent")
        return None

    def _skill(self, agents: list[dict]) -> str | None:
        cand = [a for a in agents if a["niveau"] == "salarie"]
        if not cand:
            return None
        a = self.rng.choice(cand)
        n = int(self.p.db.scalar("SELECT COUNT(*) FROM skills WHERE auteur=?", (a["id"],)) or 0)
        if n >= 3:
            return None
        s = self.p.skills.create(agent_actor(a), {
            "nom": f"{a['nom']}-astuce-{n + 1}",
            "contenu": f"## Quand l'utiliser\nProcédure n°{n + 1} de {a['nom']} pour {self.rng.choice(CONSIGNES['salarie']).lower()}.\n"
                       "## Étapes\n1. Relire la consigne.\n2. Réutiliser les notes de l'équipe.\n3. Rendre compte au responsable.",
        })
        return f"skill {s['nom']} ({s['statut']})"
