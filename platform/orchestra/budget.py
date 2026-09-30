"""Budget : compteur en direct (tokens et euros), alerte à 80 %, blocage dur à 100 %."""
from __future__ import annotations

from typing import Any

from orchestra.models import BudgetExceeded, Actor, OrchestraError, now, now_iso


class BudgetService:
    def __init__(self, p):
        self.p = p
        self.db = p.db

    # ------------------------------------------------------------------ périodes
    @staticmethod
    def _month_start() -> str:
        return now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")

    @staticmethod
    def _day_start() -> str:
        return now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")

    @property
    def cap(self) -> float:
        return float(self.p.cfg.budget.monthly_eur)

    def month_spent(self) -> float:
        return float(self.db.scalar(
            "SELECT COALESCE(SUM(montant_eur),0) FROM budget_entries WHERE kind IN ('llm','depense') AND horodatage>=?",
            (self._month_start(),)) or 0)

    def agent_day_spent(self, agent_id: str) -> float:
        return float(self.db.scalar(
            "SELECT COALESCE(SUM(montant_eur),0) FROM budget_entries WHERE agent_id=? AND kind IN ('llm','depense') AND horodatage>=?",
            (agent_id, self._day_start())) or 0)

    def agent_month_spent(self, agent_id: str) -> float:
        return float(self.db.scalar(
            "SELECT COALESCE(SUM(montant_eur),0) FROM budget_entries WHERE agent_id=? AND kind IN ('llm','depense') AND horodatage>=?",
            (agent_id, self._month_start())) or 0)

    def team_month_spent(self, responsable_id: str) -> float:
        ids = [responsable_id] + [a["id"] for a in self.db.query("SELECT id FROM agents")
                                  if self.p.perms.is_descendant(a["id"], responsable_id)]
        q = ",".join("?" * len(ids))
        return float(self.db.scalar(
            f"SELECT COALESCE(SUM(montant_eur),0) FROM budget_entries WHERE agent_id IN ({q}) AND kind IN ('llm','depense') AND horodatage>=?",
            (*ids, self._month_start())) or 0)

    def is_blocked(self) -> bool:
        return self.month_spent() >= self.cap - 1e-9

    # ------------------------------------------------------------------ contrôle AVANT dépense
    def check(self, agent: dict | None, amount_eur: float) -> None:
        if amount_eur <= 0:
            return  # modèle local / gratuit : aucune dépense
        spent = self.month_spent()
        if spent + amount_eur > self.cap + 1e-9:
            self._blocked_alert()
            raise BudgetExceeded(f"plafond mensuel atteint ({spent:.2f} € / {self.cap:.2f} €)")
        if agent:
            day = self.agent_day_spent(agent["id"])
            if day + amount_eur > float(agent.get("budget_jour_eur") or 0) + 1e-9:
                raise BudgetExceeded(f"budget du jour de {agent['nom']} épuisé ({day:.2f} € / {agent['budget_jour_eur']:.2f} €)")
            team = self.p.perms.team_root(agent["id"])
            if team:
                resp = self.p.perms.agent(team)
                env = resp.get("budget_mois_eur") if resp else None
                if env is not None and self.team_month_spent(team) + amount_eur > float(env) + 1e-9:
                    raise BudgetExceeded(f"enveloppe mensuelle de l'équipe {resp['nom']} épuisée")

    # ------------------------------------------------------------------ enregistrement
    def record_llm(self, agent_id: str | None, model: str, tokens_in: int, tokens_out: int, eur: float,
                   correlation_id: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO budget_entries(horodatage,agent_id,kind,montant_eur,tokens_in,tokens_out,modele,description) VALUES(?,?,?,?,?,?,?,?)",
            (now_iso(), agent_id, "llm", eur, tokens_in, tokens_out, model, "appel de modèle"),
        )
        self._thresholds()

    def record_expense(self, actor: Actor, montant_eur: float, description: str, agent_id: str | None = None) -> None:
        self.p.perms.require(actor, "spend.external", None, montant=montant_eur)
        if self.p.emergency.active:
            raise OrchestraError("arrêt d'urgence actif : aucune dépense possible")
        agent = self.p.perms.agent(agent_id or actor.id) if actor.is_agent or agent_id else None
        if agent and actor.is_agent:
            self.check(agent, montant_eur)
        elif self.month_spent() + montant_eur > self.cap + 1e-9:
            self._blocked_alert()
            raise BudgetExceeded("plafond mensuel atteint")
        self.db.execute(
            "INSERT INTO budget_entries(horodatage,agent_id,kind,montant_eur,description) VALUES(?,?,?,?,?)",
            (now_iso(), agent_id or (actor.id if actor.is_agent else None), "depense", montant_eur, description),
        )
        self.p.audit.record("depense", description, agent_id=actor.id, niveau=actor.niveau, cout_eur=montant_eur)
        self._thresholds()

    def record_revenue(self, actor: Actor, montant_eur: float, description: str) -> None:
        if not actor.is_owner:
            raise OrchestraError("seul le Propriétaire enregistre un revenu")
        self.db.execute("INSERT INTO budget_entries(horodatage,kind,montant_eur,description) VALUES(?,?,?,?)",
                        (now_iso(), "revenu", montant_eur, description))
        self.p.audit.record("revenu", description, agent_id=actor.id, niveau=actor.niveau, cout_eur=-montant_eur)

    def _thresholds(self) -> None:
        spent, month = self.month_spent(), now().strftime("%Y-%m")
        ratio = spent / self.cap
        self.p.bus.publish("budget", spent=round(spent, 4), cap=self.cap, ratio=round(ratio, 4))
        if ratio >= self.p.cfg.budget.alert_ratio and not self.db.get_state(f"budget_80_{month}"):
            self.db.set_state(f"budget_80_{month}", now_iso())
            self.p.alerts.raise_("budget_80", f"Budget à {ratio:.0%} ({spent:.2f} € / {self.cap:.2f} €)", gravite="grave")
        if ratio >= 1:
            self._blocked_alert()

    def _blocked_alert(self) -> None:
        month = now().strftime("%Y-%m")
        if not self.db.get_state(f"budget_100_{month}"):
            self.db.set_state(f"budget_100_{month}", now_iso())
            self.p.alerts.raise_("budget_100", "Budget mensuel atteint : toute dépense est bloquée", gravite="critique")

    # ------------------------------------------------------------------ tableau de bord
    def summary(self) -> dict[str, Any]:
        ms = self._month_start()
        by_agent = self.db.query(
            "SELECT b.agent_id, a.nom, SUM(b.montant_eur) eur, SUM(b.tokens_in+b.tokens_out) tokens FROM budget_entries b "
            "LEFT JOIN agents a ON a.id=b.agent_id WHERE b.kind IN ('llm','depense') AND b.horodatage>=? GROUP BY b.agent_id ORDER BY eur DESC",
            (ms,))
        by_model = self.db.query(
            "SELECT modele, COUNT(*) appels, SUM(tokens_in) tokens_in, SUM(tokens_out) tokens_out, SUM(montant_eur) eur "
            "FROM budget_entries WHERE kind='llm' AND horodatage>=? GROUP BY modele ORDER BY appels DESC", (ms,))
        by_day = self.db.query(
            "SELECT substr(horodatage,1,10) jour, SUM(CASE WHEN kind IN ('llm','depense') THEN montant_eur ELSE 0 END) depenses, "
            "SUM(CASE WHEN kind='revenu' THEN montant_eur ELSE 0 END) revenus, SUM(tokens_in+tokens_out) tokens "
            "FROM budget_entries WHERE horodatage>=? GROUP BY jour ORDER BY jour", (ms,))
        revenus = float(self.db.scalar("SELECT COALESCE(SUM(montant_eur),0) FROM budget_entries WHERE kind='revenu' AND horodatage>=?", (ms,)) or 0)
        spent = self.month_spent()
        return {"plafond_eur": self.cap, "depense_eur": round(spent, 4), "ratio": round(spent / self.cap, 4),
                "alerte_ratio": self.p.cfg.budget.alert_ratio, "bloque": spent >= self.cap,
                "revenus_eur": round(revenus, 2), "par_agent": by_agent, "par_modele": by_model, "par_jour": by_day}

    def agent_costs(self, agent_id: str) -> dict[str, Any]:
        a = self.p.perms.agent(agent_id)
        return {"jour_eur": round(self.agent_day_spent(agent_id), 4), "mois_eur": round(self.agent_month_spent(agent_id), 4),
                "budget_jour_eur": a["budget_jour_eur"] if a else 0,
                "tokens_mois": int(self.db.scalar("SELECT COALESCE(SUM(tokens_in+tokens_out),0) FROM budget_entries WHERE agent_id=? AND horodatage>=?",
                                                  (agent_id, self._month_start())) or 0)}
