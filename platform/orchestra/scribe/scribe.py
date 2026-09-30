"""Scribe : synchronisation bidirectionnelle base ⇄ coffre Obsidian, Git, index plein texte, journal lisible.

- Base → coffre : chaque création / modification d'agent réécrit sa fiche et crée un commit Git.
- Coffre → base : une note modifiée (ou créée) à la main dans Obsidian est validée puis appliquée au nom
  du Propriétaire ; en cas de conflit, la version du Propriétaire gagne, l'autre reste dans l'historique Git.
- Les agents n'écrivent QUE dans leur dossier (contrôle `vault.write`, refus journalisé).
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

from orchestra.models import LEVEL_LABEL, LEVELS, OWNER, Actor, NotFound, OrchestraError, now_iso, slugify
from orchestra.scribe.writer import dump_note, note_title, parse_note, sha
from orchestra.vault import LEVEL_DIRS

SECTIONS = [("Rôle", "role"), ("Contexte", "contexte"), ("Instructions", "instructions"),
            ("Objectif et KPI", "objectif"), ("Interdits", "interdits"), ("Journal de bord (rempli par l'agent)", "journal")]
SECTION_KEYS = {"role": "role", "rôle": "role", "contexte": "contexte", "instructions": "instructions",
                "objectif et kpi": "objectif", "objectif": "objectif", "interdits": "interdits", "journal de bord": "journal"}
IGNORED_DIRS = (".git/", ".obsidian/", ".trash/", "Logs/", "Modeles_de_notes/")


class Scribe:
    def __init__(self, p):
        self.p = p
        self.vault = p.vault_dir
        self.w = p.writer
        self._observer = None
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        p.agents.listeners.append(self.on_agent)
        p.audit.listeners.append(self.on_log)

    # ================================================================== base → coffre
    def on_agent(self, kind: str, agent: dict, actor: Actor, before: dict | None) -> None:
        written, removed = [], []
        if agent["statut"] == "archive" and not agent["vault_path"].startswith("Archives/"):
            new = f"Archives/Agents/{Path(agent['vault_path']).name}"
            self.w.move(agent["vault_path"], new)
            removed.append(agent["vault_path"])
            self.p.db.execute("UPDATE agents SET vault_path=? WHERE id=?", (new, agent["id"]))
            agent = self.p.agents.get(agent["id"])
        elif before and before.get("vault_path") and before["vault_path"] != agent["vault_path"]:
            self.w.move(before["vault_path"], agent["vault_path"])
            removed.append(before["vault_path"])
        written.append(self.render_agent(agent))
        parents = {agent.get("parent_id"), (before or {}).get("parent_id")} - {None}
        for pid in parents:
            if (pa := self.p.perms.agent(pid)):
                written.append(self.render_agent(pa))
        verb = {"created": "Création", "updated": "Modification"}.get(kind, kind)
        self.p.git.commit(f"{verb} de la fiche {agent['nom']} ({agent['id']}) v{agent['version']} par {actor.id}",
                          paths=written, removed=removed)

    def agent_note(self, agent: dict) -> tuple[dict[str, Any], str]:
        link = self.w.link
        subs = self.p.db.query("SELECT id FROM agents WHERE parent_id=? AND statut!='archive' ORDER BY id", (agent["id"],))
        team = self.p.perms.team_root(agent["id"])
        fm: dict[str, Any] = {
            "id": agent["id"], "nom": agent["nom"], "niveau": agent["niveau"], "superieur": agent["parent_id"],
            "statut": agent["statut"], "modele": agent["modele"], "budget_jour_eur": agent["budget_jour_eur"],
        }
        if agent.get("budget_mois_eur") is not None:
            fm["budget_mois_eur"] = agent["budget_mois_eur"]
        fm.update({
            "outils": agent["outils"], "skills": [f"[[{s}]]" for s in agent["skills"]], "kpi": agent["kpi"],
            "cree_par": agent["cree_par"], "cree_le": agent["cree_le"][:10], "version": agent["version"],
            "tags": ["agent", agent["niveau"]],
        })
        if agent["statut"] == "archive":
            fm["archive_raison"] = agent.get("archive_raison")
        meta = [LEVEL_LABEL[agent["niveau"]], f"Supérieur : {link(agent['parent_id']) if agent['parent_id'] else 'Propriétaire'}"]
        if team and team != agent["id"]:
            meta.append(f"Équipe : {link(team)}")
        if subs:
            meta.append("Subordonnés : " + ", ".join(link(s["id"]) for s in subs))
        body = [f"# {agent['nom']}", "> " + " · ".join(meta), ""]
        for title, key in SECTIONS:
            body += [f"## {title}", agent.get(key) or "", ""]
        return fm, "\n".join(body)

    def render_agent(self, agent: dict) -> str:
        fm, body = self.agent_note(agent)
        return self.w.write(agent["vault_path"], fm, body, kind="agent")

    def decision(self, actor: Actor, titre: str, texte: str, commit: bool = True) -> str:
        rel = f"Decisions/{now_iso()[:10]}-{slugify(titre)[:60]}.md"
        fm = {"type": "decision", "auteur": actor.id, "date": now_iso(), "titre": titre}
        path = self.w.write(rel, fm, f"# {titre}\n\nPar {self.w.link(actor.id) if actor.is_agent else actor.nom or actor.id}\n\n{texte}\n",
                            kind="decision")
        self.p.audit.record("decision", titre, agent_id=actor.id, niveau=actor.niveau, cible=path)
        if commit:
            self.p.git.commit(f"Décision : {titre}", paths=[path])
        return path

    def on_log(self, e: dict) -> None:
        """Journal lisible du jour dans Obsidian (le journal infalsifiable reste logs/*.jsonl)."""
        day = e["horodatage"][:10]
        path = self.vault / "Logs" / f"{day}.md"
        who = self.w.link(e["agent_id"]) if e.get("agent_id") and e["agent_id"].startswith("agent-") else (e.get("agent_id") or "système")
        icon = {"attention": "⚠️ ", "grave": "🔴 ", "critique": "🚨 "}.get(e.get("gravite"), "")
        line = f"- `{e['horodatage'][11:19]}` {icon}{who} · **{e['type_evenement']}** · {e['action']}"
        if e.get("cible"):
            line += f" → {e['cible']}"
        if e.get("resultat") and e["resultat"] != "ok":
            line += f" — {str(e['resultat'])[:200]}"
        if e.get("cout_eur"):
            line += f" ({e['cout_eur']:.4f} €)"
        new = not path.exists()
        with path.open("a", encoding="utf-8", newline="\n") as f:
            if new:
                f.write(f"---\ntype: journal\ndate: {day}\n---\n# Journal du {day}\n\n")
            f.write(line.replace("\n", " ") + "\n")

    # ================================================================== écritures des agents
    def write_as(self, actor: Actor, rel: str, content: str) -> str:
        rel = rel.replace("\\", "/").lstrip("/")
        self.p.perms.require(actor, "vault.write", rel)
        fm, body = parse_note(content) if content.lstrip().startswith("---") else (None, content)
        path = self.w.write(rel, fm or None, body, kind="note")
        self.p.audit.record("coffre", "ecriture_note", agent_id=actor.id, niveau=actor.niveau, cible=path)
        return path

    def write_agent_note(self, actor: Actor, name: str, content: str) -> str:
        from orchestra.permissions import workspace_of
        name = name.replace("\\", "/").lstrip("/")
        if actor.is_agent and not name.startswith(tuple(f"{d}/" for d in ("Agents", "Messages", "Demandes", "Skills", "Decisions",
                                                                             "Rapports", "Logs", "Budget", "Archives", "Apprentissages"))):
            ws = workspace_of(self.p.agents.get(actor.id))
            name = ws + (name if name.endswith(".md") else name + ".md")
        return self.write_as(actor, name, content)

    def read_as(self, actor: Actor, rel: str) -> str:
        rel = rel.replace("\\", "/").lstrip("/")
        self.p.perms.require(actor, "vault.read", rel)
        path = self.w.abs(rel)
        if not path.exists():
            raise NotFound("note introuvable")
        return path.read_text(encoding="utf-8")

    # ================================================================== recherche
    def search(self, query: str, actor: Actor | None = None, limit: int = 10, any_term: bool = False,
               types: tuple[str, ...] | None = None) -> list[dict]:
        terms = [t for t in re.findall(r"\w{3,}", query.lower(), flags=re.UNICODE)][:30]
        if not terms:
            return []
        expr = (" OR " if any_term else " AND ").join(f'"{t}"' for t in terms)
        where = "vault_fts MATCH ?"
        params: list[Any] = [expr]
        if types:
            where += f" AND type IN ({','.join('?' * len(types))})"
            params += list(types)
        rows = self.p.db.query(
            f"SELECT path, type, titre, snippet(vault_fts, 3, '**', '**', '…', 16) AS extrait, bm25(vault_fts) AS score "
            f"FROM vault_fts WHERE {where} ORDER BY score LIMIT ?", (*params, limit * 4))
        out = []
        for r in rows:
            if actor is None or actor.is_owner or self.p.perms.check(actor, "vault.read", r["path"]):
                out.append(r)
            if len(out) >= limit:
                break
        return out

    def reindex(self) -> int:
        n = 0
        self.p.db.execute("DELETE FROM vault_fts")
        for f in self.vault.rglob("*.md"):
            rel = f.relative_to(self.vault).as_posix()
            if rel.startswith((".git/", ".obsidian/", ".trash/")):
                continue
            try:
                fm, body = parse_note(f.read_text(encoding="utf-8"))
            except (OrchestraError, OSError, UnicodeDecodeError):
                continue
            kind = rel.split("/", 1)[0].lower() if "/" in rel else "note"
            self.w.index(rel, fm, body, {"agents": "agent", "skills": "skill", "apprentissages": "apprentissage",
                                         "decisions": "decision", "messages": "message", "demandes": "demande"}.get(kind, kind))
            n += 1
        return n

    # ================================================================== coffre → base
    def import_note(self, rel: str) -> str:
        """Applique une note modifiée à la main. Retourne l'action effectuée."""
        rel = rel.replace("\\", "/")
        path = self.vault / rel
        if rel.startswith(IGNORED_DIRS) or not rel.endswith(".md"):
            return "ignoree"
        if not path.exists():
            return self._deleted(rel)
        text = path.read_text(encoding="utf-8")
        known = self.p.db.scalar("SELECT hash FROM vault_state WHERE path=?", (rel,))
        if known == sha(text):
            return "inchangee"  # écriture de la plateforme elle-même (anti-écho)
        try:
            fm, body = parse_note(text)
            # Seules les fiches (Agents/<Niveau>/<fichier>.md) sont des définitions d'agents. Les notes de travail
            # des agents (Agents/<Niveau>/<nom>/…) ne sont JAMAIS importées comme des actions du Propriétaire.
            if rel.startswith("Agents/") and rel.count("/") == 2:
                return self._import_agent(rel, fm, body)
            if rel.startswith("Skills/") and getattr(self.p, "skills", None):
                return self.p.skills.import_note(rel, fm, body)
        except (OrchestraError, ValueError, TypeError) as e:
            self.p.audit.record("coffre", "import_refuse", agent_id=OWNER.id, niveau="proprietaire", cible=rel,
                                resultat=str(e), gravite="attention")
            self.p.alerts.raise_("import_obsidian", f"Note {rel} non appliquée : {e}", gravite="attention")
            return f"erreur: {e}"
        self.w.remember(rel, text)
        self.w.index(rel, fm, body, "note")
        return "indexee"

    def _deleted(self, rel: str) -> str:
        a = self.p.db.one("SELECT * FROM agents WHERE vault_path=?", (rel,))
        if a:  # un agent n'est jamais supprimé : la fiche est restaurée
            self.p.git.commit(f"Restauration de la fiche {a['nom']}", paths=[self.render_agent(a)])
            self.p.alerts.raise_("fiche_supprimee", f"Fiche {rel} supprimée dans Obsidian : restaurée (utiliser l'archivage)", gravite="attention")
            return "restauree"
        return "ignoree"

    def fields_from_note(self, fm: dict, body: str) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for k_fm, k in (("nom", "nom"), ("niveau", "niveau"), ("superieur", "parent_id"), ("statut", "statut"),
                        ("modele", "modele"), ("budget_jour_eur", "budget_jour_eur"), ("budget_mois_eur", "budget_mois_eur"),
                        ("outils", "outils"), ("skills", "skills"), ("kpi", "kpi")):
            if k_fm in fm and fm[k_fm] is not None:
                data[k] = fm[k_fm]
        if "parent_id" in data:
            ref = str(data["parent_id"]).strip().strip("[]").split("|")[0]
            parent = self.p.agents.find(ref)
            data["parent_id"] = parent["id"] if parent else ref
        for k in ("outils", "kpi", "skills"):
            if k in data:
                v = data[k]
                if isinstance(v, str):
                    v = [x.strip() for x in v.split(",") if x.strip()]
                data[k] = [_strip_link(x) for x in _flatten(v)] if k == "skills" else [str(x) for x in _flatten(v)]
        for k in ("budget_jour_eur", "budget_mois_eur"):
            if k in data:
                data[k] = float(data[k])
        if data.get("niveau") and data["niveau"] not in LEVELS:
            raise OrchestraError(f"niveau inconnu : {data['niveau']}")
        sections = parse_sections(body)
        data.update(sections)
        return data

    def _import_agent(self, rel: str, fm: dict, body: str) -> str:
        data = self.fields_from_note(fm, body)
        agent_id = str(fm.get("id") or "").strip()
        existing = self.p.perms.agent(agent_id) if agent_id else None
        if not existing:
            existing = self.p.db.one("SELECT * FROM agents WHERE vault_path=?", (rel,))
        if existing:
            if existing["vault_path"] != rel:
                raise OrchestraError(f"la fiche {existing['id']} vit dans {existing['vault_path']}")
            statut = data.pop("statut", existing["statut"])
            data.pop("niveau", None) if data.get("niveau") == existing["niveau"] else None
            if statut != existing["statut"]:
                self.p.agents.set_status(OWNER, existing["id"], statut, "modifié dans Obsidian par le Propriétaire")
            self.p.agents.update(OWNER, existing["id"], data, "modification manuelle dans Obsidian (le Propriétaire gagne)")
            self.p.audit.record("coffre", "import_fiche", agent_id=OWNER.id, niveau="proprietaire", cible=existing["id"])
            return "agent_modifie"
        # nouvelle fiche créée à la main
        data.setdefault("nom", Path(rel).stem.replace("-", " ").title())
        folder = rel.split("/")[1] if rel.count("/") >= 2 else ""
        if "niveau" not in data:
            inv = {v: k for k, v in LEVEL_DIRS.items()}
            data["niveau"] = inv.get(folder, "salarie")
        expected = f"Agents/{LEVEL_DIRS[data['niveau']]}/"
        if rel.startswith(expected) and not self.p.db.one("SELECT 1 FROM agents WHERE vault_path=?", (rel,)):
            data["vault_path"] = rel
        data.setdefault("statut", "brouillon")
        agent = self.p.agents.create(OWNER, data, "création depuis une note Obsidian")
        if agent["vault_path"] != rel:
            (self.vault / rel).unlink(missing_ok=True)
        self.p.audit.record("coffre", "creation_depuis_note", agent_id=OWNER.id, niveau="proprietaire", cible=agent["id"],
                            details={"note": rel})
        return "agent_cree"

    # ================================================================== surveillance du coffre
    def start(self) -> None:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        scribe = self

        class Handler(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.is_directory:
                    return
                for attr in ("src_path", "dest_path"):
                    p = getattr(event, attr, None)
                    if p and str(p).endswith(".md"):
                        try:
                            rel = Path(p).resolve().relative_to(scribe.vault.resolve()).as_posix()
                        except ValueError:
                            continue
                        if not rel.startswith(IGNORED_DIRS):
                            with scribe._lock:
                                scribe._pending[rel] = time.monotonic()

        self._stop.clear()
        self._observer = Observer()
        self._observer.schedule(Handler(), str(self.vault), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        self._worker = threading.Thread(target=self._drain, daemon=True, name="scribe")
        self._worker.start()

    def _drain(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.2)
            now_ = time.monotonic()
            with self._lock:
                ready = [r for r, t in self._pending.items() if now_ - t > 0.5]  # anti-rebond
                for r in ready:
                    self._pending.pop(r, None)
            for rel in ready:
                try:
                    self.import_note(rel)
                except Exception as e:  # ne jamais tuer la surveillance
                    self.p.audit.record("coffre", "erreur_scribe", cible=rel, resultat=str(e), gravite="grave")

    def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None


def parse_sections(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    current, buf = None, []
    for line in body.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current:
                out[current] = "\n".join(buf).strip()
            title = re.sub(r"\s*\(.*\)$", "", m.group(1)).strip().lower()
            current, buf = SECTION_KEYS.get(title), []
            continue
        if current:
            buf.append(line)
    if current:
        out[current] = "\n".join(buf).strip()
    return out


def _flatten(v: Any) -> list:
    if isinstance(v, list):
        out = []
        for x in v:
            out += _flatten(x)
        return out
    return [v] if v not in (None, "") else []


def _strip_link(x: Any) -> str:
    return str(x).strip().strip("[]").split("|")[0]
