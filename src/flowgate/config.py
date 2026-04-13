"""Configuration management with YAML file + environment variable support."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 7798


@dataclass
class SmartRouterConfig:
    enabled: bool = False
    strategy: str = "complexity"  # "complexity" | "classifier" | "off"
    tiers: dict[str, str] = field(default_factory=lambda: {
        "SIMPLE": "gpt-4o-mini",
        "MEDIUM": "gpt-4o",
        "COMPLEX": "claude-sonnet",
        "REASONING": "o1-preview",
    })
    tier_boundaries: dict[str, float] = field(default_factory=lambda: {
        "simple_medium": 0.25,
        "medium_complex": 0.50,
        "complex_reasoning": 0.75,
    })
    dimension_weights: dict[str, float] = field(default_factory=lambda: {
        "tokenCount": 0.15,
        "codePresence": 0.20,
        "reasoningMarkers": 0.25,
        "technicalTerms": 0.15,
        "simpleIndicators": 0.15,
        "multiStepPatterns": 0.05,
        "questionComplexity": 0.05,
    })
    # RouteLLM classifier settings
    classifier_type: str = "bert"
    # Tier boundaries for the classifier score (0–1).
    # Calibrated against BERT router's observed score distribution (~0.18–0.57).
    # The same 4-tier model mapping from `tiers` is reused.
    classifier_tier_boundaries: dict[str, float] = field(default_factory=lambda: {
        "simple_medium": 0.28,
        "medium_complex": 0.40,
        "complex_reasoning": 0.50,
    })
    # MF router embedding settings (only used when classifier_type == "mf").
    # FlowGate monkey-patches routellm.routers.similarity_weighted.utils.OPENAI_CLIENT
    # with a custom OpenAI client so no RouteLLM source changes are needed.
    mf_embedding_base_url: str = ""   # empty → use OPENAI_BASE_URL env or OpenAI default
    mf_embedding_api_key: str = ""    # empty → use OPENAI_API_KEY env
    # Model id from synced /api/models catalog (UI dropdown). Empty → MF uses text-embedding-3-small at runtime.
    mf_embedding_model: str = ""


@dataclass
class SkillsConfig:
    enabled: bool = False
    db_path: str = "./skills.chroma"


@dataclass
class DatabaseConfig:
    path: str = "./data.db"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_prompts: bool = True
    log_responses: bool = True
    redact_secrets: bool = True


@dataclass
class IPWhitelistConfig:
    enabled: bool = True
    mode: str = "local_only"  # local_only | whitelist | open
    allowed_ips: list[str] = field(default_factory=lambda: ["127.0.0.1", "::1"])


@dataclass
class SecurityConfig:
    vault_enabled: bool = True
    ip_whitelist: IPWhitelistConfig = field(default_factory=IPWhitelistConfig)
    auth_token_ttl_minutes: int = 60
    master_key_path: str = "~/.flowgate/master.key"


@dataclass
class Settings:
    server: ServerConfig = field(default_factory=ServerConfig)
    smart_router: SmartRouterConfig = field(default_factory=SmartRouterConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def _resolve_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} patterns with actual environment variable values."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_key = value[2:-1]
        return os.environ.get(env_key, "")
    return value


def _process_dict(d: dict) -> dict:
    """Recursively resolve env vars in a dict."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _process_dict(v)
        elif isinstance(v, str):
            result[k] = _resolve_env_vars(v)
        else:
            result[k] = v
    return result


def load_settings(config_path: str | None = None) -> Settings:
    """Load settings from YAML file, falling back to defaults.

    Priority: environment variables > YAML file > defaults.
    """
    raw: dict = {}

    search_paths = [
        Path(config_path) if config_path else None,
        Path.cwd() / "flowgate.yaml",
        Path.cwd() / "flowgate.yml",
    ]

    for p in search_paths:
        if p and p.exists():
            with open(p) as f:
                raw = yaml.safe_load(f) or {}
            raw = _process_dict(raw)
            break

    settings = Settings()

    if "server" in raw:
        settings.server = ServerConfig(**{
            k: v for k, v in raw["server"].items()
            if k in ("host", "port")
        })

    if "smart_router" in raw:
        sr = raw["smart_router"]
        settings.smart_router = SmartRouterConfig(
            enabled=sr.get("enabled", False),
            strategy=sr.get("strategy", "complexity"),
            tiers=sr.get("tiers", settings.smart_router.tiers),
            tier_boundaries=sr.get("tier_boundaries", settings.smart_router.tier_boundaries),
            dimension_weights=sr.get("dimension_weights", settings.smart_router.dimension_weights),
            classifier_type=sr.get("classifier_type", "bert"),
            classifier_tier_boundaries=sr.get(
                "classifier_tier_boundaries",
                settings.smart_router.classifier_tier_boundaries,
            ),
            mf_embedding_base_url=sr.get("mf_embedding_base_url", settings.smart_router.mf_embedding_base_url),
            mf_embedding_api_key=sr.get("mf_embedding_api_key", settings.smart_router.mf_embedding_api_key),
            mf_embedding_model=sr.get("mf_embedding_model", settings.smart_router.mf_embedding_model),
        )

    if "skills" in raw:
        settings.skills = SkillsConfig(**{
            k: v for k, v in raw["skills"].items()
            if k in ("enabled", "db_path")
        })

    if "database" in raw:
        settings.database = DatabaseConfig(**{
            k: v for k, v in raw["database"].items()
            if k in ("path",)
        })

    if "logging" in raw:
        settings.logging = LoggingConfig(**{
            k: v for k, v in raw["logging"].items()
            if k in ("level", "log_prompts", "log_responses", "redact_secrets")
        })

    if "security" in raw:
        sec = raw["security"]
        ip_cfg = sec.get("ip_whitelist", {})
        settings.security = SecurityConfig(
            vault_enabled=sec.get("vault_enabled", True),
            auth_token_ttl_minutes=sec.get("auth_token_ttl_minutes", 60),
            master_key_path=sec.get("master_key_path", "~/.flowgate/master.key"),
            ip_whitelist=IPWhitelistConfig(
                enabled=ip_cfg.get("enabled", True),
                mode=ip_cfg.get("mode", "local_only"),
                allowed_ips=ip_cfg.get("allowed_ips", ["127.0.0.1", "::1"]),
            ),
        )

    return settings
