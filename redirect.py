"""
The redirect endpoint is the highest-traffic route in a URL shortener, so
it is optimized to avoid a database round trip on cache hits:

  1. Look up `url:{code}` in Redis -> if present, use it directly.
  2. On a miss, query Postgres, then populate the cache (TTL below).
  3. Click analytics are written to Postgres synchronously for simplicity
     and correctness (guaranteed durability of the click record); at very
     high scale this write would typically move to an async queue
     (Kafka/Redis Streams) so it never blocks the redirect response - noted
     in the README as a scaling option.
  4. The denormalized `click_count` on the URL row is also incremented so
     simple counts don't require aggregating the `clicks` table.
"""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app import crud
from app.config import get_settings
from app.database import get_db
from app.rate_limiter import rate_limit
from app.redis_client import get_redis

router = APIRouter(tags=["redirect"])
settings = get_settings()

CACHE_TTL_SECONDS = 3600


def _cache_payload(url) -> str:
    return json.dumps(
        {
            "id": str(url.id),
            "long_url": url.long_url,
            "is_active": url.is_active,
            "expires_at": url.expires_at.isoformat() if url.expires_at else None,
        }
    )


def _is_expired(expires_at_iso: str | None) -> bool:
    if expires_at_iso is None:
        return False
    expires_at = datetime.fromisoformat(expires_at_iso)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


@router.get(
    "/{short_code}",
    dependencies=[Depends(rate_limit("redirect", limit_per_minute=settings.rate_limit_redirect_per_minute))],
)
async def redirect_to_long_url(
    short_code: str,
    request: Request,
    db: Session = Depends(get_db),
    redis_conn: Redis = Depends(get_redis),
):
    cache_key = f"url:{short_code}"
    cached = await redis_conn.get(cache_key)

    if cached is not None:
        # --- Cache hit: no DB read needed to resolve the redirect ---
        record = json.loads(cached)
        url_id = uuid.UUID(record["id"])
        long_url = record["long_url"]
        if not record["is_active"]:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has been deactivated")
        if _is_expired(record["expires_at"]):
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has expired")
    else:
        # --- Cache miss: fall back to Postgres and repopulate the cache ---
        url = crud.get_url_by_code(db, short_code)
        if url is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
        await redis_conn.set(cache_key, _cache_payload(url), ex=CACHE_TTL_SECONDS)
        if not url.is_active:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has been deactivated")
        if url.is_expired():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="This link has expired")
        url_id = url.id
        long_url = url.long_url

    # Click analytics + denormalized counter are still written synchronously
    # to Postgres for durability (see module docstring for the async-queue
    # alternative at very high scale).
    crud.record_click(
        db,
        url_id=url_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        referrer=request.headers.get("referer"),
    )
    db.query(crud.models.URL).filter(crud.models.URL.id == url_id).update(
        {crud.models.URL.click_count: crud.models.URL.click_count + 1}
    )
    db.commit()

    return RedirectResponse(url=long_url, status_code=status.HTTP_302_FOUND)
