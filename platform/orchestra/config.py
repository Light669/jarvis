"""Chargement et validation de config.yaml (schéma pydantic)."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class PathsCfg(BaseModel):
    vault: str = "Cerveau"
    data: str = "data"
    logs: str = "logs"


class BudgetCfg(BaseModel):
    monthly_eur: float = Field(100.0, gt=0)
    alert_ratio: float = Field(0.8, gt=0, lt=1)
    default_agent_daily_eur: float = 0.5


class PromotionCfg(BaseModel):
    min_validated_tasks: int = 20
    min_success_rate: float = 0.85


class DemotionCfg(BaseModel):
    repeated_failures: int = 2


class HierarchyCfg(BaseModel):
    promotion: PromotionCfg = PromotionCfg()
    demotion: DemotionCfg = DemotionCfg()


class MessagingCfg(BaseModel):
    max_thread_depth: int = 20
    max_messages_per_agent_per_hour: int = 30
    escalation_hours: float = 24


class ImprovementCfg(BaseModel):
    rollback_window_tasks: int = 5
    rollback_min_drop: float = 0.15
    skill_min_success_rate: float = 0.6
    skill_unused_days: int = 30


class RuntimeCfg(BaseModel):
    prefer_docker: bool = True
    image: str = "orchestra-runtime:latest"
    cpus: float = 1.0
    memory: str = "512m"
    pids_limit: int = 128
    timeout_s: int = 120
    max_active_agents: int = 3
    max_steps_per_task: int = 8


class ProviderCfg(BaseModel):
    base_url: str
    api_key_env: str | None = None
    external: bool = True
    price_in_per_mtok_eur: float = 0.0
    price_out_per_mtok_eur: float = 0.0


class LlmCfg(BaseModel):
    default_model: str = "ollama/qwen2.5:7b"
    fallback_chain: list[str] = []
    max_output_tokens: int = 1024
    providers: dict[str, ProviderCfg] = {}


class EmailCfg(BaseModel):
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    from_addr: str = ""
    to_addr: str = ""
    password_env: str = "SMTP_PASSWORD"


class AlertsCfg(BaseModel):
    windows_toast: bool = True
    email: EmailCfg = EmailCfg()


class Config(BaseModel):
    server: ServerCfg = ServerCfg()
    paths: PathsCfg = PathsCfg()
    budget: BudgetCfg = BudgetCfg()
    hierarchy: HierarchyCfg = HierarchyCfg()
    messaging: MessagingCfg = MessagingCfg()
    improvement: ImprovementCfg = ImprovementCfg()
    runtime: RuntimeCfg = RuntimeCfg()
    llm: LlmCfg = LlmCfg()
    alerts: AlertsCfg = AlertsCfg()


def load_config(root: Path) -> Config:
    path = Path(root) / "config.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    cfg = Config.model_validate(data or {})
    if cfg.server.host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("server.host doit rester local (127.0.0.1) : exposition réseau interdite")
    return cfg


def load_env(root: Path) -> dict[str, str]:
    """Lit .env (KEY=VALUE) sans l'injecter dans les logs."""
    env: dict[str, str] = {}
    path = Path(root) / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env
