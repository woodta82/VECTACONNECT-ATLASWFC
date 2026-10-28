# Setup guide

Written so a non-technical operator can get ATLAS running end to end.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose) installed
- An Anthropic API key — get one at https://console.anthropic.com

That's it — Postgres, the backend and the frontend all run in containers;
nothing else needs to be installed locally.

## 1. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Everything else has a sensible default (7-day scan cycle, MENA-anchored
regions, etc.) — see `docs/ENVIRONMENT.md` for what each variable does.

## 2. Run

```bash
docker compose up --build
```

First run takes a few minutes (building both images, installing
dependencies). Once it's up:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Backend health check: http://localhost:8000/health → `{"status":"ok"}`

The Global Scanner starts automatically — check the backend container's
logs for `Global Scanner: starting vertical=media` within a few seconds of
boot. It will not populate the pipeline instantly: the first live scan for
each of the five verticals takes roughly 30–90 seconds (it's doing a real
web search + AI analysis, not reading from a pre-built index).

## 3. (Optional) Seed demo data

To see the interface populated immediately, without waiting for the first
scan cycle:

```bash
docker compose exec backend python ../database/seed.py
```

This adds three demo opportunities, three organisations and two users. It's
safe to run once — running it again is a no-op if users already exist.

## 4. Using ATLAS day to day

- **Control Panel** (home) — live dashboard. "Run Global Scan" triggers an
  immediate full sweep alongside the 7-day schedule.
- **Opportunities** — the full pipeline, list or Kanban view, filterable by
  vertical/region/priority. Click any opportunity for its full score
  breakdown, sources, and linked contacts.
- **Regional Search** — pick a region, type a plain-language query (e.g.
  "stadium hospitality tenders in Saudi Arabia closing in Q4"), and ATLAS
  searches live. Save a search with a re-run interval to have it refresh
  automatically.
- **Relationship Intelligence** — search for decision-makers by
  organisation, region, vertical or role. Draft an outreach message with
  one click — it's saved as a draft; you review, edit and send it yourself.
- **Reports** — pipeline analytics and win rate; "Export / Print PDF" uses
  your browser's native print-to-PDF (no extra software needed).
- **Settings & Admin** — scan cadence, scan health, users, and the
  dark/light theme toggle.

## Stopping / restarting

```bash
docker compose down        # stops everything, keeps the database volume
docker compose up          # restarts without rebuilding
docker compose down -v     # stops everything AND deletes all data — careful
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Frontend loads but shows "Can't reach the API" | Backend container still starting, or `NEXT_PUBLIC_API_URL` misconfigured |
| Opportunities never appear | Check `ANTHROPIC_API_KEY` is set and valid; check backend logs for scan errors |
| `docker compose up` fails on `db` | Port 5432 already in use locally — stop any local Postgres, or change the port mapping in `docker-compose.yml` |
