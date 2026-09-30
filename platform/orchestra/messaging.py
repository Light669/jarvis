"""Messagerie entre agents (§7) : messages, demandes formelles, relais, escalade, anti-boucle.

Un message reçu est une DONNÉE : il ne peut jamais élever les droits de son destinataire.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Any

from orchestra.models import (OWNER_ID, Actor, EmergencyStop, NotFound, OrchestraError, RateLimited,
                              new_id, now, now_iso, system)

REQUEST_TYPES = ("acces_outil", "budget", "aide", "validation", "skill_equipe", "promotion", "plateforme")
PRIORITES = ("basse", "normale", "haute", "urgente")


class MessagingService:
    def __init__(self, p):
        self.p = p
        self.db = p.db

    # ------------------------------------------------------------------ destinataires
    def _resolve(self, ref: str) -> dict | str:
        if ref in (OWNER_ID, "Propriétaire", "proprietaire"):
            return OWNER_ID
        a = self.p.agents.find(ref)
        if not a:
            raise NotFound(f"destinataire inconnu : {ref}")
        return a

    def _name(self, ref: str) -> str:
        if ref == OWNER_ID:
            return "Propriétaire"
        a = self.p.perms.agent(ref)
        return a["nom"] if a else ref

    # ------------------------------------------------------------------ envoi
    def send(self, actor: Actor, to: str, sujet: str, corps: str, *, thread_id: str | None = None,
             parent_id: str | None = None, priorite: str = "normale", correlation_id: str | None = None,
             relaye_de: str | None = None, kind: str = "message") -> dict:
        recipient = self._resolve(to)
        to_id = recipient if isinstance(recipient, str) else recipient["id"]
        if actor.is_agent:
            if self.p.emergency.active:
                raise EmergencyStop("arrêt d'urgence : messagerie gelée")
            self.p.perms.require(actor, "message.send", recipient)
            self._anti_loop(actor, thread_id)
        if priorite not in PRIORITES:
            priorite = "normale"
        depth = 1
        if thread_id:
            depth = int(self.db.scalar("SELECT COUNT(*) FROM messages WHERE thread_id=?", (thread_id,)) or 0) + 1
        msg = {
            "id": new_id("msg"), "kind": kind, "de": actor.id, "a": to_id,
            "sujet": self.p.redactor.secrets(sujet)[:300], "corps": self.p.redactor.secrets(corps),
            "thread_id": thread_id or new_id("fil"), "parent_id": parent_id, "profondeur": depth,
            "priorite": priorite, "horodatage": now_iso(), "statut": "envoye", "relaye_de": relaye_de,
        }
        self.db.execute(f"INSERT INTO messages({','.join(msg)}) VALUES({','.join('?' * len(msg))})", tuple(msg.values()))
        paths = self._to_vault(msg)
        self.db.execute("UPDATE messages SET vault_path=? WHERE id=?", (paths[0], msg["id"]))
        self.p.audit.record("message", "envoi" if kind == "message" else "envoi_demande", agent_id=actor.id,
                            niveau=actor.niveau, cible=to_id, correlation_id=correlation_id,
                            details={"message": msg["id"], "sujet": msg["sujet"], "fil": msg["thread_id"], "relaye_de": relaye_de})
        self.p.bus.publish("message", id=msg["id"], de=actor.id, a=to_id, kind=kind, sujet=msg["sujet"])
        return self.get(msg["id"])

    def _anti_loop(self, actor: Actor, thread_id: str | None) -> None:
        cfg = self.p.cfg.messaging
        since = (now() - dt.timedelta(hours=1)).isoformat(timespec="seconds")
        n = int(self.db.scalar("SELECT COUNT(*) FROM messages WHERE de=? AND horodatage>=?", (actor.id, since)) or 0)
        if n >= cfg.max_messages_per_agent_per_hour:
            self._loop_alert(actor, f"{n} messages en une heure (limite {cfg.max_messages_per_agent_per_hour})")
        if thread_id:
            depth = int(self.db.scalar("SELECT COUNT(*) FROM messages WHERE thread_id=?", (thread_id,)) or 0)
            if depth >= cfg.max_thread_depth:
                self._loop_alert(actor, f"fil {thread_id} : {depth} messages (limite {cfg.max_thread_depth})")

    def _loop_alert(self, actor: Actor, detail: str) -> None:
        self.p.audit.record("message", "boucle_bloquee", agent_id=actor.id, niveau=actor.niveau, resultat=detail, gravite="grave")
        self.p.alerts.raise_("boucle_messages", f"Boucle de messages bloquée pour {actor.nom or actor.id} : {detail}",
                             gravite="grave", agent_id=actor.id)
        raise RateLimited(f"limite anti-boucle atteinte : {detail}")

    def relay(self, actor: Actor, message_id: str, to: str, commentaire: str = "") -> dict:
        """Le supérieur relaie un message vers un autre niveau / une autre équipe, avec SES droits."""
        m = self.get(message_id)
        if m["a"] != actor.id and not actor.is_owner:
            raise OrchestraError("on ne relaie que les messages qu'on a reçus")
        corps = (commentaire + "\n\n" if commentaire else "") + f"> Relayé de {self._name(m['de'])} :\n> " + m["corps"].replace("\n", "\n> ")
        return self.send(actor, to, "Relais : " + m["sujet"], corps, relaye_de=m["id"])

    # ------------------------------------------------------------------ lecture
    def get(self, message_id: str) -> dict:
        m = self.db.one("SELECT * FROM messages WHERE id=?", (message_id,))
        if not m:
            raise NotFound("message introuvable")
        return m

    def mark(self, actor: Actor, message_id: str, statut: str) -> dict:
        m = self.get(message_id)
        if statut not in ("lu", "traite"):
            raise OrchestraError("statut invalide")
        if m["a"] != actor.id and not actor.is_owner:
            raise OrchestraError("seul le destinataire change le statut")
        self.db.execute("UPDATE messages SET statut=? WHERE id=?", (statut, message_id))
        self._to_vault(self.get(message_id))
        return self.get(message_id)

    def for_agent(self, agent_id: str, limit: int = 200) -> list[dict]:
        return self.db.query("SELECT * FROM messages WHERE de=? OR a=? ORDER BY horodatage DESC LIMIT ?", (agent_id, agent_id, limit))

    def thread(self, thread_id: str) -> list[dict]:
        return self.db.query("SELECT * FROM messages WHERE thread_id=? ORDER BY horodatage", (thread_id,))

    # ------------------------------------------------------------------ demandes formelles
    def request(self, actor: Actor, type_: str, sujet: str, justification: str, gain_attendu: str = "",
                cout_eur: float = 0.0, payload: dict[str, Any] | None = None) -> dict:
        if type_ not in REQUEST_TYPES:
            raise OrchestraError(f"type de demande invalide : {type_}")
        if not justification.strip():
            raise OrchestraError("la justification est obligatoire")
        if actor.is_agent:
            me = self.p.agents.get(actor.id)
            to = OWNER_ID if (type_ == "plateforme" or not me["parent_id"]) else me["parent_id"]
        else:
            raise OrchestraError("seuls les agents font des demandes formelles")
        body = f"**Type :** {type_}\n\n**Justification :** {justification}\n\n**Gain attendu :** {gain_attendu}\n\n**Coût :** {cout_eur:.2f} €"
        msg = self.send(actor, to, f"[Demande] {sujet}", body, kind="demande", priorite="haute") if to != OWNER_ID \
            else self._send_to_owner(actor, f"[Demande] {sujet}", body)
        ts = now_iso()
        req = {
            "id": new_id("dem"), "message_id": msg["id"], "type": type_, "de": actor.id, "a": to,
            "sujet": self.p.redactor.secrets(sujet)[:300], "justification": self.p.redactor.secrets(justification),
            "gain_attendu": self.p.redactor.secrets(gain_attendu), "cout_eur": float(cout_eur), "statut": "en_attente",
            "cree_le": ts, "maj_le": ts, "payload": json.dumps(payload or {}, ensure_ascii=False),
        }
        self.db.execute(f"INSERT INTO requests({','.join(req)}) VALUES({','.join('?' * len(req))})", tuple(req.values()))
        self.p.audit.record("demande", "creation", agent_id=actor.id, niveau=actor.niveau, cible=to,
                            details={"demande": req["id"], "type": type_, "cout_eur": cout_eur})
        self._request_to_vault(self.get_request(req["id"]))
        r = self.get_request(req["id"])
        self.p.bus.publish("request", id=r["id"], de=r["de"], a=r["a"], statut=r["statut"], type_demande=type_)
        return r

    def _send_to_owner(self, actor: Actor, sujet: str, corps: str) -> dict:
        # Une demande « plateforme » va toujours au Propriétaire, quel que soit le niveau.
        return self.send(system("messagerie"), OWNER_ID, sujet, f"De {self._name(actor.id)} ({actor.id})\n\n{corps}", kind="demande")

    def get_request(self, request_id: str) -> dict:
        r = self.db.one("SELECT * FROM requests WHERE id=?", (request_id,))
        if not r:
            raise NotFound("demande introuvable")
        return r

    def pending(self, to: str | None = None) -> list[dict]:
        if to:
            return self.db.query("SELECT * FROM requests WHERE statut IN ('en_attente','escaladee') AND a=? ORDER BY cree_le", (to,))
        return self.db.query("SELECT * FROM requests WHERE statut IN ('en_attente','escaladee') ORDER BY cree_le")

    def requests_for(self, agent_id: str) -> list[dict]:
        return self.db.query("SELECT * FROM requests WHERE de=? OR a=? ORDER BY cree_le DESC", (agent_id, agent_id))

    def decide(self, actor: Actor, request_id: str, accept: bool, reponse: str = "") -> dict:
        r = self.get_request(request_id)
        if r["statut"] not in ("en_attente", "escaladee"):
            raise OrchestraError(f"demande déjà traitée ({r['statut']})")
        self.p.perms.require(actor, "request.decide", r)
        effect = ""
        statut = "acceptee" if accept else "refusee"
        if accept:
            try:
                effect = self._apply(actor, r)
            except _NeedsHigher as e:
                return self._escalate(r, f"acceptée par {self._name(actor.id)} ; {e}")
        self.db.execute("UPDATE requests SET statut=?, reponse=?, decide_par=?, maj_le=? WHERE id=?",
                        (statut, self.p.redactor.secrets(reponse + (f"\n{effect}" if effect else "")), actor.id, now_iso(), request_id))
        self._request_to_vault(self.get_request(request_id))
        r = self.get_request(request_id)
        self.p.audit.record("demande", statut, agent_id=actor.id, niveau=actor.niveau, cible=r["de"],
                            gravite="info" if accept else "attention", details={"demande": request_id, "effet": effect})
        self.p.bus.publish("request", id=r["id"], de=actor.id, a=r["de"], statut=statut, type_demande=r["type"])
        notice = f"Votre demande « {r['sujet']} » est {statut.replace('acceptee', 'acceptée').replace('refusee', 'refusée')}.\n\n{reponse}\n{effect}".strip()
        sender = actor
        if actor.is_agent and not self.p.perms.can_message(self.p.agents.get(actor.id), self.p.agents.get(r["de"])):
            sender = system("messagerie")
        self.send(sender, r["de"], f"Réponse : {r['sujet']}", notice, thread_id=None)
        requester = self.p.perms.agent(r["de"])
        if requester and requester.get("activite") == "attente":
            self.p.agents.set_activity(r["de"], "inactif")
        return r

    def _apply(self, actor: Actor, r: dict) -> str:
        """Effet d'une demande acceptée, exécuté avec les droits de celui qui décide.

        Si le décideur n'a pas le droit d'appliquer l'effet (ex. un Responsable ne peut pas accorder
        d'outil), la demande est escaladée à son supérieur avec son avis favorable.
        """
        payload = r.get("payload") or {}
        perms = self.p.perms

        def need(action: str, target=None, **ctx) -> None:
            d = perms.check(actor, action, target, **ctx)
            if not d:
                raise _NeedsHigher(f"application réservée au niveau supérieur ({d.reason})")

        if r["type"] == "acces_outil" and payload.get("outil"):
            a = self.p.agents.get(r["de"])
            if payload["outil"] in (a["outils"] or []):
                return "outil déjà accordé"
            need("agent.update", a, fields={"outils"})
            self.p.agents.update(actor, a["id"], {"outils": [*a["outils"], payload["outil"]]}, f"demande {r['id']} acceptée")
            return f"outil « {payload['outil']} » accordé"
        if r["type"] == "budget" and payload.get("budget_jour_eur") is not None:
            a = self.p.agents.get(r["de"])
            need("budget.set", a)
            self.p.agents.update(actor, a["id"], {"budget_jour_eur": float(payload["budget_jour_eur"])}, f"demande {r['id']} acceptée")
            return f"budget journalier porté à {float(payload['budget_jour_eur']):.2f} €"
        if r["type"] == "skill_equipe" and payload.get("skill"):
            need("skill.publish", None, portee="equipe")
            s = self.p.skills.grant_team_scope(actor, payload["skill"], r["id"])
            return f"skill « {s['nom']} » autorisé en portée équipe"
        if r["type"] == "promotion" and payload.get("agent_id"):
            need("agent.lifecycle", self.p.agents.get(payload["agent_id"]))
            a = self.p.agents.promote(actor, payload["agent_id"], raison=f"demande {r['id']}")
            return f"{a['nom']} promu {a['niveau']}"
        if r["type"] == "plateforme":
            if hasattr(self.p, "scribe"):
                self.p.scribe.decision(actor, f"Demande plateforme {r['id']} acceptée", f"{r['sujet']}\n\n{r['justification']}\n\n"
                                       "À appliquer manuellement par le Propriétaire.")
            return "proposition acceptée : application manuelle par le Propriétaire"
        return ""

    # ------------------------------------------------------------------ escalade
    def _escalate(self, r: dict, raison: str) -> dict:
        current = self.p.perms.agent(r["a"]) if r["a"] != OWNER_ID else None
        new_to = OWNER_ID if (current is None or not current.get("parent_id")) else current["parent_id"]
        if new_to == r["a"]:
            return r
        self.db.execute("UPDATE requests SET a=?, statut='escaladee', escalades=escalades+1, maj_le=?, reponse=? WHERE id=?",
                        (new_to, now_iso(), raison, r["id"]))
        self._request_to_vault(self.get_request(r["id"]))
        r = self.get_request(r["id"])
        self.p.audit.record("demande", "escalade", agent_id="systeme", niveau="systeme", cible=new_to,
                            gravite="attention", details={"demande": r["id"], "raison": raison})
        self.p.alerts.raise_("demande_escaladee", f"Demande « {r['sujet']} » escaladée vers {self._name(new_to)} : {raison}",
                             gravite="attention", agent_id=r["de"])
        self.send(system("messagerie"), new_to, f"[Escalade] {r['sujet']}",
                  f"Demande de {self._name(r['de'])} escaladée : {raison}\n\n{r['justification']}", kind="demande")
        self.p.bus.publish("request", id=r["id"], de=r["de"], a=new_to, statut="escaladee", type_demande=r["type"])
        return r

    def escalate_overdue(self, at: dt.datetime | None = None) -> list[dict]:
        at = at or now()
        limit = (at - dt.timedelta(hours=self.p.cfg.messaging.escalation_hours)).isoformat(timespec="seconds")
        out = []
        for r in self.db.query("SELECT * FROM requests WHERE statut IN ('en_attente','escaladee') AND maj_le<=? AND a!=?",
                               (limit, OWNER_ID)):
            out.append(self._escalate(r, f"sans réponse depuis plus de {self.p.cfg.messaging.escalation_hours:g} h"))
        return out

    # ------------------------------------------------------------------ coffre Obsidian
    def _to_vault(self, m: dict) -> list[str]:
        w = self.p.writer
        date = m["horodatage"][:10]
        fm = {"id": m["id"], "type": m["kind"], "de": m["de"], "a": m["a"], "sujet": m["sujet"], "fil": m["thread_id"],
              "priorite": m["priorite"], "statut": m["statut"], "horodatage": m["horodatage"]}
        body = (f"# {m['sujet']}\n\nDe {w.link(m['de'])} à {w.link(m['a'])} — fil `{m['thread_id']}`"
                + (f" — relayé de `{m['relaye_de']}`" if m.get("relaye_de") else "") + f"\n\n{m['corps']}\n")
        paths = []
        for owner, box in ((m["a"], "inbox"), (m["de"], "sent")):
            paths.append(w.write(f"Messages/{_safe(owner)}/{box}/{date}-{m['id']}.md", fm, body, kind="message"))
        return paths

    def _request_to_vault(self, r: dict) -> None:
        w = self.p.writer
        fm = {"id": r["id"], "type": r["type"], "de": r["de"], "a": r["a"], "statut": r["statut"],
              "cout_eur": r["cout_eur"], "cree_le": r["cree_le"], "maj_le": r["maj_le"], "escalades": r["escalades"]}
        body = (f"# {r['sujet']}\n\nDe {w.link(r['de'])} à {w.link(r['a'])}\n\n## Justification\n{r['justification']}\n\n"
                f"## Gain attendu\n{r['gain_attendu']}\n\n## Réponse\n{r.get('reponse') or ''}\n"
                + (f"\nDécidée par {w.link(r['decide_par'])}\n" if r.get("decide_par") else ""))
        path = w.write(f"Demandes/{r['cree_le'][:10]}-{r['id']}.md", fm, body, kind="demande")
        self.db.execute("UPDATE requests SET vault_path=? WHERE id=?", (path, r["id"]))


class _NeedsHigher(Exception):
    pass


def _safe(ref: str) -> str:
    return ref.replace(":", "-").replace("/", "-")
