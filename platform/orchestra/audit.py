"""Journal append-only infalsifiable : jsonl quotidien, chaque ligne contient le hash de la précédente."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from orchestra.models import now
from orchestra.redact import Redactor

GENESIS = "0" * 64
FIELDS = ("horodatage", "agent_id", "niveau", "type_evenement", "action", "cible",
          "resultat", "cout_tokens", "cout_eur", "correlation_id")


def _canonical(entry: dict[str, Any]) -> bytes:
    return json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_hash(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canonical(body)).hexdigest()


class AuditLog:
    """Seul point d'écriture des logs. Aucune API ne permet de modifier ou d'effacer une ligne."""

    def __init__(self, logs_dir: Path, redactor: Redactor):
        self.dir = Path(logs_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.redactor = redactor
        self._lock = threading.Lock()
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        self.seq, self.prev_hash = self._load_head()

    def _files(self) -> list[Path]:
        return sorted(self.dir.glob("*.jsonl"))

    def _load_head(self) -> tuple[int, str]:
        for f in reversed(self._files()):
            last = None
            with f.open("rb") as fh:
                for line in fh:
                    if line.strip():
                        last = line
            if last:
                entry = json.loads(last)
                return int(entry["seq"]), entry["hash"]
        return 0, GENESIS

    def record(
        self,
        type_evenement: str,
        action: str,
        *,
        agent_id: str | None = None,
        niveau: str | None = None,
        cible: str | None = None,
        resultat: str = "ok",
        cout_tokens: int = 0,
        cout_eur: float = 0.0,
        correlation_id: str | None = None,
        gravite: str = "info",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ts = now()
        with self._lock:
            entry = {
                "seq": self.seq + 1,
                "horodatage": ts.isoformat(timespec="milliseconds"),
                "agent_id": agent_id,
                "niveau": niveau,
                "type_evenement": type_evenement,
                "action": self.redactor.full(action),
                "cible": self.redactor.full(cible) if cible else cible,
                "resultat": self.redactor.full(resultat),
                "gravite": gravite,
                "cout_tokens": int(cout_tokens),
                "cout_eur": round(float(cout_eur), 6),
                "correlation_id": correlation_id,
                "details": self.redactor.obj(details or {}),
                "prev_hash": self.prev_hash,
            }
            entry["hash"] = compute_hash(entry)
            path = self.dir / f"{ts.date().isoformat()}.jsonl"
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                os.write(fd, _canonical(entry) + b"\n")
            finally:
                os.close(fd)
            self.seq, self.prev_hash = entry["seq"], entry["hash"]
        for cb in list(self.listeners):
            try:
                cb(entry)
            except Exception:  # un listener défaillant ne doit jamais bloquer la journalisation
                pass
        return entry

    def head(self) -> tuple[int, str]:
        return self.seq, self.prev_hash


@dataclass
class VerifyReport:
    ok: bool = True
    files: int = 0
    lines: int = 0
    errors: list[str] = field(default_factory=list)


def verify_chain(logs_dir: Path, expected_head: tuple[int, str] | None = None) -> VerifyReport:
    """Recalcule chaque hash, vérifie le chaînage et la continuité des numéros de séquence.

    `expected_head` (seq, hash) mémorisé en base permet aussi de détecter une troncature de fin.
    """
    rep = VerifyReport()
    prev, seq = GENESIS, 0
    for f in sorted(Path(logs_dir).glob("*.jsonl")):
        rep.files += 1
        with f.open("rb") as fh:
            for n, raw in enumerate(fh, 1):
                if not raw.strip():
                    continue
                rep.lines += 1
                where = f"{f.name}:{n}"
                try:
                    entry = json.loads(raw)
                except ValueError:
                    rep.errors.append(f"{where} ligne illisible")
                    continue
                if entry.get("prev_hash") != prev:
                    rep.errors.append(f"{where} chaînage rompu (prev_hash inattendu)")
                if compute_hash(entry) != entry.get("hash"):
                    rep.errors.append(f"{where} contenu altéré (hash invalide)")
                if entry.get("seq") != seq + 1:
                    rep.errors.append(f"{where} séquence discontinue ({seq} -> {entry.get('seq')}) : ligne supprimée ?")
                prev, seq = entry.get("hash", ""), int(entry.get("seq", seq + 1))
    if expected_head and expected_head[0] > seq:
        rep.errors.append(f"journal tronqué : dernière séquence {seq}, attendue {expected_head[0]}")
    elif expected_head and expected_head[0] == seq and expected_head[1] != prev:
        rep.errors.append("dernière ligne remplacée (hash de tête différent)")
    rep.ok = not rep.errors
    return rep
