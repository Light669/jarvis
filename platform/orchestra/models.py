"""Vocabulaire commun : niveaux, statuts, acteurs, erreurs."""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata
import uuid
from dataclasses import dataclass

LEVELS = ("chef", "responsable", "salarie", "apprenti")
RANK = {"proprietaire": -1, "systeme": -1, "chef": 0, "responsable": 1, "salarie": 2, "apprenti": 3}
LEVEL_LABEL = {"chef": "Chef d'Orchestre", "responsable": "Responsable", "salarie": "Salarié", "apprenti": "Apprenti"}
STATUTS = ("brouillon", "actif", "pause", "archive")
TRANSITIONS = {
    "brouillon": {"actif", "archive"},
    "actif": {"pause", "archive"},
    "pause": {"actif", "archive"},
    "archive": set(),
}

OWNER_ID = "proprietaire"
SYSTEM_ID = "systeme"


@dataclass(frozen=True)
class Actor:
    """Qui agit : le Propriétaire, un service système (Scribe, Vérificateur…) ou un agent."""

    id: str
    niveau: str
    nom: str = ""

    @property
    def is_owner(self) -> bool:
        return self.niveau == "proprietaire"

    @property
    def is_system(self) -> bool:
        return self.niveau == "systeme"

    @property
    def is_agent(self) -> bool:
        return self.niveau in LEVELS


OWNER = Actor(OWNER_ID, "proprietaire", "Propriétaire")


def system(name: str = "systeme") -> Actor:
    return Actor(f"{SYSTEM_ID}:{name}" if name != "systeme" else SYSTEM_ID, "systeme", name)


def agent_actor(agent: dict) -> Actor:
    return Actor(agent["id"], agent["niveau"], agent["nom"])


class OrchestraError(Exception):
    status = 400


class PermissionDenied(OrchestraError):
    status = 403


class NotFound(OrchestraError):
    status = 404


class BudgetExceeded(OrchestraError):
    status = 402


class EmergencyStop(OrchestraError):
    status = 423


class RateLimited(OrchestraError):
    status = 429


def now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or "sans-nom"
