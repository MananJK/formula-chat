"""
Health router — GET /health

Used by Docker health checks, uptime monitors, and Nginx upstream checks.
"""

import logging

import asyncpg
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

    overall = "ok" if all(v == "ok" for v in components.values()) else "degraded"
    return HealthResponse(status=overall, components=components)
