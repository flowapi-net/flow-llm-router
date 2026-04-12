"""Unit tests for data layer: models and engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from flowgate.db.models import ProviderKey, RequestLog, VaultMeta


# ════════════════════════════════════════════════════════════════
# RequestLog Tests
# ════════════════════════════════════════════════════════════════


class TestRequestLog:
    def test_create_minimal(self, db_session):
        log = RequestLog(
            model_requested="gpt-4o",
            model_used="gpt-4o",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.id is not None
        assert log.model_requested == "gpt-4o"
        assert log.status == "success"
        assert log.prompt_tokens == 0
        assert log.cost_usd == 0.0

    def test_create_full(self, db_session):
        now = datetime.now(timezone.utc)
        log = RequestLog(
            model_requested="claude-sonnet",
            model_used="claude-3-5-sonnet",
            provider="anthropic",
            messages='[{"role":"user","content":"hello"}]',
            temperature=0.7,
            max_tokens=1000,
            stream=True,
            response_content="Hi there!",
            status="success",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            cost_usd=0.00023,
            latency_ms=350,
            ttft_ms=120,
            session_id="sess-abc",
            user_tag="test-user",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.provider == "anthropic"
        assert log.total_tokens == 15
        assert log.cost_usd == pytest.approx(0.00023)
        assert log.session_id == "sess-abc"

    def test_uuid_auto_generated(self, db_session):
        log1 = RequestLog(model_requested="m1", model_used="m1")
        log2 = RequestLog(model_requested="m2", model_used="m2")
        db_session.add(log1)
        db_session.add(log2)
        db_session.commit()
        assert log1.id != log2.id

    def test_created_at_auto_set(self, db_session):
        log = RequestLog(model_requested="gpt-4o", model_used="gpt-4o")
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        assert log.created_at is not None
        assert isinstance(log.created_at, datetime)

    def test_query_by_model(self, db_session):
        for model in ["gpt-4o", "gpt-4o", "claude-sonnet"]:
            db_session.add(RequestLog(model_requested=model, model_used=model))
        db_session.commit()

        gpt_logs = db_session.exec(
            select(RequestLog).where(RequestLog.model_used == "gpt-4o")
        ).all()
        assert len(gpt_logs) == 2

    def test_error_status(self, db_session):
        log = RequestLog(
            model_requested="gpt-4o",
            model_used="gpt-4o",
            status="error",
            error_message="Connection timeout",
        )
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)

        assert log.status == "error"
        assert log.error_message == "Connection timeout"


# ════════════════════════════════════════════════════════════════
# VaultMeta Tests
# ════════════════════════════════════════════════════════════════


class TestVaultMeta:
    def test_create(self, db_session):
        meta = VaultMeta(
            id=1,
            salt="base64salt==",
            password_hash="abc123hash",
        )
        db_session.add(meta)
        db_session.commit()

        found = db_session.get(VaultMeta, 1)
        assert found is not None
        assert found.salt == "base64salt=="
        assert found.password_hash == "abc123hash"

    def test_singleton_id(self, db_session):
        """VaultMeta always uses id=1 (single row design)."""
        meta = VaultMeta(id=1, salt="s", password_hash="h")
        db_session.add(meta)
        db_session.commit()

        result = db_session.get(VaultMeta, 1)
        assert result.id == 1

    def test_created_at_auto(self, db_session):
        meta = VaultMeta(id=1, salt="s", password_hash="h")
        db_session.add(meta)
        db_session.commit()
        db_session.refresh(meta)
        assert isinstance(meta.created_at, datetime)


# ════════════════════════════════════════════════════════════════
# ProviderKey Tests
# ════════════════════════════════════════════════════════════════


class TestProviderKey:
    def test_create(self, db_session):
        now = datetime.now(timezone.utc)
        pk = ProviderKey(
            provider="openai",
            key_name="Production",
            encrypted_key="fernet-encrypted-blob",
            key_suffix="abcd",
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        db_session.add(pk)
        db_session.commit()
        db_session.refresh(pk)

        assert pk.id is not None
        assert pk.provider == "openai"
        assert pk.key_name == "Production"
        assert pk.key_suffix == "abcd"

    def test_uuid_auto_generated(self, db_session):
        now = datetime.now(timezone.utc)
        pk1 = ProviderKey(
            provider="openai", key_name="K1", encrypted_key="ct1",
            key_suffix="1111", created_at=now, updated_at=now,
        )
        pk2 = ProviderKey(
            provider="anthropic", key_name="K2", encrypted_key="ct2",
            key_suffix="2222", created_at=now, updated_at=now,
        )
        db_session.add(pk1)
        db_session.add(pk2)
        db_session.commit()
        assert pk1.id != pk2.id

    def test_filter_enabled(self, db_session):
        now = datetime.now(timezone.utc)
        for provider, enabled in [("openai", True), ("anthropic", False), ("google", True)]:
            db_session.add(ProviderKey(
                provider=provider, key_name=provider, encrypted_key="ct",
                key_suffix="xxxx", enabled=enabled, created_at=now, updated_at=now,
            ))
        db_session.commit()

        enabled_keys = db_session.exec(
            select(ProviderKey).where(ProviderKey.enabled == True)  # noqa: E712
        ).all()
        assert len(enabled_keys) == 2
        assert all(k.enabled for k in enabled_keys)

    def test_query_by_provider(self, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(ProviderKey(
            provider="openai", key_name="key1", encrypted_key="ct",
            key_suffix="xxxx", created_at=now, updated_at=now,
        ))
        db_session.commit()

        results = db_session.exec(
            select(ProviderKey).where(ProviderKey.provider == "openai")
        ).all()
        assert len(results) == 1
        assert results[0].provider == "openai"

    def test_extra_config_optional(self, db_session):
        now = datetime.now(timezone.utc)
        pk = ProviderKey(
            provider="azure", key_name="AZ", encrypted_key="ct",
            key_suffix="zzzz", created_at=now, updated_at=now,
        )
        db_session.add(pk)
        db_session.commit()
        db_session.refresh(pk)
        assert pk.extra_config is None
