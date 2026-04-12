"""Integration tests for Auth, Keys, and Dashboard APIs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from flowgate.db.models import RequestLog


# ════════════════════════════════════════════════════════════════
# Auth API (/api/auth)
# ════════════════════════════════════════════════════════════════


class TestAuthStatus:
    async def test_no_vault_initially(self, client):
        resp = await client.get("/api/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vault_initialized"] is False
        assert data["vault_unlocked"] is False

    async def test_status_after_setup(self, client):
        await client.post("/api/auth/setup", json={"password": "pass1234"})
        resp = await client.get("/api/auth/status")
        data = resp.json()
        assert data["vault_initialized"] is True

    async def test_status_after_verify(self, authed_client):
        resp = await authed_client.get("/api/auth/status")
        data = resp.json()
        assert data["vault_initialized"] is True
        assert data["vault_unlocked"] is True


class TestAuthSetup:
    async def test_setup_success(self, client):
        resp = await client.post("/api/auth/setup", json={"password": "mypassword"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

    async def test_setup_duplicate_returns_409(self, client):
        await client.post("/api/auth/setup", json={"password": "first"})
        resp = await client.post("/api/auth/setup", json={"password": "second"})
        assert resp.status_code == 409

    async def test_setup_unlocks_vault(self, client):
        await client.post("/api/auth/setup", json={"password": "pass"})
        status = await client.get("/api/auth/status")
        # After setup vault is unlocked (setup also calls initialize)
        assert status.json()["vault_unlocked"] is True


class TestAuthVerify:
    async def test_verify_correct_password(self, client):
        await client.post("/api/auth/setup", json={"password": "correct"})
        resp = await client.post("/api/auth/verify", json={"password": "correct"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "token" in data
        assert len(data["token"]) > 10

    async def test_verify_wrong_password(self, client):
        await client.post("/api/auth/setup", json={"password": "correct"})
        resp = await client.post("/api/auth/verify", json={"password": "wrong"})
        assert resp.status_code == 403

    async def test_verify_no_vault_404(self, client):
        resp = await client.post("/api/auth/verify", json={"password": "any"})
        assert resp.status_code == 404

    async def test_token_in_response(self, client):
        await client.post("/api/auth/setup", json={"password": "pass"})
        resp = await client.post("/api/auth/verify", json={"password": "pass"})
        data = resp.json()
        assert isinstance(data["token"], str)
        assert isinstance(data["expires_in"], int)
        assert data["expires_in"] > 0


# ════════════════════════════════════════════════════════════════
# Provider Keys API (/api/keys)
# ════════════════════════════════════════════════════════════════


class TestKeysRead:
    async def test_list_empty(self, client):
        resp = await client.get("/api/keys")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_shows_keys_after_add(self, authed_client):
        await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "Prod",
            "api_key": "sk-proj-test1234567890abcdef",
        })
        resp = await authed_client.get("/api/keys")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["provider"] == "openai"


class TestKeysAdd:
    async def test_add_requires_auth(self, client):
        resp = await client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "Test",
            "api_key": "sk-test",
        })
        assert resp.status_code == 401

    async def test_add_success(self, authed_client):
        resp = await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "Production",
            "api_key": "sk-proj-test1234567890abcdef",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["provider"] == "openai"
        assert data["key_name"] == "Production"
        assert data["enabled"] is True

    async def test_add_returns_masked_key(self, authed_client):
        resp = await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "Prod",
            "api_key": "sk-proj-test1234567890abcdef",
        })
        data = resp.json()
        # Plaintext must never appear in response
        assert "sk-proj-test1234567890abcdef" not in str(data)
        assert "key_masked" in data
        assert "..." in data["key_masked"]

    async def test_add_multiple_providers(self, authed_client):
        for provider, key in [
            ("openai", "sk-openai-key1234567890abcdef"),
            ("anthropic", "sk-ant-key1234567890abcdef"),
        ]:
            resp = await authed_client.post("/api/keys", json={
                "provider": provider,
                "key_name": f"{provider}-key",
                "api_key": key,
            })
            assert resp.status_code == 201

        resp = await authed_client.get("/api/keys")
        assert len(resp.json()) == 2


class TestKeysDelete:
    async def test_delete_requires_auth(self, client):
        # No Authorization header → should be rejected immediately
        resp = await client.delete("/api/keys/any-fake-id")
        assert resp.status_code == 401

    async def test_delete_success(self, authed_client):
        add_resp = await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "ToDelete",
            "api_key": "sk-delete1234567890abcdef",
        })
        key_id = add_resp.json()["id"]

        del_resp = await authed_client.delete(f"/api/keys/{key_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True

        list_resp = await authed_client.get("/api/keys")
        assert len(list_resp.json()) == 0

    async def test_delete_not_found(self, authed_client):
        resp = await authed_client.delete("/api/keys/nonexistent-uuid")
        assert resp.status_code == 404


class TestKeysUpdate:
    async def test_update_enabled_requires_auth(self, client):
        # No Authorization header → should be rejected immediately
        resp = await client.put("/api/keys/any-fake-id", json={"enabled": False})
        assert resp.status_code == 401

    async def test_toggle_enabled(self, authed_client):
        add_resp = await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "Toggle",
            "api_key": "sk-toggle1234567890abcdef",
        })
        key_id = add_resp.json()["id"]

        resp = await authed_client.put(f"/api/keys/{key_id}", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_update_key_name(self, authed_client):
        add_resp = await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "OldName",
            "api_key": "sk-rename1234567890abcdef",
        })
        key_id = add_resp.json()["id"]

        resp = await authed_client.put(f"/api/keys/{key_id}", json={"key_name": "NewName"})
        assert resp.json()["key_name"] == "NewName"


class TestKeysPlaintextNeverReturned:
    async def test_plaintext_not_in_list(self, authed_client):
        plaintext = "sk-supersecretkey1234567890xyz"
        await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "Secret",
            "api_key": plaintext,
        })
        resp = await authed_client.get("/api/keys")
        assert plaintext not in resp.text

    async def test_plaintext_not_in_add_response(self, authed_client):
        plaintext = "sk-anothersecret1234567890abc"
        resp = await authed_client.post("/api/keys", json={
            "provider": "anthropic",
            "key_name": "Secret",
            "api_key": plaintext,
        })
        assert plaintext not in resp.text


# ════════════════════════════════════════════════════════════════
# Dashboard API (/api/stats, /api/logs)
# ════════════════════════════════════════════════════════════════


async def _insert_log(client, **overrides):
    """Helper: directly insert a RequestLog via the app state."""
    # We use the app's DB path to create a real log entry
    import flowgate.db.engine as eng
    from flowgate.db.engine import get_session

    session = get_session()
    defaults = dict(
        model_requested="gpt-4o",
        model_used="gpt-4o",
        provider="openai",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        cost_usd=0.001,
        latency_ms=300,
        status="success",
    )
    defaults.update(overrides)
    log = RequestLog(**defaults)
    try:
        session.add(log)
        session.commit()
    finally:
        session.close()
    return log


class TestHealth:
    async def test_health_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStatsOverview:
    async def test_empty_stats(self, client):
        resp = await client.get("/api/stats/overview?period=today")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_requests"] == 0
        assert data["total_cost_usd"] == 0.0
        assert data["success_rate"] == 100.0

    async def test_period_parameter(self, client):
        for period in ["today", "week", "month"]:
            resp = await client.get(f"/api/stats/overview?period={period}")
            assert resp.status_code == 200

    async def test_invalid_period_rejected(self, client):
        resp = await client.get("/api/stats/overview?period=year")
        assert resp.status_code == 422


class TestStatsTimeline:
    async def test_timeline_empty(self, client):
        resp = await client.get("/api/stats/timeline?granularity=hour&days=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    async def test_timeline_granularity_day(self, client):
        resp = await client.get("/api/stats/timeline?granularity=day&days=7")
        assert resp.status_code == 200

    async def test_timeline_invalid_granularity(self, client):
        resp = await client.get("/api/stats/timeline?granularity=minute")
        assert resp.status_code == 422


class TestStatsProviders:
    async def test_providers_empty(self, client):
        resp = await client.get("/api/stats/providers")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestLogs:
    async def test_logs_empty(self, client):
        resp = await client.get("/api/logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["meta"]["total"] == 0

    async def test_logs_pagination_defaults(self, client):
        resp = await client.get("/api/logs")
        meta = resp.json()["meta"]
        assert meta["page"] == 1
        assert meta["size"] == 50

    async def test_log_detail_not_found(self, client):
        resp = await client.get("/api/logs/nonexistent-id")
        assert resp.status_code == 404

    async def test_logs_pagination_params(self, client):
        resp = await client.get("/api/logs?page=2&size=10")
        assert resp.status_code == 200
        meta = resp.json()["meta"]
        assert meta["page"] == 2
        assert meta["size"] == 10


# ════════════════════════════════════════════════════════════════
# Token Auth Middleware
# ════════════════════════════════════════════════════════════════


class TestTokenAuthMiddleware:
    async def test_missing_token_401(self, client):
        # Setup vault first so vault is initialized
        await client.post("/api/auth/setup", json={"password": "pass"})
        resp = await client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "K",
            "api_key": "sk-test",
        })
        assert resp.status_code == 401

    async def test_invalid_token_401(self, client):
        await client.post("/api/auth/setup", json={"password": "pass"})
        resp = await client.post(
            "/api/keys",
            json={"provider": "openai", "key_name": "K", "api_key": "sk-test"},
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401

    async def test_valid_token_succeeds(self, authed_client):
        resp = await authed_client.post("/api/keys", json={
            "provider": "openai",
            "key_name": "K",
            "api_key": "sk-valid1234567890abcdef",
        })
        assert resp.status_code == 201
