"""Shared pytest fixtures: an in-memory SQLite database, fake storage/email
services wired in via FastAPI dependency overrides, and a TestClient.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.deps import get_email_sender, get_storage
from app.main import app
from app.models.enums import UserRole
from app.models.user import User
from app.security import hash_password
from tests.fakes import FakeEmailSender, FakeObjectStorage


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite:///:memory:",
        jwt_secret_key="test-jwt-secret-key-at-least-32-bytes-long",
        refresh_cookie_secure=False,
        default_max_active_analysis_jobs=1,
        default_monthly_analysis_seconds=36000,
        max_upload_size_bytes=20 * 1024 * 1024 * 1024,
        max_video_duration_seconds=3 * 60 * 60,
        app_base_url="http://localhost:3000",
        cors_allow_origins=["http://localhost:3000"],
    )


@pytest.fixture
def engine():
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture
def db_session(session_factory) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_email_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def fake_storage() -> FakeObjectStorage:
    return FakeObjectStorage()


@pytest.fixture
def client(
    session_factory: sessionmaker,
    test_settings: Settings,
    fake_email_sender: FakeEmailSender,
    fake_storage: FakeObjectStorage,
) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_email_sender] = lambda: fake_email_sender
    app.dependency_overrides[get_storage] = lambda: fake_storage

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    role: UserRole = UserRole.USER,
    is_verified: bool = True,
    is_active: bool = True,
) -> User:
    """Insert a ready-to-use user directly, bypassing the register/verify
    HTTP flow, for tests that only need an authenticated actor."""
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_verified=is_verified,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client: TestClient, *, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}
