"""Phase 1 : arborescence, configuration, coffre, scripts."""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from orchestra.config import Config, load_config
from orchestra.platform import Platform
from orchestra.vault import VAULT_DIRS

REPO = Path(__file__).resolve().parents[1]


def test_repo_layout():
    for p in ["config.yaml", ".env.example", "docker-compose.yml", "start.ps1", "stop.ps1",
              "detect.ps1", "start.sh", "stop.sh", "platform/pyproject.toml",
              "platform/sandbox_image/Dockerfile", "docs"]:
        assert (REPO / p).exists(), p


def test_env_is_gitignored():
    gi = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in gi and "Cerveau/" in gi


def test_config_valid_and_local_only(root):
    cfg = load_config(root)
    assert cfg.server.host == "127.0.0.1"
    assert cfg.budget.monthly_eur == 100
    assert cfg.budget.alert_ratio == 0.8
    assert cfg.hierarchy.promotion.min_validated_tasks == 20
    assert cfg.llm.fallback_chain[0].startswith("ollama/")
    for model in cfg.llm.fallback_chain:
        assert model.split("/", 1)[0] in cfg.llm.providers


def test_config_refuses_network_exposure(root):
    data = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    data["server"]["host"] = "0.0.0.0"
    (root / "config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(root)


def test_vault_initialised(root):
    Platform(root).close()
    vault = root / "Cerveau"
    for d in VAULT_DIRS:
        assert (vault / d).is_dir(), d
    for f in ["00_Accueil.md", "Modeles_de_notes/agent.md", "Modeles_de_notes/skill.md",
              "Modeles_de_notes/demande.md", "Modeles_de_notes/rapport.md", ".obsidian/app.json"]:
        assert (vault / f).is_file(), f
    if shutil.which("git"):
        assert (vault / ".git").is_dir()
        out = subprocess.run(["git", "log", "--oneline"], cwd=vault, capture_output=True, text=True).stdout
        assert "Initialisation du coffre" in out


def test_init_is_idempotent_and_keeps_user_edits(root):
    Platform(root).close()
    accueil = root / "Cerveau" / "00_Accueil.md"
    accueil.write_text("modifié par le Propriétaire", encoding="utf-8")
    Platform(root).close()
    assert accueil.read_text(encoding="utf-8") == "modifié par le Propriétaire"


def test_agent_template_frontmatter_parses():
    text = (REPO / "platform/orchestra/vault_template/Modeles_de_notes/agent.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---")[1])
    for key in ["id", "nom", "niveau", "superieur", "statut", "modele", "budget_jour_eur",
                "outils", "skills", "cree_par", "cree_le", "version"]:
        assert key in fm


@pytest.mark.skipif(not shutil.which("pwsh"), reason="PowerShell absent")
def test_powershell_scripts_parse():
    for s in ["start.ps1", "stop.ps1", "detect.ps1"]:
        cmd = ("$e=$null;[System.Management.Automation.Language.Parser]::ParseFile('" + str(REPO / s)
               + "',[ref]$null,[ref]$e)|Out-Null;if($e){$e;exit 1}")
        assert subprocess.run(["pwsh", "-NoProfile", "-Command", cmd]).returncode == 0, s


def test_default_config_model_is_complete():
    # la config par défaut (sans fichier) reste valide
    assert Config().budget.monthly_eur == 100
