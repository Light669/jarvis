"""Fournisseurs LLM. Tous parlent le protocole « chat/completions » compatible OpenAI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx


class ProviderError(Exception):
    """Erreur récupérable : on passe au modèle suivant de la chaîne de repli."""


class QuotaError(ProviderError):
    """Quota / limite de débit atteint (HTTP 429)."""


@dataclass
class Completion:
    content: str
    tokens_in: int
    tokens_out: int


class Provider:
    name = "base"
    external = True
    price_in = 0.0   # € par million de tokens
    price_out = 0.0

    def available(self) -> bool:
        return True

    def chat(self, model: str, messages: list[dict], max_tokens: int) -> Completion:
        raise NotImplementedError

    def cost(self, tokens_in: int, tokens_out: int) -> float:
        return (tokens_in * self.price_in + tokens_out * self.price_out) / 1_000_000


class OpenAICompatible(Provider):
    def __init__(self, name: str, base_url: str, api_key: str | None, external: bool,
                 price_in: float, price_out: float, needs_key: bool, timeout: float = 120):
        self.name, self.base_url, self.api_key = name, base_url.rstrip("/"), api_key
        self.external, self.price_in, self.price_out = external, price_in, price_out
        self.needs_key, self.timeout = needs_key, timeout

    def available(self) -> bool:
        return bool(self.api_key) or not self.needs_key

    def chat(self, model: str, messages: list[dict], max_tokens: int) -> Completion:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name} injoignable : {type(e).__name__}") from None
        if r.status_code == 429:
            raise QuotaError(f"{self.name} : quota atteint (429)")
        if r.status_code >= 400:
            raise ProviderError(f"{self.name} : HTTP {r.status_code}")
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError(f"{self.name} : réponse inattendue") from None
        usage = data.get("usage") or {}
        tin = int(usage.get("prompt_tokens") or estimate_tokens(" ".join(m["content"] for m in messages)))
        tout = int(usage.get("completion_tokens") or estimate_tokens(content))
        return Completion(content, tin, tout)


class MockProvider(Provider):
    """Fournisseur scripté pour les tests et la démonstration hors ligne (aucun appel réseau)."""

    name = "mock"
    external = False

    def __init__(self, responder: Callable[[str, list[dict]], str] | None = None,
                 price_in: float = 0.0, price_out: float = 0.0, fail_with: Exception | None = None):
        self.responder = responder or (lambda model, msgs: '{"final": "Tâche traitée (réponse de démonstration)."}')
        self.price_in, self.price_out = price_in, price_out
        self.fail_with = fail_with
        self.calls: list[tuple[str, list[dict]]] = []

    def chat(self, model: str, messages: list[dict], max_tokens: int) -> Completion:
        self.calls.append((model, [dict(m) for m in messages]))
        if self.fail_with:
            raise self.fail_with
        content = self.responder(model, messages)
        return Completion(content, estimate_tokens(" ".join(m["content"] for m in messages)), estimate_tokens(content))


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
