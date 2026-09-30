"""Écriture dans le coffre Obsidian : frontmatter YAML, wikilinks, masquage des secrets, index plein texte."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import yaml

from orchestra.models import OWNER_ID, OrchestraError, now_iso


def dump_note(frontmatter: dict[str, Any] | None, body: str) -> str:
    if frontmatter is None:
        return body.rstrip() + "\n"
    fm = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=None, width=1000).strip()
    return f"---\n{fm}\n---\n{body.rstrip()}\n"


def parse_note(text: str) -> tuple[dict[str, Any], str]:
    text = text.lstrip("﻿")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.S)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        raise OrchestraError(f"frontmatter YAML invalide : {e}") from None
    if not isinstance(fm, dict):
        raise OrchestraError("frontmatter invalide")
    return fm, m.group(2)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def note_title(fm: dict, body: str, path: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, flags=re.M)
    return str(fm.get("nom") or fm.get("sujet") or (m.group(1) if m else Path(path).stem))


class VaultWriter:
    def __init__(self, p):
        self.p = p
        self.root = p.vault_dir

    def abs(self, rel: str) -> Path:
        rel = rel.replace("\\", "/").lstrip("/")
        path = (self.root / rel).resolve()
        if self.root.resolve() not in path.parents and path != self.root.resolve():
            raise OrchestraError("chemin hors du coffre")
        return path

    def write(self, rel: str, frontmatter: dict[str, Any] | None, body: str, commit: str | None = None,
              kind: str = "note") -> str:
        fm = self.p.redactor.obj(frontmatter, pii=False) if frontmatter else frontmatter
        text = dump_note(fm, self.p.redactor.secrets(body))
        path = self.abs(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        rel = path.relative_to(self.root.resolve()).as_posix()
        self.remember(rel, text)
        self.index(rel, fm or {}, body, kind)
        if commit:
            self.p.git.commit(commit)
        return rel

    def remember(self, rel: str, text: str) -> None:
        """Mémorise le hash écrit par la plateforme : le Scribe ignore ses propres écritures (anti-écho)."""
        self.p.db.execute("INSERT INTO vault_state(path,hash,maj) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET hash=excluded.hash, maj=excluded.maj",
                          (rel, sha(text), now_iso()))

    def index(self, rel: str, fm: dict, body: str, kind: str) -> None:
        self.p.db.execute("DELETE FROM vault_fts WHERE path=?", (rel,))
        self.p.db.execute("INSERT INTO vault_fts(path,type,titre,contenu) VALUES(?,?,?,?)",
                          (rel, kind, note_title(fm, body, rel), body))

    def move(self, old: str, new: str) -> None:
        src, dst = self.abs(old), self.abs(new)
        if src.exists() and src != dst:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)
            self.p.db.execute("DELETE FROM vault_state WHERE path=?", (old,))
            self.p.db.execute("DELETE FROM vault_fts WHERE path=?", (old,))
            ws_old, ws_new = src.with_suffix(""), dst.with_suffix("")
            if ws_old.is_dir() and not ws_new.exists():
                ws_old.replace(ws_new)

    # ------------------------------------------------------------------ liens
    def link(self, ref: str | None) -> str:
        if not ref:
            return "—"
        if ref == OWNER_ID:
            return "Propriétaire"
        a = self.p.perms.agent(ref)
        if a and a.get("vault_path"):
            return f"[[{Path(a['vault_path']).stem}|{a['nom']}]]"
        return ref
