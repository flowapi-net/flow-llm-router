"""Tests for router-managed search providers."""

from __future__ import annotations

from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from flow_llm_router.app import create_app
from flow_llm_router.db.engine import init_db


async def test_search_provider_crud_returns_only_masked_key(authed_client):
    plaintext = "tvly-test-secret-1234567890"
    create_resp = await authed_client.post(
        "/api/search/providers",
        json={
            "provider": "tavily",
            "key_name": "Tavily main",
            "api_key": plaintext,
        },
    )
    assert create_resp.status_code == 201
    assert plaintext not in create_resp.text
    created = create_resp.json()
    assert created["provider"] == "tavily"
    assert created["enabled"] is True
    assert created["key_masked"].endswith("7890")

    list_resp = await authed_client.get("/api/search/providers")
    assert list_resp.status_code == 200
    assert plaintext not in list_resp.text
    assert list_resp.json()[0]["key_masked"].endswith("7890")

    update_resp = await authed_client.put(
        f"/api/search/providers/{created['id']}",
        json={"enabled": False},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["enabled"] is False

    delete_resp = await authed_client.delete(f"/api/search/providers/{created['id']}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    list_after_delete = await authed_client.get("/api/search/providers")
    assert list_after_delete.json() == []


async def test_search_provider_management_requires_unlocked_vault(test_settings):
    init_db(test_settings.database.path)
    app = create_app(settings=test_settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post("/api/auth/setup", json={"password": "testpass123"})
        token_resp = await client.post("/api/auth/verify", json={"password": "testpass123"})
        token = token_resp.json()["token"]
        app.state.vault.lock()

        resp = await client.post(
            "/api/search/providers",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "provider": "tavily",
                "key_name": "Locked",
                "api_key": "tvly-locked",
            },
        )
        assert resp.status_code == 423


async def test_search_tavily_requires_caller_token(client):
    resp = await client.post("/api/search/tavily", json={"query": "hello"})
    assert resp.status_code == 401


async def test_search_tavily_uses_vault_key_not_body_api_key(authed_client, monkeypatch):
    stored_key = "tvly-real-vault-key"
    add_resp = await authed_client.post(
        "/api/search/providers",
        json={
            "provider": "tavily",
            "key_name": "Tavily",
            "api_key": stored_key,
        },
    )
    assert add_resp.status_code == 201

    token_resp = await authed_client.post("/api/caller-tokens", json={"name": "lumi-go"})
    caller_token = token_resp.json()["token"]
    captured = {}

    async def fake_call(api_key, base_url, body):
        captured["api_key"] = api_key
        captured["body_api_key"] = body.api_key
        captured["query"] = body.query
        captured["max_results"] = body.max_results
        return {
            "results": [
                {
                    "title": "Router result",
                    "url": "https://example.com",
                    "content": "snippet",
                }
            ]
        }

    monkeypatch.setattr("flow_llm_router.api.search._call_tavily", fake_call)

    resp = await authed_client.post(
        "/api/search/tavily",
        headers={"Authorization": f"Bearer {caller_token}"},
        json={
            "api_key": "body-token-that-is-not-tavily",
            "query": "router search",
            "max_results": 4,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["results"][0]["title"] == "Router result"
    assert captured["api_key"] == stored_key
    assert captured["body_api_key"] == "body-token-that-is-not-tavily"
    assert captured["query"] == "router search"
    assert captured["max_results"] == 4


async def test_search_tavily_accepts_caller_token_in_body(authed_client, monkeypatch):
    await authed_client.post(
        "/api/search/providers",
        json={
            "provider": "tavily",
            "key_name": "Tavily",
            "api_key": "tvly-real-vault-key",
        },
    )
    token_resp = await authed_client.post("/api/caller-tokens", json={"name": "lumi-go"})
    caller_token = token_resp.json()["token"]

    async def fake_call(api_key, base_url, body):
        return {"results": [{"title": "Body token result", "url": "https://example.com"}]}

    monkeypatch.setattr("flow_llm_router.api.search._call_tavily", fake_call)

    resp = await authed_client.post(
        "/api/search/tavily",
        headers={"Authorization": ""},
        json={"api_key": caller_token, "query": "router search"},
    )

    assert resp.status_code == 200
    assert resp.json()["results"][0]["title"] == "Body token result"


async def test_search_tavily_locked_vault_returns_423(test_settings):
    init_db(test_settings.database.path)
    app = create_app(settings=test_settings)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        await client.post("/api/auth/setup", json={"password": "testpass123"})
        token_resp = await client.post("/api/auth/verify", json={"password": "testpass123"})
        admin_token = token_resp.json()["token"]
        add_resp = await client.post(
            "/api/search/providers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"provider": "tavily", "key_name": "Tavily", "api_key": "tvly-real"},
        )
        assert add_resp.status_code == 201
        caller_resp = await client.post(
            "/api/caller-tokens",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "lumi-go"},
        )
        caller_token = caller_resp.json()["token"]
        app.state.vault.lock()

        resp = await client.post(
            "/api/search/tavily",
            headers={"Authorization": f"Bearer {caller_token}"},
            json={"query": "hello"},
        )
        assert resp.status_code == 423


async def test_search_tavily_upstream_error_redacts_key(authed_client, monkeypatch):
    stored_key = "tvly-secret-redact-key"
    await authed_client.post(
        "/api/search/providers",
        json={
            "provider": "tavily",
            "key_name": "Tavily",
            "api_key": stored_key,
        },
    )
    token_resp = await authed_client.post("/api/caller-tokens", json={"name": "lumi-go"})
    caller_token = token_resp.json()["token"]

    async def fake_call(api_key, base_url, body):
        raise HTTPException(status_code=502, detail=f"Tavily returned 401: bad key {api_key}")

    monkeypatch.setattr("flow_llm_router.api.search._call_tavily", fake_call)

    resp = await authed_client.post(
        "/api/search/tavily",
        headers={"Authorization": f"Bearer {caller_token}"},
        json={"query": "router search"},
    )

    assert resp.status_code == 502
    assert stored_key not in resp.text
