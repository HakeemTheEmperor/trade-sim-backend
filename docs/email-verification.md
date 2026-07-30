# Email verification (signup OTP)

## Why

Before this, `POST /api/v1/auth/signup` created the user, created a USD wallet,
and set the session cookie in the same response. Nothing ever established that
the email address was real or reachable, which meant:

- no password-reset flow was possible (there's no trusted address to send to),
- no shadow-invite or notification email could be trusted,
- the user table accumulated unreachable rows.

Signup now emails a 6-digit code and the account stays inert until it's entered.

## The flow

```
POST /auth/signup      → 201, NO cookie, OTP emailed
                         { message, email, verification_required: true }
POST /auth/verify-email → 200 + access & CSRF cookies set  (this is also the sign-in)
                         { message, user }
POST /auth/signin       → 403 { status: "ACCOUNT_UNVERIFIED", ... } while unverified
POST /auth/resend-otp   → 200, always the same message
```

The SPA sends the user from signup to `/verify-email` with the address in router
state (`{ email, codeSent: true }`), and `SignIn.tsx` does the same on a 403 —
keyed on `error.status === "ACCOUNT_UNVERIFIED"`, never on the message text, so
the wording can change freely.

## Why there is no unverified session

Verification endpoints are public and identified by `{email, otp}` rather than by
a "logged in but not yet verified" JWT. The alternative — issue the cookie at
signup and gate every protected route on `is_verified` — was rejected because:

- it needs the guard applied to every current *and future* protected endpoint,
  and one omission is a silent hole;
- an unverified token is still a real session, so leaking it still matters.

Here the cookie is only ever minted for a user whose `is_verified` is true. There
is exactly one code path that sets it (`verify_email`) and one that consumes it
(`signin`).

## Information disclosure

| Endpoint | What it reveals | Why that's acceptable |
|---|---|---|
| `/signin` 403 | this email is registered but unverified | only returned **after a correct password**. Anyone who can trigger it already holds the credentials. A wrong password still returns the generic 401. |
| `/verify-email` 400 | nothing | wrong code, expired code, burned code, and unknown email all return the same message. It takes no password, so it must not become an existence oracle. |
| `/resend-otp` 200 | nothing | unknown address, already-verified account, and active cooldown are indistinguishable. Always 200, always the same message. |

## OTP parameters

Defined as constants in [`app/models/email_otp.py`](../app/models/email_otp.py):

| Setting | Value | Reasoning |
|---|---|---|
| `OTP_TTL_MINUTES` | 10 | long enough for a slow mail hop, short enough that a stale inbox isn't a standing key |
| `MAX_ATTEMPTS` | 5 | a 6-digit code is only 10^6 possibilities — the attempt cap, not the length, is what makes guessing infeasible. Exceeding it burns the code outright. |
| `RESEND_COOLDOWN_SECONDS` | 60 | per-account, stored in the DB. Complements the route's `@rate_limit`, which is keyed by IP and resets on deploy. |

Other properties worth knowing:

- **Only the hash is stored** (`generate_password_hash`, same helper as
  passwords). The cleartext is returned once from `issue()` straight to the
  mailer and never persisted.
- **One live code per user.** Issuing a new code consumes any outstanding one, so
  an older email sitting in an inbox can't be replayed.
- **Single use.** A successful verify sets `consumed_at`.

## Brevo setup

Sending goes through [`EmailService`](../app/services/email_service.py) →
`Brevo.send_email_url()` in
[`providers.py`](../app/integrations/providers.py), following the existing
convention (base URL from env with a default, key from env with no default, both
read at call time).

1. Create a Brevo account (free tier: **300 emails/day**, no card).
2. **Verify a sender** — either a single confirmed address or, better, an
   authenticated domain (SPF/DKIM records on `toluwalase.me`). An unverified
   sender is accepted by the API and then silently not delivered, which looks
   exactly like a code that never arrives.
3. Set `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and optionally `BREVO_SENDER_NAME`.

Two deliberate behaviours in `EmailService`:

- **It never raises.** Every send returns a bool; provider errors are logged and
  swallowed. A Brevo outage must not turn signup into a 500 — the account is
  already committed and "Resend code" is one tap away.
- **It degrades to the log.** With `BREVO_API_KEY` unset (local dev, CI) the
  code is written to the log at WARNING instead of being sent, so the whole flow
  is exercisable with no provider account. This is why the key is listed as
  required in production: without it, signup appears to work and no user can
  ever verify.

Errors are logged without the request body on purpose — a Brevo error response
can echo the payload back, and the payload contains the OTP.

## Existing users

The migration (`a7c31f5be204`) adds `users.is_verified` with
`server_default=false` and then runs `UPDATE users SET is_verified = true` to
grandfather every account that existed at the time. Those users were never asked
for a code, and some registered with addresses they can no longer receive mail
at, so defaulting them to false would have locked out the entire current user
base.

The `server_default` stays `false` so that every row inserted afterwards starts
unverified. **Do not** change it to `true` — that would silently verify all
future signups and disable the feature without any test failing.

Two accounts bypass the OTP path by design, both created by an already-trusted
actor rather than by someone claiming an address:

- the super-admin seeded from `ADMIN_EMAIL` in `create_admin()`,
- admins created via `POST /auth/admin-signup` (super-admin only).

## Testing locally without Brevo

```bash
# leave BREVO_API_KEY unset
curl -X POST localhost:5000/api/v1/auth/signup -H 'Content-Type: application/json' \
  -d '{"first_name":"A","last_name":"B","email":"a@b.com","password":"pw123456","username":"ab"}'
# -> 201, no Set-Cookie for access_token_cookie; grep the server log for "code="

curl -X POST localhost:5000/api/v1/auth/signin -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"pw123456"}'
# -> 403 ACCOUNT_UNVERIFIED

curl -i -X POST localhost:5000/api/v1/auth/verify-email -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","otp":"<code from the log>"}'
# -> 200 with access_token_cookie + csrf_access_token
```
