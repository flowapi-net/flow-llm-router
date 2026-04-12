"""Automatic redaction of API keys and secrets from log content."""

from __future__ import annotations

import re

_KEY_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9]{2})[a-zA-Z0-9]{20,}"),        # OpenAI
    re.compile(r"(sk-ant-[a-zA-Z0-9\-]{2})[a-zA-Z0-9\-]{15,}"),  # Anthropic
    re.compile(r"(sk-proj-[a-zA-Z0-9]{2})[a-zA-Z0-9]{20,}"),    # OpenAI project keys
    re.compile(r"(AIza[a-zA-Z0-9]{2})[a-zA-Z0-9]{20,}"),        # Google AI
    re.compile(r"(gsk_[a-zA-Z0-9]{2})[a-zA-Z0-9]{20,}"),        # Groq
    re.compile(r"(xai-[a-zA-Z0-9]{2})[a-zA-Z0-9]{20,}"),        # xAI
    re.compile(r"(Bearer\s+)[a-zA-Z0-9\-_.]{20,}", re.IGNORECASE),
]

_AUTH_HEADER_RE = re.compile(r"(Authorization:\s*)\S+", re.IGNORECASE)


def redact_secrets(text: str) -> str:
    """Replace known API-key patterns with masked versions."""
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + "..." + "****", text)
    text = _AUTH_HEADER_RE.sub(r"\1[REDACTED]", text)
    return text


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of *headers* with sensitive values masked."""
    sensitive = {"authorization", "x-api-key", "api-key"}
    return {
        k: "[REDACTED]" if k.lower() in sensitive else v
        for k, v in headers.items()
    }
