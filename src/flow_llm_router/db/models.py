"""SQLModel data models for request logging and security vault."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─── Security Vault ───


class VaultMeta(SQLModel, table=True):
    """Single-row table holding the PBKDF2 salt and password verification hash."""

    __tablename__ = "vault_meta"

    id: int = Field(default=1, primary_key=True)
    salt: str  # Base64-encoded 16-byte PBKDF2 salt
    password_hash: str  # SHA-256 of master password (for verification only)
    created_at: datetime = Field(default_factory=_utcnow)


class ProviderKey(SQLModel, table=True):
    """Encrypted provider API key stored in SQLite."""

    __tablename__ = "provider_keys"

    id: str = Field(default_factory=_uuid, primary_key=True)
    provider: str = Field(index=True)  # openai / anthropic / google / azure …
    key_name: str  # user-defined label, e.g. "OpenAI Production"
    encrypted_key: str  # Fernet ciphertext (Base64)
    key_suffix: str  # last 4 chars of plaintext for display ("sk-...abcd")
    extra_config: Optional[str] = None  # JSON blob: api_base, api_version, etc.
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class CallerToken(SQLModel, table=True):
    """Access token issued to external services that call the proxy."""

    __tablename__ = "caller_tokens"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str                        # human label, e.g. "my-agent"
    token_prefix: str                # first 8 chars for display, e.g. "fgt_xxxx"
    token_hash: str                  # SHA-256 of full token
    enabled: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: Optional[datetime] = None


class ProviderModel(SQLModel, table=True):
    """A model discovered from a provider's /v1/models endpoint."""

    __tablename__ = "provider_models"

    id: str = Field(default_factory=_uuid, primary_key=True)
    provider: str = Field(index=True)   # e.g. "openai"
    model_id: str = Field(index=True)   # e.g. "gpt-4o"
    display_name: Optional[str] = None  # human-friendly label
    owned_by: Optional[str] = None      # from API response
    raw_created: Optional[int] = None   # unix timestamp from API
    synced_at: datetime = Field(default_factory=_utcnow)


class RouterConfig(SQLModel, table=True):
    """Singleton table storing smart router configuration (managed from the UI)."""

    __tablename__ = "router_config"

    id: int = Field(default=1, primary_key=True)
    enabled: bool = False
    strategy: str = "complexity"
    config_json: str = "{}"
    updated_at: datetime = Field(default_factory=_utcnow)


class RequestLog(SQLModel, table=True):
    __tablename__ = "request_logs"

    id: str = Field(default_factory=_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=_utcnow, index=True)

    # Request info
    model_requested: str
    model_used: str
    provider: str = ""
    messages: str = ""  # JSON-serialized messages array
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False

    # Routing info (Phase 2)
    complexity_score: Optional[float] = None
    complexity_tier: Optional[str] = None
    skills_injected: Optional[str] = None

    # Response info
    response_content: Optional[str] = None
    status: str = "success"
    error_message: Optional[str] = None

    # Token usage (cost_usd column retained for existing DBs; unused, always 0)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    # Performance
    latency_ms: int = 0
    ttft_ms: Optional[int] = None

    # Session tracking
    session_id: Optional[str] = None
    user_tag: Optional[str] = None
