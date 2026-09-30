"""Conteneur des services de la plateforme (un seul objet partagé par l'API et les tests)."""
from __future__ import annotations

from pathlib import Path

from orchestra.config import load_config, load_env
from orchestra.vault import VaultGit, init_vault


class Platform:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.cfg = load_config(self.root)
        self.env = load_env(self.root)
        self.vault_dir = self.root / self.cfg.paths.vault
        self.data_dir = self.root / self.cfg.paths.data
        self.logs_dir = self.root / self.cfg.paths.logs
        for d in (self.data_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
        init_vault(self.vault_dir)
        self.git = VaultGit(self.vault_dir)
        self.git.ensure_repo()

    def close(self) -> None:
        pass
