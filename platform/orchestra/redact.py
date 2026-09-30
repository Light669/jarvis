"""Masquage des secrets et données personnelles (logs, coffre, messages)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

MASK = "***"

# Secrets : jamais nulle part (logs, coffre, skills, messages).
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("cle_anthropic", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")),
    ("cle_openrouter", re.compile(r"sk-or-v1-[A-Za-z0-9]{16,}")),
    ("cle_openai", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("cle_groq", re.compile(r"gsk_[A-Za-z0-9]{16,}")),
    ("cle_google", re.compile(r"AIza[0-9A-Za-z_\-]{30,}")),
    ("jeton_github", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}")),
    ("cle_privee", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("affectation_secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|password|mot_de_passe|token)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{12,}")),
]

# Données personnelles : masquées dans les logs uniquement (RGPD).
PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("telephone", re.compile(r"(?<!\d)(?:\+33\s?|0)[1-9](?:[ .\-]?\d{2}){4}(?!\d)")),
    ("iban", re.compile(r"\bFR\d{2}(?:\s?[0-9A-Z]{4}){5}\s?[0-9A-Z]{3}\b")),
]

SENSITIVE_KEYS = re.compile(r"(?i)(api[_-]?key|password|mot_de_passe|secret|token|authorization)")


class Redactor:
    def __init__(self, env: dict[str, str] | None = None):
        # valeurs réelles de .env (longueur >= 8) : masquées partout
        self.literals = sorted(
            {v for v in (env or {}).values() if v and len(v) >= 8}, key=len, reverse=True
        )

    def secrets(self, text: str) -> str:
        if not isinstance(text, str) or not text:
            return text
        for lit in self.literals:
            text = text.replace(lit, MASK)
        for _, pat in SECRET_PATTERNS:
            text = pat.sub(MASK, text)
        return text

    def full(self, text: str) -> str:
        text = self.secrets(text)
        if not isinstance(text, str):
            return text
        for _, pat in PII_PATTERNS:
            text = pat.sub(MASK, text)
        return text

    def obj(self, value: Any, pii: bool = True) -> Any:
        """Masque récursivement dict/list/str."""
        fn = self.full if pii else self.secrets
        if isinstance(value, str):
            return fn(value)
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if isinstance(k, str) and SENSITIVE_KEYS.search(k) and isinstance(v, str) and v:
                    out[k] = MASK
                else:
                    out[k] = self.obj(v, pii)
            return out
        if isinstance(value, (list, tuple)):
            return [self.obj(v, pii) for v in value]
        return value

    def find_secrets(self, text: str) -> list[str]:
        found = [name for name, pat in SECRET_PATTERNS if pat.search(text)]
        found += ["valeur_env" for lit in self.literals if lit in text]
        return found


def scan_paths(paths: Iterable[Path], env: dict[str, str] | None = None) -> list[str]:
    """Recherche automatique de secrets dans des dossiers (hors .git)."""
    r = Redactor(env)
    hits: list[str] = []
    for base in paths:
        base = Path(base)
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or ".git" in f.parts or f.suffix.lower() not in {".md", ".jsonl", ".json", ".txt", ".yaml", ".yml", ".csv"}:
                continue
            try:
                for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    kinds = r.find_secrets(line)
                    if kinds:
                        hits.append(f"{f}:{n}: {', '.join(sorted(set(kinds)))}")
            except OSError:
                continue
    return hits
