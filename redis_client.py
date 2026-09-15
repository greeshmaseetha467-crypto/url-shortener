"""
Redis connection management.

A single connection pool is created at import time and reused across
requests. Tests override `get_redis` with a `fakeredis` instance so the
suite doesn't require a real Redis server.
"""
import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

redis_pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> redis.Redis:
    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()
