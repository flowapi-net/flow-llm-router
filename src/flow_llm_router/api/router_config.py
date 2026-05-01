"""Router configuration API — GET/PUT config, POST test, GET stats."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlmodel import text

from flow_llm_router.db.engine import get_session
from flow_llm_router.db.models import RouterConfig
from flow_llm_router.smart_router.catalog_credentials import apply_mf_credentials_from_catalog
from flow_llm_router.smart_router.service import (
    SmartRouterService,
    mf_bundle_dir,
    mf_assets_cached,
)

router = APIRouter(prefix="/api/router")


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


def _get_service(request: Request) -> SmartRouterService:
    return getattr(request.app.state, "smart_router_service", None)


def _get_vault(request: Request):
    return getattr(request.app.state, "vault", None)


def _strip_classifier_embedding_secrets(body: dict) -> dict:
    """Do not persist embedding URLs/keys from the client; credentials come from the catalog + vault."""
    out = dict(body)
    cl = out.get("classifier")
    if isinstance(cl, dict):
        cl = {k: v for k, v in cl.items() if k not in ("mf_embedding_base_url", "mf_embedding_api_key")}
        out["classifier"] = cl
    return out


# ─── GET /api/router/config ───

@router.get("/config")
async def get_router_config(request: Request):
    service = _get_service(request)
    if service is None:
        return {"success": True, "data": SmartRouterService(
            __import__("flow_llm_router.config", fromlist=["SmartRouterConfig"]).SmartRouterConfig()
        ).get_config_dict()}
    return {"success": True, "data": service.get_config_dict()}


@router.get("/classifier/mf-assets")
async def get_mf_assets_status():
    """MF assets readiness status for UI (project-local bundled model)."""
    cached = mf_assets_cached()
    return {
        "success": True,
        "data": {
            "status": "ready" if cached else "missing",
            "progress": 100 if cached else 0,
            "message": "MF assets ready" if cached else "MF assets missing in project directory",
            "error": "",
            "cached": cached,
            "local_cache_dir": mf_bundle_dir(),
        },
    }


@router.post("/classifier/mf-load")
async def load_mf_classifier(body: dict, request: Request):
    """Try loading MF classifier immediately for current runtime."""
    service = _get_service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"success": False, "error": "Service not available"})

    try:
        source = body if isinstance(body, dict) and body else service.get_config_dict()
        cfg = SmartRouterService.config_from_dict(source)
    except Exception as e:
        return JSONResponse(status_code=422, content={"success": False, "error": str(e)})

    cfg.enabled = True
    cfg.strategy = "classifier"
    cfg.classifier_type = "mf"

    db_path = _get_db_path(request)
    apply_mf_credentials_from_catalog(cfg, db_path, _get_vault(request))
    service.reload(cfg)
    runtime = service.get_config_dict()
    loaded = runtime.get("strategy") == "classifier" and runtime.get("classifier", {}).get("type") == "mf"

    return {
        "success": True,
        "data": {
            "loaded": loaded,
            "strategy": runtime.get("strategy"),
            "message": "MF model loaded." if loaded else "MF load failed, fallback to complexity.",
        },
    }


# ─── PUT /api/router/config ───

@router.put("/config")
async def update_router_config(
    body: dict,
    request: Request,
):
    service = _get_service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"success": False, "error": "Service not available"})

    try:
        new_config = SmartRouterService.config_from_dict(body)
    except Exception as e:
        return JSONResponse(status_code=422, content={"success": False, "error": str(e)})

    db_path = _get_db_path(request)
    apply_mf_credentials_from_catalog(new_config, db_path, _get_vault(request))
    service.reload(new_config)

    session = get_session(db_path)
    to_store = _strip_classifier_embedding_secrets(body)
    try:
        row = session.get(RouterConfig, 1)
        if row is None:
            row = RouterConfig(id=1)
            session.add(row)
        row.enabled = new_config.enabled
        row.strategy = new_config.strategy
        row.config_json = json.dumps(to_store, ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()

    return {"success": True, "data": service.get_config_dict()}


# ─── POST /api/router/test ───

@router.post("/test")
async def test_router(body: dict, request: Request):
    service = _get_service(request)
    if service is None:
        return JSONResponse(status_code=503, content={"success": False, "error": "Service not available"})

    messages = body.get("messages", [])
    model = body.get("model", "gpt-4o")
    if not messages:
        return JSONResponse(status_code=422, content={"success": False, "error": "messages is required"})

    result = service.test_route(messages, model)
    return {"success": True, "data": result}


# ─── GET /api/router/stats ───

@router.get("/stats")
async def router_stats(
    request: Request,
    days: int = Query(7, ge=1, le=365),
):
    db_path = _get_db_path(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    session = get_session(db_path)
    try:
        # Tier distribution
        tier_rows = session.exec(
            text(
                """
                SELECT complexity_tier, COUNT(*) as cnt
                FROM request_logs
                WHERE created_at >= :since AND complexity_tier IS NOT NULL
                GROUP BY complexity_tier
                ORDER BY cnt DESC
                """
            ),
            params={"since": since.isoformat()},
        ).all()

        total = sum(r[1] for r in tier_rows) if tier_rows else 0
        tier_distribution = [
            {
                "tier": r[0],
                "count": r[1],
                "percentage": round(r[1] / total * 100, 1) if total > 0 else 0,
            }
            for r in tier_rows
        ]

        # Daily trend
        trend_rows = session.exec(
            text(
                """
                SELECT strftime('%Y-%m-%d', created_at) as day,
                       complexity_tier,
                       COUNT(*) as cnt
                FROM request_logs
                WHERE created_at >= :since AND complexity_tier IS NOT NULL
                GROUP BY day, complexity_tier
                ORDER BY day
                """
            ),
            params={"since": since.isoformat()},
        ).all()

        daily: dict[str, dict[str, int]] = {}
        for row in trend_rows:
            day = row[0]
            if day not in daily:
                daily[day] = {}
            daily[day][row[1]] = row[2]

        daily_trend = [
            {"date": day, **counts}
            for day, counts in sorted(daily.items())
        ]
    finally:
        session.close()

    return {
        "success": True,
        "data": {
            "tier_distribution": tier_distribution,
            "daily_trend": daily_trend,
            "total_routed": total,
        },
    }
