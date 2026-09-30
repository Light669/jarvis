"""Moteur de permissions : SEUL point d'autorisation de la plateforme.

Les règles sont appliquées ici, par le code, jamais par le prompt d'un agent.
Tout refus est journalisé (type `permission_refusee`) et signalé par une alerte.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from orchestra.models import LEVELS, RANK, Actor, PermissionDenied

if TYPE_CHECKING:
    from orchestra.alerts import AlertService
    from orchestra.audit import AuditLog
    from orchestra.db import Database

# Champs qu'un agent peut modifier sur SA propre fiche (amélioration continue dans son périmètre).
SELF_EDITABLE = {"contexte", "instructions", "objectif", "kpi", "journal"}
# Champs qu'un responsable peut modifier sur les fiches de son équipe.
MANAGER_EDITABLE = SELF_EDITABLE | {"role", "interdits", "skills"}
# Champs de structure / garde-fous : Chef (hors Chef) ou Propriétaire uniquement.
STRUCTURAL = {"nom", "niveau", "parent_id", "statut", "modele", "budget_jour_eur", "budget_mois_eur", "outils"}

# Outils de base selon le niveau (en plus des outils listés dans la fiche).
BASE_TOOLS = {
    "chef": {"envoyer_message", "faire_demande", "chercher_memoire", "ecrire_note", "creer_skill", "utiliser_skill", "executer_code"},
    "responsable": {"envoyer_message", "faire_demande", "chercher_memoire", "ecrire_note", "creer_skill", "utiliser_skill", "executer_code"},
    "salarie": {"envoyer_message", "faire_demande", "chercher_memoire", "ecrire_note", "creer_skill", "utiliser_skill", "executer_code"},
    "apprenti": {"envoyer_message", "faire_demande", "chercher_memoire", "ecrire_note", "creer_skill", "utiliser_skill"},
}
# Zones du coffre lisibles par tous les agents.
SHARED_READ = ("Skills/", "Apprentissages/", "Modeles_de_notes/", "00_Accueil.md")


@dataclass
class Decision:
    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


ALLOW = Decision(True)


def deny(reason: str) -> Decision:
    return Decision(False, reason)


class Permissions:
    def __init__(self, db: "Database", audit: "AuditLog", alerts: "AlertService"):
        self.db, self.audit, self.alerts = db, audit, alerts

    # ------------------------------------------------------------------ hiérarchie
    def agent(self, agent_id: str | None) -> dict | None:
        if not agent_id:
            return None
        return self.db.one("SELECT * FROM agents WHERE id=?", (agent_id,))

    def ancestors(self, agent_id: str) -> list[str]:
        out, cur, seen = [], self.agent(agent_id), set()
        while cur and cur.get("parent_id") and cur["parent_id"] not in seen:
            seen.add(cur["parent_id"])
            out.append(cur["parent_id"])
            cur = self.agent(cur["parent_id"])
        return out

    def is_descendant(self, agent_id: str, of_id: str) -> bool:
        return of_id in self.ancestors(agent_id)

    def team_root(self, agent_id: str) -> str | None:
        """Responsable de l'équipe de l'agent (lui-même s'il est responsable)."""
        a = self.agent(agent_id)
        if not a:
            return None
        if a["niveau"] == "responsable":
            return a["id"]
        if a["niveau"] == "chef":
            return None
        for anc in self.ancestors(agent_id):
            if (x := self.agent(anc)) and x["niveau"] == "responsable":
                return x["id"]
        return None

    def same_team(self, a: str, b: str) -> bool:
        ta, tb = self.team_root(a), self.team_root(b)
        return ta is not None and ta == tb

    def tools_of(self, agent: dict) -> set[str]:
        return set(BASE_TOOLS.get(agent["niveau"], set())) | set(agent.get("outils") or [])

    # ------------------------------------------------------------------ décision
    def check(self, actor: Actor, action: str, target: Any = None, **ctx: Any) -> Decision:
        if action in ("logs.modify", "logs.delete"):
            return deny("les journaux sont en ajout seul : personne ne peut les modifier")
        if actor.is_owner:
            return ALLOW
        if action == "platform.modify":
            return deny("modification de la plateforme : validation explicite du Propriétaire requise")
        if actor.is_system:
            return ALLOW if action not in ("emergency.resume",) else deny("réservé au Propriétaire")
        me = self.agent(actor.id)
        if not me or me["statut"] == "archive":
            return deny("agent inconnu ou archivé")
        fn = getattr(self, "_" + action.replace(".", "_"), None)
        if fn is None:
            return deny(f"action inconnue : {action}")
        return fn(me, target, **ctx)

    def require(self, actor: Actor, action: str, target: Any = None, **ctx: Any) -> None:
        d = self.check(actor, action, target, **ctx)
        if not d:
            cible = target.get("id") if isinstance(target, dict) else (str(target) if target is not None else None)
            self.audit.record(
                "permission_refusee", action, agent_id=actor.id, niveau=actor.niveau, cible=cible,
                resultat=d.reason, gravite="attention", details={k: str(v)[:200] for k, v in ctx.items()},
            )
            self.alerts.raise_("action_interdite", f"{actor.nom or actor.id} : {action} refusé — {d.reason}",
                               gravite="attention", agent_id=actor.id if actor.is_agent else None)
            raise PermissionDenied(d.reason)

    # ------------------------------------------------------------------ règles par action
    def _agent_create(self, me: dict, target: Any, niveau: str = "", parent_id: str | None = None, **_: Any) -> Decision:
        if niveau not in LEVELS:
            return deny("niveau invalide")
        if me["niveau"] == "chef":
            return ALLOW if niveau in ("responsable", "salarie", "apprenti") else deny("le Chef ne crée pas de Chef")
        if me["niveau"] == "responsable":
            if niveau != "apprenti":
                return deny("un Responsable ne peut créer que des apprentis")
            if parent_id and (parent_id == me["id"] or self.is_descendant(parent_id, me["id"])):
                return ALLOW
            return deny("l'apprenti doit être rattaché à un membre de son équipe")
        return deny(f"un {me['niveau']} ne peut pas créer d'agent")

    def _agent_update(self, me: dict, target: dict, fields: set[str] | None = None, **_: Any) -> Decision:
        fields = set(fields or [])
        if target["id"] == me["id"]:
            extra = fields - SELF_EDITABLE
            if me["niveau"] == "chef" and not extra & {"niveau", "parent_id", "budget_jour_eur", "budget_mois_eur", "statut"}:
                return ALLOW
            return ALLOW if not extra else deny(f"champs protégés sur sa propre fiche : {sorted(extra)}")
        if me["niveau"] == "chef":
            return ALLOW if target["niveau"] != "chef" else deny("seul le Propriétaire modifie le Chef")
        if me["niveau"] == "responsable" and self.is_descendant(target["id"], me["id"]):
            extra = fields - MANAGER_EDITABLE
            return ALLOW if not extra else deny(f"champs réservés au Chef : {sorted(extra)}")
        return deny("modification d'une fiche hors de son périmètre")

    def _agent_lifecycle(self, me: dict, target: dict, **_: Any) -> Decision:
        if me["niveau"] == "chef" and target["niveau"] != "chef":
            return ALLOW
        return deny("promotion, rétrogradation, pause et licenciement : Chef ou Propriétaire")

    def _budget_set(self, me: dict, target: dict, **_: Any) -> Decision:
        if me["niveau"] == "chef" and target["id"] != me["id"]:
            return ALLOW
        return deny("répartition du budget : Chef d'Orchestre ou Propriétaire")

    def _request_decide(self, me: dict, target: dict, **_: Any) -> Decision:
        if target["a"] == me["id"]:
            if target["type"] == "plateforme":
                return deny("une modification de la plateforme ne peut être validée que par le Propriétaire")
            return ALLOW
        return deny("seul le destinataire de la demande peut y répondre")

    def _vault_write(self, me: dict, target: str, **_: Any) -> Decision:
        path = str(target).replace("\\", "/").lstrip("/")
        if ".." in path.split("/"):
            return deny("chemin invalide")
        ws = workspace_of(me)
        if ws and path.startswith(ws):
            return ALLOW
        return deny(f"écriture hors de son dossier ({ws})")

    def _vault_read(self, me: dict, target: str, **_: Any) -> Decision:
        path = str(target).replace("\\", "/").lstrip("/")
        if ".." in path.split("/"):
            return deny("chemin invalide")
        if me["niveau"] == "chef" or path.startswith(SHARED_READ):
            return ALLOW
        allowed_ids = {me["id"]}
        if me["niveau"] == "responsable":
            allowed_ids |= {a["id"] for a in self.db.query("SELECT id FROM agents") if self.is_descendant(a["id"], me["id"])}
        for aid in allowed_ids:
            a = self.agent(aid)
            ws = workspace_of(a)
            if ws and (path.startswith(ws) or path == a.get("vault_path")):
                return ALLOW
            if path.startswith(f"Messages/{aid}/"):
                return ALLOW
        return deny("lecture hors de son périmètre")

    def _skill_create(self, me: dict, target: Any, portee: str = "agent", **_: Any) -> Decision:
        return self._skill_scope(me, portee)

    def _skill_publish(self, me: dict, target: Any, portee: str = "agent", **_: Any) -> Decision:
        return self._skill_scope(me, portee)

    def _skill_scope(self, me: dict, portee: str) -> Decision:
        if portee == "agent":
            return ALLOW
        if portee == "equipe":
            if me["niveau"] in ("chef", "responsable"):
                return ALLOW
            return deny("portée équipe : demande formelle au Responsable requise")
        if portee == "global":
            return ALLOW if me["niveau"] == "chef" else deny("portée globale : réservée au Chef d'Orchestre")
        return deny("portée inconnue")

    def _spend_external(self, me: dict, target: Any, **_: Any) -> Decision:
        if me["niveau"] in ("chef", "responsable"):
            return ALLOW
        return deny("un salarié ou un apprenti ne peut pas engager de dépense")

    def _tool_use(self, me: dict, target: str, **_: Any) -> Decision:
        return ALLOW if target in self.tools_of(me) else deny(f"outil non autorisé par la fiche : {target}")

    def _emergency_stop(self, me: dict, target: Any, **_: Any) -> Decision:
        return ALLOW if me["niveau"] == "chef" else deny("arrêt d'urgence : Chef ou Propriétaire")

    def _emergency_resume(self, me: dict, target: Any, **_: Any) -> Decision:
        return deny("reprise après arrêt d'urgence : Propriétaire uniquement")

    def _task_assign(self, me: dict, target: dict, **_: Any) -> Decision:
        if me["niveau"] == "chef" or self.is_descendant(target["id"], me["id"]):
            return ALLOW
        return deny("on ne confie une tâche qu'à un subordonné")

    def _task_validate(self, me: dict, target: dict, **_: Any) -> Decision:
        agent_id = target["agent_id"]
        if agent_id == me["id"]:
            return deny("un agent ne valide pas son propre travail")
        if me["niveau"] == "chef" or self.is_descendant(agent_id, me["id"]):
            return ALLOW
        return deny("validation réservée à la hiérarchie de l'agent")

    def _message_send(self, me: dict, target: dict, **_: Any) -> Decision:
        return self.can_message(me, target)

    # ------------------------------------------------------------------ communication (§7)
    def can_message(self, sender: dict, recipient: dict | str) -> Decision:
        if isinstance(recipient, str):  # proprietaire
            if recipient == "proprietaire":
                return ALLOW if sender["niveau"] == "chef" else deny("seul le Chef écrit au Propriétaire : passer par le supérieur")
            return deny("destinataire inconnu")
        if recipient["statut"] == "archive":
            return deny("destinataire archivé")
        if sender["id"] == recipient["id"]:
            return deny("message à soi-même")
        if sender["niveau"] == "chef":
            return ALLOW
        if recipient["id"] == sender.get("parent_id") or recipient.get("parent_id") == sender["id"]:
            return ALLOW  # ligne hiérarchique directe
        if sender["niveau"] == recipient["niveau"]:
            if sender["niveau"] == "responsable" or self.same_team(sender["id"], recipient["id"]):
                return ALLOW  # pairs du même niveau, même équipe
            return deny("autre équipe : passer par son supérieur, qui relaie ou autorise")
        if sender["niveau"] == "apprenti":
            return deny("un apprenti n'écrit qu'à son référent et aux apprentis de son équipe")
        return deny("autre niveau : passer par son supérieur, qui relaie ou autorise")


def workspace_of(agent: dict | None) -> str | None:
    """Dossier personnel d'un agent dans le coffre (seule zone où il écrit directement)."""
    if not agent or not agent.get("vault_path"):
        return None
    vp = agent["vault_path"]
    return vp[:-3] + "/" if vp.endswith(".md") else vp.rstrip("/") + "/"


def rank(niveau: str) -> int:
    return RANK[niveau]
