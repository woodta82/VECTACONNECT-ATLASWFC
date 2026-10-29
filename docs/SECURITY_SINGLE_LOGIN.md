# Single-login security specification and threat controls

## Account model
- Exactly one credential row (`auth_credential`, enforced by a singleton primary key). All access is through this one shared credential.
- Any number of concurrent sessions: one login is not one device.
- Owners and contacts (`people`) are descriptive records and never log in.
- Company, region and service parameters are **filters**. They never restrict what the shared account can read.
- Contract territory and capability restrictions are business rules on recommendations, not permissions.
- Each customer instance (WFC, VECTA, any other) has its own database and credential. There is no cross-instance access path.

## Credential and sessions

| Control | Implementation | Test evidence |
|---|---|---|
| Hashing | PBKDF2-HMAC-SHA256, 600,000 iterations, 16-byte salt, iterations stored per hash; schema rejects non-`pbkdf2_sha256$` values | `test_password_hash_roundtrip_and_strength`, `test_single_shared_credential` |
| Bootstrap | Insert-only from `LOGIN_BOOTSTRAP_PASSWORD`; weak values refused; inert once a credential exists | `test_auth_service_full_cycle` |
| Session token | 256-bit random; only its SHA-256 is stored; HttpOnly cookie, `SameSite=Lax`, `Secure` + `__Host-` prefix in staging/production | `test_login_cookie_flags_session_and_csrf` |
| Expiry | 12 h absolute, 60 min idle | `test_session_validity_rules`, `test_forged_and_expired_cookies_rejected` |
| CSRF | Token = HMAC-SHA256 keyed by the raw HttpOnly session token. The page can't read the cookie, so a cross-site attacker can't compute it. It is the same in every tab and is returned by `GET /auth/session` after a reload. It is required on every POST/PUT/PATCH/DELETE except login | `test_login_cookie_flags_session_and_csrf`, `test_import_through_http_and_exact_decimals` |
| Logout / logout-all | Revokes this session / every session (`sessions_valid_after` + `revoked_at`) | `test_concurrent_sessions_logout_and_logout_all` |
| Password change | Requires current password; strength rule; revokes every session | `test_password_change_revokes_and_new_password_works` |
| Brute force | Durable `login_throttle` shared by replicas: 5 failures per IP in 15 min locks that IP; account-wide delay of 0.5 s per recent failure, capped at 5 s (never a hard lock of the only account) | `test_auth_service_full_cycle` |
| Client IP | One rule (`auth_policy.client_ip`) with `TRUSTED_PROXY_HOPS`; left-most forwarded entries are ignored | `test_throttle_and_client_ip` |

## Request protection
- `AuthGateMiddleware` makes everything except `/health/live`, `/health/ready` and `/auth/login` require a valid session. That includes direct IDs, search, exports, reports, imports, settings and the API docs (which are also disabled entirely in production).
- Every response carries `Cache-Control: no-store`, `nosniff`, `X-Frame-Options: DENY`, a `default-src 'none'` CSP, `no-referrer`, and HSTS in staging/production.
- Errors return `{error: {code, detail, request_id}}`; failures are never turned into empty successes.
- Same-origin deployment: the browser talks only to the web service, which proxies `/api/*`. There is no CORS.
- The VECTA 2.9 service worker is replaced by a self-unregistering worker that deletes `atlas*` caches; the shell also unregisters any worker on load.

## Audit
`audit_events` records the shared account, a 12-hex session reference, request id, IP, user agent, entity and metadata-only detail. Keys matching password/secret/token/key/cookie/body/content/payload are omitted. Logged: logins (success, failure, lockout), logout, logout-all, password change, overrides, stage changes, approvals, imports (dry run, commit, reversal), exports, budget/kill-switch/schedule changes, exception resolution. **It cannot and does not claim to identify an individual.**

## Retrieval (SSRF) and untrusted content
- HTTP(S) only; ports 80/443/8080/8443; no userinfo.
- Rejects localhost, `.local` and `.internal` names.
- Every resolved IPv4/IPv6 address must be global. Loopback, private, link-local, CGNAT, multicast, reserved, unspecified and cloud-metadata addresses are refused, including addresses embedded in IPv4-mapped, 6to4, Teredo and NAT64 forms.
- The connection is pinned to the validated address, with TLS verified against the hostname, which defeats DNS rebinding.
- Redirects are followed manually; each hop is re-validated, up to a limit of 5.
- 5 MB size limit, 10 s timeout, content-type allow-list.
- Downloaded content is never executed.
- Tests: `tests/domain/test_retrieval_ssrf.py` (39 cases, including a real loopback server that receives zero requests).

## AI controls
- Off until a key, model and prices are configured. A budget reservation must succeed **before** dispatch: the kill switch, per-run cap and monthly cap are enforced atomically in PostgreSQL. Tested with 25 concurrent reservations, of which exactly 10 fit the cap.
- The model receives only the public document inside `<document>` delimiters plus the schema. It has no tools, so injected text cannot fetch, send, read secrets or approve anything.
- Output is strictly parsed: exact keys, string values, allowed claim types, and a quote that must appear verbatim in the document. Anything else is quarantined (`ai_quarantine`) and recorded in `ai_calls`.
- AI output is a proposal (`assessed_by='ai_proposed'`). Qualification approval is always a human action.
- `guard_public_query` refuses any public search query containing a registered private WFC term.

## Imports and exports
- Uploads: `.csv` (UTF-8) or `.xlsx` only, at most 20 MB, zip-bomb guard. `.xlsm`/`.xls`/`.xlsb` and any workbook containing `vbaProject.bin` are refused. Rows are parsed as data, never evaluated.
- Exports are generated on the server, audited, and every cell starting with `= + - @ TAB CR` is prefixed with `'` (plain negative numbers excepted).

## Secrets
- Server-side only.
- `tools/secret_scan.py` runs in CI and fails on realistic secret shapes. Unlike the 2.9 grep, it does not flag its own patterns or placeholders.
- Error messages and job errors are redacted against known secret values.
