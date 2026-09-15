"""
Test configuration.

- Points the app at a throwaway on-disk SQLite database (via env vars, set
  *before* the app is imported) instead of Postgres, so the suite runs with
  zero external services. Env vars must be set first because
  `app.config.get_settings()` is `lru_cache`d at import time.
- Uses `fakeredis` instead of a real Redis server, wired in through
  FastAPI's `dependency_overrides`.
- Tables are dropped/recreated around every test for full isolation.
"""
import os
import tempfile

_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp_db_path}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ENVIRONMENT", "test")
# Small redirect limit keeps the rate-limit test fast and deterministic;
# a high general API limit keeps unrelated tests (which fire many requests
# against /urls, /auth, etc.) from tripping the limiter incidentally.
os.environ.setdefault("RATE_LIMIT_REDIRECT_PER_MINUTE", "5")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "1000")

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.redis_client import get_redis  # noqa: E402


@pytest.fixture()
def db_session():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fake_redis():
    server = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield server


@pytest.fixture()
def client(db_session, fake_redis):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def registered_user(client):
    payload = {"email": "[email protected]", "password": "supersecret123"}
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201
    return payload


@pytest.fixture()
def auth_headers(client, registered_user):
    resp = client.post(
        "/auth/login",
        data={"username": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
