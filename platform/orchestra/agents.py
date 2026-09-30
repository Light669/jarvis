"""Service Agents : création, modification versionnée, cycle de vie, promotion."""
from __future__ import annotations

from typing import Any, Callable

from orchestra.db import Database, enc
from orchestra.models import (LEVELS, RANK, TRANSITIONS, Actor, NotFound, OrchestraError,
                              now_iso, slugify)
from orchestra.vault import LEVEL_DIRS

EDITABLE = ("nom", "niveau", "parent_id", "statut", "modele", "budget_jour_eur", "budget_mois_eur",
            "outils", "skills", "kpi", "role", "contexte", "instructions", "objectif", "interdits", "journal")
LIST_FIELDS = {"outils", "skills", "kpi"}


class AgentService:
    def __init__(self, p):  # p: Platform
        self.p = p
        self.db: Database = p.db
        self.listeners: list[Callable[[str, dict, Actor, dict | None], None]] = []

    # ------------------------------------------------------------------ lecture
    def get(self, agent_id: str) -> dict:
        a = self.db.one("SELECT * FROM agents WHERE id=?", (agent_id,))
        if not a:
            raise NotFound(f"agent {agent_id} introuvable")
        return a

    def list(self, include_archived: bool = True) -> list[dict]:
        where = "" if include_archived else "WHERE statut!='archive'"
        return self.db.query(f"SELECT * FROM agents {where} ORDER BY id")

    def find(self, ref: str) -> dict | None:
        ref = (ref or "").strip().strip("[]")
        return (self.db.one("SELECT * FROM agents WHERE id=?", (ref,))
                or self.db.one("SELECT * FROM agents WHERE nom=? ORDER BY statut='archive'", (ref,))
                or self.db.one("SELECT * FROM agents WHERE vault_path LIKE ?", (f"%/{slugify(ref)}.md",)))

    def versions(self, agent_id: str) -> list[dict]:
        return self.db.query("SELECT * FROM agent_versions WHERE agent_id=? ORDER BY version DESC", (agent_id,))

    # ------------------------------------------------------------------ création
    def _next_id(self) -> str:
        n = self.db.scalar("SELECT COALESCE(MAX(CAST(substr(id,7) AS INTEGER)),0) FROM agents WHERE id LIKE 'agent-%'")
        return f"agent-{int(n) + 1:04d}"

    def note_path(self, nom: str, niveau: str, agent_id: str | None = None) -> str:
        base = f"Agents/{LEVEL_DIRS[niveau]}/{slugify(nom)}"
        existing = self.db.one("SELECT id FROM agents WHERE vault_path=?", (base + ".md",))
        if existing and existing["id"] != agent_id:
            base += f"-{(agent_id or 'x')[-4:]}"
        return base + ".md"

    def _validate_structure(self, niveau: str, parent_id: str | None, agent_id: str | None = None) -> None:
        if niveau not in LEVELS:
            raise OrchestraError(f"niveau invalide : {niveau}")
        if niveau == "chef":
            if parent_id:
                raise OrchestraError("le Chef d'Orchestre n'a pas de supérieur")
            other = self.db.one("SELECT id FROM agents WHERE niveau='chef' AND statut!='archive' AND id!=?", (agent_id or "",))
            if other:
                raise OrchestraError(f"un Chef d'Orchestre existe déjà ({other['id']})")
            return
        if not parent_id:
            raise OrchestraError("un supérieur est obligatoire")
        parent = self.db.one("SELECT * FROM agents WHERE id=?", (parent_id,))
        if not parent or parent["statut"] == "archive":
            raise OrchestraError("supérieur introuvable ou archivé")
        if RANK[parent["niveau"]] != RANK[niveau] - 1:
            raise OrchestraError(f"un {niveau} doit être rattaché à un {LEVELS[RANK[niveau] - 1]}")

    def create(self, actor: Actor, data: dict[str, Any], raison: str = "création") -> dict:
        niveau = data.get("niveau", "salarie")
        parent_id = data.get("parent_id") or None
        self.p.perms.require(actor, "agent.create", None, niveau=niveau, parent_id=parent_id)
        self._validate_structure(niveau, parent_id)
        nom = (data.get("nom") or "").strip()
        if not nom:
            raise OrchestraError("le nom est obligatoire")
        ts = now_iso()
        with self.db.transaction():
            agent_id = data.get("id") if data.get("id") and not self.db.one("SELECT 1 FROM agents WHERE id=?", (data["id"],)) else self._next_id()
            row = {
                "id": agent_id, "nom": nom, "niveau": niveau, "parent_id": parent_id,
                "statut": data.get("statut") or "brouillon",
                "modele": data.get("modele") or self.p.cfg.llm.default_model,
                "budget_jour_eur": float(data.get("budget_jour_eur", self.p.cfg.budget.default_agent_daily_eur) or 0),
                "budget_mois_eur": data.get("budget_mois_eur"),
                "outils": enc(list(data.get("outils") or [])), "skills": enc(list(data.get("skills") or [])),
                "kpi": enc(list(data.get("kpi") or [])),
                **{k: self.p.redactor.secrets(str(data.get(k) or "")) for k in ("role", "contexte", "instructions", "objectif", "interdits", "journal")},
                "cree_par": actor.id, "cree_le": data.get("cree_le") or ts, "modifie_le": ts, "version": 1,
                "vault_path": data.get("vault_path") or self.note_path(nom, niveau, agent_id),
            }
            if row["statut"] not in ("brouillon", "actif", "pause"):
                raise OrchestraError("statut initial invalide")
            cols = ",".join(row)
            self.db.execute(f"INSERT INTO agents({cols}) VALUES({','.join('?' * len(row))})", tuple(row.values()))
            agent = self.get(agent_id)
            self._snapshot(agent, actor, raison)
        self.p.audit.record("agent", "creation", agent_id=actor.id, niveau=actor.niveau, cible=agent_id,
                            details={"apres": _public(agent)})
        self.p.bus.publish("agent_created", agent=agent)
        self._notify("created", agent, actor)
        return agent

    # ------------------------------------------------------------------ modification
    def update(self, actor: Actor, agent_id: str, changes: dict[str, Any], raison: str = "modification",
               _action: str = "agent.update") -> dict:
        before = self.get(agent_id)
        changes = {k: v for k, v in changes.items() if k in EDITABLE}
        diff = {}
        for k, v in changes.items():
            if k in LIST_FIELDS:
                v = list(v or [])
            elif k in ("budget_jour_eur",):
                v = float(v or 0)
            elif k == "budget_mois_eur":
                v = None if v in (None, "") else float(v)
            elif k == "parent_id":
                v = v or None
            elif isinstance(v, str) or v is None:
                v = self.p.redactor.secrets(v or "")
            if before.get(k) != v:
                diff[k] = v
        if not diff:
            return before
        if _action == "agent.update":
            self.p.perms.require(actor, "agent.update", before, fields=set(diff))
            if {"budget_jour_eur", "budget_mois_eur"} & diff.keys():
                self.p.perms.require(actor, "budget.set", before)
        if "statut" in diff and diff["statut"] not in TRANSITIONS[before["statut"]]:
            raise OrchestraError(f"transition interdite : {before['statut']} → {diff['statut']}")
        if "niveau" in diff or "parent_id" in diff:
            niveau = diff.get("niveau", before["niveau"])
            self._validate_structure(niveau, diff.get("parent_id", before["parent_id"]), agent_id)
            if "niveau" in diff and self.db.one("SELECT 1 FROM agents WHERE parent_id=? AND statut!='archive'", (agent_id,)):
                raise OrchestraError("réaffecter d'abord les subordonnés de cet agent")
        if "niveau" in diff or "nom" in diff:
            diff["vault_path"] = self.note_path(diff.get("nom", before["nom"]), diff.get("niveau", before["niveau"]), agent_id)
        with self.db.transaction():
            sets = {k: (enc(v) if k in LIST_FIELDS else v) for k, v in diff.items()}
            sets["modifie_le"] = now_iso()
            sets["version"] = before["version"] + 1
            self.db.execute(
                f"UPDATE agents SET {','.join(f'{k}=?' for k in sets)} WHERE id=?", (*sets.values(), agent_id)
            )
            after = self.get(agent_id)
            self._snapshot(after, actor, raison)
        self.p.audit.record(
            "agent", "modification_fiche", agent_id=actor.id, niveau=actor.niveau, cible=agent_id,
            details={"raison": raison, "version": after["version"],
                     "avant": {k: before.get(k) for k in diff}, "apres": {k: after.get(k) for k in diff}},
        )
        self.p.bus.publish("agent_updated", agent=after, changed=sorted(diff), previous_level=before["niveau"])
        self._notify("updated", after, actor, before=before)
        return after

    def _snapshot(self, agent: dict, actor: Actor, raison: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO agent_versions(agent_id,version,snapshot,auteur,horodatage,raison) VALUES(?,?,?,?,?,?)",
            (agent["id"], agent["version"], enc(_public(agent)), actor.id, now_iso(), raison),
        )

    def restore_version(self, actor: Actor, agent_id: str, version: int, raison: str | None = None) -> dict:
        v = self.db.one("SELECT * FROM agent_versions WHERE agent_id=? AND version=?", (agent_id, version))
        if not v:
            raise NotFound(f"version {version} introuvable")
        snap = v["snapshot"]
        fields = {k: snap.get(k) for k in ("role", "contexte", "instructions", "objectif", "interdits", "kpi", "skills", "outils", "modele", "budget_jour_eur")}
        return self.update(actor, agent_id, fields, raison or f"restauration de la version {version}")

    # ------------------------------------------------------------------ cycle de vie
    def set_status(self, actor: Actor, agent_id: str, statut: str, raison: str = "") -> dict:
        a = self.get(agent_id)
        self.p.perms.require(actor, "agent.lifecycle", a, statut=statut)
        if statut == "archive":
            if not raison:
                raise OrchestraError("la raison de l'archivage est obligatoire")
            if self.db.one("SELECT 1 FROM agents WHERE parent_id=? AND statut!='archive'", (agent_id,)):
                raise OrchestraError("réaffecter d'abord les subordonnés de cet agent")
            self.db.execute("UPDATE agents SET archive_raison=? WHERE id=?", (raison, agent_id))
        labels = {"actif": "activation", "pause": "mise_en_pause", "archive": "archivage"}
        out = self.update(actor, agent_id, {"statut": statut}, raison or labels.get(statut, statut), _action="lifecycle")
        self.p.audit.record("agent", labels.get(statut, statut), agent_id=actor.id, niveau=actor.niveau,
                            cible=agent_id, details={"raison": raison})
        return out

    def promote(self, actor: Actor, agent_id: str, new_parent_id: str | None = None, raison: str = "promotion") -> dict:
        return self._change_level(actor, agent_id, -1, new_parent_id, raison, "promotion")

    def demote(self, actor: Actor, agent_id: str, new_parent_id: str | None = None, raison: str = "rétrogradation") -> dict:
        return self._change_level(actor, agent_id, +1, new_parent_id, raison, "retrogradation")

    def _change_level(self, actor: Actor, agent_id: str, delta: int, new_parent_id: str | None, raison: str, label: str) -> dict:
        a = self.get(agent_id)
        self.p.perms.require(actor, "agent.lifecycle", a, operation=label)
        r = RANK[a["niveau"]] + delta
        if r < 1 or r > 3:
            raise OrchestraError(f"{label} impossible depuis le niveau {a['niveau']}")
        niveau = LEVELS[r]
        if not new_parent_id:
            if delta < 0:  # promotion : on remonte d'un cran, rattaché au supérieur de son supérieur
                parent = self.get(a["parent_id"]) if a["parent_id"] else None
                new_parent_id = parent["parent_id"] if parent else None
            else:
                raise OrchestraError("rétrogradation : indiquer le nouveau supérieur")
        out = self.update(actor, agent_id, {"niveau": niveau, "parent_id": new_parent_id}, raison, _action="lifecycle")
        self.p.audit.record("agent", label, agent_id=actor.id, niveau=actor.niveau, cible=agent_id,
                            details={"de": a["niveau"], "vers": niveau, "raison": raison})
        self.p.bus.publish("agent_level_changed", agent=out, de=a["niveau"], vers=niveau, operation=label)
        return out

    def set_activity(self, agent_id: str, activite: str, detail: str = "") -> None:
        """inactif | travail | attente | erreur — pour l'animation de la carte."""
        self.db.execute("UPDATE agents SET activite=?, activite_detail=? WHERE id=?", (activite, detail[:300], agent_id))
        self.p.bus.publish("agent_activity", agent_id=agent_id, activite=activite, detail=detail[:300])

    def _notify(self, kind: str, agent: dict, actor: Actor, **kw: Any) -> None:
        for cb in list(self.listeners):
            cb(kind, agent, actor, kw.get("before"))


def _public(agent: dict) -> dict:
    return {k: agent.get(k) for k in ("id", *EDITABLE, "version", "vault_path")}
