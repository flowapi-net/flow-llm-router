"""SSE streaming for proxying LiteLLM responses."""

from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

import litellm

from flowgate.db.engine import get_session
from flowgate.db.models import RequestLog
from flowgate.proxy.schemas import ChatCompletionRequest


async def stream_completion(
    litellm_kwargs: dict[str, Any],
    request: ChatCompletionRequest,
    db_path: str,
    provider: str = "",
) -> AsyncGenerator[str, None]:
    """Stream litellm response as SSE, then persist log."""
    start = time.monotonic()
    first_chunk_time: float | None = None
    full_content: list[str] = []
    prompt_tokens = completion_tokens = total_tokens = 0
    cost = 0.0
    model_used = litellm_kwargs.get("model", request.model)
    error_msg: str | None = None
    status = "success"

    kw = dict(litellm_kwargs)
    kw["stream"] = True
    # Always request usage in the final chunk when the provider supports it
    kw.setdefault("stream_options", {"include_usage": True})

    try:
        response = await litellm.acompletion(**kw)

        async for chunk in response:
            if first_chunk_time is None:
                first_chunk_time = time.monotonic()

            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    full_content.append(delta.content)

            if hasattr(chunk, "usage") and chunk.usage:
                prompt_tokens    = getattr(chunk.usage, "prompt_tokens",    0) or 0
                completion_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0
                total_tokens     = getattr(chunk.usage, "total_tokens",     0) or 0

            if hasattr(chunk, "_hidden_params"):
                cost = chunk._hidden_params.get("response_cost", cost) or cost
                if not provider:
                    provider = chunk._hidden_params.get("custom_llm_provider", "")
                model_used = getattr(chunk, "model", model_used) or model_used

            yield f"data: {chunk.model_dump_json()}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        status = "error"
        error_msg = str(exc)
        yield f"data: {json.dumps({'error': {'message': str(exc), 'type': type(exc).__name__}})}\n\n"
        yield "data: [DONE]\n\n"

    latency_ms = int((time.monotonic() - start) * 1000)
    ttft_ms = int((first_chunk_time - start) * 1000) if first_chunk_time else None

    _save_log(
        request=request, model_used=model_used, provider=provider,
        response_content="".join(full_content), status=status, error_message=error_msg,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        total_tokens=total_tokens, cost_usd=cost,
        latency_ms=latency_ms, ttft_ms=ttft_ms, db_path=db_path,
    )


def _save_log(
    *, request: ChatCompletionRequest, model_used: str, provider: str,
    response_content: str, status: str, error_message: str | None,
    prompt_tokens: int, completion_tokens: int, total_tokens: int,
    cost_usd: float, latency_ms: int, ttft_ms: int | None, db_path: str,
) -> None:
    messages_json = json.dumps(
        [m.model_dump(exclude_none=True) for m in request.messages], ensure_ascii=False,
    )
    log = RequestLog(
        model_requested=request.model, model_used=model_used, provider=provider,
        messages=messages_json, temperature=request.temperature,
        max_tokens=request.max_tokens, stream=True,
        response_content=response_content or None,
        status=status, error_message=error_message,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        total_tokens=total_tokens, cost_usd=cost_usd,
        latency_ms=latency_ms, ttft_ms=ttft_ms,
        session_id=request.session_id, user_tag=request.user_tag,
    )
    session = get_session(db_path)
    try:
        session.add(log)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
