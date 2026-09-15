"""Database access layer - keeps raw SQLAlchemy queries out of the routers."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.utils import generate_short_code

settings = get_settings()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def get_user_by_email(db: Session, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def create_user(db: Session, email: str, hashed_password: str) -> models.User:
    user = models.User(email=email, hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
def get_url_by_code(db: Session, short_code: str) -> models.URL | None:
    return db.query(models.URL).filter(models.URL.short_code == short_code).first()


def get_url_owned(db: Session, short_code: str, owner_id: uuid.UUID) -> models.URL | None:
    return (
        db.query(models.URL)
        .filter(models.URL.short_code == short_code, models.URL.owner_id == owner_id)
        .first()
    )


def _unique_short_code(db: Session) -> str:
    for _ in range(5):
        code = generate_short_code(settings.short_code_length)
        if not get_url_by_code(db, code):
            return code
    # Extremely unlikely fallback: widen the search space.
    for _ in range(5):
        code = generate_short_code(settings.short_code_length + 2)
        if not get_url_by_code(db, code):
            return code
    raise RuntimeError("Unable to generate a unique short code")


def create_url(
    db: Session,
    long_url: str,
    owner_id: uuid.UUID | None,
    custom_alias: str | None = None,
    expires_at: datetime | None = None,
) -> models.URL:
    if custom_alias:
        if get_url_by_code(db, custom_alias):
            raise ValueError("That custom alias is already taken")
        short_code = custom_alias
    else:
        short_code = _unique_short_code(db)

    url = models.URL(
        short_code=short_code,
        long_url=long_url,
        owner_id=owner_id,
        expires_at=expires_at,
    )
    db.add(url)
    db.commit()
    db.refresh(url)
    return url


def list_urls_for_user(
    db: Session, owner_id: uuid.UUID, skip: int = 0, limit: int = 50
) -> tuple[int, list[models.URL]]:
    query = db.query(models.URL).filter(models.URL.owner_id == owner_id).order_by(
        models.URL.created_at.desc()
    )
    total = query.count()
    items = query.offset(skip).limit(limit).all()
    return total, items


def update_url(db: Session, url: models.URL, **fields) -> models.URL:
    for key, value in fields.items():
        if value is not None:
            setattr(url, key, value)
    db.commit()
    db.refresh(url)
    return url


def delete_url(db: Session, url: models.URL) -> None:
    db.delete(url)
    db.commit()


def increment_click_count(db: Session, url: models.URL) -> None:
    url.click_count += 1
    db.commit()


# ---------------------------------------------------------------------------
# Clicks / analytics
# ---------------------------------------------------------------------------
def record_click(
    db: Session,
    url_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
    referrer: str | None,
) -> models.Click:
    click = models.Click(
        url_id=url_id, ip_address=ip_address, user_agent=user_agent, referrer=referrer
    )
    db.add(click)
    db.commit()
    return click


def clicks_by_day(db: Session, url_id: uuid.UUID, days: int = 30) -> list[tuple[str, int]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            func.date(models.Click.clicked_at).label("day"),
            func.count(models.Click.id).label("count"),
        )
        .filter(models.Click.url_id == url_id, models.Click.clicked_at >= since)
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [(str(row.day), row.count) for row in rows]


def top_referrers(db: Session, url_id: uuid.UUID, limit: int = 5) -> list[tuple[str, int]]:
    rows = (
        db.query(models.Click.referrer, func.count(models.Click.id).label("count"))
        .filter(models.Click.url_id == url_id, models.Click.referrer.isnot(None))
        .group_by(models.Click.referrer)
        .order_by(func.count(models.Click.id).desc())
        .limit(limit)
        .all()
    )
    return [(row.referrer, row.count) for row in rows]


def top_user_agents(db: Session, url_id: uuid.UUID, limit: int = 5) -> list[tuple[str, int]]:
    rows = (
        db.query(models.Click.user_agent, func.count(models.Click.id).label("count"))
        .filter(models.Click.url_id == url_id, models.Click.user_agent.isnot(None))
        .group_by(models.Click.user_agent)
        .order_by(func.count(models.Click.id).desc())
        .limit(limit)
        .all()
    )
    return [(row.user_agent, row.count) for row in rows]
