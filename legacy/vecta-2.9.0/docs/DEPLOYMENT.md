# Deployment guide

`docker-compose.yml` at the repo root runs the whole system anywhere Docker
runs — a laptop, a VECTA office server, or any cloud VM. This guide covers
deploying it somewhere reachable by the whole commercial team, using
Railway as a concrete example (the same steps apply to any container host).

## Option A — Railway (recommended for a small internal team)

1. Push this repository to a **private** GitHub repo.
2. Railway → **New Project** → **Add PostgreSQL**.
3. **+ Create → GitHub Repo** (backend) → **Settings → Root Directory** →
   `backend`. Add variables from `.env.example` (`DATABASE_URL` referencing
   the Postgres service, `ANTHROPIC_API_KEY`, the `SCAN_*` variables,
   `FRONTEND_ORIGIN` — fill this in after step 4 — and the security
   variables `ENVIRONMENT=production`, `DOCS_ENABLED=false`, `FRONTEND_ORIGIN`;
   see `docs/SECURITY.md`).
4. **+ Create → GitHub Repo** (frontend, same repo) → **Root Directory** →
   `frontend`. Add `NEXT_PUBLIC_API_URL` pointing at the backend's Railway
   domain. That is the only public variable the frontend needs — it is a
   URL, not a secret. No authentication key is ever placed in the frontend
   build: the database-backed login session is the sole authentication
   mechanism (see `docs/SECURITY.md`).
5. Generate domains for both services (**Settings → Networking → Generate
   Domain**). Update the backend's `FRONTEND_ORIGIN` to the frontend's
   domain.
6. Confirm `https://<backend-domain>/health` returns `{"status":"ok"}`, and
   check the backend's **Logs** tab for the Global Scanner starting.

## Option B — Any Docker host

```bash
git clone <your-repo>
cd atlas
cp .env.example .env   # fill in real values
docker compose up -d --build
```

Put a reverse proxy (Caddy, Nginx, Railway/Fly's built-in ones, etc.) in
front of ports 3000 and 8000 for HTTPS and a real domain.

## Authentication

ATLAS is a private, owner-operated platform with **one authorised login**
and no public registration, invitations, roles or additional accounts.
Authentication is fully implemented (v2.8 Phase 1) and is the sole
application security boundary:

- Password stored only as a PBKDF2-HMAC-SHA256 hash (600k iterations,
  per-hash salt) — never in source, environment files or logs.
- Server-side database-backed sessions delivered in an HttpOnly, Secure,
  SameSite=None cookie; 24h absolute and 60min idle expiry.
- CSRF token required on every state-changing request.
- Per-IP lockout (5 failures / 15 min) plus an account-level escalating
  delay; all auth events written to `security_events`.

There is deliberately **no static shared-secret gate**. A key shipped in
the frontend build is readable by anyone who can load the page, so it was
never a private security layer; it was removed in v2.9. Do not
reintroduce one.

Set `FRONTEND_ORIGIN` to the exact frontend URL in production — CORS
fails closed without it. See `docs/SECURITY.md` and
`docs/PHASE1_HANDOVER.md` for the full checklist and the post-deployment
password rotation procedure.

## LinkedIn integration — upgrading Relationship Intelligence

Today, contact discovery runs entirely on public-web AI research and hands
back LinkedIn *search* links for a human to open and act on — fully
functional, fully compliant with LinkedIn's terms, zero extra setup.

If VECTA later obtains **LinkedIn's official API or a Sales Navigator
integration**, the upgrade point is `backend/app/ai/contact_discovery.py`:
replace `linkedin_search_url()` with a real API call, and the rest of the
system (Contact model, Interaction drafting, human-in-the-loop send flow)
needs no changes. `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` are
already reserved in `.env.example` for this.

## Scaling beyond a single instance

The automation engine (`backend/app/scheduler.py`) runs as background
`asyncio` tasks inside the one backend process. This is the right amount of
complexity for a single-replica deployment — which is almost certainly
right-sized for one internal commercial team. If ATLAS is ever scaled to
multiple backend replicas, the scan loops would run redundantly on each
replica; at that point, move the scheduler into a separate worker process
(or an external cron hitting `POST /scans/trigger`) so only one instance
drives the automation.

## Database backups

Whichever host you use, enable automated Postgres backups before this
becomes the system of record for VECTA's commercial pipeline — this is
genuinely a business-critical dataset the moment it's in daily use.
