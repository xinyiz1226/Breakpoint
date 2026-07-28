from __future__ import annotations

import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import EmailToken, RefreshSession
from app.models.base import utcnow
from app.models.user import User
from app.routers import auth
from app.schemas.auth import ResetPasswordRequest
from app.security import hash_token
from tests.conftest import auth_headers
from tests.fakes import FakeEmailSender

EMAIL = "player@example.com"
PASSWORD = "correct-horse-battery"


def _register_and_get_verify_token(client: TestClient, fake_email_sender: FakeEmailSender) -> str:
    response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert response.status_code == 201, response.text
    assert fake_email_sender.last_email.to_address == EMAIL
    return fake_email_sender.last_email.token


def test_register_rejects_extra_password_field_and_creates_nothing(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    # A legacy/attacker-supplied `password` alongside `email` must be
    # rejected outright, not silently ignored -- registration never
    # accepts, hashes, or binds a password (see VerifyEmailRequest, where
    # the mailbox owner alone chooses the eventual credential).
    response = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": "attacker-chosen-pw"}
    )
    assert response.status_code == 422, response.text

    assert fake_email_sender.sent_emails == []
    assert db_session.execute(select(User).where(User.email == EMAIL)).scalar_one_or_none() is None
    assert db_session.execute(select(EmailToken)).scalars().all() == []


def test_register_email_only_still_succeeds(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert response.status_code == 201, response.text


def test_register_request_schema_forbids_additional_properties() -> None:
    from app.main import app

    schema = app.openapi()["components"]["schemas"]["RegisterRequest"]
    assert schema.get("additionalProperties") is False


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
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})

    response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert response.status_code == 409


def test_register_again_for_unverified_account_resends_a_fresh_verification_token(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    first_token = _register_and_get_verify_token(client, fake_email_sender)

    response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert response.status_code == 201, response.text
    assert len(fake_email_sender.sent_emails) == 2
    second_token = fake_email_sender.last_email.token
    assert second_token != first_token

    # The stale token from the first attempt was invalidated by the retry.
    stale_verify = client.post("/api/v1/auth/verify-email", json={"token": first_token, "password": PASSWORD})
    assert stale_verify.status_code == 400

    fresh_verify = client.post("/api/v1/auth/verify-email", json={"token": second_token, "password": PASSWORD})
    assert fresh_verify.status_code == 200

    # No duplicate account was created.
    users = db_session.execute(select(User).where(User.email == EMAIL)).scalars().all()
    assert len(users) == 1


def test_register_recovers_after_smtp_failure_via_retry(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    fake_email_sender.fail_next_sends = 1
    failed_response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert failed_response.status_code == 503

    # The account exists (unverified) even though the email never sent, so
    # the registrant is not stranded behind an unrecoverable 409.
    users = db_session.execute(select(User).where(User.email == EMAIL)).scalars().all()
    assert len(users) == 1
    assert users[0].is_verified is False
    assert fake_email_sender.sent_emails == []

    retry_response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert retry_response.status_code == 201, retry_response.text
    assert len(fake_email_sender.sent_emails) == 1

    token = fake_email_sender.last_email.token
    verify_response = client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    assert verify_response.status_code == 200

    users_after = db_session.execute(select(User).where(User.email == EMAIL)).scalars().all()
    assert len(users_after) == 1


def test_login_before_verification_is_rejected(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    """Before verification there is no submitted password to match at
    all -- the account's real password_hash is an unguessable placeholder
    -- so login fails on password mismatch (401), not just an is_verified
    gate."""
    _register_and_get_verify_token(client, fake_email_sender)
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 401


def test_verify_then_login_succeeds_and_sets_refresh_cookie(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)

    verify_response = client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    assert verify_response.status_code == 200

    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200, login_response.text
    body = login_response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == EMAIL
    assert "bp_refresh_token" in login_response.cookies


def test_verify_email_rejects_invalid_token(client: TestClient) -> None:
    response = client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token", "password": PASSWORD})
    assert response.status_code == 400


def test_verify_email_rejects_reused_token(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    first = client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    assert second.status_code == 400


def test_login_rejects_wrong_password(client: TestClient, fake_email_sender: FakeEmailSender) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})

    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "wrong-password"})
    assert response.status_code == 401


def test_refresh_rotates_token_and_revokes_the_old_one(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
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
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
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
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200

    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 401


def test_logout_with_stale_pre_rotation_token_revokes_entire_session_family(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session, test_settings
) -> None:
    """logout must identify the user from *any* RefreshSession matching the
    presented token hash -- active or already revoked -- and then revoke
    every active session for that user, not just the one session matching
    the presented (possibly stale, pre-rotation) token. Presenting a
    revoked predecessor must not leave a rotated successor session usable.
    """
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200
    stale_token_a = client.cookies.get(test_settings.refresh_cookie_name)
    assert stale_token_a is not None

    # Rotate: the cookie jar now holds the fresh token B, and A is revoked.
    refresh_response = client.post("/api/v1/auth/refresh")
    assert refresh_response.status_code == 200, refresh_response.text
    current_token_b = client.cookies.get(test_settings.refresh_cookie_name)
    assert current_token_b is not None
    assert current_token_b != stale_token_a

    # Present the stale, already-revoked predecessor token to logout.
    client.cookies.set(test_settings.refresh_cookie_name, stale_token_a)
    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200

    # The rotated successor (B), which logout never directly saw, must now
    # be rejected too -- the whole session family for this user was
    # revoked, not just the stale token's own row.
    client.cookies.set(test_settings.refresh_cookie_name, current_token_b)
    refresh_after_logout = client.post("/api/v1/auth/refresh")
    assert refresh_after_logout.status_code == 401

    sessions = db_session.execute(select(RefreshSession)).scalars().all()
    assert len(sessions) == 2
    assert all(session.revoked_at is not None for session in sessions)


def test_logout_with_current_token_or_unknown_token_remains_safe(
    client: TestClient, fake_email_sender: FakeEmailSender, test_settings
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    # Logging out with the current, still-active token remains a normal
    # idempotent success.
    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    assert test_settings.refresh_cookie_name not in logout_response.cookies

    # A wholly unknown token is also a safe, idempotent success.
    client.cookies.set(test_settings.refresh_cookie_name, "unknown-token-value")
    unknown_logout_response = client.post("/api/v1/auth/logout")
    assert unknown_logout_response.status_code == 200


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
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
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
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    access_token = login_response.json()["access_token"]

    response = client.get("/api/v1/projects", headers=auth_headers(access_token))
    assert response.status_code == 200
    assert response.json() == []


def test_attacker_registered_email_cannot_choose_owners_password(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    """register never accepts a password at all, so an attacker who
    registers an email they do not control cannot pre-choose the
    eventual credential. The real mailbox owner re-registering (a
    resend, not a password choice) and then verifying with the latest
    token, supplying their own chosen password, is the only way the
    account ever gets a usable password. The stale token from the first
    registration attempt must be dead.
    """
    owner_password = "owner-chosen-password-B"

    register_a = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert register_a.status_code == 201, register_a.text
    stale_token = fake_email_sender.last_email.token

    register_b = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert register_b.status_code == 201, register_b.text
    latest_token = fake_email_sender.last_email.token
    assert latest_token != stale_token

    verify_response = client.post(
        "/api/v1/auth/verify-email", json={"token": latest_token, "password": owner_password}
    )
    assert verify_response.status_code == 200, verify_response.text

    # The stale token from the first (attacker's) registration attempt is
    # dead and cannot be used to choose any password.
    stale_verify = client.post(
        "/api/v1/auth/verify-email",
        json={"token": stale_token, "password": "attacker-chosen-password-A"},
    )
    assert stale_verify.status_code == 400

    # Only the mailbox owner's chosen password logs in.
    attacker_login = client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": "attacker-chosen-password-A"},
    )
    assert attacker_login.status_code == 401

    owner_login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": owner_password})
    assert owner_login.status_code == 200, owner_login.text

    # A further unauthenticated re-registration attempt after verification
    # is rejected outright (already verified) and cannot affect the
    # chosen password either way.
    repeat_register = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert repeat_register.status_code == 409
    still_owner_login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": owner_password})
    assert still_owner_login.status_code == 200

    user = db_session.execute(select(User).where(User.email == EMAIL)).scalar_one()
    assert user.is_verified is True


def test_verify_before_re_registration_uses_the_only_submitted_password(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    """A single registration (no re-registration race) still works: the
    one password submitted at verify time is what ends up usable."""
    token = _register_and_get_verify_token(client, fake_email_sender)
    verify_response = client.post(
        "/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD}
    )
    assert verify_response.status_code == 200

    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200, login_response.text


def test_unverified_user_cannot_login_even_with_registered_password(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    """Before verification, the account's real password_hash is a random,
    unusable placeholder -- not derived from any submitted password."""
    _register_and_get_verify_token(client, fake_email_sender)
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 401


# --- Registration/mailbox password authority contract ------------------------
#
# Registration proves nothing but "I want to send a verification email to
# this address" -- it must never accept, hash, store, or bind a password.
# The password is chosen only when the verification token is consumed, so
# whoever controls the mailbox -- not whoever first (or last) POSTs to
# /register -- controls the account's eventual credential.


def test_register_is_email_only_and_verify_requires_chosen_password(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    """register accepts only an email (no password field at all) and
    creates an unverified account with an unguessable placeholder
    password_hash. The mailbox owner's password is submitted only at
    verify-email, alongside the token, and that is what ends up usable."""
    register_response = client.post("/api/v1/auth/register", json={"email": EMAIL})
    assert register_response.status_code == 201, register_response.text
    assert fake_email_sender.last_email.to_address == EMAIL
    token = fake_email_sender.last_email.token

    user = db_session.execute(select(User).where(User.email == EMAIL)).scalar_one()
    assert user.is_verified is False
    # The placeholder hash is not derived from anything an unauthenticated
    # caller submitted, and login is blocked for unverified accounts
    # regardless -- there is no password that logs in yet.
    login_before_verify = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    assert login_before_verify.status_code == 401

    verify_response = client.post(
        "/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD}
    )
    assert verify_response.status_code == 200, verify_response.text

    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200, login_response.text


def test_reset_password_invalidates_all_sibling_reset_tokens(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})

    client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    first_reset_token = fake_email_sender.last_email.token
    client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    second_reset_token = fake_email_sender.last_email.token
    assert first_reset_token != second_reset_token

    consume_response = client.post(
        "/api/v1/auth/reset-password",
        json={"token": second_reset_token, "new_password": "brand-new-password-1"},
    )
    assert consume_response.status_code == 200, consume_response.text

    # The other outstanding, never-used RESET_PASSWORD token for the same
    # user is invalidated in the same locked transaction.
    stale_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": first_reset_token, "new_password": "attacker-password"},
    )
    assert stale_reset.status_code == 400

    login_response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "brand-new-password-1"}
    )
    assert login_response.status_code == 200


def test_refresh_locks_user_row_before_revalidating_session(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session, engine
) -> None:
    """Refresh must identify the user via a non-locking session lookup,
    then lock the User row, then re-select/revalidate the session -- so a
    concurrent reset (which locks the user first) always serializes ahead
    of or behind a refresh rather than racing it. This inspects statement
    order directly since SQLite cannot exercise real lock contention.
    """
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    touched_tables: list[str] = []

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        upper = statement.upper()
        if "SELECT" in upper:
            if "REFRESH_SESSIONS" in upper:
                touched_tables.append("refresh_sessions")
            elif "FROM USERS" in upper or "USERS " in upper.split("FROM", 1)[-1][:20]:
                touched_tables.append("users")

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        refresh_response = client.post("/api/v1/auth/refresh")
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)

    assert refresh_response.status_code == 200, refresh_response.text
    assert "refresh_sessions" in touched_tables
    assert "users" in touched_tables
    first_session_index = touched_tables.index("refresh_sessions")
    first_user_index = touched_tables.index("users")
    # The initial (non-locking) session lookup happens before the user lock.
    assert first_session_index < first_user_index


def test_forgot_password_locks_user_before_touching_reset_tokens(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session, engine
) -> None:
    """forgot_password must identify the user via a non-locking lookup by
    email, then lock the User row -- the same serialization point
    login/refresh/reset use -- before invalidating stale tokens or minting
    a new one, so it can never interleave inside a concurrent reset
    transaction. Inspects statement order directly since SQLite cannot
    exercise real lock contention.
    """
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})

    touched_tables: list[str] = []

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        upper = statement.upper()
        if "FROM USERS" in upper:
            touched_tables.append("users")
        elif "EMAIL_TOKENS" in upper:
            touched_tables.append("email_tokens")

    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        response = client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)

    assert response.status_code == 200
    # Identify (non-locking) then lock: two separate touches of "users"
    # before anything touches email_tokens.
    assert touched_tables.count("users") >= 2
    first_email_token_index = touched_tables.index("email_tokens")
    assert touched_tables[:2] == ["users", "users"]
    assert first_email_token_index > 1


def test_forgot_password_after_reset_mints_independent_post_reset_token(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    """A forgot-password request issued after a reset has already
    completed must still work (mint a fresh, independently valid token)
    without any leftover interaction from the finished reset -- it simply
    cannot interleave with an in-progress one.
    """
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})

    client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    first_reset_token = fake_email_sender.last_email.token
    first_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": first_reset_token, "new_password": "post-reset-password-1"},
    )
    assert first_reset.status_code == 200, first_reset.text

    second_response = client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    assert second_response.status_code == 200
    assert "reset link has been sent" in second_response.json()["message"]
    second_reset_token = fake_email_sender.last_email.token
    assert second_reset_token != first_reset_token

    second_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": second_reset_token, "new_password": "post-reset-password-2"},
    )
    assert second_reset.status_code == 200, second_reset.text

    login_response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "post-reset-password-2"}
    )
    assert login_response.status_code == 200


# --- Rereview item 1: stale identity-map rows must not be trusted -------------
#
# The tests below use two genuinely independent ``Session`` objects (not the
# TestClient, which gets a brand-new session per HTTP request and therefore
# can never itself hold a stale identity-map entry). Session A preloads a
# row -- mimicking the router's own internal state at the point just before
# its locking reselect -- then session B independently mutates and commits
# that same row. Session A's own call into the router function must then
# observe B's committed state via its FOR UPDATE reselect, not a stale
# in-memory copy, because SQLAlchemy does not refresh already-identity-mapped
# rows on a plain ``select()`` without ``populate_existing=True``.


def _request_with_cookie(name: str, value: str):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(b"cookie", f"{name}={value}".encode())],
    }
    return Request(scope)


def test_refresh_observes_concurrently_revoked_session_despite_stale_preload(
    client: TestClient, fake_email_sender: FakeEmailSender, session_factory, test_settings
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    login_response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login_response.status_code == 200, login_response.text
    raw_refresh_token = client.cookies.get(test_settings.refresh_cookie_name)
    assert raw_refresh_token is not None
    token_hash = hash_token(raw_refresh_token)

    session_a = session_factory()
    session_b = session_factory()
    try:
        # Session A preloads the session row into its own identity map --
        # exactly what would happen if it had already looked at this row
        # earlier in a longer-lived transaction.
        preloaded = session_a.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        ).scalar_one()
        assert preloaded.revoked_at is None
        user_id = preloaded.user_id

        # Session B independently revokes the same session and commits,
        # simulating a concurrent reset-password transaction.
        b_row = session_b.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        ).scalar_one()
        b_row.revoked_at = utcnow()
        session_b.commit()

        request = _request_with_cookie(test_settings.refresh_cookie_name, raw_refresh_token)
        response = Response()
        with pytest.raises(HTTPException) as excinfo:
            auth.refresh(request=request, response=response, db=session_a, settings=test_settings)
        assert excinfo.value.status_code == 401

        # No new session was minted from A's stale, seemingly-still-active
        # preloaded copy.
        remaining_sessions = (
            session_a.execute(select(RefreshSession).where(RefreshSession.user_id == user_id))
            .scalars()
            .all()
        )
        assert len(remaining_sessions) == 1
        assert remaining_sessions[0].revoked_at is not None
    finally:
        session_a.close()
        session_b.close()


def test_reset_password_observes_concurrently_used_token_despite_stale_preload(
    client: TestClient, fake_email_sender: FakeEmailSender, session_factory
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})
    client.post("/api/v1/auth/forgot-password", json={"email": EMAIL})
    raw_reset_token = fake_email_sender.last_email.token
    token_hash = hash_token(raw_reset_token)

    session_a = session_factory()
    session_b = session_factory()
    try:
        preloaded = session_a.execute(
            select(EmailToken).where(EmailToken.token_hash == token_hash)
        ).scalar_one()
        assert preloaded.used_at is None

        # Session B independently consumes the same token and commits,
        # simulating a concurrent reset-password request winning the race.
        b_token = session_b.execute(
            select(EmailToken).where(EmailToken.token_hash == token_hash)
        ).scalar_one()
        b_token.used_at = utcnow()
        session_b.commit()

        with pytest.raises(HTTPException) as excinfo:
            auth.reset_password(
                ResetPasswordRequest(token=raw_reset_token, new_password="attacker-new-password-1"),
                db=session_a,
            )
        assert excinfo.value.status_code == 400

        # The attacker's password never took effect.
        login_response = client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": "attacker-new-password-1"}
        )
        assert login_response.status_code == 401
    finally:
        session_a.close()
        session_b.close()


def test_register_rechecks_verification_state_after_lock_despite_stale_preload(
    client: TestClient, fake_email_sender: FakeEmailSender, session_factory, test_settings
) -> None:
    """register's re-registration branch previews the existing account
    (non-locking), then locks it. If session A's preview of that row is
    stale -- e.g. because it already touched the row earlier in a
    longer-lived transaction -- and session B concurrently verifies the
    account and commits, A's own populate_existing reselect at lock time
    must observe the fresh (now verified) state and reject with 409
    rather than trusting its stale unverified snapshot to invalidate/mint
    a new pending-password token."""
    from app.schemas.auth import RegisterRequest, VerifyEmailRequest

    raw_token = _register_and_get_verify_token(client, fake_email_sender)

    session_a = session_factory()
    session_b = session_factory()
    try:
        preloaded = session_a.execute(select(User).where(User.email == EMAIL)).scalar_one()
        assert preloaded.is_verified is False
        user_id = preloaded.id

        # Session B independently verifies the account and commits,
        # simulating a concurrent verification racing the re-registration.
        auth.verify_email(VerifyEmailRequest(token=raw_token, password=PASSWORD), db=session_b)
        assert session_b.execute(select(User).where(User.id == user_id)).scalar_one().is_verified

        with pytest.raises(HTTPException) as excinfo:
            auth.register(
                RegisterRequest(email=EMAIL),
                db=session_a,
                settings=test_settings,
                email_sender=fake_email_sender,
            )
        assert excinfo.value.status_code == 409

        # No new pending-password verification token was minted from A's
        # stale, seemingly-still-unverified snapshot.
        remaining_tokens = (
            session_a.execute(
                select(EmailToken).where(
                    EmailToken.user_id == user_id,
                    EmailToken.purpose == auth.EmailTokenPurpose.VERIFY_EMAIL,
                    EmailToken.used_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert remaining_tokens == []

        # The attacker's password never took effect: the mailbox owner's
        # original password still logs in, the attacker's does not.
        login_original = client.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert login_original.status_code == 200, login_original.text
        login_attacker = client.post(
            "/api/v1/auth/login",
            json={"email": EMAIL, "password": "attacker-new-password-1"},
        )
        assert login_attacker.status_code == 401
    finally:
        session_a.close()
        session_b.close()


def test_forgot_password_rechecks_active_state_after_lock_despite_stale_preload(
    client: TestClient, fake_email_sender: FakeEmailSender, session_factory, test_settings
) -> None:
    """forgot_password previews the user by email (non-locking), then
    locks it. If session A's preview is stale -- e.g. because it already
    touched the row earlier -- and session B concurrently disables the
    account and commits, A's own populate_existing reselect at lock time
    must observe the fresh (now inactive) state and mint/send nothing,
    preserving the generic response."""
    from app.schemas.auth import ForgotPasswordRequest

    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token, "password": PASSWORD})

    session_a = session_factory()
    session_b = session_factory()
    try:
        preloaded = session_a.execute(select(User).where(User.email == EMAIL)).scalar_one()
        assert preloaded.is_active is True
        user_id = preloaded.id

        # Session B independently disables the account and commits,
        # simulating a concurrent admin action racing forgot-password.
        b_user = session_b.execute(select(User).where(User.id == user_id)).scalar_one()
        b_user.is_active = False
        session_b.commit()

        emails_before = len(fake_email_sender.sent_emails)
        response = auth.forgot_password(
            ForgotPasswordRequest(email=EMAIL),
            db=session_a,
            settings=test_settings,
            email_sender=fake_email_sender,
        )
        assert response.message == auth._GENERIC_FORGOT_PASSWORD_MESSAGE

        # No reset token was minted and no email was sent from A's stale,
        # seemingly-still-active snapshot.
        reset_tokens = (
            session_a.execute(
                select(EmailToken).where(
                    EmailToken.user_id == user_id,
                    EmailToken.purpose == auth.EmailTokenPurpose.RESET_PASSWORD,
                )
            )
            .scalars()
            .all()
        )
        assert reset_tokens == []
        assert len(fake_email_sender.sent_emails) == emails_before
    finally:
        session_a.close()
        session_b.close()
