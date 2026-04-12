"""Request/Response Pydantic models for the OpenAI-compatible proxy."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: Any = None
    name: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    n: Optional[int] = None
    stream: Optional[bool] = False
    stream_options: Optional[dict] = None
    stop: Optional[str | list[str]] = None
    max_tokens: Optional[int] = None
    max_completion_tokens: Optional[int] = None  # o1/o3 series
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    logit_bias: Optional[dict[str, float]] = None
    logprobs: Optional[bool] = None
    top_logprobs: Optional[int] = None
    user: Optional[str] = None
    tools: Optional[list[dict]] = None
    tool_choice: Optional[str | dict] = None
    parallel_tool_calls: Optional[bool] = None
    response_format: Optional[dict] = None
    seed: Optional[int] = None
    reasoning_effort: Optional[str] = None   # o1/o3: "low"|"medium"|"high"
    service_tier: Optional[str] = None
    metadata: Optional[dict] = None

    # FlowGate extensions
    session_id: Optional[str] = Field(None, alias="x_session_id")
    user_tag: Optional[str] = Field(None, alias="x_user_tag")

    model_config = {"populate_by_name": True}


class EmbeddingRequest(BaseModel):
    model: str
    input: Any  # str | list[str] | list[int] | list[list[int]]
    encoding_format: Optional[str] = None  # "float" | "base64"
    dimensions: Optional[int] = None
    user: Optional[str] = None
