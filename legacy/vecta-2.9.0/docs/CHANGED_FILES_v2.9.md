# ATLAS v2.9 — Changed Files & Validation Summary

**Baseline:** v2.7 (last deployed build)
**Release:** v2.9.0

---

## Inventory

| | Count |
|---|---|
| Backend modules | 44 (~7,700 lines) |
| Committed tests | 103 across 4 files |
| Alembic migrations | 3 |
| Phase 2 tables | 17 |
| Frontend components | 19 |
| Documentation files | 10 |

---

## New files

### Backend — Phase 2 engines
| File | Purpose |
|---|---|
| `app/taxonomy.py` | Single source of truth for all classifications: 6 verticals, 6 opportunity classes, 20 commercial types, 9 route requirements, 4 source tiers, 5 value statuses, 16 qualification items |
| `app/scoring_v2.py` | Four-dimension scoring, 39 factors with 0/50/100 anchors, coverage governance, Pursuit Priority |
| `app/qualification.py` | Qualification gate, typed failures, pipeline-entry rule hierarchy |
| `app/evidence.py` | Claim-level evidence model, Confirmed Opportunity enforcement |
| `app/ai_schema.py` | Strict versioned Pydantic contract for AI output |
| `app/models_phase2.py` | 17 normalised tables |
| `app/timeutils.py` | Timezone-aware and naive-UTC helpers |

### Backend — services & pipeline
| File | Purpose |
|---|---|
| `app/services/opportunity_service.py` | The single write path; all eight business rules enforced here |
| `app/services/opportunity_serializer.py` | API/frontend contract with display labels and safety flags |
| `app/scanner/scan_runner_v2.py` | Phase 2 scan pipeline |
| `app/scanner/url_validator.py` | ATLAS-side URL validation (injectable) |
| `app/ai/opportunity_scan_v2.py` | Phase 2 prompt, generated from the engines |
| `app/auth.py` | Login, logout, password change with lockout and audit |

### Backend — migrations, tooling, tests
`alembic.ini`, `alembic/env.py`, three migrations (`0001_baseline`,
`0002_phase2_model`, `0003_legacy_backfill`), `requirements-dev.txt`,
`tools/verify_imports.py`, `tools/validate_release.sh`,
`tools/demo_end_to_end.py`, four test files, three fixtures.

### Frontend
`Phase2Display.tsx` (9 components), `Phase2OpportunityCard.tsx`,
`Phase2OpportunityDetail.tsx`, `QualificationWorkflow.tsx`,
`AuthGate.tsx`, `LoginScreen.tsx`, `.eslintrc.json`.

### Documentation
`RELEASE_NOTES_v2.9.md`, `CHANGED_FILES_v2.9.md`,
`PHASE2_DEPLOYMENT.md`, `PHASE2_STATUS.md`, `PHASE1_HANDOVER.md`,
`PHASE3_ARCHITECTURE.md`.

---

## Modified files

| File | Change |
|---|---|
| `app/models.py` | Auth tables; 9 Phase 2 columns on `opportunities`; `owner_name`; `users` marked inert |
| `app/security.py` | PBKDF2 hashing, DB sessions, CSRF middleware, lockout; `ApiKeyMiddleware` removed |
| `app/main.py` | Credential seeding, CORS fail-closed, users router unwired |
| `app/config.py` | `SettingsConfigDict`; plaintext password default removed |
| `app/routers/opportunities.py` | Phase 2 endpoints and qualification workflow |
| `app/routers/scans.py`, `regions.py`, `app/scheduler.py` | Switched to `scan_runner_v2` |
| `app/schemas.py` | User schemas removed; evidence claim support |
| `database/schema.sql`, `database/seed.py` | No users table, roles or seeded accounts |
| `frontend/lib/api.ts` | Cookie auth, CSRF header, Phase 2 types and methods; API key removed |
| `frontend/app/settings/page.tsx` | Change-password panel; Users & roles removed |
| `frontend/package.json` | `typecheck`/`lint`/`validate` scripts, ESLint, `@types/react-dom` |
| `frontend/Dockerfile`, `docker-compose.yml` | API key build arg removed |

## Deleted files

`app/routers/users.py` — the multi-user API surface.

---

## Validation summary

Reproduce with `cd backend && bash tools/validate_release.sh`.

### Backend
| Check | Result |
|---|---|
| Tests collected | 103 |
| Passed | **103** |
| Failed | 0 |
| Errors | 0 |
| Import resolution | 44 modules, all resolve |

### Static audits
| Sweep | Result |
|---|---|
| `Project27` (plaintext password) | 0 |
| `ATLAS_API_KEY` / `NEXT_PUBLIC_ATLAS_API_KEY` | 0 |
| `X-API-Key` / `ApiKeyMiddleware` | 0 |
| `datetime.utcnow` | 0 |
| `declarative_base`, legacy `Query.get`, `class Config` | 0 |

### Security posture
| Control | Location |
|---|---|
| PBKDF2-HMAC-SHA256, 600k iterations | `security.py:106` |
| HttpOnly / Secure / SameSite cookie | `auth.py:63-69` |
| CSRF, only `/auth/login` exempt | `security.py:293` |
| Lockout threshold 5 | `security.py:233` |
| Security event log | `security.py:218` |
| Users router | absent |

### Operator-run steps
These must be executed in the deployment environment; they are not
performed by the build author:

- `npm install` → commit the resulting `package-lock.json`
- `npm run typecheck` / `lint` / `build`
- `alembic upgrade head` on a clean database
- `alembic upgrade head` on a v2.8 dataset (prints the migration report)
- `python3 tools/demo_end_to_end.py`

---

## Fixes in the final validation cycle

| Issue | Root cause | Fix |
|---|---|---|
| Confirmed → Unverified Lead | AI schema had no `url_validation_status`, so evidence stayed `not_reviewed` and failed the Confirmed gate — which cascaded into qualification and priority | Added the missing URL-validation pipeline step. ATLAS validates; the AI does not self-certify |
| Qualification stuck at Verification Required | Cascade from the above (`unverified_lead` is a non-pipeline classification) | Resolved by the same fix |
| Priority stayed restricted | Cascade from the above | Resolved; added regression test and fixed a latent `bool(None)` coercion bug |
| `NOT NULL summary` | Creation paths could omit it | Required in the AI schema, scanner falls back to title, migration backfills |
| Migration review flag appeared False | Test read stale ORM identity map after raw SQL | `expire_all()`; migration was already correct |
| Deadline vs classification precedence | Gate short-circuited on the first rule | Gate now reports **all** blocking reasons; hierarchy documented |
| ~170 deprecation warnings | `datetime.utcnow()` in 8 modules | Replaced with `utcnow_naive()` — identical semantics, no warning |
