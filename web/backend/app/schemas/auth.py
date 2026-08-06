from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.user import UserRead


class RegisterRequest(BaseModel):
    # Registration proves nothing but "I want to send a verification email
    # to this address" -- it never accepts, hashes, stores, or binds a
    # password. The password is chosen only when the verification token is
    # consumed (see VerifyEmailRequest), so whoever controls the mailbox --
    # not whoever first (or last) POSTs to /register -- controls the
    # account's eventual credential. `extra="forbid"` ensures a legacy or
    # attacker-supplied `password` field is rejected outright rather than
    # silently ignored, so a client can never mistake this endpoint for
    # accepting a credential.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class VerifyEmailRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginResponse(AccessTokenResponse):
    user: UserRead


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
