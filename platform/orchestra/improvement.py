"""Amélioration continue (§11.2).

- Après chaque tâche : note d'apprentissage (base + `Apprentissages/`) et ligne dans le journal de bord de l'agent.
- À chaque validation : éligibilité à la promotion, échecs répétés (rétrogradation proposée), retour arrière
  automatique si les résultats se dégradent après une modification de fiche ou de skill.
- Chaque jour : le Formateur extrait les apprentissages récurrents, signale les skills inefficaces ou inutilisés,
  fusionne les doublons, propose des skills.
- Chaque semaine : rétrospective (réussite, coût, délais, erreurs, demandes refusées) → décisions
  « garder / améliorer / retirer » dans `Decisions/` et rapport dans `Rapports/`.
Aucune de ces mécaniques ne peut affaiblir un garde-fou : elles passent par les mêmes services et permissions.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from typing import Any

from orchestra.models import LEVEL_LABEL, now, now_iso, system

RETRO = system("retrospective")
FORMATEUR = system("formateur")
PROMPT_FIELDS = {"role", "contexte", "instructions", "objectif", "interdits", "modele", "kpi", "skills", "outils"}
STOPWORDS = set("dans pour avec sans cette cela plus mais tout tous très faire être avoir les des une sur par que qui aux ses son sont été était avant après".split())


class ImprovementService:
    def __init__(self, p):
        self.p = p
        self.db = p.db

    # ================================================================== après chaque tâche
    def record_learning(self, agent: dict, task: dict, texte: str) -> None:
        texte = self.p.redactor.secrets((texte or "").strip())
        if not texte:
            texte = f"Tâche « {task['consigne'][:80]} » : {task['statut']}."
        cur = self.db.execute("INSERT INTO learnings(agent_id,task_id,succes,texte,horodatage) VALUES(?,?,?,?,?)",
                              (agent["id"], task["id"], task.get("succes"), texte, now_iso()))
        rel = f"Apprentissages/{now_iso()[:10]}-{agent['id']}-{task['id']}.md"
        body = (f"# Apprentissage — {agent['nom']}\n\nTâche `{task['id']}` par {self.p.writer.link(agent['id'])}\n\n"
                f"**Consigne :** {task['consigne']}\n\n**Retour d'expérience :** {texte}\n")
        path = self.p.writer.write(rel, {"type": "apprentissage", "agent": agent["id"], "tache": task["id"],
                                         "date": now_iso()}, body, kind="apprentissage")
        self.db.execute("UPDATE learnings SET vault_path=? WHERE id=?", (path, cur.lastrowid))
        self.append_journal(agent["id"], f"{now_iso()[:16]} — {task['consigne'][:60]} → {texte[:160]}")

    def append_journal(self, agent_id: str, line: str) -> None:
        """Journal de bord : rempli par l'agent, sans créer de nouvelle version de fiche."""
        a = self.p.agents.get(agent_id)
        journal = ((a["journal"] + "\n") if a["journal"] else "") + f"- {line}"
        journal = "\n".join(journal.splitlines()[-50:])  # les 50 dernières entrées (l'historique complet est dans Git)
        self.db.execute("UPDATE agents SET journal=? WHERE id=?", (self.p.redactor.secrets(journal), agent_id))
        self.p.scribe.render_agent(self.p.agents.get(agent_id))

    # ================================================================== à chaque validation
    def on_task_validated(self, task: dict) -> None:
        agent = self.p.agents.get(task["agent_id"])
        for sid in task.get("skills_utilises") or []:
            self._check_skill_rollback(sid)
        if self._check_agent_rollback(agent):
            return
        self._check_promotion(agent)
        self._check_repeated_failures(agent)

    def _validated(self, agent_id: str, where: str = "", params: tuple = ()) -> list[dict]:
        return self.db.query(f"SELECT * FROM tasks WHERE agent_id=? AND succes IS NOT NULL {where} ORDER BY fin, debut",
                             (agent_id, *params))

    def _check_agent_rollback(self, agent: dict) -> bool:
        cfg = self.p.cfg.improvement
        versions = self.p.agents.versions(agent["id"])  # du plus récent au plus ancien
        # dernière modification « de prompt » (on ignore statut, budget, journal…)
        change = None
        for newer, older in zip(versions, versions[1:]):
            diff = {k for k in PROMPT_FIELDS if newer["snapshot"].get(k) != older["snapshot"].get(k)}
            if diff:
                change = (newer, older)
                break
        if not change:
            return False
        newer, older = change
        v = newer["version"]
        key = f"rollback_agent_{agent['id']}_v{v}"
        if self.db.get_state(key):
            return False
        after = self._validated(agent["id"], "AND agent_version>=?", (v,))
        before = self._validated(agent["id"], "AND agent_version<?", (v,))[-cfg.rollback_window_tasks * 2:]
        if len(after) < cfg.rollback_window_tasks or len(before) < cfg.rollback_window_tasks:
            return False
        after = after[:cfg.rollback_window_tasks]
        rate_after = sum(t["succes"] for t in after) / len(after)
        rate_before = sum(t["succes"] for t in before) / len(before)
        self.db.set_state(key, now_iso())
        if rate_after >= rate_before - cfg.rollback_min_drop:
            self.p.audit.record("amelioration", "modification_confirmee", agent_id=RETRO.id, niveau="systeme", cible=agent["id"],
                                details={"version": v, "avant": rate_before, "apres": rate_after})
            return False
        raison = (f"retour arrière automatique : réussite {rate_before:.0%} → {rate_after:.0%} sur "
                  f"{len(after)} tâches après la v{v}")
        restored = self.p.agents.restore_version(RETRO, agent["id"], older["version"], raison)
        self.db.set_state(f"rollback_agent_{agent['id']}_v{restored['version']}", now_iso())  # la restauration elle-même n'est pas réévaluée
        self.p.audit.record("amelioration", "retour_arriere", agent_id=RETRO.id, niveau="systeme", cible=agent["id"],
                            gravite="attention", details={"de": v, "vers": older["version"], "avant": rate_before, "apres": rate_after})
        self.p.alerts.raise_("retour_arriere", f"{agent['nom']} : {raison} (restauration de la v{older['version']})",
                             gravite="attention", agent_id=agent["id"])
        self.p.scribe.decision(RETRO, f"Retour arrière de {agent['nom']}", raison)
        return True

    def _check_skill_rollback(self, skill_id: str) -> None:
        cfg = self.p.cfg.improvement
        s = self.db.one("SELECT * FROM skills WHERE id=?", (skill_id,))
        if not s or s["version"] < 2:
            return
        key = f"rollback_skill_{skill_id}_v{s['version']}"
        if self.db.get_state(key):
            return
        cur = self.db.query("SELECT succes FROM skill_usage WHERE skill_id=? AND skill_version=? AND succes IS NOT NULL", (skill_id, s["version"]))
        prev = self.db.query("SELECT succes FROM skill_usage WHERE skill_id=? AND skill_version<? AND succes IS NOT NULL", (skill_id, s["version"]))
        if len(cur) < cfg.rollback_window_tasks or len(prev) < cfg.rollback_window_tasks:
            return
        r_cur = sum(x["succes"] for x in cur) / len(cur)
        r_prev = sum(x["succes"] for x in prev) / len(prev)
        self.db.set_state(key, now_iso())
        if r_cur < r_prev - cfg.rollback_min_drop:
            last_prev = self.db.scalar("SELECT MAX(skill_version) FROM skill_usage WHERE skill_id=? AND skill_version<?", (skill_id, s["version"]))
            restored = self.p.skills.restore_version(RETRO, skill_id, int(last_prev), f"réussite {r_prev:.0%} → {r_cur:.0%}")
            self.db.set_state(f"rollback_skill_{skill_id}_v{restored['version']}", now_iso())
            self.p.alerts.raise_("retour_arriere", f"Skill « {s['nom']} » : retour à la v{last_prev} (réussite {r_prev:.0%} → {r_cur:.0%})",
                                 gravite="attention")

    def _check_promotion(self, agent: dict) -> None:
        if agent["niveau"] != "apprenti":
            return
        cfg = self.p.cfg.hierarchy.promotion
        done = self._validated(agent["id"])
        if len(done) < cfg.min_validated_tasks:
            return
        rate = sum(t["succes"] for t in done) / len(done)
        key = f"promotion_signalee_{agent['id']}"
        if rate >= cfg.min_success_rate and not self.db.get_state(key):
            self.db.set_state(key, now_iso())
            team = self.p.perms.team_root(agent["id"])
            msg = (f"{agent['nom']} a {len(done)} tâches validées ({rate:.0%} de réussite) : éligible à la promotion "
                   f"Apprenti → Salarié. Le Responsable propose (demande « promotion »), le Chef valide.")
            self.p.audit.record("amelioration", "eligible_promotion", agent_id=RETRO.id, niveau="systeme", cible=agent["id"],
                                details={"taches": len(done), "reussite": rate})
            self.p.alerts.raise_("promotion_eligible", msg, gravite="info", agent_id=agent["id"])
            if team:
                self.p.messaging.send(RETRO, team, f"Promotion possible : {agent['nom']}", msg)

    def _check_repeated_failures(self, agent: dict) -> None:
        n = self.p.cfg.hierarchy.demotion.repeated_failures
        fails = [t for t in self._validated(agent["id"]) if t["succes"] == 0 and t["point_echec"]]
        by_point: dict[str, list[dict]] = {}
        for t in fails:
            by_point.setdefault(t["point_echec"].strip().lower(), []).append(t)
        for point, ts in by_point.items():
            versions = {t["agent_version"] for t in ts}
            # « après correction » : les échecs répétés s'étalent sur au moins deux versions de la fiche
            if len(ts) >= n and len(versions) >= 2:
                key = f"echecs_repetes_{agent['id']}_{point[:40]}"
                if self.db.get_state(key):
                    continue
                self.db.set_state(key, now_iso())
                msg = (f"{agent['nom']} échoue {len(ts)} fois sur « {point} » malgré une correction de sa fiche : "
                       "rétrogradation ou licenciement à examiner par le Chef d'Orchestre.")
                self.p.audit.record("amelioration", "echecs_repetes", agent_id=RETRO.id, niveau="systeme", cible=agent["id"],
                                    gravite="attention", details={"point": point, "taches": [t["id"] for t in ts]})
                self.p.alerts.raise_("echecs_repetes", msg, gravite="grave", agent_id=agent["id"])
                chef = self.db.one("SELECT id FROM agents WHERE niveau='chef' AND statut!='archive'")
                if chef:
                    self.p.messaging.send(RETRO, chef["id"], f"Échecs répétés : {agent['nom']}", msg)

    # ================================================================== chaque jour : le Formateur
    def daily(self) -> str:
        since = (now() - dt.timedelta(days=1)).isoformat(timespec="seconds")
        learnings = self.db.query("SELECT * FROM learnings WHERE horodatage>=?", (since,))
        words = Counter(w for l in learnings for w in set(re.findall(r"[a-zà-ÿ]{5,}", l["texte"].lower())) if w not in STOPWORDS)
        recurrent = [(w, c) for w, c in words.most_common(10) if c >= 3]
        cfg = self.p.cfg.improvement
        flagged, unused, merged = [], [], []
        for s in self.p.skills.list(statut="approuve"):
            if s["signale"]:
                flagged.append(s)
            last = s.get("derniere_utilisation") or s["cree_le"]
            if last < (now() - dt.timedelta(days=cfg.skill_unused_days)).isoformat():
                unused.append(s)
        for s in self.p.skills.list(statut="approuve"):
            s2 = self.db.one("SELECT * FROM skills WHERE id=?", (s["id"],))
            if s2["statut"] != "approuve":
                continue
            dup = self.p.skills._find_duplicate(s2)
            if dup:
                keep, drop = (dup, s2) if (dup["utilisations"] >= s2["utilisations"]) else (s2, dup)
                self.p.skills.obsolete(FORMATEUR, drop["id"], f"doublon fusionné dans « {keep['nom']} »", fusionne_dans=keep["id"])
                merged.append((drop["nom"], keep["nom"]))
        tasks = self.db.query("SELECT * FROM tasks WHERE debut>=?", (since,))
        lines = [f"# Rapport quotidien — {now_iso()[:10]}", "",
                 f"- Tâches : {len(tasks)} (terminées {sum(t['statut'] == 'terminee' for t in tasks)}, "
                 f"erreurs {sum(t['statut'] == 'erreur' for t in tasks)})",
                 f"- Apprentissages : {len(learnings)}", "", "## Apprentissages récurrents (Formateur)"]
        lines += [f"- « {w} » ({c} occurrences) → **proposition** : formaliser un skill sur ce thème" for w, c in recurrent] or ["- aucun thème récurrent"]
        lines += ["", "## Skills à améliorer (taux de réussite bas)"]
        lines += [f"- {s['nom']} v{s['version']} : {s['taux_reussite']:.0%} sur {s['evaluations']} usages" for s in flagged] or ["- aucun"]
        lines += ["", f"## Skills inutilisés depuis {cfg.skill_unused_days} jours"]
        lines += [f"- {s['nom']}" for s in unused] or ["- aucun"]
        lines += ["", "## Doublons fusionnés"] + ([f"- {a} → {b}" for a, b in merged] or ["- aucun"])
        for s in flagged:
            self.p.alerts.raise_("skill_inefficace", f"Skill « {s['nom']} » peu efficace ({s['taux_reussite']:.0%})", gravite="info")
        rel = self.p.writer.write(f"Rapports/{now_iso()[:10]}-quotidien.md", {"type": "rapport", "periode": "quotidien", "date": now_iso()[:10]},
                                  "\n".join(lines), kind="rapport")
        self.p.git.commit("Rapport quotidien du Formateur", paths=[rel])
        self.p.audit.record("amelioration", "rapport_quotidien", agent_id=FORMATEUR.id, niveau="systeme", cible=rel,
                            details={"recurrents": len(recurrent), "signales": len(flagged), "fusions": len(merged)})
        self.db.set_state("last_daily", now_iso())
        return rel

    # ================================================================== chaque semaine : rétrospective
    def weekly(self) -> str:
        since = (now() - dt.timedelta(days=7)).isoformat(timespec="seconds")
        rows: list[dict[str, Any]] = []
        for a in self.p.agents.list(include_archived=False):
            ts = self.db.query("SELECT * FROM tasks WHERE agent_id=? AND debut>=?", (a["id"], since))
            val = [t for t in ts if t["succes"] is not None]
            rate = (sum(t["succes"] for t in val) / len(val)) if val else None
            durations = [(dt.datetime.fromisoformat(t["fin"]) - dt.datetime.fromisoformat(t["debut"])).total_seconds() for t in ts if t["fin"]]
            refused = int(self.db.scalar("SELECT COUNT(*) FROM requests WHERE de=? AND statut='refusee' AND cree_le>=?", (a["id"], since)) or 0)
            errors = sum(t["statut"] == "erreur" for t in ts)
            cost = sum(t["cout_eur"] for t in ts)
            if rate is None:
                decision = "garder" if not errors else "améliorer"
                why = "pas encore de tâches évaluées" if not errors else f"{errors} erreur(s)"
            elif rate >= 0.8 and errors == 0:
                decision, why = "garder", f"réussite {rate:.0%}"
            elif rate >= 0.5:
                decision, why = "améliorer", f"réussite {rate:.0%}, {errors} erreur(s)"
            else:
                decision, why = "retirer", f"réussite {rate:.0%} : pause ou licenciement à décider par le Chef / le Propriétaire"
            rows.append({"a": a, "n": len(ts), "val": len(val), "rate": rate, "cost": cost, "dur": (sum(durations) / len(durations)) if durations else 0,
                         "errors": errors, "refused": refused, "decision": decision, "why": why})
        skills = self.p.skills.list()
        head = ["| Agent | Niveau | Tâches | Évaluées | Réussite | Coût | Durée moy. | Erreurs | Demandes refusées | Décision |",
                "|---|---|---|---|---|---|---|---|---|---|"]
        table = [f"| {self.p.writer.link(r['a']['id'])} | {LEVEL_LABEL[r['a']['niveau']]} | {r['n']} | {r['val']} | "
                 f"{_pct(r['rate'])} | {r['cost']:.3f} € | {r['dur']:.0f} s | {r['errors']} | {r['refused']} | "
                 f"**{r['decision']}** — {r['why']} |" for r in rows]
        sk = [f"| {s['nom']} | {s['portee']} | {s['statut']} | {s['utilisations']} | {s['taux_reussite']:.0%} | "
              f"{'retirer' if s['signale'] else 'garder'} |" for s in skills if s["statut"] != "obsolete"]
        budget = self.p.budget.summary()
        body = "\n".join([f"# Rétrospective hebdomadaire — semaine du {since[:10]}", "",
                          f"Budget : {budget['depense_eur']:.2f} € / {budget['plafond_eur']:.0f} € ({budget['ratio']:.0%}) · revenus {budget['revenus_eur']:.2f} €", "",
                          "## Agents : garder / améliorer / retirer", *head, *table, "",
                          "## Skills", "| Skill | Portée | Statut | Utilisations | Réussite | Décision |", "|---|---|---|---|---|---|", *sk, "",
                          "> Les décisions « retirer » sont des propositions : aucune mise en pause ou licenciement n'est "
                          "automatique. Le Chef d'Orchestre ou le Propriétaire tranche."])
        dec = self.p.scribe.decision(RETRO, f"Rétrospective hebdomadaire {now_iso()[:10]}", body)
        rel = self.p.writer.write(f"Rapports/{now_iso()[:10]}-hebdomadaire.md", {"type": "rapport", "periode": "hebdomadaire", "date": now_iso()[:10]},
                                  body + f"\n\nDécisions consignées : [[{dec.rsplit('/', 1)[-1][:-3]}]]\n", kind="rapport")
        self.p.git.commit("Rapport hebdomadaire", paths=[rel])
        self.p.audit.record("amelioration", "retrospective", agent_id=RETRO.id, niveau="systeme", cible=dec,
                            details={"garder": sum(r["decision"] == "garder" for r in rows),
                                     "ameliorer": sum(r["decision"] == "améliorer" for r in rows),
                                     "retirer": sum(r["decision"] == "retirer" for r in rows)})
        self.db.set_state("last_weekly", now_iso())
        return rel

    def scheduled(self) -> None:
        """Appelé toutes les 10 minutes : lance les rapports quand ils sont dus."""
        n = now()
        last_d = self.db.get_state("last_daily")
        if not last_d or n - dt.datetime.fromisoformat(last_d) >= dt.timedelta(hours=24):
            self.daily()
        last_w = self.db.get_state("last_weekly")
        if not last_w or n - dt.datetime.fromisoformat(last_w) >= dt.timedelta(days=7):
            self.weekly()


def _pct(rate: float | None) -> str:
    return "—" if rate is None else f"{rate:.0%}"
