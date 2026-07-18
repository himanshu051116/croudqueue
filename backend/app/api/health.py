"""Liveness and readiness probes for CrowdCue."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_db

router = APIRouter(prefix="/api/health", tags=["Health"])
logger = logging.getLogger(__name__)


@router.get("/live")
async def health_live() -> dict[str, Any]:
    """Return process liveness without consulting external dependencies."""

    return {
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready")
async def health_ready(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Require PostgreSQL; report optional Redis without failing readiness."""

    details: dict[str, str] = {
        "database": "DISCONNECTED",
        "redis": "DISCONNECTED",
    }
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            details["database"] = "CONNECTED"
    except Exception:
        logger.exception("Database readiness check failed")

    redis_client = aioredis.from_url(  # type: ignore[no-untyped-call]
        settings.REDIS_URL, socket_timeout=3.0
    )
    try:
        if await redis_client.ping():
            details["redis"] = "CONNECTED"
    except Exception:
        logger.exception("Redis readiness check failed")
    finally:
        await redis_client.aclose()

    if details["database"] != "CONNECTED" or (
        settings.REDIS_REQUIRED and details["redis"] != "CONNECTED"
    ):
        raise HTTPException(
            status_code=503,
            detail={"status": "UNAVAILABLE", "components": details},
        )
    return {
        "status": "OK",
        "components": details,
        "optional_components": [] if settings.REDIS_REQUIRED else ["redis"],
    }
