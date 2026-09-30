"""Initialisation du coffre Obsidian et versionnage Git du coffre."""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

TEMPLATE_DIR = Path(__file__).parent / "vault_template"

LEVEL_DIRS = {
    "chef": "Chef",
    "responsable": "Responsables",
    "salarie": "Salaries",
    "apprenti": "Apprentis",
}

VAULT_DIRS = [
    *(f"Agents/{d}" for d in LEVEL_DIRS.values()),
    "Messages",
    "Demandes",
    "Skills/globaux",
    "Skills/equipes",
    "Skills/agents",
    "Apprentissages",
    "Decisions",
    "Rapports",
    "Logs",
    "Budget",
    "Modeles_de_notes",
    "Archives/Agents",
    "Archives/Skills",
]


def init_vault(vault: Path) -> None:
    """Crée l'arborescence et copie les modèles sans écraser l'existant."""
    vault.mkdir(parents=True, exist_ok=True)
    for d in VAULT_DIRS:
        (vault / d).mkdir(parents=True, exist_ok=True)
    for src in TEMPLATE_DIR.rglob("*"):
        if src.is_dir():
            continue
        dst = vault / src.relative_to(TEMPLATE_DIR)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    gi = vault / ".gitignore"
    if not gi.exists():
        gi.write_text(".obsidian/workspace*.json\n.trash/\n", encoding="utf-8")


class VaultGit:
    """Commit automatique dans le dépôt Git du coffre (historique + retour arrière).

    Les commits sont écrits par un thread dédié pour ne pas ralentir les agents ;
    `flush()` attend que tout soit commité.
    """

    def __init__(self, vault: Path):
        self.vault = vault
        self._lock = threading.Lock()
        self._cv = threading.Condition()
        self._queue: list[tuple[str, dict[str, bytes] | None, list[str]]] = []
        self._busy = False
        self._thread: threading.Thread | None = None
        self.available = shutil.which("git") is not None

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-c", "user.name=Orchestra Scribe", "-c", "user.email=scribe@orchestra.local",
             "-c", "core.autocrlf=false", "-c", "core.quotepath=false", *args],
            cwd=self.vault, capture_output=True, text=True, encoding="utf-8",
        )

    def ensure_repo(self) -> None:
        if not self.available:
            return
        if not (self.vault / ".git").exists():
            self._run("init", "-q")
            self._commit_all("Initialisation du coffre")

    def commit(self, message: str, paths: list[str] | None = None, removed: list[str] | None = None,
               wait: bool = False) -> None:
        """Planifie un commit.

        Avec `paths`, le contenu des fichiers est capturé IMMÉDIATEMENT : chaque version d'une fiche a
        son propre commit, même si le fichier est modifié à nouveau avant que le commit soit écrit.
        Sans `paths`, tout le coffre est commité (`git add -A`).
        """
        if not self.available:
            return
        snap: dict[str, bytes] | None = None
        if paths is not None:
            snap = {}
            for rel in dict.fromkeys(paths):
                f = self.vault / rel
                if f.is_file():
                    snap[rel] = f.read_bytes()
        with self._cv:
            self._queue.append((message, snap, list(removed or [])))
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._loop, daemon=True, name="vault-git")
                self._thread.start()
            self._cv.notify_all()
        if wait:
            self.flush()

    def _loop(self) -> None:
        while True:
            with self._cv:
                while not self._queue:
                    if not self._cv.wait(timeout=30):
                        self._thread = None
                        return
                batch, self._queue = self._queue, []
                self._busy = True
            try:
                group: list = []
                for item in batch + [None]:
                    if item is not None and item[1] is not None:
                        group.append(item)
                        continue
                    if group:
                        self._fast_import(group)
                        group = []
                    if item is not None:
                        self._commit_all(item[0])
            except Exception:  # le versionnage ne doit jamais bloquer la plateforme
                pass
            finally:
                with self._cv:
                    self._busy = False
                    self._cv.notify_all()

    def _fast_import(self, items: list) -> None:
        """Écrit N commits (un par changement, contenu capturé) en un seul processus `git fast-import`."""
        with self._lock:
            branch = self._run("symbolic-ref", "-q", "HEAD").stdout.strip() or "refs/heads/master"
            parent = self._run("rev-parse", "-q", "--verify", "HEAD").stdout.strip()
            out = bytearray()
            ts = int(time.time())
            for i, (message, snap, removed) in enumerate(items):
                msg = message.encode("utf-8")
                out += f"commit {branch}\ncommitter Orchestra Scribe <scribe@orchestra.local> {ts} +0000\n".encode()
                out += f"data {len(msg)}\n".encode() + msg + b"\n"
                if i == 0 and parent:
                    out += f"from {parent}\n".encode()
                for rel in removed:
                    out += b"D " + _quote(rel) + b"\n"
                for rel, content in snap.items():
                    out += b"M 100644 inline " + _quote(rel) + b"\n" + f"data {len(content)}\n".encode() + content + b"\n"
                out += b"\n"
            r = subprocess.run(["git", "fast-import", "--quiet", "--force"], cwd=self.vault, input=bytes(out), capture_output=True)
            if r.returncode == 0:
                self._run("read-tree", "HEAD")  # l'index suit HEAD ; le reste est repris par le prochain `add -A`

    def _commit_all(self, message: str) -> None:
        with self._lock:
            self._run("add", "-A")
            self._run("commit", "-q", "-m", message)

    def flush(self, timeout: float = 30) -> None:
        end = time.monotonic() + timeout
        with self._cv:
            while (self._queue or self._busy) and time.monotonic() < end:
                self._cv.wait(timeout=0.1)

    def log(self, path: str | None = None, limit: int = 20) -> list[str]:
        if not self.available:
            return []
        self.flush()
        args = ["log", f"-{limit}", "--pretty=%H %ad %s", "--date=iso"]
        if path:
            args += ["--follow", "--", path]
        return [l for l in self._run(*args).stdout.splitlines() if l]

    def show(self, rev: str, path: str) -> str | None:
        self.flush()
        r = self._run("show", f"{rev}:{path}")
        return r.stdout if r.returncode == 0 else None


def _quote(path: str) -> bytes:
    """Chemin pour git fast-import (guillemets style C si nécessaire)."""
    if any(c in path for c in '"\\\n') or path.startswith(" "):
        esc = path.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return ('"' + esc + '"').encode("utf-8")
    return path.encode("utf-8")
