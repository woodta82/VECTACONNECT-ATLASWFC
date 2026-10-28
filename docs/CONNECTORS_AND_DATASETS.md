# Connector register and dataset contracts

Connectors implement one interface (`backend/app/connectors/registry.py`). Each declares its capabilities, the **name**
of the credential it needs (never the value), its permitted scope, health reporting, and `fetch(checkpoint)` with cost
reporting. Status is shown verbatim in **Data Sources and Imports**. A connector that is not connected says
**Not connected**, and the views that depend on it show that gap, never a zero.

| Code | Connector | Status in this build | Credential (name) | How the workflow is exercised today |
|---|---|---|---|---|
| `file_import` | Controlled CSV/XLSX import | **Implemented and verified.** All 19 datasets: upload → mapping preview → validation → preview → commit → reconciliation; duplicate keys update rather than duplicate; reversal for 12 datasets, re-import correction for the other 7 (table below) | none | This is the authorised route for every WFC dataset until a live feed is supplied |
| `public_web` | Public web and RSS sources | **Implemented** (SSRF-safe fetch, document and provenance storage). Sources are disabled until registered and enabled | none | Retrieval alone never creates claims |
| `anthropic_extraction` | AI claim extraction | **Not connected** until `ANTHROPIC_API_KEY`, `AI_MODEL` and prices are set server-side | `ANTHROPIC_API_KEY` | Budget-reserved per call; strict schema; quarantine. Without it, reviewers record claims by hand |
| `wfc_booking_system` | WFC booking / quoting system | **Not connected** (adapter contract only) | `WFC_BOOKING_API_TOKEN` | bookings and quotes imports |
| `airline_schedule_feed` | Airline schedules and capacity | **Not connected** (adapter contract only) | `SCHEDULE_FEED_TOKEN` | capacity and gateway_connections imports |
| `reservation_exceptions_feed` | Reservation / supervision exceptions | **Not connected** (adapter contract only) | `OPS_FEED_TOKEN` | exceptions import |
| `digital_channel_analytics` | Digital booking channel events | **Not connected** (adapter contract only) | `CHANNEL_ANALYTICS_TOKEN` | channel_events import; without linked events the funnel reports `instrumentation_missing` |

No endpoint has been invented and no private system is scraped.

## What is needed to connect each live adapter

Nothing below has been supplied. Each item is required before an adapter can be written; the adapter then has to provide
incremental retrieval from a checkpoint, retries with back-off, idempotent upserts on the source's own id, reconciliation
of counts and totals per batch, health reporting, and visible freshness (the same guarantees the import path has today).

| Adapter | Exact information required from WFC or the provider |
|---|---|
| `wfc_booking_system` | The system's name and version; API documentation (base URL per environment, authentication method, rate limits); the endpoints or export that list bookings and quotes **changed since a timestamp or cursor**; the field dictionary, including booking status values, weight units (actual vs chargeable), currency, time zone of timestamps, and how amendments and cancellations are represented; a read-only test credential limited to the WFC companies in scope; a written authorisation for ATLAS to read this data |
| `airline_schedule_feed` | Which provider (airline direct, OAG/Cirium, or an internal schedule file); its licence terms for this use; API documentation; whether capacity is bookable or physical, in kg or volume, per flight or per period; how schedule changes are versioned; a test credential |
| `reservation_exceptions_feed` | Where exceptions are recorded today (system and export); API or scheduled export documentation; exception types and severity values; how status changes and resolution are represented; a test credential |
| `digital_channel_analytics` | The analytics platform and property; the event names for quote request, quote, booking and integration failure; the session identifier and how a booking reference is attached to a session; export or API documentation; a read-only credential |
| `anthropic_extraction` | An `ANTHROPIC_API_KEY` set as a server-side secret (never in chat or the browser), the model id and per-million-token prices from the provider's current pricing page, and the monthly and per-run budget caps to enforce |

<!-- BEGIN GENERATED DATASETS (tools/gen_import_templates.py) -->

All 19 datasets support upload, mapping, validation, preview, commit and reconciliation. Generated from the contracts; field detail is in `docs/import-templates/FIELDS.md`.

| Dataset | Kind | Target table | Source of truth | Refresh | Duplicate key | Corrections | Required fields | Reconciliation totals |
|---|---|---|---|---|---|---|---|---|
| agreements | operational | `representation_agreements` | WFC contract register | on change | external_id | re-import | `external_id`, `airline_iata`, `airline_name`, `operating_company`, `territories`, `services` | — |
| airlines | setup | `airlines` | Airline reference list maintained by WFC | on change | iata_code | re-import | `iata_code`, `name` | — |
| airports | setup | `airports` | Airport reference list maintained by WFC | on change | iata_code | reversible | `iata_code`, `name`, `country`, `timezone` | — |
| bookings | operational | `bookings` | WFC booking system export (Not connected) | every 24 h | external_id | reversible | `external_id`, `origin`, `destination`, `booked_at`, `status` | chargeable_weight, revenue |
| capabilities | operational | `capability_records` | WFC group capability register | on change | operating_company + service_code + station ('*' if company-wide) | re-import | `operating_company`, `service_code`, `status` | — |
| capacity | operational | `capacity_snapshots` | Airline schedule/capacity file (Not connected) | every 168 h | external_id | reversible | `external_id`, `origin`, `destination`, `period_start`, `period_end`, `basis`, `capacity_type`, `amount`, `snapshot_at` | amount |
| channel_events | operational | `channel_events` | Digital channel analytics export (Not connected) | every 24 h | external_id | reversible | `external_id`, `event_type`, `channel`, `occurred_at` | — |
| contacts | setup | `people` | WFC relationship records | on change | external_id | reversible | `external_id`, `full_name` | — |
| exceptions | operational | `operational_exceptions` | Reservation/supervision exception log (Not connected) | every 1 h | external_id | re-import | `external_id`, `exception_type`, `severity`, `description`, `status` | — |
| finance | operational | `financial_aggregates` | WFC finance month-end pack | every 744 h | operating_company + period_start + period_end + metric + currency | reversible | `operating_company`, `period_start`, `period_end`, `metric`, `amount`, `currency`, `basis` | amount |
| gateway_connections | operational | `gateway_connections` | Airline schedules at WFC gateways | every 720 h | external_id | reversible | `external_id`, `gateway`, `destination`, `departure_days`, `departure_time` | — |
| operating_companies | setup | `operating_companies` | WFC group structure | on change | name | re-import | `name` | — |
| quotes | operational | `quotes` | WFC quoting tool export (Not connected) | every 24 h | external_id | reversible | `external_id`, `forwarder`, `origin`, `destination`, `quoted_at`, `status` | amount |
| service_requirements | setup | `service_credential_requirements` | WFC service catalogue: credentials each service always requires | on change | service_code + credential_type | reversible | `service_code`, `credential_type` | — |
| services | setup | `services` | WFC service catalogue | on change | code | re-import | `code`, `name`, `category` | — |
| stations | setup | `stations` | WFC station network | on change | code | reversible | `code`, `name`, `is_offline` | — |
| territories | setup | `territories` | WFC territory definitions | on change | code | re-import | `code`, `name`, `kind` | — |
| training_credentials | operational | `training_credentials` | WFC training and certification register | on change | external_id | reversible | `external_id`, `operating_company`, `credential_type` | — |
| trucking | operational | `road_feeder_services` | Trucking provider schedules | every 720 h | external_id | reversible | `external_id`, `provider`, `origin_station`, `gateway`, `departure_days`, `departure_time` | — |

<!-- END GENERATED DATASETS -->

## Conventions

All timestamps carry a UTC offset (or a time zone is stated at upload). Money carries its ISO 4217 currency and is never
converted or summed across currencies. Weights are kg, with actual and chargeable weight kept separate; volume is m³.
Every view that uses imported data shows each dataset's source, its last successful import and whether it is Loaded,
Stale (older than its refresh requirement) or Not connected.
