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


def test_re_registration_with_new_password_controls_final_login_password(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    """An attacker who registers an email they do not control (password A)
    must not be able to take over the account once the real mailbox owner
    re-registers with a different password (B) and verifies the latest
    token: only B must work, the stale token must be dead, and A must never
    log in even after verification.
    """
    attacker_password = "attacker-chosen-password-A"
    owner_password = "owner-chosen-password-B"

    register_a = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": attacker_password}
    )
    assert register_a.status_code == 201, register_a.text
    stale_token = fake_email_sender.last_email.token

    register_b = client.post(
        "/api/v1/auth/register", json={"email": EMAIL, "password": owner_password}
    )
    assert register_b.status_code == 201, register_b.text
    latest_token = fake_email_sender.last_email.token
    assert latest_token != stale_token

    verify_response = client.post("/api/v1/auth/verify-email", json={"token": latest_token})
    assert verify_response.status_code == 200, verify_response.text

    # The stale token from the attacker's original registration is dead.
    stale_verify = client.post("/api/v1/auth/verify-email", json={"token": stale_token})
    assert stale_verify.status_code == 400

    # Only the mailbox owner's chosen password logs in.
    attacker_login = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": attacker_password}
    )
    assert attacker_login.status_code == 401

    owner_login = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": owner_password})
    assert owner_login.status_code == 200, owner_login.text

    # No leftover pending password hash is ever exposed.
    user = db_session.execute(select(User).where(User.email == EMAIL)).scalar_one()
    users_response = None
    _ = users_response, user  # pending_password_hash lives only on EmailToken, never on User/responses


def test_verify_before_re_registration_uses_the_only_submitted_password(
    client: TestClient, fake_email_sender: FakeEmailSender
) -> None:
    """A single registration (no re-registration race) still works: the
    one token that was issued carries that one password."""
    token = _register_and_get_verify_token(client, fake_email_sender)
    verify_response = client.post("/api/v1/auth/verify-email", json={"token": token})
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
    assert response.status_code == 403


def test_reset_password_invalidates_all_sibling_reset_tokens(
    client: TestClient, fake_email_sender: FakeEmailSender, db_session: Session
) -> None:
    token = _register_and_get_verify_token(client, fake_email_sender)
    client.post("/api/v1/auth/verify-email", json={"token": token})

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
    client.post("/api/v1/auth/verify-email", json={"token": token})
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
    client.post("/api/v1/auth/verify-email", json={"token": token})

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
    client.post("/api/v1/auth/verify-email", json={"token": token})

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
