"""Dashboard REST API for statistics, logs, and security."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, col, func, select, text

from flowgate.api.auth import verify_auth_token
from flowgate.db.engine import get_session
from flowgate.db.models import RequestLog

router = APIRouter(prefix="/api")


def _get_db_path(request: Request) -> str:
    return getattr(request.app.state, "db_path", "./data.db")


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        return now - timedelta(days=7)
    elif period == "month":
        return now - timedelta(days=30)
    return now - timedelta(days=1)


# ─── Stats Overview ───

@router.get("/stats/overview")
async def stats_overview(
    request: Request,
    period: str = Query("today", pattern="^(today|week|month)$"),
):
    db_path = _get_db_path(request)
    since = _period_start(period)

    session = get_session(db_path)
    try:
        stmt = select(
            func.count(RequestLog.id).label("total_requests"),
            func.sum(RequestLog.prompt_tokens).label("total_prompt_tokens"),
            func.sum(RequestLog.completion_tokens).label("total_completion_tokens"),
            func.sum(RequestLog.total_tokens).label("total_tokens"),
            func.avg(RequestLog.latency_ms).label("avg_latency_ms"),
            func.count(
                func.nullif(RequestLog.status, "success")
            ).label("error_count"),
        ).where(col(RequestLog.created_at) >= since)

        row = session.exec(stmt).first()
    finally:
        session.close()

    total_requests = row[0] or 0
    success_count = total_requests - (row[5] or 0)
    success_rate = (success_count / total_requests * 100) if total_requests > 0 else 100.0

    return {
        "success": True,
        "data": {
            "total_requests": total_requests,
            "total_prompt_tokens": row[1] or 0,
            "total_completion_tokens": row[2] or 0,
            "total_tokens": row[3] or 0,
            "avg_latency_ms": round(row[4] or 0, 1),
            "success_rate": round(success_rate, 1),
            "error_count": row[5] or 0,
            "period": period,
        },
    }


# ─── Stats Timeline ───

@router.get("/stats/timeline")
async def stats_timeline(
    request: Request,
    granularity: str = Query("hour", pattern="^(hour|day)$"),
    days: int = Query(7, ge=1, le=365),
):
    db_path = _get_db_path(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    fmt = "%Y-%m-%d %H:00:00" if granularity == "hour" else "%Y-%m-%d"
    session = get_session(db_path)
    try:
        result = session.exec(
            text(
                f"""
                SELECT strftime('{fmt}', created_at) as bucket,
                       COUNT(*) as requests,
                       COALESCE(SUM(total_tokens), 0) as tokens
                FROM request_logs
                WHERE created_at >= :since
                GROUP BY bucket
                ORDER BY bucket
                """
            ),
            params={"since": since.isoformat()},
        )
        rows = result.all()
    finally:
        session.close()

    return {
        "success": True,
        "data": [
            {"time": r[0], "requests": r[1], "tokens": r[2]}
            for r in rows
        ],
    }


# ─── Stats by Provider ───

@router.get("/stats/providers")
async def stats_providers(
    request: Request,
    days: int = Query(30, ge=1, le=365),
):
    db_path = _get_db_path(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    session = get_session(db_path)
    try:
        result = session.exec(
            text(
                """
                SELECT provider,
                       COUNT(*) as requests,
                       COALESCE(SUM(total_tokens), 0) as tokens
                FROM request_logs
                WHERE created_at >= :since AND provider != ''
                GROUP BY provider
                ORDER BY tokens DESC
                """
            ),
            params={"since": since.isoformat()},
        )
        rows = result.all()
    finally:
        session.close()

    return {
        "success": True,
        "data": [
            {"provider": r[0], "requests": r[1], "tokens": r[2]}
            for r in rows
        ],
    }


# ─── Stats by Model ───

@router.get("/stats/models")
async def stats_models(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
):
    db_path = _get_db_path(request)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    session = get_session(db_path)
    try:
        result = session.exec(
            text(
                """
                SELECT model_used,
                       COUNT(*) as requests,
                       COALESCE(SUM(total_tokens), 0) as tokens
                FROM request_logs
                WHERE created_at >= :since
                GROUP BY model_used
                ORDER BY requests DESC
                LIMIT :limit
                """
            ),
            params={"since": since.isoformat(), "limit": limit},
        )
        rows = result.all()
    finally:
        session.close()

    return {
        "success": True,
        "data": [
            {"model": r[0], "requests": r[1], "tokens": r[2]}
            for r in rows
        ],
    }


# ─── Logs List ───

@router.get("/logs")
async def list_logs(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    model: Optional[str] = None,
    status: Optional[str] = None,
    session_id: Optional[str] = None,
):
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        count_stmt = select(func.count(RequestLog.id))
        list_stmt = select(RequestLog)

        if model:
            count_stmt = count_stmt.where(RequestLog.model_used == model)
            list_stmt = list_stmt.where(RequestLog.model_used == model)
        if status:
            count_stmt = count_stmt.where(RequestLog.status == status)
            list_stmt = list_stmt.where(RequestLog.status == status)
        if session_id:
            count_stmt = count_stmt.where(RequestLog.session_id == session_id)
            list_stmt = list_stmt.where(RequestLog.session_id == session_id)

        total = session.exec(count_stmt).one()
        logs = session.exec(
            list_stmt
            .order_by(col(RequestLog.created_at).desc())
            .offset((page - 1) * size)
            .limit(size)
        ).all()

        data = []
        for log in logs:
            data.append({
                "id": log.id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "model_requested": log.model_requested,
                "model_used": log.model_used,
                "provider": log.provider,
                "stream": log.stream,
                "status": log.status,
                "prompt_tokens": log.prompt_tokens,
                "completion_tokens": log.completion_tokens,
                "total_tokens": log.total_tokens,
                "latency_ms": log.latency_ms,
                "ttft_ms": log.ttft_ms,
                "session_id": log.session_id,
                "complexity_tier": log.complexity_tier,
            })
    finally:
        session.close()

    return {
        "success": True,
        "data": data,
        "meta": {
            "page": page,
            "size": size,
            "total": total,
        },
    }


# ─── Log Detail ───

@router.get("/logs/{log_id}")
async def get_log(log_id: str, request: Request):
    db_path = _get_db_path(request)
    session = get_session(db_path)
    try:
        log = session.get(RequestLog, log_id)
        if not log:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "Log not found"},
            )
        data = {
            "id": log.id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "model_requested": log.model_requested,
            "model_used": log.model_used,
            "provider": log.provider,
            "messages": log.messages,
            "temperature": log.temperature,
            "max_tokens": log.max_tokens,
            "stream": log.stream,
            "complexity_score": log.complexity_score,
            "complexity_tier": log.complexity_tier,
            "skills_injected": log.skills_injected,
            "response_content": log.response_content,
            "status": log.status,
            "error_message": log.error_message,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "total_tokens": log.total_tokens,
            "latency_ms": log.latency_ms,
            "ttft_ms": log.ttft_ms,
            "session_id": log.session_id,
            "user_tag": log.user_tag,
        }
    finally:
        session.close()

    return {"success": True, "data": data}


# ─── Health Check ───

@router.get("/health")
async def health():
    return {"status": "ok"}


# ─── Server config (read-only, for frontend display) ───

@router.get("/server-config")
async def server_config(request: Request):
    """Return non-sensitive server config so the frontend can display it."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return {"host": "127.0.0.1", "port": 7798, "ip_mode": "local_only", "allowed_ips": []}
    ip_cfg = settings.security.ip_whitelist
    return {
        "host": settings.server.host,
        "port": settings.server.port,
        "ip_mode": ip_cfg.mode,
        "allowed_ips": ip_cfg.allowed_ips,
    }


# ─── IP Whitelist CRUD ───

@router.get("/security/ip-whitelist")
async def get_ip_whitelist(
    request: Request,
    _auth: bool = Depends(verify_auth_token),
):
    """Return current IP whitelist configuration. Requires auth token."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return {"success": True, "data": {"enabled": True, "mode": "local_only", "allowed_ips": []}}

    ip_cfg = settings.security.ip_whitelist
    return {
        "success": True,
        "data": {
            "enabled": ip_cfg.enabled,
            "mode": ip_cfg.mode,
            "allowed_ips": ip_cfg.allowed_ips,
        },
    }


@router.put("/security/ip-whitelist")
async def update_ip_whitelist(
    body: dict,
    request: Request,
    _auth: bool = Depends(verify_auth_token),
):
    """Update IP whitelist mode and allowed IPs. Requires auth token.

    Accepted body fields:
      mode: "local_only" | "whitelist" | "open"
      allowed_ips: list[str]   (CIDR notation supported)
      enabled: bool
    """
    valid_modes = {"local_only", "whitelist", "open"}
    mode = body.get("mode")
    if mode is not None and mode not in valid_modes:
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": f"Invalid mode '{mode}'. Must be one of: {sorted(valid_modes)}"},
        )

    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        return JSONResponse(status_code=503, content={"success": False, "error": "Settings not available"})

    ip_cfg = settings.security.ip_whitelist
    if mode is not None:
        ip_cfg.mode = mode
    if "allowed_ips" in body:
        ip_cfg.allowed_ips = list(body["allowed_ips"])
    if "enabled" in body:
        ip_cfg.enabled = bool(body["enabled"])

    return {
        "success": True,
        "data": {
            "enabled": ip_cfg.enabled,
            "mode": ip_cfg.mode,
            "allowed_ips": ip_cfg.allowed_ips,
        },
    }

