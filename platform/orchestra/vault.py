"""Initialisation du coffre Obsidian et versionnage Git du coffre."""
from __future__ import annotations

import shutil
import subprocess
import threading
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
    """Commit automatique dans le dépôt Git du coffre (historique + retour arrière)."""

    def __init__(self, vault: Path):
        self.vault = vault
        self._lock = threading.Lock()
        self.available = shutil.which("git") is not None

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-c", "user.name=Orchestra Scribe", "-c", "user.email=scribe@orchestra.local",
             "-c", "core.autocrlf=false", *args],
            cwd=self.vault, capture_output=True, text=True, encoding="utf-8",
        )

    def ensure_repo(self) -> None:
        if not self.available:
            return
        if not (self.vault / ".git").exists():
            self._run("init", "-q")
            self.commit("Initialisation du coffre")

    def commit(self, message: str) -> str | None:
        """Ajoute tout et commite ; retourne le hash ou None si rien à commiter."""
        if not self.available:
            return None
        with self._lock:
            self._run("add", "-A")
            res = self._run("commit", "-q", "-m", message)
            if res.returncode != 0:
                return None
            return self._run("rev-parse", "HEAD").stdout.strip()

    def log(self, path: str | None = None, limit: int = 20) -> list[str]:
        if not self.available:
            return []
        args = ["log", f"-{limit}", "--pretty=%H %s"]
        if path:
            args += ["--", path]
        return [l for l in self._run(*args).stdout.splitlines() if l]
