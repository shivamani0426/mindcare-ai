# MindCareAI authentication rollout and verification

This feature branch introduces a **password recovery flow** without replacing existing patient or caregiver data. Do not deploy this change to the production Render service until the authorized administrator has completed an encrypted backup and isolated restore drill.

## Password recovery design

- Request code: `GET/POST /forgot-password`. The form always gives a generic response, including for nonexistent email addresses.
- Verify and change: `GET/POST /reset-password`, accepting email, a one-use 43-character random code and a new password of 10–128 characters.
- Codes are randomly generated on the server, emailed through authenticated TLS SMTP and stored only as HMAC-SHA256 hashes in the `password_recovery` table. They expire in 15 minutes, are consumed on success and are invalidated if delivery fails.
- Recovery request / verify attempts are limited per IP and per email identifier using the existing opaque-hash throttling mechanism; a throttled request receives HTTP 429 with Retry-After.
- The form keeps the recovery code out of the URL to avoid including it in HTTP request-path logs and browser history.
- Every session has an HMAC stamp bound to the current password hash; changing the password invalidates previous sessions. Existing sessions from before the rollout will have to sign in again. Phone-only accounts that use internal placeholder emails do not receive an email recovery code.
- The application adds the `password_recovery` table via the existing SQLAlchemy `db.create_all()` on startup; no existing table is dropped or modified.

## Configure email delivery securely on existing Render web service

Set these service environment variables privately (do not put values into Git, the issue tracker or a chat):

| Key | Description |
| --- | --- |
| `SMTP_HOST` | Trusted mail provider SMTP server |
| `SMTP_PORT` | `465` for implicit TLS or `587` for STARTTLS |
| `SMTP_USERNAME` | Provider username |
| `SMTP_PASSWORD` | Provider credential or application-specific password |
| `SMTP_FROM` | Verified authorized sender address |

No SMTP provider is provisioned by this branch. Without all five settings, the form displays an unavailable notice and does **not** falsely claim code delivery. Check provider account quotas, verified domain and delivery before enabling for patients. Keep the existing `SECRET_KEY` stable; changing it invalidates sessions and any outstanding recovery codes.

## Google OAuth (existing code; must live-verify)

- In Google Auth Platform, configure the OAuth consent screen, publish/test users according to provider requirements, and create a web OAuth client.
- The authorized redirect URI must match exactly: `https://mindcare-ai-ner.onrender.com/auth/google/callback`.
- Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` privately on the existing Render service.
- Verify with a real eligible Google account: new user onboarding, returning-user login, linking Google from an existing MindCare account, and rejection of silent links. Existing accounts are not automatically merged based on matching email.
- Never claim provider activation solely because code is present; OAuth configuration and an actual round trip must pass.

## Firebase phone OTP (existing code; must live-verify)

- Enable Firebase Authentication Phone provider, configure authorized domain `mindcare-ai-ner.onrender.com`, SMS-region policies, anti-abuse/quotas and billing/spend limits where required.
- Set `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID` and `FIREBASE_SERVICE_ACCOUNT_JSON` privately in Render. The service account JSON is secret and **must not** be included in client HTML; the public web configuration may be embedded on auth pages.
- Use Firebase **fictional test phone numbers** for initial QA to avoid live SMS charges. Verify reCAPTCHA, sending code, verifying token, creation/linking, returning login, and denial for incorrect, expired and reused credentials.
- Once approved by the owner, test a real SMS on an owned phone and confirm billing/region policies. Phone-only login cannot rely on password recovery until a verified recoverable email is deliberately added.

## Pre-release checks

1. Take and test an encrypted backup of the **existing** PostgreSQL database. Confirm its free-tier expiry (reported as December 12, 2026).
2. Run `pytest -q` in a disposable local SQLite environment; the new tests mock mail delivery and never send actual email.
3. Verify new `password_recovery` table and unique code index on the intended database after deployment; do not modify patient records.
4. Confirm 429 throttling, CSRF, generic email responses, expired/reused codes, password login after reset, session invalidation and role permissions.
5. Check error logs without leaking codes, email addresses or credentials. Confirm `/health` reports connected database.
6. Preserve existing patient/caregiver consent, reminders, games, Milo and WebRTC functionality.
7. Do not tag v1.0.0 until the external authentication providers and recovery-email delivery have been verified end to end.

**No production secret or SMTP credential was set by preparing this branch.**
