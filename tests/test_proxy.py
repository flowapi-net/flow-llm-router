"""Integration tests for the proxy endpoint (/v1/chat/completions).

LiteLLM is fully mocked — no real HTTP calls are made.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import select

from flowgate.db.engine import get_session
from flowgate.db.models import RequestLog


# ── LiteLLM Mock Factories ────────────────────────────────────────────────────


def _make_litellm_response(
    content: str = "Hello!",
    model: str = "gpt-4o",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> MagicMock:
    """Build a mock non-streaming LiteLLM response."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    response.model = model
    response._hidden_params = {"response_cost": 0.0003, "custom_llm_provider": "openai"}
    response.model_dump.return_value = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}, "index": 0}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return response


async def _stream_chunks(content: str = "Hello!"):
    """Async generator yielding mock SSE chunks."""
    words = content.split()
    for i, word in enumerate(words):
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = word + (" " if i < len(words) - 1 else "")
        chunk.usage = None
        chunk._hidden_params = {"custom_llm_provider": "openai"}
        chunk.model = "gpt-4o"
        chunk.model_dump_json.return_value = json.dumps({
            "id": "chunk-test",
            "choices": [{"delta": {"content": word}, "index": 0}],
        })
        yield chunk

    # Final chunk with usage
    final = MagicMock()
    final.choices = []
    final.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    final._hidden_params = {"response_cost": 0.0003, "custom_llm_provider": "openai"}
    final.model = "gpt-4o"
    final.model_dump_json.return_value = json.dumps({"id": "chunk-final", "choices": []})
    yield final


# ════════════════════════════════════════════════════════════════
# Non-streaming Tests
# ════════════════════════════════════════════════════════════════


class TestProxyNonStream:
    async def test_basic_completion(self, client):
        mock_response = _make_litellm_response("The answer is 42.")
        with patch("flowgate.proxy.router.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            resp = await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "What is the answer?"}],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "The answer is 42."

    async def test_optional_params_forwarded(self, client):
        mock_response = _make_litellm_response()
        captured = {}

        async def capture_call(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("flowgate.proxy.router.litellm.acompletion", new=capture_call):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0.5,
                "max_tokens": 100,
            })

        assert captured.get("temperature") == 0.5
        assert captured.get("max_tokens") == 100

    async def test_error_returns_500(self, client):
        with patch(
            "flowgate.proxy.router.litellm.acompletion",
            new=AsyncMock(side_effect=Exception("API Error")),
        ):
            resp = await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
            })

        assert resp.status_code == 500
        assert "error" in resp.json()

    async def test_logs_to_db_on_success(self, client, test_settings):
        mock_response = _make_litellm_response("Success response")
        with patch("flowgate.proxy.router.litellm.acompletion", new=AsyncMock(return_value=mock_response)):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "log me"}],
            })

        session = get_session(test_settings.database.path)
        try:
            logs = session.exec(select(RequestLog)).all()
            assert len(logs) == 1
            assert logs[0].model_requested == "gpt-4o"
            assert logs[0].status == "success"
            assert logs[0].prompt_tokens == 10
        finally:
            session.close()

    async def test_logs_error_to_db(self, client, test_settings):
        with patch(
            "flowgate.proxy.router.litellm.acompletion",
            new=AsyncMock(side_effect=Exception("Timeout")),
        ):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "fail"}],
            })

        session = get_session(test_settings.database.path)
        try:
            logs = session.exec(select(RequestLog)).all()
            assert any(l.status == "error" for l in logs)
            error_log = next(l for l in logs if l.status == "error")
            assert "Timeout" in error_log.error_message
        finally:
            session.close()

    async def test_vault_api_key_passed_to_litellm(self, client):
        """When vault has a key for a provider, it must be passed as api_key."""
        mock_response = _make_litellm_response()
        captured = {}

        async def capture_call(**kwargs):
            captured.update(kwargs)
            return mock_response

        # Set up vault with an openai key
        setup_resp = await client.post("/api/auth/setup", json={"password": "pass"})
        assert setup_resp.status_code == 200
        verify_resp = await client.post("/api/auth/verify", json={"password": "pass"})
        token = verify_resp.json()["token"]
        await client.post(
            "/api/keys",
            json={"provider": "openai", "key_name": "Prod", "api_key": "sk-testvaultkey123456"},
            headers={"Authorization": f"Bearer {token}"},
        )

        with patch("flowgate.proxy.router.litellm.acompletion", new=capture_call):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
            })

        assert captured.get("api_key") == "sk-testvaultkey123456"

    async def test_no_api_key_when_vault_not_initialized(self, client):
        """When vault is not initialized, api_key should NOT be passed."""
        mock_response = _make_litellm_response()
        captured = {}

        async def capture_call(**kwargs):
            captured.update(kwargs)
            return mock_response

        with patch("flowgate.proxy.router.litellm.acompletion", new=capture_call):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
            })

        assert "api_key" not in captured


# ════════════════════════════════════════════════════════════════
# Streaming Tests
# ════════════════════════════════════════════════════════════════


class TestProxyStream:
    async def test_stream_returns_sse(self, client):
        with patch(
            "flowgate.proxy.streaming.litellm.acompletion",
            new=AsyncMock(return_value=_stream_chunks("Hello world")),
        ):
            resp = await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            })

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        assert "data:" in resp.text
        assert "[DONE]" in resp.text

    async def test_stream_logs_to_db(self, client, test_settings):
        with patch(
            "flowgate.proxy.streaming.litellm.acompletion",
            new=AsyncMock(return_value=_stream_chunks("Streamed response")),
        ):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "stream me"}],
                "stream": True,
            })

        session = get_session(test_settings.database.path)
        try:
            logs = session.exec(select(RequestLog)).all()
            assert len(logs) == 1
            assert logs[0].stream is True
        finally:
            session.close()

    async def test_stream_api_key_passed(self, client):
        """Streaming path also passes api_key from vault."""
        captured = {}

        async def capture_call(**kwargs):
            captured.update(kwargs)
            return _stream_chunks("ok")

        await client.post("/api/auth/setup", json={"password": "pass"})
        verify_resp = await client.post("/api/auth/verify", json={"password": "pass"})
        token = verify_resp.json()["token"]
        await client.post(
            "/api/keys",
            json={"provider": "openai", "key_name": "P", "api_key": "sk-streamkey12345678"},
            headers={"Authorization": f"Bearer {token}"},
        )

        with patch("flowgate.proxy.streaming.litellm.acompletion", new=capture_call):
            await client.post("/v1/chat/completions", json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": "stream"}],
                "stream": True,
            })

        assert captured.get("api_key") == "sk-streamkey12345678"


# ════════════════════════════════════════════════════════════════
# Models List
# ════════════════════════════════════════════════════════════════


class TestModelsList:
    async def test_get_models(self, client):
        resp = await client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) > 0
        models = [m["id"] for m in data["data"]]
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models


# ════════════════════════════════════════════════════════════════
# Provider Inference
# ════════════════════════════════════════════════════════════════


class TestProviderInference:
    def test_infer_openai(self):
        from flowgate.proxy.router import _infer_provider
        assert _infer_provider("gpt-4o") == "openai"
        assert _infer_provider("gpt-4o-mini") == "openai"
        assert _infer_provider("o1-preview") == "openai"

    def test_infer_anthropic(self):
        from flowgate.proxy.router import _infer_provider
        assert _infer_provider("claude-sonnet") == "anthropic"
        assert _infer_provider("claude-3-5-sonnet") == "anthropic"

    def test_infer_google(self):
        from flowgate.proxy.router import _infer_provider
        assert _infer_provider("gemini-pro") == "google"

    def test_infer_slash_format(self):
        from flowgate.proxy.router import _infer_provider
        assert _infer_provider("azure/gpt-4") == "azure"

    def test_infer_unknown(self):
        from flowgate.proxy.router import _infer_provider
        assert _infer_provider("unknown-model") == ""
