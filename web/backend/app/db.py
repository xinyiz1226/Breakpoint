"""Database engine/session wiring.

The engine and session factory are created lazily and cached so the
application only ever holds a single engine (and its connection pool) per
process, instead of creating one per request. Tests replace the ``get_db``
FastAPI dependency entirely, so the real engine is never constructed during
unit tests.
"""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
