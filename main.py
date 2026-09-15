"""
FastAPI application entrypoint.

Route layout:
  POST   /auth/register              create an account
  POST   /auth/login                 obtain a JWT access token
  POST   /urls                       create a short URL (auth optional)
  GET    /urls                       list the current user's URLs
  GET    /urls/{short_code}          get details of an owned URL
  PUT    /urls/{short_code}          update an owned URL
  DELETE /urls/{short_code}          delete an owned URL
  GET    /analytics/{short_code}     aggregated click analytics
  GET    /analytics/{short_code}/clicks   raw click log
  GET    /health                     liveness/readiness probe
  GET    /{short_code}               redirect to the long URL (public, hot path)
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import analytics, redirect, urls
from app.routers import auth as auth_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In production, prefer Alembic migrations over create_all. This is
    # kept for local/dev convenience and for the test suite.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="A production-style URL shortener with auth, analytics, caching and rate limiting.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


# Order matters: `/{short_code}` in the redirect router is a single-segment
# catch-all GET, so it must be included *last* - after every other route,
# including `/health` above - to avoid shadowing more specific routes like
# `/urls`, `/analytics/...`, or `/health` itself.
app.include_router(auth_router.router)
app.include_router(urls.router)
app.include_router(analytics.router)
app.include_router(redirect.router)
