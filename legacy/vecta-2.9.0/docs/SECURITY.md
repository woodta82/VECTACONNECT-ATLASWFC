# Security

A plain account of what protects ATLAS today, what was just added, and what
still needs a deliberate decision from VECTA before this holds real
commercial data at scale. Nothing here is generic advice — every item is
either already true of this codebase or a specific, actionable gap in it.

## What's implemented

| Protection | Where | Notes |
|---|---|---|
| **HTTPS everywhere** | Railway (or any reverse proxy in front) | TLS termination is handled by the platform, not application code — nothing to configure, but confirm it's actually enforced on your host if you move off Railway |
| **Security response headers** | `backend/app/security.py` — `SecurityHeadersMiddleware` | `X-Content-Type-Options`, `X-Frame-Options: DENY` (stops the app being framed/clickjacked), `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security` |
| **Rate limiting** | `backend/app/security.py` — `RateLimitMiddleware` | 120 requests/minute per IP by default (`RATE_LIMIT_PER_MINUTE`). Mainly protects the Anthropic API budget from a runaway or malicious client, not a substitute for a real WAF |
| **Login gate (hardened, Phase 1)** | `backend/app/auth.py`, `backend/app/security.py`, `backend/app/models.py` | Single shared credential. Password stored **only as a PBKDF2-HMAC-SHA256 hash** (600k iterations, per-hash salt, algorithm + iteration count stored for future upgrades) in `auth_credential` — `LOGIN_PASSWORD` has **no committed default**, is bootstrap-only (insert-only seed, fails closed if absent, can never overwrite), and should be deleted from Railway after first rotation. Sessions: server-side rows (`auth_sessions`, tokens stored SHA-256'd, creation/last-used/expiry timestamps, **24h absolute + 60min idle expiry**, fresh token per login) via an **HttpOnly, Secure, SameSite=None cookie**. Mutating requests require **X-CSRF-Token** (double-submit). Failed logins: **per-IP lockout (5/15min)** using the trusted proxy's X-Forwarded-For entry (last, not client-spoofable first) **plus account-level escalating delay** (0.5s/failure, 5s cap — throttles distributed attacks without ever hard-locking the owner). Every auth event logged to `security_events` (never passwords/hashes/tokens). Password change requires current password, enforces strength, revokes all sessions |
| **Restricted CORS** | `backend/app/main.py` | Explicit origin allow-list (your real frontend URL), no wildcard; `localhost:3000` is only added when `ENVIRONMENT=development` |
| **API docs gating** | `backend/app/main.py` | `DOCS_ENABLED=false` removes `/docs`, `/redoc`, `/openapi.json` entirely — set this once the API-key gate is on, since there's no reason to publish your schema once it's authenticated anyway |
| **SQL injection** | Everywhere (SQLAlchemy ORM) | All queries go through SQLAlchemy's parameterised query builder — there is no raw/string-interpolated SQL anywhere in the codebase, so this class of vulnerability doesn't apply |
| **XSS** | Frontend (React) | React escapes all rendered text by default; the codebase contains no `dangerouslySetInnerHTML` except the theme-preference script in `layout.tsx`, which renders a fixed literal string with no user input |
| **Secrets handling** | `.env` (gitignored), Railway env vars | No credential is hardcoded or logged anywhere in the codebase |


### Known limitation — failed-login counters are in-memory

Both the per-IP lockout and the account-level escalating delay are held
in process memory. They **reset on every backend restart or redeploy**,
so a restart clears an active lockout. This is an accepted trade for the
current single-instance deployment; the durable record is unaffected —
every attempt, failure and lockout is written to the `security_events`
table regardless. Moving the counters to database-backed storage is the
fix if ATLAS ever runs multiple replicas (where in-memory counts also
would not be shared between processes).

## What you need to decide and turn on

These aren't code bugs — they're configuration and product decisions that
only VECTA can make, listed in the order I'd act on them:

1. **Rotate the login password** if `tom@vectasports` / the default password
   was ever shared more widely than intended, or before this is used
   beyond the initial small team — set `LOGIN_USERNAME` / `LOGIN_PASSWORD`
   on the backend to change it, no code edit needed.
2. **Set `DOCS_ENABLED=false`** on the backend.
3. **Set `ENVIRONMENT=production`** on the backend so CORS drops the
   localhost fallback.
4. **Real per-user authentication.** The login gate added in this pass is
   a single shared credential, not individual accounts — everyone on the
   team looks identical in the audit trail, same limitation as before,
   just now behind a proper login screen instead of no login at all. You
   still can't tell who moved an opportunity to "Won" or who sent an
   outreach message. The `users` table and `owner_id` fields already
   exist for this; wiring up VECTA's actual SSO (Google Workspace or
   Microsoft Entra, most likely) replacing the shared login is the real
   fix, and is deliberately not guessed at in this build — see
   `docs/DEPLOYMENT.md`.
5. **Database backups.** Enable Railway's automated Postgres backups (or
   your host's equivalent) before this is the system of record for live
   commercial pipeline data — it will be, quickly.
6. **Encryption at rest.** Railway's managed Postgres encrypts storage at
   the infrastructure level by default; if you move to self-hosted
   Postgres, confirm the same is true there. Nothing in this dataset
   currently warrants additional field-level encryption (no passwords, no
   payment data) — if that changes (e.g. storing personal data on
   individuals beyond public business contact details), revisit this.
7. **Dependency scanning.** Turn on GitHub's Dependabot alerts on the repo
   (free, one click in repo settings) so you're notified when a dependency
   in `requirements.txt` or `package.json` gets a security advisory.
8. **If ATLAS is ever scaled to multiple backend replicas**, the login
   session store needs to move to a shared store (Redis) — right now a
   session is only recognised by the specific backend instance that
   issued it.

## Deliberately out of scope for a generated codebase

- **Penetration testing** — worth commissioning once real commercial data
  is flowing through this, especially before any external stakeholder
  (a federation, a brand) is ever given access.
- **Formal PDPL/GDPR compliance review** — the spec's governance section
  flags this; it's a legal/compliance exercise, not an engineering one.
- **A Web Application Firewall (e.g. Cloudflare) in front of the app** —
  cheap and worthwhile once this is public-facing rather than
  internal-only; not necessary for a VPN'd or API-key-gated internal tool.
