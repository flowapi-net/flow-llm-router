"""Provider Key CRUD API – all mutations require a valid auth token."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from flowgate.api.auth import verify_auth_token
from flowgate.db.engine import get_session
from flowgate.db.models import ProviderKey
from flowgate.security.vault import Vault

router = APIRouter(prefix="/api/keys", tags=["keys"])


def _get_vault(request: Request) -> Vault:
    vault = getattr(request.app.state, "vault", None)
    if vault is None:
        raise HTTPException(status_code=500, detail="Vault not available")
    if not vault.is_initialized:
        raise HTTPException(status_code=423, detail="Vault is locked. Verify master password first.")
    return vault


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


# ─── Request / Response Models ───


class AddKeyRequest(BaseModel):
    provider: str
    key_name: str
    api_key: str
    extra_config: Optional[str] = None


class UpdateKeyRequest(BaseModel):
    key_name: Optional[str] = None
    api_key: Optional[str] = None
    extra_config: Optional[str] = None
    enabled: Optional[bool] = None


class KeyResponse(BaseModel):
    id: str
    provider: str
    key_name: str
    key_masked: str
    extra_config: Optional[str]
    enabled: bool
    created_at: str
    updated_at: str


# ─── Endpoints ───


@router.get("", response_model=list[KeyResponse])
async def list_keys(request: Request):
    """List all provider keys (masked, no auth required for read)."""
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        keys = session.exec(select(ProviderKey)).all()
        return [
            KeyResponse(
                id=k.id,
                provider=k.provider,
                key_name=k.key_name,
                key_masked=f"...{k.key_suffix}",
                extra_config=k.extra_config,
                enabled=k.enabled,
                created_at=k.created_at.isoformat(),
                updated_at=k.updated_at.isoformat(),
            )
            for k in keys
        ]
    finally:
        session.close()


@router.post("", response_model=KeyResponse, status_code=201)
async def add_key(
    body: AddKeyRequest,
    request: Request,
    _auth: bool = Depends(verify_auth_token),
):
    """Add a new provider API key (encrypted)."""
    vault = _get_vault(request)
    db_path = _get_db_path(request)

    # Enforce unique provider name
    session_check = get_session(db_path)
    try:
        existing = session_check.exec(
            select(ProviderKey).where(ProviderKey.provider == body.provider)
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Provider '{body.provider}' already exists. Delete the existing entry first or use a different name.",
            )
    finally:
        session_check.close()

    encrypted = vault.encrypt_key(body.api_key)
    suffix = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key

    now = datetime.now(timezone.utc)
    pk = ProviderKey(
        provider=body.provider,
        key_name=body.key_name,
        encrypted_key=encrypted,
        key_suffix=suffix,
        extra_config=body.extra_config,
        enabled=True,
        created_at=now,
        updated_at=now,
    )

    session = get_session(db_path)
    try:
        session.add(pk)
        session.commit()
        session.refresh(pk)
    finally:
        session.close()

    vault.add_to_cache(body.provider, encrypted)

    return KeyResponse(
        id=pk.id,
        provider=pk.provider,
        key_name=pk.key_name,
        key_masked=Vault.mask_key(body.api_key),
        extra_config=pk.extra_config,
        enabled=pk.enabled,
        created_at=pk.created_at.isoformat(),
        updated_at=pk.updated_at.isoformat(),
    )


@router.put("/{key_id}", response_model=KeyResponse)
async def update_key(
    key_id: str,
    body: UpdateKeyRequest,
    request: Request,
    _auth: bool = Depends(verify_auth_token),
):
    """Update an existing provider key."""
    vault = _get_vault(request)
    db_path = _get_db_path(request)

    session = get_session(db_path)
    try:
        pk = session.get(ProviderKey, key_id)
        if pk is None:
            raise HTTPException(status_code=404, detail="Key not found")

        if body.key_name is not None:
            pk.key_name = body.key_name
        if body.api_key is not None:
            pk.encrypted_key = vault.encrypt_key(body.api_key)
            pk.key_suffix = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key
        if body.extra_config is not None:
            pk.extra_config = body.extra_config
        if body.enabled is not None:
            pk.enabled = body.enabled

        pk.updated_at = datetime.now(timezone.utc)
        session.add(pk)
        session.commit()
        session.refresh(pk)

        if pk.enabled:
            vault.add_to_cache(pk.provider, pk.encrypted_key)
        else:
            vault.remove_from_cache(pk.provider)

        return KeyResponse(
            id=pk.id,
            provider=pk.provider,
            key_name=pk.key_name,
            key_masked=f"...{pk.key_suffix}",
            extra_config=pk.extra_config,
            enabled=pk.enabled,
            created_at=pk.created_at.isoformat(),
            updated_at=pk.updated_at.isoformat(),
        )
    finally:
        session.close()


@router.delete("/{key_id}")
async def delete_key(
    key_id: str,
    request: Request,
    _auth: bool = Depends(verify_auth_token),
):
    """Permanently delete a provider key."""
    db_path = _get_db_path(request)
    vault = _get_vault(request)

    session = get_session(db_path)
    try:
        pk = session.get(ProviderKey, key_id)
        if pk is None:
            raise HTTPException(status_code=404, detail="Key not found")
        provider = pk.provider
        session.delete(pk)
        session.commit()
    finally:
        session.close()

    vault.remove_from_cache(provider)

    return {"success": True, "message": "Key deleted"}
