"""Authentication: registration, email verification, login, refresh
rotation, logout, and forgot/reset password.

Access tokens are short-lived JWTs returned in the response body. Refresh
tokens are opaque random strings stored client-side only in an HttpOnly,
``SameSite=Lax`` cookie; the server only ever persists their SHA-256 hash.
"""

from __future__ import annotations

import smtplib
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_email_sender
from app.models.auth import EmailToken, RefreshSession
from app.models.base import utcnow
from app.models.enums import EmailTokenPurpose
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.schemas.user import UserRead
from app.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.services.email import EmailSender, send_password_reset_email, send_verification_email

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_COOKIE_PATH = "/api/v1/auth"
_GENERIC_FORGOT_PASSWORD_MESSAGE = (
    "If that email address is registered, a password reset link has been sent."
)


def _set_refresh_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(key=settings.refresh_cookie_name, path=_COOKIE_PATH)


def _issue_access_token(user: User, settings: Settings) -> str:
    return create_access_token(
        subject=str(user.id),
        role=user.role.value,
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        ttl_minutes=settings.access_token_ttl_minutes,
    )


def _send_verification_email_or_fail(
    email_sender: EmailSender, settings: Settings, *, to_address: str, raw_token: str
) -> None:
    """Send the verification email, surfacing SMTP failures as an explicit,
    retryable error instead of an unhandled 500.

    The user row and token are already committed by the time this is
    called, so a failure here never strands the registrant: retrying
    ``register`` with the same email invalidates the stale token, mints a
    fresh one, and resends (see ``register``).
    """
    verify_url = f"{settings.app_base_url}/verify-email?token={raw_token}"
    try:
        send_verification_email(email_sender, to_address=to_address, verify_url=verify_url)
    except (smtplib.SMTPException, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send the verification email. Please try registering again.",
        ) from exc


@router.post("/register", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    email_sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    normalized_email = payload.email.lower()
    existing = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()

    if existing is not None:
        if existing.is_verified or not existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )
        # Unverified account retrying registration (e.g. the first
        # verification email was never delivered): invalidate any
        # outstanding, unused verification tokens so only the newly minted
        # one is redeemable, then mint and send a fresh one. This avoids
        # permanently stranding a registrant behind a 409 with no way to
        # get a new email.
        user = existing
        now = utcnow()
        stale_tokens = db.execute(
            select(EmailToken).where(
                EmailToken.user_id == user.id,
                EmailToken.purpose == EmailTokenPurpose.VERIFY_EMAIL,
                EmailToken.used_at.is_(None),
            )
        ).scalars()
        for stale_token in stale_tokens:
            stale_token.used_at = now
    else:
        user = User(email=normalized_email, password_hash=hash_password(payload.password))
        db.add(user)
        db.flush()

    raw_token = generate_opaque_token()
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=EmailTokenPurpose.VERIFY_EMAIL,
            token_hash=hash_token(raw_token),
            expires_at=utcnow() + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    db.commit()

    _send_verification_email_or_fail(email_sender, settings, to_address=user.email, raw_token=raw_token)

    return MessageResponse(message="Registration successful. Check your email to verify your account.")


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(payload: VerifyEmailRequest, db: Session = Depends(get_db)) -> MessageResponse:
    token_hash = hash_token(payload.token)
    # Lock the token row so a concurrent replay of the same one-time token
    # cannot both pass the is_usable check before either commits.
    token = db.execute(
        select(EmailToken)
        .where(
            EmailToken.token_hash == token_hash,
            EmailToken.purpose == EmailTokenPurpose.VERIFY_EMAIL,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if token is None or not token.is_usable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    token.used_at = utcnow()
    user.is_verified = True
    db.commit()
    return MessageResponse(message="Email verified. You can now log in.")


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    normalized_email = payload.email.lower()
    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if not user.is_verified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

    raw_refresh_token = generate_opaque_token()
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    db.commit()

    _set_refresh_cookie(response, raw_refresh_token, settings)
    access_token = _issue_access_token(user, settings)
    return LoginResponse(access_token=access_token, user=UserRead.model_validate(user))


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccessTokenResponse:
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    token_hash = hash_token(raw_refresh_token)
    # Lock the session row so only one concurrent refresh request can
    # observe it as active and rotate it; a second concurrent request with
    # the same (still-valid-looking) token waits for this transaction to
    # commit and then correctly sees it as revoked/replaced.
    session = db.execute(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash).with_for_update()
    ).scalar_one_or_none()
    if session is None or not session.is_active:
        _clear_refresh_cookie(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh session")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        _clear_refresh_cookie(response, settings)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not available")

    # Atomic rotation: mint the replacement before revoking the old session,
    # then commit both changes together so a crash never leaves the user
    # with zero valid refresh sessions and no way to recover except re-login,
    # nor with two simultaneously valid sessions.
    new_raw_refresh_token = generate_opaque_token()
    new_session = RefreshSession(
        user_id=user.id,
        token_hash=hash_token(new_raw_refresh_token),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_ttl_days),
    )
    db.add(new_session)
    db.flush()
    session.revoked_at = utcnow()
    session.replaced_by_id = new_session.id
    db.commit()

    _set_refresh_cookie(response, new_raw_refresh_token, settings)
    access_token = _issue_access_token(user, settings)
    return AccessTokenResponse(access_token=access_token)


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    raw_refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh_token is not None:
        token_hash = hash_token(raw_refresh_token)
        session = db.execute(
            select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        ).scalar_one_or_none()
        if session is not None and session.revoked_at is None:
            session.revoked_at = utcnow()
            db.commit()

    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="Logged out.")


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    email_sender: EmailSender = Depends(get_email_sender),
) -> MessageResponse:
    normalized_email = payload.email.lower()
    user = db.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is not None and user.is_active:
        raw_token = generate_opaque_token()
        db.add(
            EmailToken(
                user_id=user.id,
                purpose=EmailTokenPurpose.RESET_PASSWORD,
                token_hash=hash_token(raw_token),
                expires_at=utcnow() + timedelta(hours=settings.password_reset_ttl_hours),
            )
        )
        db.commit()
        reset_url = f"{settings.app_base_url}/reset-password?token={raw_token}"
        send_password_reset_email(email_sender, to_address=user.email, reset_url=reset_url)

    # Always the same response, whether or not the email is registered.
    return MessageResponse(message=_GENERIC_FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    token_hash = hash_token(payload.token)
    # Lock the token row so a concurrent replay of the same one-time token
    # cannot both pass the is_usable check before either commits.
    token = db.execute(
        select(EmailToken)
        .where(
            EmailToken.token_hash == token_hash,
            EmailToken.purpose == EmailTokenPurpose.RESET_PASSWORD,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if token is None or not token.is_usable:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user = db.get(User, token.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")

    user.password_hash = hash_password(payload.new_password)
    token.used_at = utcnow()

    active_sessions = db.execute(
        select(RefreshSession).where(
            RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None)
        )
    ).scalars()
    for session in active_sessions:
        session.revoked_at = utcnow()

    db.commit()
    return MessageResponse(message="Password reset. Please log in again.")
