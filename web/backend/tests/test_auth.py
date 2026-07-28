from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import RefreshSession
from app.models.user import User
from tests.conftest import auth_headers
from tests.fakes import FakeEmailSender

EMAIL = "player@example.com"
PASSWORD = "correct-horse-battery"


def _register_and_get_verify_token(client: TestClient, fake_email_sender: FakeEmailSender) -> str:
    response = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 201, response.text
    assert fake_email_sender.last_email.to_address == EMAIL
    return fake_email_sender.last_email.token


def test_register_sends_verification_email_and_creates_unverified_user(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    _register_and_get_verify_token(client, fake_email_sender)

    user = db_session.execute(select(User).where(User.email == EMAIL)).scalar_one()
    assert user.is_verified is False


def test_register_duplicate_email_for_verified_account_is_rejected(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})

    response = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 409


def test_register_again_for_unverified_account_resends_a_fresh_verification_token(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    first_token = _register_and_get_verify_token(client, fake_email_sender)

    response = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 201, response.text
    assert len(fake_email_sender.sent_emails) == 2
    second_token = fake_email_sender.last_email.token
    assert second_token != first_token

    # The stale token from the first attempt was invalidated by the retry.
    stale_verify = client.post("/api/v1/auth/verify-email", json={"token": first_token})
    assert stale_verify.status_code == 400

    fresh_verify = client.post("/api/v1/auth/verify-email", json={"token": second_token})
    assert fresh_verify.status_code == 200

    # No duplicate account was created.
    users = db_session.execute(select(User).where(User.email == EMAIL)).scalars().all()
    assert len(users) == 1


def test_register_recovers_after_smtp_failure_via_retry(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    fake_email_sender.fail_next_sends = 1
    failed_response = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert failed_response.status_code == 503

    # The account exists (unverified) even though the email never sent, so
    # the registrant is not stranded behind an unrecoverable 409.
    users = db_session.execute(select(User).where(User.email == EMAIL)).scalars().all()
    assert len(users) == 1
    assert users[0].is_verified is False
    assert fake_email_sender.sent_emails == []

    retry_response = client.post("/api/v1/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert retry_response.status_code == 201, retry_response.text
    assert len(fake_email_sender.sent_emails) == 1

    token = fake_email_sender.last_email.token
    verify_response = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify_response.status_code == 200

    users_after = db_session.execute(select(User).where(User.email == EMAIL)).scalars().all()
    assert len(users_after) == 1


def test_login_before_verification_is_rejected(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    _register_and_get_verify_token(client, fake_email_sender)
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 403


def test_verify_then_login_succeeds_and_sets_refresh_cookie(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)

    verify_response = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verify_response.status_code == 200

    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200, login_response.text
    body = login_response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == EMAIL
    assert "bp_refresh_token" in login_response.cookies


def test_verify_email_rejects_invalid_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400


def test_verify_email_rejects_reused_token(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    first = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400


def test_login_rejects_wrong_password(client: TestClient, fake_email_sender: FakeEmailSender) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})

    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert response.status_code == 401


def test_refresh_rotates_token_and_revokes_the_old_one(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200

    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200, refresh_response.text
    assert refresh_response.json()["token_type"] == "bearer"

    sessions = db_session.execute(select(RefreshSession)).scalars().all()
    assert len(sessions) == 2
    revoked = [s for s in sessions if s.revoked_at is not None]
    active = [s for s in sessions if s.revoked_at is None]
    assert len(revoked) == 1
    assert len(active) == 1
    assert revoked[0].replaced_by_id == active[0].id

    # Retrying refresh with the (now revoked) client cookie jar's original
    # cookie would fail, but the client's cookie jar has already been
    # updated to the new token by the Set-Cookie response header, so this
    # call exercises rotation again rather than reuse.
    second_refresh = client.post("/api/v1/auth/refresh")
    assert second_refresh.status_code == 200


def test_refresh_without_cookie_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


def test_reused_revoked_refresh_token_is_rejected(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    original_cookie_value = client.cookies.get("bp_refresh_token")
    client.post("/api/v1/auth/refresh")  # rotates; cookie jar now holds the new token

    # Manually replay the original (now-revoked) refresh cookie.
    client.cookies.set("bp_refresh_token", original_cookie_value)
    replay_response = client.post("/api/v1/auth/refresh")
    assert replay_response.status_code == 401


def test_logout_revokes_session_and_clears_cookie(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200

    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


def test_forgot_password_returns_generic_message_for_unknown_email(client: TestClient) -> None:
    known_response = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert known_response.status_code == 200
    generic_message = known_response.json()["message"]
    assert "reset link has been sent" in generic_message


def test_forgot_password_and_reset_revokes_all_sessions(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200

    forgot_response = client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    assert forgot_response.status_code == 200
    same_generic_message = forgot_response.json()["message"]
    unknown_response = client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    assert unknown_response.json()["message"] == same_generic_message

    reset_token = fake_email_sender.last_email.token
    new_password = "new-correct-horse"
    reset_response = client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": new_password}
    )
    assert reset_response.status_code == 200

    # All refresh sessions issued before the reset are now revoked.
    sessions = db_session.execute(select(RefreshSession)).scalars().all()
    assert all(session.revoked_at is not None for session in sessions)

    # Old password no longer works; new password does.
    old_login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert old_login.status_code == 401
    new_login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": new_password})
    assert new_login.status_code == 200


def test_protected_endpoint_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_protected_endpoint_accepts_valid_bearer_token(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    access_token = login_response.json()["access_token"]

    response = client.get("/api/v1/projects", headers=auth_headers(access_token))
    assert response.status_code == 200
    assert response.json() == []
