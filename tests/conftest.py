"""Shared pytest fixtures for FlowGate tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, SQLModel, create_engine

from flowgate.app import create_app
from flowgate.config import (
    DatabaseConfig,
    IPWhitelistConfig,
    LoggingConfig,
    SecurityConfig,
    Settings,
)
from flowgate.security.vault import Vault


# ── In-Memory Database Fixtures ──────────────────────────────────────────────


@pytest.fixture()
def db_engine():
    """Per-test in-memory SQLite engine. Isolated from the real data.db."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """SQLModel session bound to the in-memory engine."""
    with Session(db_engine) as session:
        yield session


# ── Settings Fixture ──────────────────────────────────────────────────────────


@pytest.fixture()
def test_settings(tmp_path):
    """Settings with in-memory DB path and security enabled."""
    db_path = str(tmp_path / "test.db")
    return Settings(
        database=DatabaseConfig(path=db_path),
        logging=LoggingConfig(redact_secrets=True),
        security=SecurityConfig(
            vault_enabled=True,
            ip_whitelist=IPWhitelistConfig(enabled=False),  # disabled so tests can reach endpoints
        ),
    )


# ── FastAPI App & Clients ─────────────────────────────────────────────────────


@pytest_asyncio.fixture()
async def client(test_settings):
    """Async httpx client connected to a fresh FlowGate app instance.

    The DB engine is explicitly initialised here because httpx's ASGITransport
    does not trigger FastAPI's lifespan events.
    """
    import flowgate.db.engine as engine_module
    from flowgate.db.engine import init_db

    resolved = str(Path(test_settings.database.path).resolve())
    stale = engine_module._engines.pop(resolved, None)
    if stale is not None:
        stale.dispose()

    init_db(test_settings.database.path)

    app = create_app(settings=test_settings)

    from flowgate.smart_router.service import SmartRouterService
    app.state.smart_router_service = SmartRouterService(test_settings.smart_router)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    eng = engine_module._engines.pop(resolved, None)
    if eng is not None:
        eng.dispose()


@pytest_asyncio.fixture()
async def authed_client(client):
    """Client with master-password-authenticated Bearer token."""
    # Setup vault
    await client.post("/api/auth/setup", json={"password": "testpass123"})
    # Verify and get token
    resp = await client.post("/api/auth/verify", json={"password": "testpass123"})
    token = resp.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client


# ── Vault Fixture ─────────────────────────────────────────────────────────────


@pytest.fixture()
def vault():
    """Initialized Vault instance with master password 'test-master'."""
    v = Vault()
    v.initialize("test-master")
    return v


@pytest.fixture()
def vault_with_openai_key(vault):
    """Vault with one openai key pre-loaded in cache."""
    encrypted = vault.encrypt_key("sk-proj-test1234567890abcdef")
    vault.add_to_cache("openai", encrypted)
    return vault
