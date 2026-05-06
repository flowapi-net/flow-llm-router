"""Search provider key management and router-hosted search API."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field as PydanticField
from sqlmodel import select

from flow_llm_router.api.auth import verify_auth_token
from flow_llm_router.api.caller_tokens import (
    is_caller_token_auth_enabled,
    validate_caller_token,
)
from flow_llm_router.db.engine import get_session
from flow_llm_router.db.models import SearchProviderKey
from flow_llm_router.security.vault import Vault

router = APIRouter(prefix="/api/search", tags=["search"])

DEFAULT_TAVILY_URL = "https://api.tavily.com/search"
SUPPORTED_PROVIDERS = {"tavily"}


def _get_vault(request: Request) -> Vault:
    vault = getattr(request.app.state, "vault", None)
    if vault is None:
        raise HTTPException(status_code=500, detail="Vault not available")
    if not vault.is_initialized:
        raise HTTPException(status_code=423, detail="Vault is locked. Verify master password first.")
    return vault


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


def _normalize_provider(provider: str) -> str:
    normalized = provider.strip().lower()
    if normalized not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unsupported search provider: {provider}")
    return normalized


def _mask_from_suffix(suffix: str) -> str:
    return f"...{suffix}" if suffix else "****"


def _to_response(row: SearchProviderKey) -> "SearchProviderResponse":
    return SearchProviderResponse(
        id=row.id,
        provider=row.provider,
        key_name=row.key_name,
        key_masked=_mask_from_suffix(row.key_suffix),
        base_url=row.base_url,
        enabled=row.enabled,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _redact(text: str, *secrets: str) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _extract_caller_token(request: Request, body_api_key: Optional[str]) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return (body_api_key or "").strip()


def _first_enabled_tavily_key(db_path: str) -> SearchProviderKey | None:
    session = get_session(db_path)
    try:
        return session.exec(
            select(SearchProviderKey)
            .where(
                SearchProviderKey.provider == "tavily",
                SearchProviderKey.enabled == True,  # noqa: E712
            )
            .order_by(SearchProviderKey.created_at)
        ).first()
    finally:
        session.close()


class SearchProviderCreate(BaseModel):
    provider: str = "tavily"
    key_name: str
    api_key: str
    base_url: Optional[str] = None


class SearchProviderUpdate(BaseModel):
    key_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    enabled: Optional[bool] = None


class SearchProviderResponse(BaseModel):
    id: str
    provider: str
    key_name: str
    key_masked: str
    base_url: Optional[str]
    enabled: bool
    created_at: str
    updated_at: str


class TavilySearchRequest(BaseModel):
    api_key: Optional[str] = None
    query: str
    max_results: int = PydanticField(default=5, ge=1, le=10)
    search_depth: str = "advanced"
    include_answer: bool = False
    include_images: bool = False
    include_raw_content: bool = False


class SearchProviderTestRequest(BaseModel):
    query: str = "Flow LLM Router"
    max_results: int = PydanticField(default=3, ge=1, le=5)


async def _call_tavily(
    api_key: str,
    base_url: Optional[str],
    body: TavilySearchRequest,
) -> dict[str, Any]:
    url = base_url or DEFAULT_TAVILY_URL
    payload = {
        "api_key": api_key,
        "query": body.query,
        "search_depth": body.search_depth,
        "include_answer": body.include_answer,
        "include_images": body.include_images,
        "include_raw_content": body.include_raw_content,
        "max_results": body.max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Tavily request failed: {exc}") from exc

    if resp.status_code >= 400:
        detail = _redact(resp.text[:500], api_key)
        raise HTTPException(status_code=502, detail=f"Tavily returned {resp.status_code}: {detail}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Tavily returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Tavily returned an unexpected response")
    return data


@router.get("/providers", response_model=list[SearchProviderResponse])
async def list_search_providers(
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        rows = session.exec(
            select(SearchProviderKey).order_by(SearchProviderKey.provider, SearchProviderKey.key_name)
        ).all()
        return [_to_response(row) for row in rows]
    finally:
        session.close()


@router.post("/providers", response_model=SearchProviderResponse, status_code=201)
async def create_search_provider(
    body: SearchProviderCreate,
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    vault = _get_vault(request)
    db_path = _get_db_path(request)
    provider = _normalize_provider(body.provider)
    key_name = body.key_name.strip()
    api_key = body.api_key.strip()
    base_url = body.base_url.strip() if body.base_url else None
    if not key_name:
        raise HTTPException(status_code=422, detail="key_name is required")
    if not api_key:
        raise HTTPException(status_code=422, detail="api_key is required")

    now = datetime.now(timezone.utc)
    row = SearchProviderKey(
        provider=provider,
        key_name=key_name,
        encrypted_key=vault.encrypt_key(api_key),
        key_suffix=api_key[-4:] if len(api_key) >= 4 else api_key,
        base_url=base_url,
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    session = get_session(db_path)
    try:
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_response(row)
    finally:
        session.close()


@router.put("/providers/{provider_id}", response_model=SearchProviderResponse)
async def update_search_provider(
    provider_id: str,
    body: SearchProviderUpdate,
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    vault = _get_vault(request)
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        row = session.get(SearchProviderKey, provider_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Search provider key not found")

        if body.key_name is not None:
            key_name = body.key_name.strip()
            if not key_name:
                raise HTTPException(status_code=422, detail="key_name is required")
            row.key_name = key_name
        if body.api_key is not None:
            api_key = body.api_key.strip()
            if not api_key:
                raise HTTPException(status_code=422, detail="api_key is required")
            row.encrypted_key = vault.encrypt_key(api_key)
            row.key_suffix = api_key[-4:] if len(api_key) >= 4 else api_key
        if body.base_url is not None:
            row.base_url = body.base_url.strip() or None
        if body.enabled is not None:
            row.enabled = body.enabled

        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_response(row)
    finally:
        session.close()


@router.delete("/providers/{provider_id}")
async def delete_search_provider(
    provider_id: str,
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    _get_vault(request)
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        row = session.get(SearchProviderKey, provider_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Search provider key not found")
        session.delete(row)
        session.commit()
    finally:
        session.close()
    return {"success": True, "message": "Search provider key deleted"}


@router.post("/providers/{provider_id}/test")
async def test_search_provider(
    provider_id: str,
    body: SearchProviderTestRequest,
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    vault = _get_vault(request)
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        row = session.get(SearchProviderKey, provider_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Search provider key not found")
        api_key = vault.decrypt_key(row.encrypted_key)
        started = time.perf_counter()
        data = await _call_tavily(
            api_key,
            row.base_url,
            TavilySearchRequest(query=body.query, max_results=body.max_results),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        results = data.get("results") or []
        sample_title = None
        if results and isinstance(results[0], dict):
            sample_title = results[0].get("title")
        return {
            "ok": True,
            "latency_ms": latency_ms,
            "result_count": len(results) if isinstance(results, list) else 0,
            "sample_title": sample_title,
        }
    finally:
        session.close()


@router.post("/tavily")
async def tavily_search(body: TavilySearchRequest, request: Request):
    db_path = _get_db_path(request)
    if is_caller_token_auth_enabled(request):
        caller_token = _extract_caller_token(request, body.api_key)
        if not caller_token or not validate_caller_token(db_path, caller_token):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing Flow LLM Router access token",
            )

    vault = _get_vault(request)
    row = _first_enabled_tavily_key(db_path)
    if row is None:
        raise HTTPException(status_code=404, detail="No enabled Tavily search key configured")

    api_key = vault.decrypt_key(row.encrypted_key)
    try:
        return await _call_tavily(api_key, row.base_url, body)
    except HTTPException as exc:
        if isinstance(exc.detail, str):
            raise HTTPException(status_code=exc.status_code, detail=_redact(exc.detail, api_key)) from exc
        raise
