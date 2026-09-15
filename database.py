"""
SQLAlchemy engine / session management.

`get_db` is a FastAPI dependency that yields a request-scoped session and
guarantees it is closed afterwards, even if an exception is raised.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# `pool_pre_ping` avoids using stale/dead connections from the pool, which
# matters in long-running production deployments behind load balancers.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
