"""Caller Token CRUD – manage who can call the Flow LLM Router proxy."""

from __future__ import annotations

import os
import hashlib
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from flow_llm_router.api.auth import verify_auth_token
from flow_llm_router.db.engine import get_session, init_db
from flow_llm_router.db.models import CallerToken

router = APIRouter(prefix="/api/caller-tokens", tags=["caller-tokens"])

TOKEN_PREFIX = "fgt_"


def is_caller_token_auth_enabled(request: Request) -> bool:
    """Whether proxy/search endpoints should enforce caller token auth.

    Behavior:
    - `FLOW_LLM_ROUTER_ENFORCE_CALLER_TOKENS=1` always enforces.
    - `FLOW_LLM_ROUTER_DISABLE_CALLER_TOKENS=1` always disables.
    - Otherwise follow `settings.security.vault_enabled`.
    """
    force_on = os.getenv("FLOW_LLM_ROUTER_ENFORCE_CALLER_TOKENS", "").strip().lower()
    if force_on in {"1", "true", "yes", "on"}:
        return True

    force_off = os.getenv("FLOW_LLM_ROUTER_DISABLE_CALLER_TOKENS", "").strip().lower()
    if force_off in {"1", "true", "yes", "on"}:
        return False

    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return True
    return bool(getattr(settings.security, "vault_enabled", True))


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ─── Request / Response ───

class CreateTokenRequest(BaseModel):
    name: str


class TokenCreatedResponse(BaseModel):
    id: str
    name: str
    token: str          # plaintext – only shown once
    token_prefix: str
    created_at: str


class TokenListItem(BaseModel):
    id: str
    name: str
    token_prefix: str
    enabled: bool
    created_at: str
    last_used_at: Optional[str]


# ─── Endpoints ───

@router.get("", response_model=List[TokenListItem])
async def list_tokens(request: Request, _: bool = Depends(verify_auth_token)):
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        rows = session.exec(select(CallerToken).order_by(CallerToken.created_at)).all()
    finally:
        session.close()
    return [
        TokenListItem(
            id=r.id,
            name=r.name,
            token_prefix=r.token_prefix,
            enabled=r.enabled,
            created_at=r.created_at.isoformat(),
            last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
        )
        for r in rows
    ]


@router.post("", response_model=TokenCreatedResponse, status_code=201)
async def create_token(body: CreateTokenRequest, request: Request, _: bool = Depends(verify_auth_token)):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    db_path = _get_db_path(request)
    init_db(db_path)

    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    prefix = raw[:12]   # "fgt_" + 8 chars

    row = CallerToken(
        name=body.name.strip(),
        token_prefix=prefix,
        token_hash=_hash_token(raw),
    )
    session = get_session(db_path)
    try:
        session.add(row)
        session.commit()
        session.refresh(row)
    finally:
        session.close()

    return TokenCreatedResponse(
        id=row.id,
        name=row.name,
        token=raw,
        token_prefix=prefix,
        created_at=row.created_at.isoformat(),
    )


@router.put("/{token_id}")
async def update_token(
    token_id: str,
    body: dict,
    request: Request,
    _: bool = Depends(verify_auth_token),
):
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        row = session.get(CallerToken, token_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Token not found")
        if "enabled" in body:
            row.enabled = bool(body["enabled"])
        if "name" in body and body["name"].strip():
            row.name = body["name"].strip()
        session.add(row)
        session.commit()
    finally:
        session.close()
    return {"ok": True}


@router.delete("/{token_id}", status_code=204)
async def delete_token(token_id: str, request: Request, _: bool = Depends(verify_auth_token)):
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        row = session.get(CallerToken, token_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Token not found")
        session.delete(row)
        session.commit()
    finally:
        session.close()


# ─── Helper used by the proxy ───

def validate_caller_token(db_path: str, raw_token: str) -> bool:
    """Return True if the token is valid and enabled.

    If no caller tokens exist in the DB, access is unrestricted (backward compat).
    """
    session = get_session(db_path)
    try:
        total = session.exec(select(CallerToken)).all()
        if not total:
            return True  # no tokens configured → open

        token_hash = _hash_token(raw_token)
        row = session.exec(
            select(CallerToken).where(
                CallerToken.token_hash == token_hash,
                CallerToken.enabled == True,  # noqa: E712
            )
        ).first()
        if row is None:
            return False

        # Update last_used_at
        row.last_used_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        return True
    finally:
        session.close()
