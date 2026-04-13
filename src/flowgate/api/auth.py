"""Authentication API: master password setup, verification, and token management."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from flowgate.db.engine import get_session, init_db
from flowgate.db.models import VaultMeta
from flowgate.security.master_key_store import save_master_key
from flowgate.security.vault import Vault

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_active_tokens: dict[str, float] = {}


class SetupRequest(BaseModel):
    password: str


class VerifyRequest(BaseModel):
    password: str


class SetupResponse(BaseModel):
    success: bool
    message: str


class VerifyResponse(BaseModel):
    success: bool
    token: str | None = None
    expires_in: int | None = None


class StatusResponse(BaseModel):
    vault_initialized: bool
    vault_unlocked: bool


def _get_vault(request: Request) -> Vault:
    vault = getattr(request.app.state, "vault", None)
    if vault is None:
        raise HTTPException(status_code=500, detail="Vault not available")
    return vault


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


def _get_token_ttl(request: Request) -> int:
    settings = getattr(request.app.state, "settings", None)
    if settings:
        return settings.security.auth_token_ttl_minutes * 60
    return 3600


def create_auth_token(request: Request) -> str:
    """Generate a random token and store it with expiry."""
    token = secrets.token_urlsafe(32)
    ttl = _get_token_ttl(request)
    _active_tokens[token] = time.time() + ttl
    return token


def verify_auth_token(request: Request) -> bool:
    """Dependency: verify the Bearer token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization token")
    token = auth[7:]
    expiry = _active_tokens.get(token)
    if expiry is None or time.time() > expiry:
        _active_tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    return True


@router.get("/status", response_model=StatusResponse)
async def auth_status(request: Request):
    """Check whether the vault has been set up and whether it's unlocked."""
    vault = _get_vault(request)
    db_path = _get_db_path(request)

    session = get_session(db_path)
    try:
        meta = session.get(VaultMeta, 1)
        initialized = meta is not None
    finally:
        session.close()

    return StatusResponse(
        vault_initialized=initialized,
        vault_unlocked=vault.is_initialized,
    )


@router.post("/setup", response_model=SetupResponse)
async def auth_setup(body: SetupRequest, request: Request):
    """First-time master password setup.  Creates the vault metadata."""
    vault = _get_vault(request)
    db_path = _get_db_path(request)

    # Ensure tables exist even if DB was recreated while the server was running.
    try:
        init_db(db_path)
    except Exception as exc:
        logger.exception("init_db failed during setup")
        raise HTTPException(status_code=500, detail=f"Database initialization failed: {exc}") from exc

    try:
        session = get_session(db_path)
        try:
            existing = session.get(VaultMeta, 1)
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Master password already set. Use /api/auth/verify to unlock.",
                )

            salt = vault.initialize(body.password)

            meta = VaultMeta(
                id=1,
                salt=base64.b64encode(salt).decode(),
                password_hash=Vault.hash_password(body.password),
            )
            session.add(meta)
            session.commit()
            _persist_master_key(request, vault)
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during vault setup")
        raise HTTPException(status_code=500, detail=f"Setup failed: {exc}") from exc

    _load_encrypted_cache(vault, db_path)

    return SetupResponse(success=True, message="Master password set successfully")


@router.post("/verify", response_model=VerifyResponse)
async def auth_verify(body: VerifyRequest, request: Request):
    """Verify master password and return a temporary auth token."""
    vault = _get_vault(request)
    db_path = _get_db_path(request)

    try:
        init_db(db_path)
    except Exception as exc:
        logger.exception("init_db failed during verify")
        raise HTTPException(status_code=500, detail=f"Database initialization failed: {exc}") from exc

    try:
        session = get_session(db_path)
        try:
            meta = session.get(VaultMeta, 1)
            if meta is None:
                raise HTTPException(status_code=404, detail="Vault not initialized. Call /api/auth/setup first.")

            if Vault.hash_password(body.password) != meta.password_hash:
                raise HTTPException(status_code=403, detail="Invalid master password")

            if not vault.is_initialized:
                salt = base64.b64decode(meta.salt)
                vault.initialize(body.password, salt=salt)
                _load_encrypted_cache(vault, db_path)
            _persist_master_key(request, vault)
        finally:
            session.close()
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during vault verify")
        raise HTTPException(status_code=500, detail=f"Verify failed: {exc}") from exc

    token = create_auth_token(request)
    ttl = _get_token_ttl(request)

    return VerifyResponse(success=True, token=token, expires_in=ttl)


def _load_encrypted_cache(vault: Vault, db_path: str) -> None:
    """Load all enabled ProviderKey ciphertexts into the vault's memory cache."""
    from flowgate.db.models import ProviderKey
    from sqlmodel import select

    session = get_session(db_path)
    try:
        keys = session.exec(select(ProviderKey).where(ProviderKey.enabled == True)).all()  # noqa: E712
        vault.load_encrypted_cache(keys)
    finally:
        session.close()


def _persist_master_key(request: Request, vault: Vault) -> None:
    """Persist Fernet key locally so restart auto-unlock does not require re-entry."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return
    try:
        save_master_key(settings, vault.export_key())
    except Exception:
        logger.warning("Failed to persist master key; restart will require manual unlock")
