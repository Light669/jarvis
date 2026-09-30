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


@pytest.fixture()
def plat(root):
    from orchestra.platform import Platform

    p = Platform(root)
    yield p
    p.close()


@pytest.fixture()
def org(plat):
    """Organisation type : Chef > 2 Responsables > Salariés > Apprentis."""
    from orchestra.models import OWNER

    A = plat.agents
    chef = A.create(OWNER, {"nom": "Chef", "niveau": "chef", "statut": "actif"})
    r1 = A.create(OWNER, {"nom": "Resp Ventes", "niveau": "responsable", "parent_id": chef["id"], "statut": "actif"})
    r2 = A.create(OWNER, {"nom": "Resp Contenu", "niveau": "responsable", "parent_id": chef["id"], "statut": "actif"})
    s1 = A.create(OWNER, {"nom": "Prospecteur", "niveau": "salarie", "parent_id": r1["id"], "statut": "actif", "outils": ["recherche_web"]})
    s2 = A.create(OWNER, {"nom": "Redacteur Ventes", "niveau": "salarie", "parent_id": r1["id"], "statut": "actif"})
    s3 = A.create(OWNER, {"nom": "Monteur", "niveau": "salarie", "parent_id": r2["id"], "statut": "actif"})
    a1 = A.create(OWNER, {"nom": "Apprenti Ventes", "niveau": "apprenti", "parent_id": s1["id"], "statut": "actif"})
    a2 = A.create(OWNER, {"nom": "Apprenti Contenu", "niveau": "apprenti", "parent_id": s3["id"], "statut": "actif"})
    return {k: A.get(v["id"]) for k, v in dict(chef=chef, r1=r1, r2=r2, s1=s1, s2=s2, s3=s3, a1=a1, a2=a2).items()}
