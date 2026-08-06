# Verification Email Context Design

## Goal

Show the account email on the email-verification password form so the user can
confirm which account they are establishing before choosing a password.

## Scope

This change applies only to the email-verification page. Password-reset behavior
is unchanged. The page displays the complete email address returned by the
backend.

## Backend Contract

Add a read-only endpoint:

`GET /api/v1/auth/verify-email/context?token=<opaque-token>`

The endpoint hashes the opaque token and validates that:

- The token exists and has the verify-email purpose.
- The token is unused and unexpired.
- The associated user still exists and is not verified.

A valid request returns:

```json
{ "email": "player@example.com" }
```

The lookup does not consume the token or extend its lifetime. Unknown, expired,
used, and otherwise invalid verification contexts return the same error response
so the endpoint does not reveal account state distinctions.

## Frontend Flow

When the verify-email page opens, it requests the context using the token already
present in the URL.

While loading, the page shows the existing loading treatment and does not render
the password form. On success, the page displays a localized label followed by
the complete email address in a visually emphasized treatment, then renders the
existing new-password and confirmation-password fields.

The email must come only from the backend response. The frontend does not accept
an email query parameter or decode account data from the opaque token.

## Invalid Link State

If the context request fails because the token is unknown, expired, used, or
otherwise unavailable, the page hides the password form and displays a localized
generic message that the verification link is invalid or expired. It provides a
link to registration so the user can begin again.

Network and server failures use the same unavailable state in this focused
change. They do not expose an email or permit password submission.

## Localization

Add English and Chinese strings for:

- Verification-context loading
- "Setting password for" / "正在为以下邮箱设置密码"
- Invalid or expired verification link
- Start registration again

## Tests

Backend tests cover:

- A valid token returns its account email.
- Reading context does not consume the token, and verification can still finish.
- Unknown, expired, and used tokens return the same failure.
- A token for an already verified user is unavailable.

Frontend tests cover:

- The loading state hides password inputs.
- A valid response renders the complete email and then the password form.
- An unavailable response renders no email or password inputs.
- The unavailable state links back to registration.
- Existing password-confirmation and successful-login-redirect behavior remains
  intact.
