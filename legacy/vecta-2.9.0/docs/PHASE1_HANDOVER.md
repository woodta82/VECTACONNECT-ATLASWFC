# ATLAS Phase 1 Security Handover — v2.8

**Scope:** Phase 1 of the rebuild specification — the security foundation.
Single hardened login, hashed credential, server-side sessions, CSRF,
lockout, security logging, and removal of all multi-user functionality.

---

## 1. Changed files (complete list)

**Backend**
- `backend/app/models.py` — added `AuthCredential`, `AuthSession`
  (incl. `last_used_at`), `SecurityEvent`; annotated retained-but-inert
  `User` table
- `backend/app/security.py` — PBKDF2 hashing/verification, password
  strength rules, DB-backed sessions (absolute + idle expiry, hashed
  tokens), CSRF-enforcing `SessionAuthMiddleware`, per-IP lockout,
  account-level escalating throttle
- `backend/app/auth.py` — hardened login (lockout, throttle,
  trusted-proxy IP extraction), logout, change-password (revokes all
  sessions); security-event logging throughout
- `backend/app/main.py` — credential seeding (insert-only, fails
  closed), CORS: credentials enabled, CSRF header allowed, production
  fails closed without a configured frontend origin; users router
  removed
- `backend/app/config.py` — plaintext password default REMOVED;
  `LOGIN_PASSWORD` is bootstrap-only with no committed value
- `backend/app/schemas.py` — user schemas removed
- `backend/app/routers/users.py` — **deleted**
- `backend/requirements-dev.txt` — new (pytest, httpx; test-only)
- `backend/tests/test_auth_phase1.py` — new (see §7)

**Frontend**
- `frontend/lib/api.ts` — cookie auth (`credentials: "include"`), CSRF
  header on mutating requests, `changePassword`; `User`/`UserRole`
  types and user API methods removed
- `frontend/app/settings/page.tsx` — Change Password panel added;
  Users & roles panel removed entirely

**Docs**
- `.env.example` — plaintext password removed
- `docs/SECURITY.md`, `docs/SPECIFICATION_TRACEABILITY.md`, `README.md`
  — updated to the single-login model; outdated role/SSO language
  removed
- `docs/PHASE1_HANDOVER.md` — this file

## 2. Migration

No hand-written migration needed. The three new tables are created
automatically by `create_all()` on first startup against the existing
v2.7 database (it only creates missing tables and never touches existing
ones). The inert `users` table is deliberately retained (three tables
hold `owner_id` foreign keys to it). Rollback leaves the new tables in
place harmlessly — v2.7 simply ignores them.

## 3. Deployment (Codespace, usual clean-overwrite)

1. **Before deploying**, in Railway → backend service → Variables, set:
   `LOGIN_PASSWORD` = the agreed initial password (this is the last time
   it exists as plaintext anywhere)
2. Upload `atlas-vecta-v2.8.zip` to the repo root
3. Codespace: `git pull` → `rm -rf frontend backend` →
   `unzip -o atlas-vecta-v2.8 -d /tmp/update` →
   `cp -r /tmp/update/atlas/frontend /tmp/update/atlas/backend .`
4. Verify (see §6), then `rm -f atlas-vecta-v2.8`, `git add -A`,
   `git commit -m "Deploy v2.8 - Phase 1 security"`, `git push`
5. **Both Railway services must redeploy together** (CORS changed —
   mixed old/new versions cannot authenticate)

## 4. Railway environment-variable checklist

| Variable | Backend | Action |
|---|---|---|
| `LOGIN_PASSWORD` | required at first v2.8 boot only | **Set before deploy; DELETE after step 5 below** |
| `LOGIN_USERNAME` | optional | leave unset (defaults to the fixed authorised account) |
| `FRONTEND_ORIGIN` | required in production | must be the exact frontend URL — CORS now fails closed without it |
| `ENVIRONMENT` | should be `production` | enables Secure/SameSite=None cookie |
| `DATABASE_URL`, `ANTHROPIC_API_KEY` | unchanged | — |

## 5. Post-deployment password procedure (do this immediately)

1. Log in once with the initial password (seeded as a hash on first boot)
2. Settings & Admin → **Change password** → rotate to a new password
   (12+ chars, 3 of 4 character classes). All sessions log out — sign in
   with the new password
3. Railway → backend Variables → **delete `LOGIN_PASSWORD`** → service
   restarts
4. Confirm: log in again with the NEW password. Restarts/redeploys can
   never reseed or reset the credential — seeding is insert-only and
   permanently inert once the credential row exists

## 6. Verification (fuller than grep counts)

Static checks executed in the build environment (results in the v2.8
delivery message): AST parse of every backend file; brace/paren balance
of every frontend file; import cross-checks (frontend↔`lib/api.ts`,
backend↔schemas/models/security); repo-wide sweep confirming **zero
plaintext-password occurrences** and zero multi-user API/UI remnants.

Runtime verification — run in the Codespace before deploying:
```
cd backend
pip install -r requirements.txt -r requirements-dev.txt
DATABASE_URL=sqlite:///./test_atlas.db pytest tests/ -v
cd ../frontend && npm install && npx tsc --noEmit && npm run build
```

## 7. Test suite (backend/tests/test_auth_phase1.py)

31 tests: hash format/salt/iteration storage, no-plaintext-at-rest,
insert-only seeding, env-var-never-a-fallback, HttpOnly cookie flags,
generic error messages, username normalisation + immutability, hashed
session storage + per-login rotation, logout/absolute-expiry/idle-expiry
invalidation, CSRF missing/forged/valid/GET-exempt, password-change
(wrong current, weak, reused, fresh salt, all-sessions-revoked), IP
lockout + recovery + clearing, account-throttle escalation + cap,
security-log contents (no secrets, IPs recorded), absence of user
registration/listing endpoints, inert users table. Uses safe test
credentials only — the production password appears nowhere.

**Honest status:** this build environment has no network access and
cannot install pytest/Node, so these tests are delivered written-and-
syntax-verified but not yet executed. Run the §6 commands in the
Codespace — treat Phase 1 as closed only when they pass there and the
deployed login/change-password/lockout behaviour is confirmed by hand.

## 8. Known limitations

- Lockout/throttle counters are in-memory: they reset on restart
  (durable record of every attempt remains in `security_events`), and
  assume the single-instance deployment ATLAS runs today
- MFA not implemented (spec: optional, and not at the cost of identity-
  platform complexity)
- Frontend lint/type-check/build and the runtime test suite require the
  Codespace (see §7)
- `security_events` grows unbounded — trivial today, worth a retention
  policy in Phase 5

## 9. Rollback

Redeploy `atlas-vecta-v2.7.zip` over both folders (same clean-overwrite).
The v2.8 tables persist harmlessly. Note v2.7 returns to the old
plaintext-default behaviour — rollback is an emergency measure, not a
resting state.

## 10. Phase 2 readiness

Confirmed: Phase 2 (scoring, classification, evidence, qualification)
builds on this authentication layer without restructuring it. Session,
CSRF and credential handling are self-contained in
`security.py`/`auth.py` with a stable surface (middleware + three
endpoints).
