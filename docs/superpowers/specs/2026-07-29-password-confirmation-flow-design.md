# Password Confirmation Flow Design

## Goal

Require users to enter a new password twice when establishing an account or
resetting a forgotten password. After a successful operation, return the user
to sign-in and show a clear success message.

## Scope

This change applies to both `verify` and `reset` modes in the existing
`AuthForm`. Login, registration, and forgot-password behavior remain unchanged.
The backend contracts remain unchanged because password confirmation is a
client-side input safeguard.

## Interaction

The verify-email and reset-password forms display:

1. New password
2. Confirm new password
3. Continue

Both password fields use the existing 8-128 character constraints and
`autocomplete="new-password"`. The confirmation error appears when the user
leaves the confirmation field or submits the form with different values.
Submission is blocked before any API request while the values differ.

Changing either password field clears a stale mismatch error. While a request
is pending, both password fields and the submit button are disabled.

The submit button remains enabled when the values differ so it can explain the
problem rather than silently blocking the user. A mismatched submit focuses and
selects the confirmation field. Pasting and password-manager autofill remain
available, and pressing Enter follows the same validation path as Continue.

## Success Navigation

Successful account verification redirects to:

`/login?notice=account-verified`

Successful password reset redirects to:

`/login?notice=password-reset`

The login form recognizes only these two notice values and renders the
corresponding localized success message:

- `account-verified`: account verified and password set successfully
- `password-reset`: password changed successfully

After reading the notice, the login form removes only the `notice` parameter
with `router.replace` while retaining the semantic notice in local state.
Refresh therefore does not replay an old success message. Unknown notice values
are ignored and removed. The notice is cleared when a login submission starts
and updates immediately when the user switches languages.

## Error Handling

Password mismatch is a localized client-side validation error. It does not
replace existing server errors. Expired or invalid tokens, password-policy
rejections, and network failures continue to use the current API error path and
leave the user on the form.

No success redirect occurs unless the API call completes successfully.

## Implementation Boundary

Extend the existing `AuthForm` rather than introducing a new component or
splitting the authentication forms. Add local confirmation state and derive
whether confirmation is required from the current mode. Keep API client method
signatures unchanged and send only the original password field to the backend.

Add English and Chinese strings for the confirmation label, mismatch error,
and the two login-page success notices.

## Tests

Component regressions must prove:

- Verify-email and reset-password modes render both password fields.
- A mismatch discovered on confirmation-field blur displays an error.
- Submitting mismatched passwords displays an error and makes no API request.
- Editing either field clears a stale mismatch error.
- Successful verification redirects to the account-verification login notice.
- Successful reset redirects to the password-reset login notice.
- Login renders each recognized notice in English and Chinese.
- Unknown notice values render no success message.
- API errors leave the user on the originating form and do not redirect.

Existing API contract, authentication sequencing, and browser-flow tests remain
unchanged except where their rendered form expectations require the second
password field.
