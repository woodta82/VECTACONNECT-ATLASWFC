# Environment variables

Secrets are read on the server only. Nothing here reaches the browser bundle: the frontend has no `NEXT_PUBLIC_*` variables, and the only build-time variable is the internal API address.

| Variable | Service | Required | Default (development only) | Notes |
|---|---|---|---|---|
| `ENVIRONMENT` | api, worker, migrate | yes in deploys | `development` | `development` / `test` / `staging` / `production`. Staging and production refuse development credentials, non-HTTPS origins and (in production) enabled API docs. |
| `DATABASE_URL` | api, worker, migrate | **yes** outside development | local dev DB | `postgresql+psycopg://…`. A separate database per customer instance. Never share with the VECTA database. |
| `LOGIN_USERNAME` | api | **yes** outside development | none | Username of the single shared account. |
| `LOGIN_BOOTSTRAP_PASSWORD` | api | first boot only | none | Used once to create the credential if none exists. Remove after first sign-in. Ignored once a credential exists. |
| `PUBLIC_ORIGIN` | api | **yes** outside development | `http://localhost:3000` | Must be `https://` in staging/production. |
| `TRUSTED_PROXY_HOPS` | api | yes behind proxies | `0` | Number of trusted proxies in front of the API (web proxy = 1, plus any load balancer). Drives the single client-IP rule used for throttling and audit. |
| `REPORTING_TIMEZONE` | api | no | `Asia/Dubai` | Reporting time zone. Operational deadlines keep their source time zone as well. |
| `CUSTOMER_NAME` | api | no | `World Freight Company` | Shown as "configured for". Not the product name. |
| `BUILD_ID` | api | recommended | `local` | Commit SHA or image tag, shown on `/health/*`. |
| `PROXY_SIGNATURE_SECRET` | api | only with a Netlify front end | empty (off) | When set (32+ characters), every request except `/health/live` must carry a valid signed-proxy header `x-nf-sign` (HS256, issuer `netlify`, unexpired). Set the same value on the Netlify site. See `DEPLOYMENT.md` §8. |
| `API_DOCS_ENABLED` | api | no | on in dev/test | Must be off in production. Docs are behind the session in every environment. |
| `SNAPSHOT_DIR` | api, worker | no | `/var/lib/atlas/snapshots` | Source snapshots, only where the source permits retention. Include in backups. |
| `ANTHROPIC_API_KEY` | worker, api | no | empty | Leaves AI extraction **Not connected** when empty. The api uses it for relationship research (AI people reading), under the same budget caps. |
| `AI_MODEL` | worker, api | with key | empty | Model id. Check against provider documentation when configuring. |
| `SEARCH_PROVIDER` | api | no | empty | `brave` (Brave Search API, needs `SEARCH_API_KEY`) or `anthropic` (the Claude API's web search tool, uses `ANTHROPIC_API_KEY`; only its result URLs are used) enables the open-web discovery that every search runs by default, relationship research and contact discovery. Empty: the Discover page says so, searches are listed as not run with links, and a run with nothing else to search ends as "search not configured". |
| `SEARCH_API_KEY` | api | with provider | empty | Brave Search API key. Secret: redacted from logs and errors; never sent to the browser. |
| `SEARCH_MAX_QUERIES` / `SEARCH_RESULTS_PER_QUERY` | api | no | 6 / 5 | Searches per research run (0–20) and results read per search (1–10). |
| `RATE_LIMIT_PER_MINUTE` | api | no | 300 | Requests per minute per client address (60–10000). Keep the default in deployments; only automated test stacks raise it. |
| `SEARCH_API_BASE_URL` | api | no | `https://api.search.brave.com` | Development and test only may point elsewhere (a local stand-in); must be https otherwise. |
| `NOTICE_AGE_REVIEW_DAYS` | api, worker | no | 90 | A notice older than this whose open status has no closing date is shown as *unverified*; one with no supported status wording as *historical*. Triggers review only; never invents a closing date. |
| `AI_PRICE_INPUT_PER_MTOK`, `AI_PRICE_OUTPUT_PER_MTOK` | worker, api | with key | empty | USD per million tokens, from the provider's published pricing at configuration time. Used for conservative budget reservations. |
| `AI_API_BASE_URL` | worker, api | no | `https://api.anthropic.com` | Messages API base URL. Must be `https://` outside development/test. Local verification points it at the SIMULATED provider (`tools/fake_ai_provider.py`); never do that in a deployment. |
| `RETRIEVAL_ALLOW_PRIVATE_HOSTS` | worker, api | no | empty | Comma-separated `host:port` entries the SSRF guard may fetch although they are private (the local fixture site). **Refused outside development/test**; leave empty in every deployment. |
| `WORKER_LEASE_SECONDS` | worker | no | `300` | How long a running job's lease lasts without a heartbeat before another worker reclaims it. Lowered only in restart tests. |
| `BACKEND_INTERNAL_URL` | web (build arg) | yes | `http://127.0.0.1:8000` | Where `/api/*` is proxied. Fixed at build time. |
| `WFC_BOOKING_API_TOKEN`, `SCHEDULE_FEED_TOKEN`, `OPS_FEED_TOKEN`, `CHANNEL_ANALYTICS_TOKEN` | worker | not yet used | none | Names reserved by the adapter contracts. Those connectors stay **Not connected** until endpoints are provided and implemented. |

AI spend is blocked on a fresh database (`ai_kill_switch = true`, no monthly budget). Enabling it requires both a budget and turning the kill switch off under **Settings**.

Configuring the AI extractor (directive §3): set `ANTHROPIC_API_KEY`, `AI_MODEL` and both price variables on the worker, then under **Settings** set a monthly budget and lift the kill switch. From that moment, discovery runs extract claims from retrieved documents within the budget; with any of these missing, documents are still retrieved and wait in **Evidence Review** for a person to add claims.

Verification-only variables (`tools/local_stack.py`, `e2e/`): `WFC_STACK_PG`, `STACK_PYTHON`, `STACK_USER`, `STACK_PASSWORD`, `STACK_WEB_CMD`, `E2E_BASE`, `E2E_ARTIFACTS`, `E2E_USER`, `E2E_PASSWORD`, `WFC_TEST_PG`. None of them is read by the application.


## Reference datasets (30 Oct 2026)

The global airport directory is loaded from OurAirports' `airports.csv` (public domain) by the `airports` deployment step
(`python -m app.airports_cli load --auto --if-stale 30 --optional`, after the migration). Optional variables:

| Variable | Purpose |
|---|---|
| `AIRPORTS_PACKAGE` | Path inside the container of a verified import package (e.g. `/srv/airports-package`); when set, the package is loaded instead of downloading. |
| `AIRPORTS_PACKAGE_DIR` | Host directory mounted at `/srv/airports-package` (default `./deploy/airports-package`). |

Manual alternatives: `python tools/load_airports.py --download | --file airports.csv | --package DIR` with `DATABASE_URL` set, or upload
under Settings → Data sources → Airport directory. Until the full file is loaded the page says **Bundled seed only** (424 airports) or
**Partial directory**.
