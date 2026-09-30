"""LLM Gateway : un seul point d'appel des modèles, repli automatique, coûts et plafond."""
from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass

from orchestra.gateway.providers import Completion, OpenAICompatible, Provider, ProviderError, estimate_tokens
from orchestra.models import BudgetExceeded, EmergencyStop

_POOL = cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="llm")


@dataclass
class ChatResult:
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_eur: float
    fallbacks: int


class LLMGateway:
    def __init__(self, p):
        self.p = p
        self.providers: dict[str, Provider] = {}
        for name, pc in p.cfg.llm.providers.items():
            key = p.env.get(pc.api_key_env) if pc.api_key_env else None
            self.providers[name] = OpenAICompatible(name, pc.base_url, key, pc.external,
                                                    pc.price_in_per_mtok_eur, pc.price_out_per_mtok_eur,
                                                    needs_key=bool(pc.api_key_env))

    def register(self, provider: Provider) -> None:
        self.providers[provider.name] = provider

    def chain_for(self, agent: dict | None) -> list[str]:
        chain = []
        for m in ([agent["modele"]] if agent and agent.get("modele") else []) + [self.p.cfg.llm.default_model] + list(self.p.cfg.llm.fallback_chain):
            if m and m not in chain:
                chain.append(m)
        return chain

    def chat(self, agent: dict | None, messages: list[dict], correlation_id: str | None = None,
             max_tokens: int | None = None) -> ChatResult:
        max_tokens = max_tokens or self.p.cfg.llm.max_output_tokens
        agent_id = agent["id"] if agent else None
        niveau = agent["niveau"] if agent else "systeme"
        errors: list[str] = []
        for i, spec in enumerate(self.chain_for(agent)):
            if self.p.emergency.active:
                raise EmergencyStop("arrêt d'urgence : appels de modèles suspendus")
            pname, _, model = spec.partition("/")
            prov = self.providers.get(pname)
            if not prov or not prov.available():
                errors.append(f"{spec}: non configuré")
                continue
            estimate = prov.cost(estimate_tokens(" ".join(m["content"] for m in messages)), max_tokens)
            try:
                self.p.budget.check(agent, estimate)
            except BudgetExceeded as e:
                errors.append(f"{spec}: {e}")
                self.p.audit.record("budget", "appel_refuse", agent_id=agent_id, niveau=niveau, cible=spec,
                                    resultat=str(e), gravite="attention", correlation_id=correlation_id)
                continue
            try:
                comp = self._call_abortable(prov, model, messages, max_tokens)
            except ProviderError as e:
                errors.append(f"{spec}: {e}")
                self.p.audit.record("modele", "repli", agent_id=agent_id, niveau=niveau, cible=spec, resultat=str(e),
                                    gravite="attention", correlation_id=correlation_id)
                continue
            cost = prov.cost(comp.tokens_in, comp.tokens_out)
            self.p.budget.record_llm(agent_id, spec, comp.tokens_in, comp.tokens_out, cost, correlation_id)
            self.p.audit.record("modele", "appel_modele", agent_id=agent_id, niveau=niveau, cible=spec,
                                cout_tokens=comp.tokens_in + comp.tokens_out, cout_eur=cost, correlation_id=correlation_id,
                                details={"tokens_in": comp.tokens_in, "tokens_out": comp.tokens_out, "replis": i})
            return ChatResult(comp.content, spec, comp.tokens_in, comp.tokens_out, cost, len(errors))
        if any("plafond" in e or "budget" in e or "enveloppe" in e for e in errors):
            raise BudgetExceeded("aucun modèle utilisable dans le budget : " + " | ".join(errors))
        self.p.alerts.raise_("modeles_indisponibles", "Aucun modèle disponible : " + " | ".join(errors)[:400],
                             gravite="grave", agent_id=agent_id)
        raise ProviderError("aucun modèle disponible : " + " | ".join(errors))

    def _call_abortable(self, prov: Provider, model: str, messages: list[dict], max_tokens: int) -> Completion:
        """Exécute l'appel dans un thread et l'abandonne dès que l'arrêt d'urgence est déclenché."""
        fut = _POOL.submit(prov.chat, model, messages, max_tokens)
        while True:
            try:
                return fut.result(timeout=0.1)
            except cf.TimeoutError:
                if self.p.emergency.active:
                    fut.cancel()
                    raise EmergencyStop("arrêt d'urgence pendant l'appel au modèle")
