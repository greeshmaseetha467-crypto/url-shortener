"""
Redis-backed rate limiting.

Implements a fixed-window counter per client per route-group:
  key = "rl:{scope}:{client_id}:{window_start_epoch_minute}"
  INCR key; if this is the first hit in the window, set a 60s TTL.

Fixed-window is simple, O(1) per request, and accurate enough for API
rate limiting; a sliding-window-log or token-bucket could be swapped in
behind the same dependency interface if stricter smoothing is needed.

The client identity is the authenticated user id when available, else the
caller's IP address, so anonymous traffic is still throttled per-source.
"""
import time

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.config import get_settings
from app.redis_client import get_redis

settings = get_settings()


def _client_identifier(request: Request) -> str:
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        # Bucket by token rather than decoding it here (decoding happens in
        # the auth dependency); this is sufficient to key a rate limit.
        return f"token:{auth_header[7:][:32]}"
    if request.client:
        return f"ip:{request.client.host}"
    return "anonymous"


def rate_limit(scope: str, limit_per_minute: int | None = None):
    """Returns a FastAPI dependency that enforces `limit_per_minute` requests
    per rolling 60s window for the given `scope` (e.g. "api", "redirect")."""

    async def _dependency(request: Request, redis_conn: Redis = Depends(get_redis)):
        limit = limit_per_minute or settings.rate_limit_per_minute
        client_id = _client_identifier(request)
        window = int(time.time() // 60)
        key = f"rl:{scope}:{client_id}:{window}"

        current = await redis_conn.incr(key)
        if current == 1:
            await redis_conn.expire(key, 60)

        if current > limit:
            ttl = await redis_conn.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please slow down.",
                headers={"Retry-After": str(max(ttl, 1))},
            )

    return _dependency
