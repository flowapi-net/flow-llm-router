"""FastAPI application entry point."""

from __future__ import annotations

import base64
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from flowgate import __version__
from flowgate.api.auth import router as auth_router
from flowgate.api.caller_tokens import router as caller_tokens_router
from flowgate.api.dashboard import router as dashboard_router
from flowgate.api.keys import router as keys_router
from flowgate.api.models import router as models_router
from flowgate.api.router_config import router as router_config_router
from flowgate.config import Settings, load_settings
from flowgate.db.engine import get_session, init_db
from flowgate.db.models import CallerToken, ProviderKey, ProviderModel, RouterConfig, VaultMeta
from flowgate.proxy.router import router as proxy_router
from flowgate.security.ip_guard import IPGuardMiddleware
from flowgate.security.master_key_store import load_master_key
from flowgate.security.vault import Vault
from flowgate.smart_router.catalog_credentials import apply_mf_credentials_from_catalog
from flowgate.smart_router.service import SmartRouterService

logger = logging.getLogger("flowgate")


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        import os

        config_path = os.environ.get("FLOWGATE_CONFIG")
        settings = load_settings(config_path)

    vault = Vault()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings.database.path)
        _try_auto_unlock(vault, settings)
        _init_smart_router(app, settings)
        yield

    app = FastAPI(
        title="FlowGate",
        description="Local-first LLM gateway with token usage analytics",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    app.state.db_path = settings.database.path
    app.state.settings = settings
    app.state.vault = vault

    ip_cfg = settings.security.ip_whitelist
    if ip_cfg.enabled:
        app.add_middleware(
            IPGuardMiddleware,
            mode=ip_cfg.mode,
            allowed_ips=ip_cfg.allowed_ips,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(proxy_router)
    app.include_router(dashboard_router)
    app.include_router(auth_router)
    app.include_router(keys_router)
    app.include_router(models_router)
    app.include_router(caller_tokens_router)
    app.include_router(router_config_router)

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists() and any(static_dir.iterdir()):
        # Mount static assets (JS/CSS/_next/…) without html=True so /api/* won't be shadowed
        app.mount("/_next", StaticFiles(directory=static_dir / "_next"), name="next-assets")

        # SPA catch-all: serve index.html for any non-API, non-asset path
        index_html = static_dir / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            # Try an exact file first (e.g. /favicon.ico, /logo.png)
            candidate = static_dir / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            # Next.js exports each page as <slug>/index.html
            page_html = static_dir / full_path / "index.html"
            if page_html.is_file():
                return FileResponse(page_html)
            return FileResponse(index_html)

    return app


def _init_smart_router(app: FastAPI, settings: Settings) -> None:
    """Load router config from DB (if saved) or fall back to YAML defaults."""
    import json as _json

    config = settings.smart_router
    db_path = settings.database.path
    session = get_session(db_path)
    try:
        row = session.get(RouterConfig, 1)
        if row is not None and row.config_json:
            data = _json.loads(row.config_json)
            config = SmartRouterService.config_from_dict(data)
            logger.info("Smart Router config loaded from DB (strategy=%s)", config.strategy)
    except Exception:
        pass
    finally:
        session.close()

    vault = getattr(app.state, "vault", None)
    apply_mf_credentials_from_catalog(config, db_path, vault)
    app.state.smart_router_service = SmartRouterService(config)


def _try_auto_unlock(vault: Vault, settings: Settings) -> None:
    """Auto-unlock via persisted key (preferred) or env password (fallback)."""
    import os

    db_path = settings.database.path
    session = get_session(db_path)
    try:
        meta = session.get(VaultMeta, 1)
        if meta is None:
            return

        from sqlmodel import select

        keys = session.exec(select(ProviderKey).where(ProviderKey.enabled == True)).all()  # noqa: E712

        # Preferred path: persisted Fernet key file
        stored_key = load_master_key(settings)
        if stored_key:
            try:
                vault.initialize_from_key(stored_key)
                if keys:
                    # Validate key against one ciphertext before accepting unlock.
                    vault.decrypt_key(keys[0].encrypted_key)
                vault.load_encrypted_cache(keys)
                logger.info("Vault auto-unlocked via persisted master key (%d keys loaded)", len(keys))
                return
            except Exception:
                vault.lock()
                logger.warning("Persisted master key is invalid for this vault; falling back to password env")

        # Backward-compatible fallback: plain master password env var
        master_pw = os.environ.get("FLOWGATE_MASTER_PASSWORD")
        if not master_pw:
            return
        if Vault.hash_password(master_pw) != meta.password_hash:
            logger.warning("FLOWGATE_MASTER_PASSWORD does not match stored hash – vault stays locked")
            return

        salt = base64.b64decode(meta.salt)
        vault.initialize(master_pw, salt=salt)
        vault.load_encrypted_cache(keys)
        logger.info("Vault auto-unlocked via FLOWGATE_MASTER_PASSWORD (%d keys loaded)", len(keys))
    finally:
        session.close()
