"""Provider model catalogue – sync and list models from configured providers."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from flow_llm_router.api.auth import verify_auth_token
from flow_llm_router.db.engine import get_session, init_db
from flow_llm_router.db.models import ProviderKey, ProviderModel
from flow_llm_router.security.vault import Vault

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models", tags=["models"])


def _get_vault(request: Request) -> Vault:
    vault = getattr(request.app.state, "vault", None)
    if vault is None:
        raise HTTPException(status_code=500, detail="Vault not available")
    return vault


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


# ─── Response schemas ───

class ModelItem(BaseModel):
    id: str
    provider: str
    model_id: str
    display_name: Optional[str]
    owned_by: Optional[str]
    raw_created: Optional[int]
    enabled: bool
    synced_at: str


class SyncResult(BaseModel):
    provider: str
    synced: int
    models: List[str]


class AddManualModelBody(BaseModel):
    """Add a catalog entry without calling the provider /v1/models API."""

    provider: str
    model_name: str = ""
    #: Upstream model id (OpenAI-style), e.g. ``BAAI/bge-large-en-v1.5`` — shown as ``{provider}/{slug}``.
    slug: str


class UpdateModelBody(BaseModel):
    display_name: Optional[str] = None
    enabled: Optional[bool] = None


# ─── Helpers ───

async def _fetch_models_from_provider(
    api_key: str,
    base_url: str,
) -> list[dict]:
    """Call GET {base_url}/models and return the model list."""
    url = base_url.rstrip("/") + "/models"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    # OpenAI-compatible: {"object":"list","data":[{"id":...},...]}
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def default_base_url_for_provider(provider: str) -> str:
    """OpenAI-compatible base URL for a known provider slug (used by sync + MF embedding)."""
    mapping = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "google": "https://generativelanguage.googleapis.com/v1beta/openai",
        "groq": "https://api.groq.com/openai/v1",
        "mistral": "https://api.mistral.ai/v1",
        "together": "https://api.together.xyz/v1",
        "perplexity": "https://api.perplexity.ai",
        "siliconflow": "https://api.siliconflow.cn/v1",
    }
    return mapping.get(provider.lower(), "")


def to_model_item(row: ProviderModel) -> ModelItem:
    return ModelItem(
        id=row.id,
        provider=row.provider,
        model_id=row.model_id,
        display_name=row.display_name,
        owned_by=row.owned_by,
        raw_created=row.raw_created,
        enabled=row.enabled,
        synced_at=row.synced_at.isoformat(),
    )


# ─── Endpoints ───

@router.get("", response_model=List[ModelItem])
async def list_models(
    request: Request,
    provider: Optional[str] = None,
    enabled: Optional[bool] = None,
):
    """List synced models, optionally filtered by provider and enabled state."""
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        stmt = select(ProviderModel)
        if provider:
            stmt = stmt.where(ProviderModel.provider == provider)
        if enabled is not None:
            stmt = stmt.where(ProviderModel.enabled == enabled)
        stmt = stmt.order_by(ProviderModel.provider, ProviderModel.model_id)
        rows = session.exec(stmt).all()
    finally:
        session.close()

    return [to_model_item(r) for r in rows]


@router.post("/manual", response_model=ModelItem)
async def add_manual_model(
    request: Request,
    body: AddManualModelBody,
    _: bool = Depends(verify_auth_token),
):
    """Insert a single model row (manual pin). Requires an enabled key for that provider."""
    db_path = _get_db_path(request)
    init_db(db_path)

    raw_provider = body.provider.strip()
    slug = body.slug.strip()
    if not raw_provider:
        raise HTTPException(status_code=422, detail="provider is required")
    if not slug:
        raise HTTPException(status_code=422, detail="slug is required")

    pref = raw_provider.rstrip("/") + "/"
    if slug.lower().startswith(pref.lower()):
        slug = slug[len(pref) :].lstrip()

    model_name = body.model_name.strip()
    display = model_name or slug

    session = get_session(db_path)
    try:
        keys = session.exec(
            select(ProviderKey).where(ProviderKey.enabled == True)  # noqa: E712
        ).all()
        pk_match = next(
            (k for k in keys if k.provider.lower() == raw_provider.lower()),
            None,
        )
        if pk_match is None:
            raise HTTPException(
                status_code=404,
                detail=f"No enabled provider key for '{raw_provider}'. Add a key on the Providers page first.",
            )
        provider = pk_match.provider

        existing = session.exec(
            select(ProviderModel).where(
                ProviderModel.provider == provider,
                ProviderModel.model_id == slug,
            )
        ).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="This model is already in the catalog.")

        now = datetime.now(timezone.utc)
        row = ProviderModel(
            provider=provider,
            model_id=slug,
            display_name=display,
            owned_by=None,
            raw_created=None,
            enabled=False,
            synced_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return to_model_item(row)
    finally:
        session.close()


@router.put("/{model_id}", response_model=ModelItem)
async def update_model(
    model_id: str,
    request: Request,
    body: UpdateModelBody,
    _: bool = Depends(verify_auth_token),
):
    """Update a synced/manual model catalog row."""
    db_path = _get_db_path(request)
    init_db(db_path)
    session = get_session(db_path)
    try:
        row = session.get(ProviderModel, model_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Model not found")
        if body.display_name is not None:
            row.display_name = body.display_name.strip() or None
        if body.enabled is not None:
            row.enabled = body.enabled
        session.add(row)
        session.commit()
        session.refresh(row)
        return to_model_item(row)
    finally:
        session.close()


@router.post("/sync/{provider_name}", response_model=SyncResult)
async def sync_models(
    provider_name: str,
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    """Fetch models from a provider's API and store them locally."""
    db_path = _get_db_path(request)
    vault = _get_vault(request)

    if not vault.is_initialized:
        raise HTTPException(status_code=423, detail="Vault is locked")

    # Look up the provider key
    session = get_session(db_path)
    try:
        stmt = select(ProviderKey).where(
            ProviderKey.provider == provider_name,
            ProviderKey.enabled == True,  # noqa: E712
        )
        pk = session.exec(stmt).first()
        if pk is None:
            raise HTTPException(
                status_code=404,
                detail=f"No enabled key found for provider '{provider_name}'",
            )

        api_key = vault.decrypt_key(pk.encrypted_key)

        # Resolve base URL: extra_config > known defaults
        base_url = ""
        if pk.extra_config:
            try:
                cfg = json.loads(pk.extra_config)
                base_url = cfg.get("base_url", "")
            except Exception:
                pass
        if not base_url:
            base_url = default_base_url_for_provider(provider_name)
        if not base_url:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown provider '{provider_name}'. Set a Base URL when adding the key.",
            )
    finally:
        session.close()

    # Fetch from provider
    try:
        raw_models = await _fetch_models_from_provider(api_key, base_url)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Provider returned {exc.response.status_code}: {exc.response.text[:200]}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch models: {exc}") from exc

    # Upsert into DB
    session = get_session(db_path)
    init_db(db_path)
    synced_ids: list[str] = []
    try:
        now = datetime.now(timezone.utc)
        for m in raw_models:
            model_id = m.get("id") or m.get("name") or ""
            if not model_id:
                continue
            # Check for existing record
            existing = session.exec(
                select(ProviderModel).where(
                    ProviderModel.provider == provider_name,
                    ProviderModel.model_id == model_id,
                )
            ).first()
            if existing:
                existing.synced_at = now
                existing.owned_by = m.get("owned_by")
                existing.raw_created = m.get("created")
                session.add(existing)
            else:
                row = ProviderModel(
                    provider=provider_name,
                    model_id=model_id,
                    display_name=model_id,
                    owned_by=m.get("owned_by"),
                    raw_created=m.get("created"),
                    enabled=False,
                    synced_at=now,
                )
                session.add(row)
            synced_ids.append(model_id)
        session.commit()
    finally:
        session.close()

    logger.info("Synced %d models for provider '%s'", len(synced_ids), provider_name)
    return SyncResult(provider=provider_name, synced=len(synced_ids), models=synced_ids)
