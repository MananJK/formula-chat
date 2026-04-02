"""
Health router — GET /health

Returns the status of each backend component (database, Redis, FastF1 cache).
Used by Docker health checks, uptime monitors, and Nginx upstream checks.
"""

import logging

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter

from app.config import settings
from app.models.schemas import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    components: dict[str, str] = {}

    # PostgreSQL
    try:
        conn = await asyncpg.connect(settings.database_url)
        await conn.execute("SELECT 1")
        await conn.close()
        components["postgres"] = "ok"
    except Exception as exc:
        logger.warning("Postgres health check failed: %s", exc)
        components["postgres"] = "unavailable"

    # Redis
    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        components["redis"] = "ok"
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        components["redis"] = "unavailable"

    # FastF1 cache dir
    import os
    components["fastf1_cache"] = (
        "ok" if os.path.isdir(settings.fastf1_cache_dir) else "missing"
    )

    overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"
    return HealthResponse(status=overall, components=components)
