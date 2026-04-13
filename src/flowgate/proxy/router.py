"""OpenAI-compatible proxy endpoints."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import litellm
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import select

from flowgate.api.caller_tokens import validate_caller_token
from flowgate.config import LoggingConfig, Settings
from flowgate.db.engine import get_session
from flowgate.db.models import ProviderKey, ProviderModel, RequestLog
from flowgate.proxy.schemas import ChatCompletionRequest, EmbeddingRequest
from flowgate.proxy.streaming import stream_completion
from flowgate.security.redact import redact_secrets as _redact
from flowgate.smart_router.service import SmartRouterService

router = APIRouter()

# ─── Provider inference ───

_MODEL_PROVIDER_MAP: dict[str, str] = {
    "gpt":      "openai",
    "o1":       "openai",
    "o3":       "openai",
    "o4":       "openai",
    "claude":   "anthropic",
    "gemini":   "google",
    "deepseek": "deepseek",
    "qwen":     "qwen",
    "mistral":  "mistral",
    "llama":    "groq",
}


def _infer_provider(model: str) -> str:
    model_lower = model.lower()
    for prefix, provider in _MODEL_PROVIDER_MAP.items():
        if model_lower.startswith(prefix):
            return provider
    if "/" in model:
        return model.split("/")[0]
    return ""


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


def _get_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", Settings())


def _resolve_vault_info(request: Request, provider: str) -> tuple[str | None, str | None]:
    """Return (api_key, api_base) for *provider* from the vault + extra_config.

    api_base comes from the ProviderKey.extra_config JSON field so custom
    endpoints (SiliconFlow, local Ollama, …) are forwarded correctly.
    """
    vault = getattr(request.app.state, "vault", None)
    if vault is None or not vault.is_initialized or not provider:
        return None, None

    api_key = vault.get_key(provider)
    if api_key is None:
        return None, None

    # Read base_url from extra_config stored alongside the key
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        pk = session.exec(
            select(ProviderKey).where(
                ProviderKey.provider == provider,
                ProviderKey.enabled == True,  # noqa: E712
            )
        ).first()
        api_base = None
        if pk and pk.extra_config:
            try:
                api_base = json.loads(pk.extra_config).get("base_url")
            except Exception:
                pass
    finally:
        session.close()

    return api_key, api_base


def _upstream_model_for_openai_compatible(model: str, vault_provider: str) -> str:
    """Strip FlowGate vault key prefix if present (e.g. siliconflow/deepseek-ai/... → deepseek-ai/...)."""
    vp = vault_provider.lower()
    m = model
    if m.lower().startswith(vp + "/"):
        return m[len(vault_provider) + 1 :]
    return m


def _build_litellm_kwargs(
    model: str,
    api_key: str | None,
    api_base: str | None,
    *,
    vault_provider: str = "",
) -> dict[str, Any]:
    """Base litellm kwargs with auth info.

    Custom ``api_base`` endpoints use the OpenAI-compatible adapter (``openai/<upstream>``);
    strip the vault key prefix (e.g. ``siliconflow/...``) when present.
    """
    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
        upstream = _upstream_model_for_openai_compatible(model, vault_provider) if vault_provider else model
        kwargs["model"] = f"openai/{upstream}"
    else:
        kwargs["model"] = model
    return kwargs


# ─── Caller token validation ───

def _check_caller_token(request: Request, body_api_key: str | None, db_path: str) -> bool:
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else (body_api_key or "")
    return validate_caller_token(db_path, token)


# ─── /v1/chat/completions ───

def _chat_litellm_kwargs(body: ChatCompletionRequest, base: dict[str, Any]) -> dict[str, Any]:
    """Merge all ChatCompletion parameters into litellm kwargs."""
    kw = dict(base)
    kw["messages"] = [m.model_dump(exclude_none=True) for m in body.messages]
    _add_if_not_none(kw, body, [
        "temperature", "top_p", "n", "stop", "max_tokens", "max_completion_tokens",
        "presence_penalty", "frequency_penalty", "logit_bias", "logprobs",
        "top_logprobs", "user", "tools", "tool_choice", "parallel_tool_calls",
        "response_format", "seed", "reasoning_effort", "service_tier", "metadata",
    ])
    return kw


def _add_if_not_none(kw: dict, body: Any, fields: list[str]) -> None:
    for f in fields:
        v = getattr(body, f, None)
        if v is not None:
            kw[f] = v


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    db_path = _get_db_path(request)
    settings = _get_settings(request)

    if not _check_caller_token(request, body.user, db_path):
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Invalid or missing FlowGate access token", "type": "auth_error"}},
        )

    # Smart Router: evaluate complexity, potentially reroute to a different model
    service: SmartRouterService | None = getattr(request.app.state, "smart_router_service", None)
    messages_list = [m.model_dump(exclude_none=True) for m in body.messages]
    if service:
        routing = service.route(messages_list, body.model)
    else:
        from flowgate.smart_router.complexity import RoutingResult
        routing = RoutingResult(model=body.model, tier="DIRECT", score=0.0, original_model=body.model)

    provider = _infer_provider(routing.model)
    api_key, api_base = _resolve_vault_info(request, provider)
    base = _build_litellm_kwargs(routing.model, api_key, api_base, vault_provider=provider)

    is_routed = routing.tier != "DIRECT"
    if body.stream:
        kw = _chat_litellm_kwargs(body, base)
        return StreamingResponse(
            stream_completion(
                litellm_kwargs=kw,
                request=body,
                db_path=db_path,
                provider=provider,
                log_config=settings.logging,
                model_requested=body.model,
                complexity_score=routing.score if is_routed else None,
                complexity_tier=routing.tier if is_routed else None,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    start = time.monotonic()
    kw = _chat_litellm_kwargs(body, base)

    status, error_msg, response_content = "success", None, ""
    prompt_tokens = completion_tokens = total_tokens = 0
    cost_usd = 0.0
    model_used = base["model"]

    try:
        response = await litellm.acompletion(**kw)
        if response.choices:
            response_content = response.choices[0].message.content or ""
        if response.usage:
            prompt_tokens = response.usage.prompt_tokens or 0
            completion_tokens = response.usage.completion_tokens or 0
            total_tokens = response.usage.total_tokens or 0
        if hasattr(response, "_hidden_params"):
            if not provider:
                provider = response._hidden_params.get("custom_llm_provider", "")
            cost_usd = float(response._hidden_params.get("response_cost") or 0.0)
        model_used = getattr(response, "model", model_used) or model_used
        response_data = response.model_dump()
    except Exception as e:
        status, error_msg = "error", str(e)
        latency_ms = int((time.monotonic() - start) * 1000)
        _save_chat_log(
            body, model_used, provider, "", status, error_msg,
            0, 0, 0, latency_ms, 0.0, db_path,
            log_config=settings.logging,
            model_requested=body.model,
            complexity_score=routing.score if is_routed else None,
            complexity_tier=routing.tier if is_routed else None,
        )
        return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": type(e).__name__}})

    latency_ms = int((time.monotonic() - start) * 1000)
    _save_chat_log(
        body, model_used, provider, response_content, status, error_msg,
        prompt_tokens, completion_tokens, total_tokens, latency_ms, cost_usd, db_path,
        log_config=settings.logging,
        model_requested=body.model,
        complexity_score=routing.score if is_routed else None,
        complexity_tier=routing.tier if is_routed else None,
    )
    return JSONResponse(content=response_data)


# ─── /v1/embeddings ───

@router.post("/v1/embeddings")
async def embeddings(body: EmbeddingRequest, request: Request):
    db_path = _get_db_path(request)
    if not _check_caller_token(request, None, db_path):
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid or missing FlowGate access token", "type": "auth_error"}})

    provider = _infer_provider(body.model)
    api_key, api_base = _resolve_vault_info(request, provider)

    # Custom OpenAI-compatible gateways: forward JSON directly. LiteLLM's embedding
    # router mis-classifies some upstream model ids (e.g. SiliconFlow Qwen embeddings).
    if api_base and api_key:
        upstream = _upstream_model_for_openai_compatible(body.model, provider) if provider else body.model
        payload: dict[str, Any] = {"model": upstream, "input": body.input}
        if body.encoding_format:
            payload["encoding_format"] = body.encoding_format
        if body.dimensions is not None:
            payload["dimensions"] = body.dimensions
        if body.user:
            payload["user"] = body.user
        url = f"{api_base.rstrip('/')}/embeddings"
        try:
            async with httpx.AsyncClient(timeout=120.0) as ac:
                r = await ac.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
            try:
                data = r.json()
            except Exception:
                data = {"error": {"message": r.text, "type": "invalid_json"}}
            if r.status_code != 200:
                if isinstance(data, dict) and "error" in data:
                    return JSONResponse(status_code=r.status_code, content=data)
                msg = data.get("error", data) if isinstance(data, dict) else str(data)
                return JSONResponse(
                    status_code=r.status_code,
                    content={"error": {"message": str(msg), "type": "upstream_error"}},
                )
            return JSONResponse(content=data)
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": type(e).__name__}})

    kw = _build_litellm_kwargs(body.model, api_key, api_base, vault_provider=provider)
    kw["input"] = body.input
    if body.encoding_format:
        kw["encoding_format"] = body.encoding_format
    if body.dimensions:
        kw["dimensions"] = body.dimensions
    if body.user:
        kw["user"] = body.user

    try:
        response = await litellm.aembedding(**kw)
        return JSONResponse(content=response.model_dump())
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": {"message": str(e), "type": type(e).__name__}})


# ─── /v1/models ───

@router.get("/v1/models")
async def list_models(request: Request):
    """Return synced models from DB; fall back to a minimal default list."""
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        rows = session.exec(select(ProviderModel).order_by(ProviderModel.provider, ProviderModel.model_id)).all()
    except Exception:
        rows = []
    finally:
        session.close()

    if rows:
        data = [
            {
                "id": r.model_id,
                "object": "model",
                "created": r.raw_created or 0,
                "owned_by": r.owned_by or r.provider,
            }
            for r in rows
        ]
    else:
        # Sensible defaults before any sync
        data = [
            {"id": "gpt-4o",       "object": "model", "created": 0, "owned_by": "openai"},
            {"id": "gpt-4o-mini",  "object": "model", "created": 0, "owned_by": "openai"},
            {"id": "claude-3-5-sonnet-20241022", "object": "model", "created": 0, "owned_by": "anthropic"},
            {"id": "gemini-1.5-pro", "object": "model", "created": 0, "owned_by": "google"},
        ]
    return {"object": "list", "data": data}


# ─── DB logging ───

def _save_chat_log(
    request: ChatCompletionRequest,
    model_used: str, provider: str, response_content: str,
    status: str, error_message: str | None,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    latency_ms: int, cost_usd: float, db_path: str,
    *,
    log_config: LoggingConfig | None = None,
    model_requested: str | None = None,
    complexity_score: float | None = None,
    complexity_tier: str | None = None,
) -> None:
    if log_config is None:
        log_config = LoggingConfig()

    messages_json: str
    if log_config.log_prompts:
        raw = json.dumps(
            [m.model_dump(exclude_none=True) for m in request.messages], ensure_ascii=False,
        )
        messages_json = _redact(raw) if log_config.redact_secrets else raw
    else:
        messages_json = "[redacted]"

    stored_response: str | None
    if log_config.log_responses and response_content:
        stored_response = _redact(response_content) if log_config.redact_secrets else response_content
    else:
        stored_response = None if not log_config.log_responses else (response_content or None)

    log = RequestLog(
        model_requested=model_requested or request.model,
        model_used=model_used,
        provider=provider,
        messages=messages_json,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        stream=False,
        complexity_score=complexity_score,
        complexity_tier=complexity_tier,
        response_content=stored_response,
        status=status,
        error_message=error_message,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        session_id=request.session_id,
        user_tag=request.user_tag,
    )
    session = get_session(db_path)
    try:
        session.add(log)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
