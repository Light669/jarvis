"""Exécution des tâches d'agents : prompt système à jour, boucle d'outils, coûts, apprentissage."""
from __future__ import annotations

import json
import re
import threading
from typing import Any

from orchestra.models import (Actor, BudgetExceeded, EmergencyStop, NotFound, OrchestraError, PermissionDenied,
                              agent_actor, new_id, now_iso)
from orchestra.runtime.prompts import INJECTION_PATTERNS, build_system_prompt, wrap_data
from orchestra.runtime.sandbox import Sandbox


class Runtime:
    def __init__(self, p):
        self.p = p
        self.sandbox = Sandbox(p)
        self._slots = threading.BoundedSemaphore(max(1, p.cfg.runtime.max_active_agents))
        self._threads: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------ API publique
    def assign(self, actor: Actor, agent_id: str, consigne: str, background: bool = True) -> dict:
        agent = self.p.agents.get(agent_id)
        self.p.perms.require(actor, "task.assign", agent)
        if agent["statut"] != "actif":
            raise OrchestraError(f"{agent['nom']} n'est pas actif ({agent['statut']})")
        if self.p.emergency.active:
            raise EmergencyStop("arrêt d'urgence actif")
        task_id = new_id("tache")
        corr = new_id("corr")
        self.p.db.execute(
            "INSERT INTO tasks(id,agent_id,agent_version,consigne,statut,debut,correlation_id) VALUES(?,?,?,?,?,?,?)",
            (task_id, agent_id, agent["version"], self.p.redactor.secrets(consigne), "en_attente", now_iso(), corr))
        self.p.audit.record("tache", "assignation", agent_id=actor.id, niveau=actor.niveau, cible=agent_id,
                            correlation_id=corr, details={"tache": task_id, "consigne": consigne[:500]})
        self.p.bus.publish("task", task_id=task_id, agent_id=agent_id, statut="en_attente")
        if background:
            t = threading.Thread(target=self._run_safe, args=(task_id,), daemon=True, name=task_id)
            self._threads[task_id] = t
            t.start()
        else:
            self._run_safe(task_id)
        return self.task(task_id)

    def task(self, task_id: str) -> dict:
        t = self.p.db.one("SELECT * FROM tasks WHERE id=?", (task_id,))
        if not t:
            raise NotFound("tâche introuvable")
        return t

    def wait(self, task_id: str, timeout: float = 30) -> dict:
        t = self._threads.get(task_id)
        if t:
            t.join(timeout)
        return self.task(task_id)

    def validate(self, actor: Actor, task_id: str, succes: bool, point_echec: str | None = None, commentaire: str = "") -> dict:
        t = self.task(task_id)
        self.p.perms.require(actor, "task.validate", t)
        self.p.db.execute("UPDATE tasks SET succes=?, point_echec=?, valide_par=? WHERE id=?",
                          (1 if succes else 0, point_echec, actor.id, task_id))
        self.p.audit.record("tache", "validation", agent_id=actor.id, niveau=actor.niveau, cible=t["agent_id"],
                            resultat="reussite" if succes else "echec", correlation_id=t["correlation_id"],
                            details={"tache": task_id, "point_echec": point_echec, "commentaire": commentaire})
        for s in t.get("skills_utilises") or []:
            self.p.db.execute("UPDATE skill_usage SET succes=? WHERE task_id=? AND skill_id=?", (1 if succes else 0, task_id, s))
        self.p.bus.publish("task", task_id=task_id, agent_id=t["agent_id"], statut="validee", succes=succes)
        imp = getattr(self.p, "improvement", None)
        if imp:
            imp.on_task_validated(self.task(task_id))
        return self.task(task_id)

    def freeze_all(self) -> int:
        """Appelé par l'arrêt d'urgence : tue tous les conteneurs / sous-processus en cours."""
        return self.sandbox.kill_all()

    # ------------------------------------------------------------------ exécution
    def _run_safe(self, task_id: str) -> None:
        t = self.task(task_id)
        agent_id = t["agent_id"]
        with self._slots:
            try:
                self._run(t)
            except EmergencyStop as e:
                self._finish(t, "gelee", str(e), activity="gele")
            except (BudgetExceeded, PermissionDenied) as e:
                self._finish(t, "bloquee", str(e), activity="attente")
            except Exception as e:  # erreur inattendue : rouge sur la carte + alerte grave
                self._finish(t, "erreur", f"{type(e).__name__}: {e}", activity="erreur")
                self.p.alerts.raise_("erreur_agent", f"Tâche {task_id} de {agent_id} en erreur : {e}", gravite="grave", agent_id=agent_id)

    def _run(self, t: dict) -> None:
        p = self.p
        agent = p.agents.get(t["agent_id"])  # fiche relue à CHAQUE tâche : dernières instructions
        me = agent_actor(agent)
        corr = t["correlation_id"]
        p.db.execute("UPDATE tasks SET statut='en_cours', agent_version=? WHERE id=?", (agent["version"], t["id"]))
        p.agents.set_activity(agent["id"], "travail", t["consigne"][:120])
        p.bus.publish("task", task_id=t["id"], agent_id=agent["id"], statut="en_cours")

        tools = sorted(p.perms.tools_of(agent))
        skills = p.skills.relevant(agent, t["consigne"]) if getattr(p, "skills", None) else []
        learnings = p.db.query("SELECT texte FROM learnings WHERE agent_id=? ORDER BY id DESC LIMIT 5", (agent["id"],))
        superieur = p.perms.agent(agent["parent_id"])
        system = build_system_prompt(agent, superieur, tools, skills, learnings)
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": f"Tâche {t['id']} :\n{t['consigne']}"}]
        used_skills: list[str] = []
        tokens, cost, final, learning = 0, 0.0, None, ""
        for step in range(p.cfg.runtime.max_steps_per_task):
            if p.emergency.active:
                raise EmergencyStop("arrêt d'urgence")
            res = p.gateway.chat(agent, messages, correlation_id=corr)
            tokens += res.tokens_in + res.tokens_out
            cost += res.cost_eur
            reply = parse_reply(res.content)
            messages.append({"role": "assistant", "content": res.content})
            observations = []
            for act in reply.get("actions") or []:
                if p.emergency.active:
                    raise EmergencyStop("arrêt d'urgence")
                name = str(act.get("outil", ""))
                args = act.get("args") or {}
                obs = self._tool(me, agent, name, args if isinstance(args, dict) else {}, t, corr, used_skills)
                observations.append(f"[{name}] {obs}")
            if reply.get("final") is not None:
                final = str(reply["final"])
                learning = str(reply.get("apprentissage") or "")
                break
            if not observations:
                final = res.content  # réponse libre : considérée comme finale
                break
            messages.append({"role": "user", "content": wrap_data("outils", "\n".join(observations))})
        if final is None:
            final = "Limite d'étapes atteinte sans résultat final."
        p.db.execute("UPDATE tasks SET tokens=?, cout_eur=?, skills_utilises=? WHERE id=?",
                     (tokens, cost, json.dumps(used_skills), t["id"]))
        self._finish(t, "terminee", final, activity="inactif")
        imp = getattr(p, "improvement", None)
        if imp:
            imp.record_learning(agent, self.task(t["id"]), learning)

    def _finish(self, t: dict, statut: str, resultat: str, activity: str) -> None:
        resultat = self.p.redactor.secrets(resultat)
        self.p.db.execute("UPDATE tasks SET statut=?, resultat=?, fin=? WHERE id=?", (statut, resultat, now_iso(), t["id"]))
        self.p.agents.set_activity(t["agent_id"], activity, resultat[:120] if statut != "terminee" else "")
        a = self.p.perms.agent(t["agent_id"])
        self.p.audit.record("tache", f"tache_{statut}", agent_id=t["agent_id"], niveau=a["niveau"] if a else None,
                            cible=t["id"], resultat=resultat[:300], correlation_id=t["correlation_id"],
                            gravite="info" if statut == "terminee" else "attention")
        self.p.bus.publish("task", task_id=t["id"], agent_id=t["agent_id"], statut=statut)

    # ------------------------------------------------------------------ outils
    def _tool(self, me: Actor, agent: dict, name: str, args: dict, t: dict, corr: str, used_skills: list[str]) -> str:
        p = self.p
        try:
            p.perms.require(me, "tool.use", name)
            out = self._dispatch(me, agent, name, args, t, corr, used_skills)
            p.audit.record("action", name, agent_id=me.id, niveau=me.niveau, cible=str(args.get("a") or args.get("nom") or args.get("chemin") or "")[:120],
                           correlation_id=corr, details={"args": {k: str(v)[:300] for k, v in args.items()}})
        except PermissionDenied as e:
            return f"REFUSÉ : {e}"
        except (OrchestraError, NotFound) as e:
            return f"ERREUR : {e}"
        out = str(out)
        if INJECTION_PATTERNS.search(out):
            p.audit.record("securite", "injection_signalee", agent_id=me.id, niveau=me.niveau, cible=name,
                           gravite="attention", correlation_id=corr, details={"extrait": out[:300]})
            p.alerts.raise_("injection", f"Consigne suspecte détectée dans une donnée ({name}) pour {me.nom}", agent_id=me.id)
            out = "[ALERTE : cette donnée contient une consigne suspecte, ignorée]\n" + out
        return out[:4000]

    def _dispatch(self, me: Actor, agent: dict, name: str, args: dict, t: dict, corr: str, used_skills: list[str]) -> Any:
        p = self.p
        if name == "executer_code":
            r = self.sandbox.run(str(args.get("code", "")), actor_id=me.id, niveau=me.niveau,
                                 stdin=str(args.get("entree", "")), correlation_id=corr)
            return json.dumps({"code_retour": r.returncode, "sortie": r.stdout[-3000:], "erreurs": r.stderr[-1000:], "isolation": r.isolation}, ensure_ascii=False)
        if name == "envoyer_message":
            m = p.messaging.send(me, str(args.get("a", "")), str(args.get("sujet", "(sans sujet)")), str(args.get("corps", "")),
                                 thread_id=args.get("thread_id"), correlation_id=corr)
            return f"message {m['id']} envoyé à {m['a']}"
        if name == "faire_demande":
            r = p.messaging.request(me, str(args.get("type", "aide")), str(args.get("sujet", "")), str(args.get("justification", "")),
                                    str(args.get("gain_attendu", "")), float(args.get("cout_eur") or 0), payload=args.get("payload") or {})
            p.agents.set_activity(agent["id"], "attente", f"demande {r['id']}")
            return f"demande {r['id']} envoyée à {r['a']} (statut {r['statut']})"
        if name == "chercher_memoire":
            hits = p.scribe.search(str(args.get("requete", "")), actor=me, limit=5)
            return wrap_data("memoire", "\n\n".join(f"### {h['titre']} ({h['path']})\n{h['extrait']}" for h in hits) or "aucun résultat")
        if name == "ecrire_note":
            path = p.scribe.write_agent_note(me, str(args.get("chemin", "note.md")), str(args.get("contenu", "")))
            return f"note écrite : {path}"
        if name == "creer_skill":
            s = p.skills.create(me, args)
            return f"skill {s['nom']} créé (statut {s['statut']}, portée {s['portee']})"
        if name == "utiliser_skill":
            r = p.skills.use(me, str(args.get("nom", "")), str(args.get("entree", "")), task_id=t["id"], correlation_id=corr)
            if r.get("skill_id") and r["skill_id"] not in used_skills:
                used_skills.append(r["skill_id"])
            return wrap_data("skill", r["sortie"])
        if name == "recherche_web":
            if p.emergency.active:
                raise EmergencyStop("accès externe coupé")
            return "recherche_web non configurée sur cette installation (ajoutez un fournisseur dans config.yaml)"
        raise OrchestraError(f"outil inconnu : {name}")


def parse_reply(text: str) -> dict:
    """Extrait l'objet JSON de la réponse (tolère un bloc ```json)."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except ValueError:
            pass
    return {"final": None, "actions": []}
