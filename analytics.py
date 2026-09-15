from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import get_current_user
from app.database import get_db
from app.models import Click, User
from app.rate_limiter import rate_limit

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_owned_url_or_404(db: Session, short_code: str, user: User):
    url = crud.get_url_owned(db, short_code, user.id)
    if not url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Short URL not found")
    return url


@router.get(
    "/{short_code}",
    response_model=schemas.AnalyticsSummary,
    dependencies=[Depends(rate_limit("api"))],
)
def get_analytics_summary(
    short_code: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = _get_owned_url_or_404(db, short_code, current_user)

    by_day = crud.clicks_by_day(db, url.id, days=days)
    referrers = crud.top_referrers(db, url.id)
    user_agents = crud.top_user_agents(db, url.id)

    return schemas.AnalyticsSummary(
        short_code=url.short_code,
        long_url=url.long_url,
        total_clicks=url.click_count,
        created_at=url.created_at,
        expires_at=url.expires_at,
        is_active=url.is_active,
        clicks_by_day=[schemas.DailyClickCount(date=d, count=c) for d, c in by_day],
        top_referrers=[{"referrer": r or "(direct)", "count": c} for r, c in referrers],
        top_user_agents=[{"user_agent": ua, "count": c} for ua, c in user_agents],
    )


@router.get(
    "/{short_code}/clicks",
    response_model=list[schemas.ClickOut],
    dependencies=[Depends(rate_limit("api"))],
)
def get_raw_clicks(
    short_code: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    url = _get_owned_url_or_404(db, short_code, current_user)
    clicks = (
        db.query(Click)
        .filter(Click.url_id == url.id)
        .order_by(Click.clicked_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return clicks
