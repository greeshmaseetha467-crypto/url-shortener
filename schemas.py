"""Pydantic v2 schemas used for request validation and response serialization."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class UserCreate(BaseModel):
    email: EmailStr
    # bcrypt has a hard 72-byte input limit; cap here so long passwords fail
    # validation with a clear 422 instead of an obscure hashing error.
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str | None = None
    exp: int | None = None


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------
class URLCreate(BaseModel):
    long_url: HttpUrl
    custom_alias: str | None = Field(
        default=None, min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$"
    )
    expires_at: datetime | None = None


class URLUpdate(BaseModel):
    long_url: HttpUrl | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


class URLOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    short_code: str
    long_url: str
    short_url: str
    click_count: int
    is_active: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class URLListOut(BaseModel):
    total: int
    items: list[URLOut]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
class ClickOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clicked_at: datetime
    ip_address: str | None
    user_agent: str | None
    referrer: str | None


class DailyClickCount(BaseModel):
    date: str
    count: int


class AnalyticsSummary(BaseModel):
    short_code: str
    long_url: str
    total_clicks: int
    created_at: datetime
    expires_at: datetime | None
    is_active: bool
    clicks_by_day: list[DailyClickCount]
    top_referrers: list[dict]
    top_user_agents: list[dict]
