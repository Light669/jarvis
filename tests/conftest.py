import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "platform"))


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """Racine Orchestra isolée : config.yaml du dépôt + dossiers vides."""
    shutil.copy(REPO / "config.yaml", tmp_path / "config.yaml")
    (tmp_path / "platform").mkdir()
    (tmp_path / ".env").write_text(
        "ORCHESTRA_TOKEN=test-token-0123456789\nGROQ_API_KEY=gsk_testsecretvalue1234567890\n",
        encoding="utf-8",
    )
    return tmp_path
