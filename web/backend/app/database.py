from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    return create_async_engine(settings.database_url, echo=False)


def _create_session_factory(eng):
    return async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    eng = _create_engine()
    session_factory = _create_session_factory(eng)
    async with session_factory() as session:
        yield session
