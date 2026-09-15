from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user, get_current_user_optional
from app.config import get_settings
from app.database import get_db
from app.models import User
from app.rate_limiter import rate_limit
from app.redis_client import get_redis

router = APIRouter(prefix="/urls", tags=["urls"])
settings = get_settings()

CACHE_TTL_SECONDS = 3600


def _to_out(url) -> schemas.URLOut:
    """Builds the response model, adding the computed `short_url` field
    (base_url + short_code) that doesn't exist as a DB column."""
    return schemas.URLOut(
        id=url.id,
        short_code=url.short_code,
        long_url=url.long_url,
        short_url=f"{settings.base_url.rstrip('/')}/{url.short_code}",
        click_count=url.click_count,
        is_active=url.is_active,
        expires_at=url.expires_at,
        created_at=url.created_at,
        updated_at=url.updated_at,
    )


@router.post(
    "",
    response_model=schemas.URLOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("api"))],
)
def create_short_url(
    payload: schemas.URLCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """Create a short URL. Works for both authenticated users (link is
    owned by them, appears in their dashboard/analytics) and anonymous
    callers (link works, but has no owner and can't be listed/managed)."""
    try:
        url = crud.create_url(
            db,
            long_url=str(payload.long_url),
            owner_id=current_user.id if current_user else None,
            custom_alias=payload.custom_alias,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return _to_out(url)


@router.get("", response_model=schemas.URLListOut, dependencies=[Depends(rate_limit("api"))])
def list_my_urls(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total, items = crud.list_urls_for_user(db, current_user.id, skip=skip, limit=limit)
    return schemas.URLListOut(total=total, items=[_to_out(u) for u in items])


@router.get("/{short_code}", response_model=schemas.URLOut, dependencies=[Depends(rate_limit("api"))])
def get_url_details(
    short_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = crud.get_url_owned(db, short_code, current_user.id)
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
    return _to_out(url)


@router.put("/{short_code}", response_model=schemas.URLOut, dependencies=[Depends(rate_limit("api"))])
async def update_short_url(
    short_code: str,
    payload: schemas.URLUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis_conn: Redis = Depends(get_redis),
):
    url = crud.get_url_owned(db, short_code, current_user.id)
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")

    updated = crud.update_url(
        db,
        url,
        long_url=str(payload.long_url) if payload.long_url else None,
        is_active=payload.is_active,
        expires_at=payload.expires_at,
    )
    # Invalidate the redirect cache since long_url/is_active may have changed.
    await redis_conn.delete(f"url:{short_code}")
    return _to_out(updated)


@router.delete("/{short_code}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(rate_limit("api"))])
async def delete_short_url(
    short_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis_conn: Redis = Depends(get_redis),
):
    url = crud.get_url_owned(db, short_code, current_user.id)
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
    crud.delete_url(db, url)
    await redis_conn.delete(f"url:{short_code}")
