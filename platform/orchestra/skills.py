"""Skills : compétences réutilisables, en nombre illimité.

Cycle : brouillon → auto-test (conteneur isolé) → revue du Vérificateur → approuvé (publié dans sa portée) → obsolète.
- Apprenti : portée `agent`. Salarié : `agent`, `equipe` via demande formelle. Responsable : `equipe`, `global` via le Chef.
  Chef : `global`.
- Un skill ne contient jamais de secret et n'accorde jamais de droit : ses `permissions_requises` doivent déjà
  appartenir à son utilisateur (sinon : demande formelle).
- Rien n'est supprimé : un skill retiré ou fusionné passe `obsolete` et sa note va dans `Archives/Skills/`.
"""
from __future__ import annotations

import json
import re
from typing import Any

from orchestra.models import (OWNER, Actor, NotFound, OrchestraError, PermissionDenied, new_id, now_iso,
                              slugify, system)
from orchestra.runtime.prompts import INJECTION_PATTERNS

VERIFIER = system("verificateur")
FORMATEUR = system("formateur")
SCOPES = ("agent", "equipe", "global")


class SkillService:
    def __init__(self, p):
        self.p = p
        self.db = p.db

    # ================================================================== lecture
    def get(self, ref: str) -> dict:
        s = self.db.one("SELECT * FROM skills WHERE id=? OR nom=?", (ref, slugify(ref)))
        if not s:
            raise NotFound(f"skill introuvable : {ref}")
        return self._stats(s)

    def _stats(self, s: dict) -> dict:
        row = self.db.one("SELECT SUM(succes=1) ok, SUM(succes=0) ko, COUNT(*) n, AVG(cout_eur) cout FROM skill_usage WHERE skill_id=?", (s["id"],))
        ok, ko = int(row["ok"] or 0), int(row["ko"] or 0)
        s["evaluations"] = ok + ko
        s["taux_reussite"] = round(ok / (ok + ko), 4) if ok + ko else 0.0
        s["cout_moyen_eur"] = round(float(row["cout"] or 0), 6)
        cfg = self.p.cfg.improvement
        s["signale"] = bool(s["statut"] == "approuve" and ((s["evaluations"] >= 3 and s["taux_reussite"] < cfg.skill_min_success_rate)))
        return s

    def list(self, agent_id: str | None = None, portee: str | None = None, statut: str | None = None) -> list[dict]:
        where, params = [], []
        if portee:
            where.append("portee=?"); params.append(portee)
        if statut:
            where.append("statut=?"); params.append(statut)
        rows = self.db.query("SELECT * FROM skills" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY maj_le DESC", tuple(params))
        if agent_id:
            agent = self.p.agents.get(agent_id)
            rows = [s for s in rows if s["auteur"] == agent_id or self.visible(agent, s)]
        return [self._stats(s) for s in rows]

    def visible(self, agent: dict, s: dict) -> bool:
        if s["statut"] == "obsolete":
            return False
        if s["auteur"] == agent["id"]:
            return True
        if s["statut"] != "approuve":
            return False
        if s["portee"] == "global":
            return True
        if s["portee"] == "equipe":
            return agent["niveau"] == "chef" or s["equipe_id"] == self.p.perms.team_root(agent["id"])
        return False

    def relevant(self, agent: dict, consigne: str, limit: int = 3) -> list[dict]:
        """Découverte : skills pertinents pour la tâche (index plein texte), à réutiliser avant d'agir."""
        hits = self.p.scribe.search(consigne, None, limit=20, any_term=True, types=("skill",))
        out = []
        for h in hits:
            s = self.db.one("SELECT * FROM skills WHERE vault_path=?", (h["path"],))
            if s and self.visible(agent, s) and s["id"] not in {x["id"] for x in out}:
                s = self._stats(s)
                s["taux"] = s["taux_reussite"]
                out.append(s)
            if len(out) >= limit:
                break
        return out

    # ================================================================== création / amélioration
    def create(self, actor: Actor, args: dict[str, Any]) -> dict:
        nom = slugify(str(args.get("nom") or ""))
        if not nom or nom == "sans-nom":
            raise OrchestraError("nom de skill obligatoire (kebab-case)")
        portee = str(args.get("portee") or "agent")
        if portee not in SCOPES:
            raise OrchestraError(f"portée invalide : {portee}")
        contenu = str(args.get("contenu") or "")
        code = str(args.get("code") or "")
        tests = args.get("tests") or []
        if isinstance(tests, str):
            tests = json.loads(tests) if tests.strip().startswith("[") else []
        perms_req = [str(x) for x in (args.get("permissions_requises") or [])]
        self._guard_content(actor, nom, contenu, code, perms_req)

        requested = portee
        if actor.is_agent and not self.p.perms.check(actor, "skill.create", None, portee=portee):
            me = self.p.agents.get(actor.id)
            if me["niveau"] == "apprenti" or (portee == "global" and me["niveau"] == "salarie"):
                self.p.perms.require(actor, "skill.create", None, portee=portee)  # refus journalisé
            # créé dans la portée autorisée ; la portée demandée passe par une demande formelle
            portee = "equipe" if me["niveau"] == "responsable" else "agent"

        existing = self.db.one("SELECT * FROM skills WHERE nom=?", (nom,))
        if existing:
            if existing["auteur"] != actor.id and not actor.is_owner:
                raise OrchestraError(f"le skill « {nom} » existe déjà (auteur {existing['auteur']}) : réutilisez-le ou proposez une amélioration")
            return self.update(actor, existing["id"], {"contenu": contenu, "code": code, "tests": tests,
                                                       "permissions_requises": perms_req}, "amélioration par l'auteur")
        ts = now_iso()
        equipe = self.p.perms.team_root(actor.id) if actor.is_agent and portee == "equipe" else None
        s = {"id": new_id("skill"), "nom": nom, "portee": portee, "equipe_id": equipe, "auteur": actor.id,
             "statut": "brouillon", "version": 1, "permissions_requises": json.dumps(perms_req), "tests": json.dumps(tests, ensure_ascii=False),
             "code": code, "contenu": contenu, "cree_le": ts, "maj_le": ts}
        self.db.execute(f"INSERT INTO skills({','.join(s)}) VALUES({','.join('?' * len(s))})", tuple(s.values()))
        self._snapshot(s["id"], actor, "création")
        self.p.audit.record("skill", "creation", agent_id=actor.id, niveau=actor.niveau, cible=nom, details={"portee": portee})
        skill = self._pipeline(s["id"], actor)
        if requested != portee and actor.is_agent:
            self.p.messaging.request(actor, "skill_equipe", f"Publier le skill « {nom} » en portée {requested}",
                                     f"Skill testé et revu ({skill['statut']}), utile au-delà de mon usage personnel.",
                                     "Réutilisation par l'équipe", 0, payload={"skill": skill["id"], "portee": requested})
        return self.get(skill["id"])

    def update(self, actor: Actor, skill_id: str, changes: dict[str, Any], raison: str = "modification") -> dict:
        s = self.get(skill_id)
        if not (actor.is_owner or actor.is_system or s["auteur"] == actor.id):
            raise PermissionDenied("seul l'auteur (ou le Propriétaire) améliore un skill")
        fields = {}
        for k in ("contenu", "code"):
            if k in changes and changes[k] is not None and changes[k] != s[k]:
                fields[k] = str(changes[k])
        for k in ("tests", "permissions_requises"):
            if k in changes and changes[k] is not None and list(changes[k]) != list(s[k] or []):
                fields[k] = json.dumps(list(changes[k]), ensure_ascii=False)
        if not fields:
            return s
        self._guard_content(actor, s["nom"], fields.get("contenu", s["contenu"]), fields.get("code", s["code"]),
                            json.loads(fields["permissions_requises"]) if "permissions_requises" in fields else s["permissions_requises"])
        fields.update({"version": s["version"] + 1, "maj_le": now_iso(), "statut": "brouillon" if actor.is_agent else s["statut"]})
        self.db.execute(f"UPDATE skills SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), skill_id))
        self._snapshot(skill_id, actor, raison)
        self.p.audit.record("skill", "nouvelle_version", agent_id=actor.id, niveau=actor.niveau, cible=s["nom"],
                            details={"version": fields["version"], "raison": raison, "champs": sorted(fields)})
        if actor.is_agent:
            return self._pipeline(skill_id, actor)
        self._to_vault(self.get(skill_id), f"Skill {s['nom']} v{fields['version']} ({raison})")
        return self.get(skill_id)

    def _guard_content(self, actor: Actor, nom: str, contenu: str, code: str, perms_req: list[str]) -> None:
        found = self.p.redactor.find_secrets(contenu + "\n" + code)
        if found:
            self.p.audit.record("securite", "skill_refuse_secret", agent_id=actor.id, niveau=actor.niveau, cible=nom,
                                gravite="grave", details={"types": found})
            self.p.alerts.raise_("secret_skill", f"Skill « {nom} » refusé : il contient un secret ({', '.join(found)})",
                                 gravite="grave", agent_id=actor.id if actor.is_agent else None)
            raise OrchestraError("un skill ne doit jamais contenir de secret")
        if actor.is_agent:
            me = self.p.agents.get(actor.id)
            missing = set(perms_req) - self.p.perms.tools_of(me)
            if missing:
                raise PermissionDenied(f"un skill n'accorde pas de droits : outils non détenus {sorted(missing)} (faire une demande)")

    def _snapshot(self, skill_id: str, actor: Actor, raison: str) -> None:
        s = self.db.one("SELECT * FROM skills WHERE id=?", (skill_id,))
        snap = {k: s[k] for k in ("nom", "portee", "equipe_id", "contenu", "code", "tests", "permissions_requises", "statut")}
        self.db.execute("INSERT OR REPLACE INTO skill_versions(skill_id,version,snapshot,auteur,horodatage,raison) VALUES(?,?,?,?,?,?)",
                        (skill_id, s["version"], json.dumps(snap, ensure_ascii=False), actor.id, now_iso(), raison))

    def versions(self, skill_id: str) -> list[dict]:
        return self.db.query("SELECT * FROM skill_versions WHERE skill_id=? ORDER BY version DESC", (skill_id,))

    def restore_version(self, actor: Actor, skill_id: str, version: int, raison: str) -> dict:
        v = self.db.one("SELECT * FROM skill_versions WHERE skill_id=? AND version=?", (skill_id, version))
        if not v:
            raise NotFound("version introuvable")
        snap = v["snapshot"]
        s = self.get(skill_id)
        self.db.execute("UPDATE skills SET contenu=?, code=?, tests=?, permissions_requises=?, version=?, maj_le=?, statut='approuve' WHERE id=?",
                        (snap["contenu"], snap["code"], json.dumps(snap["tests"]), json.dumps(snap["permissions_requises"]),
                         s["version"] + 1, now_iso(), skill_id))
        self._snapshot(skill_id, actor, raison)
        self.p.audit.record("amelioration", "retour_arriere_skill", agent_id=actor.id, niveau=actor.niveau, cible=s["nom"],
                            gravite="attention", details={"version_restauree": version, "raison": raison})
        self._to_vault(self.get(skill_id), f"Skill {s['nom']} : retour à la v{version}")
        return self.get(skill_id)

    # ================================================================== auto-test + revue
    def _pipeline(self, skill_id: str, actor: Actor) -> dict:
        ok, report = self.self_test(skill_id)
        if ok:
            self._set(skill_id, statut="teste", revue=report)
            ok, review = self.review(skill_id)
            report += "\n" + review
        else:
            self._set(skill_id, statut="brouillon", revue=report)
        s = self.get(skill_id)
        self._to_vault(s, f"Skill {s['nom']} v{s['version']} : {s['statut']}")
        self.p.bus.publish("skill", id=skill_id, nom=s["nom"], statut=s["statut"], auteur=s["auteur"])
        return s

    def self_test(self, skill_id: str) -> tuple[bool, str]:
        s = self.get(skill_id)
        tests = s["tests"] or []
        if s["code"] and not tests:
            return False, "auto-test : un skill avec du code doit fournir au moins un test"
        lines = []
        for i, t in enumerate(tests, 1):
            if not s["code"]:
                break
            entree = str(t.get("entree", "")) if isinstance(t, dict) else ""
            attendu = str(t.get("attendu", "")).strip() if isinstance(t, dict) else ""
            r = self.p.runtime.sandbox.run(s["code"], actor_id=VERIFIER.id, niveau="systeme", stdin=entree,
                                           timeout=30, label=f"auto_test_skill:{s['nom']}")
            passed = r.ok and attendu in r.stdout.strip()
            lines.append(f"test {i} : {'OK' if passed else 'ÉCHEC'} (isolation {r.isolation})")
            if not passed:
                self.p.audit.record("skill", "auto_test_echec", agent_id=VERIFIER.id, niveau="systeme", cible=s["nom"],
                                    resultat=f"test {i}", gravite="attention", details={"stderr": r.stderr[-300:]})
                return False, "auto-test : " + "; ".join(lines)
        self.p.audit.record("skill", "auto_test_ok", agent_id=VERIFIER.id, niveau="systeme", cible=s["nom"],
                            details={"tests": len(tests)})
        return True, "auto-test : " + ("; ".join(lines) if lines else "procédure sans code, aucun test à exécuter")

    def review(self, skill_id: str) -> tuple[bool, str]:
        """Revue du Vérificateur (contrôles déterministes, appliqués par le code)."""
        s = self.get(skill_id)
        problems = []
        if self.p.redactor.find_secrets(s["contenu"] + s["code"]):
            problems.append("secret détecté")
        if INJECTION_PATTERNS.search(s["contenu"]):
            problems.append("consigne suspecte dans le contenu (injection)")
        if len(s["contenu"].strip()) < 20 and not s["code"]:
            problems.append("contenu trop pauvre (décrire quand l'utiliser et les étapes)")
        if s["auteur"].startswith("agent-"):
            author = self.p.perms.agent(s["auteur"])
            if author and set(s["permissions_requises"] or []) - self.p.perms.tools_of(author):
                problems.append("permissions requises non détenues par l'auteur")
        if s["code"] and re.search(r"\b(os\.system|subprocess|socket|requests|urllib|shutil\.rmtree)\b", s["code"]):
            problems.append("code : appels système ou réseau interdits dans un skill")
        dup = self._find_duplicate(s)
        if dup:
            problems.append(f"doublon probable de « {dup['nom']} » : réutiliser ou fusionner")
        ok = not problems
        verdict = "revue du Vérificateur : " + ("approuvé" if ok else "refusé — " + "; ".join(problems))
        self._set(skill_id, statut="approuve" if ok else "brouillon", revue=verdict)
        self.p.audit.record("skill", "revue_approuvee" if ok else "revue_refusee", agent_id=VERIFIER.id, niveau="systeme",
                            cible=s["nom"], resultat=verdict, gravite="info" if ok else "attention")
        if ok:
            self.p.audit.record("skill", "publication", agent_id=VERIFIER.id, niveau="systeme", cible=s["nom"],
                                details={"portee": s["portee"], "version": s["version"]})
        return ok, verdict

    def _set(self, skill_id: str, **fields: Any) -> None:
        fields["maj_le"] = now_iso()
        self.db.execute(f"UPDATE skills SET {','.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), skill_id))

    def _find_duplicate(self, s: dict) -> dict | None:
        words = _words(s["contenu"] + " " + s["nom"])
        if len(words) < 5:
            return None
        for o in self.db.query("SELECT * FROM skills WHERE statut='approuve' AND id!=? AND portee=?", (s["id"], s["portee"])):
            if o["portee"] == "agent" and o["auteur"] != s["auteur"]:
                continue
            ow = _words(o["contenu"] + " " + o["nom"])
            if ow and len(words & ow) / len(words | ow) >= 0.8:
                return o
        return None

    # ================================================================== portée / retrait
    def grant_team_scope(self, actor: Actor, skill_ref: str, request_id: str, portee: str = "equipe") -> dict:
        s = self.get(skill_ref)
        req = self.db.one("SELECT payload FROM requests WHERE id=?", (request_id,))
        if req and isinstance(req["payload"], dict) and req["payload"].get("portee") in SCOPES:
            portee = req["payload"]["portee"]
        self.p.perms.require(actor, "skill.publish", None, portee=portee)
        equipe = self.p.perms.team_root(s["auteur"]) if portee == "equipe" and s["auteur"].startswith("agent-") else None
        old = s["vault_path"]
        self._set(s["id"], portee=portee, equipe_id=equipe, version=s["version"] + 1)
        self._snapshot(s["id"], actor, f"portée {portee} accordée (demande {request_id})")
        self.p.audit.record("skill", "portee_accordee", agent_id=actor.id, niveau=actor.niveau, cible=s["nom"],
                            details={"portee": portee, "demande": request_id})
        s = self.get(s["id"])
        if s["statut"] != "approuve":
            self.review(s["id"])
        self._to_vault(self.get(s["id"]), f"Skill {s['nom']} publié en portée {portee}", old_path=old)
        return self.get(s["id"])

    def obsolete(self, actor: Actor, skill_ref: str, raison: str, fusionne_dans: str | None = None) -> dict:
        s = self.get(skill_ref)
        if not (actor.is_owner or actor.is_system or s["auteur"] == actor.id
                or (actor.is_agent and self.p.agents.get(actor.id)["niveau"] == "chef")):
            raise PermissionDenied("retrait d'un skill : auteur, Chef ou Propriétaire")
        old = s["vault_path"]
        self._set(s["id"], statut="obsolete", fusionne_dans=fusionne_dans, revue=raison)
        self.p.audit.record("skill", "obsolete", agent_id=actor.id, niveau=actor.niveau, cible=s["nom"],
                            details={"raison": raison, "fusionne_dans": fusionne_dans})
        self._to_vault(self.get(s["id"]), f"Skill {s['nom']} marqué obsolète", old_path=old)
        self.p.bus.publish("skill", id=s["id"], nom=s["nom"], statut="obsolete")
        return self.get(s["id"])

    # ================================================================== utilisation
    def use(self, actor: Actor, nom: str, entree: str = "", task_id: str | None = None, correlation_id: str | None = None) -> dict:
        s = self.get(nom)
        if actor.is_agent:
            me = self.p.agents.get(actor.id)
            if not self.visible(me, s):
                raise PermissionDenied(f"skill « {s['nom']} » hors de votre portée ou non approuvé")
            for tool in s["permissions_requises"] or []:
                self.p.perms.require(actor, "tool.use", tool)  # un skill n'accorde jamais de droit
        elif s["statut"] != "approuve":
            raise OrchestraError("skill non approuvé")
        succes: int | None = None
        if s["code"]:
            r = self.p.runtime.sandbox.run(s["code"], actor_id=actor.id, niveau=actor.niveau, stdin=entree,
                                           correlation_id=correlation_id, label=f"skill:{s['nom']}")
            sortie = r.stdout if r.ok else f"ÉCHEC (code {r.returncode}) : {r.stderr[-500:]}"
            if not r.ok:
                succes = 0
        else:
            sortie = s["contenu"]
        self.db.execute("INSERT INTO skill_usage(skill_id,skill_version,agent_id,task_id,succes,cout_eur,horodatage) VALUES(?,?,?,?,?,?,?)",
                        (s["id"], s["version"], actor.id, task_id, succes, 0.0, now_iso()))
        self.db.execute("UPDATE skills SET utilisations=utilisations+1, derniere_utilisation=? WHERE id=?", (now_iso(), s["id"]))
        self.p.audit.record("skill", "utilisation", agent_id=actor.id, niveau=actor.niveau, cible=s["nom"],
                            correlation_id=correlation_id, details={"version": s["version"], "tache": task_id})
        self.p.bus.publish("skill", id=s["id"], nom=s["nom"], utilisation=True, agent_id=actor.id)
        return {"skill_id": s["id"], "sortie": sortie}

    def record_outcome(self, skill_id: str, task_id: str, succes: bool, cout_eur: float = 0.0) -> None:
        self.db.execute("UPDATE skill_usage SET succes=?, cout_eur=? WHERE skill_id=? AND task_id=?",
                        (1 if succes else 0, cout_eur, skill_id, task_id))
        self.db.execute(f"UPDATE skills SET {'succes=succes+1' if succes else 'echecs=echecs+1'} WHERE id=?", (skill_id,))

    # ================================================================== coffre Obsidian
    def _folder(self, s: dict) -> str:
        if s["statut"] == "obsolete":
            return "Archives/Skills"
        if s["portee"] == "global":
            return "Skills/globaux"
        if s["portee"] == "equipe":
            return f"Skills/equipes/{s['equipe_id'] or 'sans-equipe'}"
        return f"Skills/agents/{s['auteur'].replace(':', '-')}"

    def _to_vault(self, s: dict, commit_msg: str, old_path: str | None = None) -> str:
        rel = f"{self._folder(s)}/{s['nom']}.md"
        old_path = old_path or s.get("vault_path")
        fm = {"nom": s["nom"], "version": s["version"], "auteur": s["auteur"], "portee": s["portee"], "statut": s["statut"],
              "permissions_requises": s["permissions_requises"], "tests": [f"cas-{i}" for i in range(1, len(s["tests"] or []) + 1)],
              "utilisations": s["utilisations"], "taux_reussite": s.get("taux_reussite", 0.0), "id": s["id"], "tags": ["skill", s["portee"]]}
        hist = "\n".join(f"- v{v['version']} ({v['horodatage'][:10]}, {v['auteur']}) : {v['raison']}" for v in self.versions(s["id"]))
        body = (f"{s['contenu'].strip()}\n\n"
                + (f"## Code (exécuté en conteneur isolé)\n```python\n{s['code'].strip()}\n```\n\n" if s["code"] else "")
                + (f"## Revue\n{s['revue']}\n\n" if s.get("revue") else "")
                + f"Auteur : {self.p.writer.link(s['auteur'])}\n\n## Historique des versions\n{hist}\n")
        removed = []
        if old_path and old_path != rel:
            self.p.writer.abs(old_path).unlink(missing_ok=True)
            self.db.execute("DELETE FROM vault_fts WHERE path=?", (old_path,))
            removed.append(old_path)
        rel = self.p.writer.write(rel, fm, body, kind="skill")
        self.db.execute("UPDATE skills SET vault_path=? WHERE id=?", (rel, s["id"]))
        self.p.git.commit(commit_msg, paths=[rel], removed=removed)
        return rel

    def import_note(self, rel: str, fm: dict, body: str) -> str:
        """Le Propriétaire modifie (ou crée) un skill dans Obsidian : sa version gagne."""
        contenu = re.split(r"\n## (Code \(exécuté|Revue\n|Historique des versions)", body)[0].strip()
        s = self.db.one("SELECT * FROM skills WHERE id=? OR vault_path=?", (str(fm.get("id") or ""), rel))
        if s:
            self.update(OWNER, s["id"], {"contenu": contenu}, "modification manuelle dans Obsidian (le Propriétaire gagne)")
            return "skill_modifie"
        portee = "global" if rel.startswith("Skills/globaux/") else "equipe" if rel.startswith("Skills/equipes/") else "agent"
        self.p.writer.abs(rel).unlink(missing_ok=True)
        self.create(OWNER, {"nom": fm.get("nom") or rel.rsplit("/", 1)[-1][:-3], "portee": portee, "contenu": contenu})
        return "skill_cree"


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w{4,}", text.lower())}
