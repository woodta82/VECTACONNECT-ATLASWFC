# Environment variable reference

All variables live in a single root `.env` file (copy from `.env.example`).
`docker-compose.yml` passes the relevant ones into each container.

## Core

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://atlas:atlas@localhost:5432/atlas` | Overridden to point at the `db` service automatically inside docker-compose |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | For CORS — set to your deployed frontend URL in production |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | The frontend's view of the backend — must be reachable from the *browser*, not just the frontend container |

## AI layer (required)

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Powers every AI call: scanning, scoring inputs, NL search parsing, contact research, outreach drafting |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Change to point at a different Claude model |

## Automation engine

| Variable | Default | Notes |
|---|---|---|
| `SCAN_ENABLED` | `true` | Set `false` to disable the background Global Scanner entirely (e.g. in a test environment) |
| `SCAN_INTERVAL_HOURS` | `168` | Per spec — full sweep every 7 days. Also adjustable at runtime from Settings & Admin (non-persistent — see below) |
| `SAVED_SEARCH_CHECK_MINUTES` | `15` | How often the scheduler checks whether a saved search is due to re-run |
| `DIGEST_HOUR_LOCAL` | `7` | Server-time hour (24h) the daily digest is composed and sent |

Changes made via Settings & Admin's "Sweep interval" field take effect
immediately but only for the running process — they reset to the `.env`
value on restart. For a permanent change, edit `.env` and restart.

## Notifications (optional)

| Variable | Default | Notes |
|---|---|---|
| `RESEND_API_KEY` | empty | Without this, the daily digest and alerts are still generated and stored as in-app notifications — email sending is skipped (logged, not sent) |
| `NOTIFICATION_FROM_EMAIL` | `atlas@vectasports.com` | Must be a domain verified with Resend |
| `DIGEST_TO_EMAIL` | empty | Who receives the daily digest email |

## LinkedIn (optional)

| Variable | Default | Notes |
|---|---|---|
| `LINKEDIN_CLIENT_ID` | empty | Not currently used by any code path — reserved for when VECTA obtains official LinkedIn API / Sales Navigator access |
| `LINKEDIN_CLIENT_SECRET` | empty | Same |

Relationship Intelligence works fully without these: contact discovery uses
public-web AI research, and every contact gets a LinkedIn *search* deep-link
rather than a scraped profile, which is fully permitted and requires no
credentials. See `docs/SPECIFICATION_TRACEABILITY.md` Section 06 for the
detailed reasoning.

## Security

See `docs/SECURITY.md` for the full picture — this is the reference table.

| Variable | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `development` | Set `production` on deploy — tightens CORS (drops the localhost fallback) |
| `RATE_LIMIT_PER_MINUTE` | `120` | Per-client-IP request limit before a 429 is returned |
| `DOCS_ENABLED` | `true` | Set `false` in production to remove `/docs`, `/redoc`, `/openapi.json` |

## Commercial reporting

| Variable | Default | Notes |
|---|---|---|
| `ESTIMATED_COST_PER_SCAN_USD` | `0.50` | Feeds the Commercial ROI panel on Reports (cost per Priority opportunity found, pipeline-to-cost ratio). A rough estimate, not pulled from real Anthropic billing — recalibrate after a few weeks of actual invoices |
