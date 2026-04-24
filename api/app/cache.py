import logging
import json
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    global _redis_client
    _redis_client = redis.from_url(
        settings.redis_url,
        decode_responses=False,
        encoding="utf-8",
    )
    await _redis_client.ping()
    logger.info("Redis connection established")
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis connection closed")


def get_redis() -> redis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return _redis_client


async def cache_get(key: str) -> dict[str, Any] | None:
    try:
        data = await get_redis().get(key)
        if data:
            return json.loads(data)
    except Exception as exc:
        logger.warning("Cache get failed for key %s: %s", key, exc)
    return None


async def cache_set(key: str, value: dict[str, Any], ttl: int) -> bool:
    try:
        await get_redis().setex(key, ttl, json.dumps(value))
        return True
    except Exception as exc:
        logger.warning("Cache set failed for key %s: %s", key, exc)
        return False


async def cache_delete(key: str) -> bool:
    try:
        await get_redis().delete(key)
        return True
    except Exception as exc:
        logger.warning("Cache delete failed for key %s: %s", key, exc)
        return False