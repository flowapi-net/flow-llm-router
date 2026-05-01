"""Resolve OpenAI-compatible API key + base URL for a catalog model id (MF embedding)."""

from __future__ import annotations

import json
import logging
from sqlmodel import select

from flow_llm_router.api.models import default_base_url_for_provider
from flow_llm_router.config import SmartRouterConfig
from flow_llm_router.db.engine import get_session
from flow_llm_router.db.models import ProviderKey, ProviderModel
from flow_llm_router.security.vault import Vault

logger = logging.getLogger("flow_llm_router.smart_router")


def _split_provider_prefixed_model(s: str) -> tuple[str | None, str]:
    """If `s` is `vault_provider/upstream_id`, return (vault_provider, upstream_id); else (None, s)."""
    s = (s or "").strip()
    if "/" not in s:
        return (None, s)
    a, b = s.split("/", 1)
    a, b = a.strip(), b.strip()
    if a and b:
        return (a, b)
    return (None, s)


def resolve_openai_credentials_for_model_id(
    db_path: str,
    vault: Vault | None,
    model_id: str,
) -> tuple[str, str] | None:
    """Return (api_key, base_url) for the provider that owns this model_id, or None.

    ``model_id`` may be the catalog's upstream id (e.g. ``BAAI/bge-large-en-v1.5``) or a
    UI routing id with vault prefix (e.g. ``siliconflow/BAAI/bge-large-en-v1.5``).
    """
    if not model_id or not vault or not vault.is_initialized:
        return None

    vault_key, upstream_id = _split_provider_prefixed_model(model_id)

    session = get_session(db_path)
    try:
        if vault_key:
            stmt = select(ProviderModel).where(
                ProviderModel.provider == vault_key,
                ProviderModel.model_id == upstream_id,
                ProviderModel.enabled == True,  # noqa: E712
            )
        else:
            stmt = select(ProviderModel).where(
                ProviderModel.model_id == upstream_id,
                ProviderModel.enabled == True,  # noqa: E712
            )
        rows = list(session.exec(stmt).all())
    finally:
        session.close()

    if not rows:
        return None

    for row in rows:
        session = get_session(db_path)
        try:
            stmt = select(ProviderKey).where(
                ProviderKey.provider == row.provider,
                ProviderKey.enabled == True,  # noqa: E712
            )
            pk = session.exec(stmt).first()
        finally:
            session.close()
        if pk is None:
            continue
        try:
            api_key = vault.decrypt_key(pk.encrypted_key)
        except Exception:
            continue
        base_url = ""
        if pk.extra_config:
            try:
                cfg = json.loads(pk.extra_config)
                base_url = (cfg.get("base_url") or "").strip()
            except Exception:
                pass
        if not base_url:
            base_url = default_base_url_for_provider(row.provider)
        if base_url and api_key:
            return (api_key, base_url)

    return None


def apply_mf_credentials_from_catalog(
    config: SmartRouterConfig,
    db_path: str,
    vault: Vault | None,
) -> None:
    """Mutate config: fill mf_embedding_api_key / mf_embedding_base_url from catalog when unset.

    Skips when the user already set an API key (e.g. YAML override). UI never sends keys.
    """
    if not config.enabled or config.strategy != "classifier" or config.classifier_type != "mf":
        return
    if (config.mf_embedding_api_key or "").strip():
        return
    model_id = (config.mf_embedding_model or "").strip()
    if not model_id:
        return
    resolved = resolve_openai_credentials_for_model_id(db_path, vault, model_id)
    if resolved:
        config.mf_embedding_api_key, config.mf_embedding_base_url = resolved
        logger.info(
            "MF embedding credentials resolved from catalog for model_id=%s",
            model_id,
        )
