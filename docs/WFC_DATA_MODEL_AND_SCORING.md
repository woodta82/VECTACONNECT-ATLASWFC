# VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE
## WFC freight data model and scoring specification (design, Phase 1 input)

**Status:** design only. No schema in this document has been migrated or tested yet; see `BASELINE_AUDIT.md` §1 for the environment blocker.

Conventions for every table: a UUID primary key `id`; `created_at` and `updated_at` as `timestamptz` in UTC; `source_ref` (FK to `provenance`) where a row came from an import or retrieval; and `numeric(18,4)` with an explicit `currency` (ISO 4217) for money, never float. Enumerations are stored as text with check constraints, so new values need a migration and no sports value is reused. There is no `visibility` column and no per-company access: everything in this instance is visible to the shared login (spec §10).

---

## 1. Authentication (single shared login)

| Table | Key columns | Notes |
|---|---|---|
| `auth_credential` | `username`, `password_hash`, `password_changed_at`, `sessions_valid_after` | Exactly one row, enforced by a `CHECK (singleton)` unique column. PBKDF2-SHA256 at ≥600k iterations (carried from baseline). |
| `auth_sessions` | `token_hash` (unique), `csrf_token_hash`, `created_at`, `last_used_at`, `expires_at`, `user_agent`, `ip`, `revoked_at` | Concurrent sessions allowed. Logout-all sets `revoked_at` on every row, and the password change bumps `sessions_valid_after`. |
| `login_throttle` | `key` (ip or `account`), `window_start`, `failures` | Durable and shared between replicas, replacing the in-memory dicts. |
| `audit_events` | `event_type`, `session_ref` (hash prefix), `request_id`, `ip`, `user_agent`, `entity_type`, `entity_id`, `detail` (jsonb, metadata only) | Logs exports, overrides, credential events and job runs. It never claims to identify an individual. |

Access is through the one shared credential; there is no per-record access control.

## 2. Network

| Table | Key columns |
|---|---|
| `operating_companies` | `name`, `legal_entity_name` (nullable; a brand is not a legal entity), `country`, `is_group_member` |
| `brands` | `operating_company_id`, `name` |
| `organisations` | `canonical_name`, `kind` (airline / forwarder / gssa / airport_operator / trucking_provider / other), `country`, `website` |
| `organisation_aliases` | `organisation_id`, `alias`, `source_ref`; unique on (normalised alias, organisation) |
| `organisation_merges` | `survivor_id`, `merged_id`, `reason`, `decided_at`, `reversed_at`: merges are reversible |
| `airlines` | `organisation_id` (1:1), `iata_code` (2-char, nullable), `icao_code` (3-char, nullable), `prefix` (3-digit AWB prefix, nullable) |
| `forwarders` | `organisation_id` (1:1), `network` (nullable) |
| `airports` | `iata_code` (3-char, validated), `icao_code`, `name`, `country`, `timezone` (IANA) |
| `territories` | `code`, `name`, `kind` (country / region / station) |
| `trade_lanes` | `origin_airport_id`, `destination_airport_id`; **unique (origin, destination)**; a check constraint rules out origin = destination. A→B and B→A are two rows. |

## 3. Capability

| Table | Key columns |
|---|---|
| `services` | `code`, `name`, `category` (gssa / tcm / handling / trucking / data_processing / accounting / invoicing / collections / training / technology) |
| `capability_records` | `operating_company_id`, `service_id`, `station_airport_id` (nullable), `status` (verified / unverified / expired), `verification_owner`, `valid_from`, `valid_to` (nullable = unknown), `commodity_restrictions`, `resource_constraints`, `languages`, `capacity_note`, `evidence_ref` |
| `training_credentials` | `operating_company_id`, `credential_type`, `holder_description`, `issued_on`, `expires_on` (**nullable = unknown, never defaulted**), `source_ref` |

## 4. Contracts

`representation_agreements`: `airline_id`, `operating_company_id`, `service_scope` (FK set via `agreement_services`), territories (FK set via `agreement_territories`), `effective_from`, `effective_to`, `renewal_date`, `notice_date`, `exclusivity` (exclusive / non_exclusive / **unknown**), `remuneration_model` (commission / fixed_fee / tcm_margin / hybrid / **unknown**), `remuneration_terms` (jsonb, as stated in the contract), `source_use_restrictions`, `appointment_rights` (**unknown** by default).

`third_party_appointments` records known appointments held by *other* GSSAs (`airline_id`, `territory_id`, `holder_organisation_id`, `exclusivity`, `evidence_ref`). This is what blocks unsupported expansion recommendations.

## 5. Intelligence

| Table | Purpose |
|---|---|
| `sources` | Source definitions: `name`, `family`, `kind` (public_web / rss / api / import), `authorisation_note`, `retention_permitted`, `enabled`, `connector_id` |
| `source_documents` | `original_url`, `canonical_url`, `publisher`, `published_at`, `event_date`, `retrieved_at`, `content_hash` (sha256), `content_type`, `bytes`, `snapshot_path` (nullable when retention is not permitted), `excerpt`, `page_ref`, `parser_version`, `ingestion_run_id`, `announcement_family_id` |
| `announcement_families` | Groups syndicated copies of one underlying announcement; confidence is counted per family, never per copy |
| `document_checks` | One row per check type, each with a separate result: `reachability`, `authenticity`, `relevance`, `current_status` |
| `claims` | `claim_type` (route_launch / route_suspension / gssa_tender / tender_deadline / tender_scope / representation_change / tcm_signal / capacity_statement / partnership / other), `subject_organisation_id`, `airline_id`, `territory_id`, `trade_lane_id`, `value` (jsonb, typed per claim type), `stated_deadline_utc`, `deadline_source_tz` |
| `claim_evidence` | `claim_id`, `source_document_id`, `stance` (**supports / contradicts / mentions**), `excerpt`, `page_ref`, `assessed_by` (rule / ai_proposed / human) |
| `signals` | `module`, `classification` (market_signal / unverified_lead / qualified_opportunity / risk_alert / research_item), `title`, `summary`, links to claims |
| `opportunities` | `module`, `signal_id`, `commercial_stage` (new / reviewing / qualified / pursuing / proposal / negotiation / won / lost / deferred / expired), `qualification_status` (incomplete / blocked / ready_for_review / approved_for_pursuit), `owner_person_id`, `dedup_key` (unique per module) |
| `opportunity_status_history` | Every stage/status change, with reason |
| `qualification_checks` | `opportunity_id`, `check_code`, `result` (pass / fail / unknown / review_required), `evidence_ref`, `reviewer_note`, `reviewed_at` |
| `qualification_overrides` | `check_code`, `reason` (required), `session_ref`, `created_at`, `expires_at`. These can change a check *result*, never create evidence. |

## 6. Commercial work

`people` holds descriptive owners, contacts and researched people (with research facts, evidence, relationships and introduction routes since `wfc_0011`). Further tables: `contacts` (person ↔ organisation, role), `account_ownership`, `engagements`, `tasks` (`source_type`/`source_id`, `due_at_utc`, `status`, `owner_person_id`, unique on `dedup_key`), `referrals` (from operating company → to operating company, `opportunity_id`), `decisions`, `proposals`, `outcomes`, `realised_values`.

## 7. Performance (only what the defined use cases need)

| Table | Key columns and bases |
|---|---|
| `quotes` | `external_id` + `source_id` unique; `forwarder_id`, `trade_lane_id`, `quoted_at`, `status`, `lost_reason`, `chargeable_weight_kg`, `amount` + `currency` |
| `bookings` | `external_id` + `source_id` unique; `forwarder_id`, `airline_id`, `trade_lane_id`, `flight_date`, `booked_at`, `status` (confirmed / amended / cancelled), `actual_weight_kg`, `chargeable_weight_kg`, `volume_m3`, `revenue` + `currency`, `fx_rate`, `fx_source`, `fx_date`, `amends_booking_id` |
| `capacity_snapshots` | `airline_id`, `trade_lane_id`, `flight_date` or period, `basis` (**weight_kg / volume_m3**), `capacity_type` (offered / bookable / allotted), `amount`, `snapshot_at` |
| `operational_exceptions` | `exception_type` (reservation / supervision / post_flight), `severity`, `dedup_key` unique while active, `customer_organisation_id`, `operating_company_id`, `deadline_utc`, `status`, `resolved_at` |
| `operational_exception_history` | Every state change |
| `road_feeder_services` / `gateway_connections` | `provider_id`, `origin_station`, `gateway_airport_id`, `schedule`, `connection_cutoff_local` (**nullable = unresolved**), `restrictions` |
| `channel_events` | `event_type` (search / quote_request / quote / booking), `session_key`, `booking_external_id`, `occurred_at`, `channel` |
| `financial_aggregates` | `operating_company_id`, `period_start`, `period_end`, `metric`, `amount`, `currency`, `basis` |

Both the flight/event date and the reporting period are stored. The reporting timezone setting defaults to `Asia/Dubai`.

## 8. Ingestion and automation

`connectors` (`kind`, `status` = **not_connected** / configured / healthy / degraded, `credential_ref` (env-var name only), `scope`), `import_jobs` (`dataset`, `file_hash`, `mapping`, `mode` dry_run/commit, `status`, totals), `import_row_errors` (quarantined rows with raw values), `import_reversals`, `checkpoints`, `schedules` (`job_type`, `scope` (source/region/module), `cron`, `timezone`, `overlap_policy`, `next_run_at`, `last_success_at`, `enabled`), `jobs` (`job_type`, `execution_key` **unique**, `status`, `run_after`, `attempts`, `max_attempts`, `lease_owner`, `lease_expires_at`, `last_error`, `checkpoint`), `job_attempts`, `budget_periods` (`month`, `cap`, `warn_at`), `budget_reservations` (`job_id`, `estimated`, `actual`, `status`), `ai_calls` (`provider`, `model`, `prompt_version`, `schema_version`, tokens, `estimated_cost`, `actual_cost`, `status`), `notifications` (`dedup_key` unique, `delivery_state`), `system_flags` (`kill_switch`).

---

## 9. Scoring (provisional, version `wfc-score-0.1`)

Rules (spec §7):
- **Four separate assessments**, never merged into one number: *commercial attractiveness*, *evidence confidence*, *pursuit readiness*, *risk*.
- Scores are computed on the server, deterministically, from `scoring_model_versions` rows (factor, anchors, weight). Changing a weight creates a new version; previous assessments keep their version.
- Each factor value is `known` (0–4 anchor) or `unknown`. Missing is **not zero**. Coverage = known weight ÷ total weight. Below **60% coverage** the assessment displays "Insufficient evidence" instead of a number.
- Evidence confidence counts **announcement families**, not documents. Assumptions add no confidence.
- Opportunities are ranked only within their module. No label uses "probability" or "win chance".
- **All weights are provisional** until evaluated against at least 20 recorded outcomes per module.

### 9.1 Proposed factors: Airline representation (GSSA / TCM tender or route signal)

| Assessment | Factor | Anchors (0 → 4) | Weight |
|---|---|---|---|
| Attractiveness | Territory fit with existing WFC network | none → contiguous → same region → existing station → existing station + same airline | 0.30 |
| Attractiveness | Expected retained contribution band (only if remuneration terms known) | unknown stays unknown; bands set by WFC | 0.30 |
| Attractiveness | Strategic airline relationship | none → contact → active engagement → existing agreement elsewhere → multi-territory agreement | 0.20 |
| Attractiveness | Duration / renewal prospects | as stated in tender; otherwise unknown | 0.20 |
| Evidence confidence | Independent supporting families | 0 → 1 → 2 → 3 → ≥4 families, at least one official | 0.50 |
| Evidence confidence | Source authority of best family | unverified → trade press → airline/airport release → official tender portal | 0.30 |
| Evidence confidence | Recency of latest supporting family | >180d → 90–180 → 30–90 → 7–30 → <7d | 0.20 |
| Readiness | Capability verified for service+station | expired/unverified → partial → verified | gate + 0.50 |
| Readiness | Eligibility criteria satisfied | fail → unknown → partial → pass | 0.30 |
| Readiness | Owner assigned and deadline workable | — | 0.20 |
| Risk | Known exclusive appointment elsewhere / territory conflict | blocking | gate |
| Risk | Contradicting evidence present | none → minor → material | 0.60 |
| Risk | Guarantee / exposure required | none → unknown → material | 0.40 |

Equivalent tables for the other eight modules (account growth, forwarder sales, capacity, service, trucking, outsourcing/training, technology, network development) follow the same structure. They will be written alongside each module's implementation, so the factors match the data that module actually has.

### 9.2 Commercial economics

Stored separately on `commercial_values`, all `numeric` with currency: `airline_revenue`, `wfc_remuneration`, `incremental_costs`, `guarantee_exposure`, `duration_months`, `retained_contribution`, plus `basis` (contract / scenario / unknown) and `assumptions` (jsonb list, each with a source date).

Generic contribution = retained remuneration − relevant incremental costs, used only when no contract terms exist and labelled as a scenario. If the terms are unknown, the value status is **unqualified** and no figure is shown.

Pipeline totals:
- They never sum across currencies.
- They never sum alternatives that compete for the same mandate (shared `competition_group_id`, so only the maximum counts).
- They count a referral once, attributed to the receiving company.
- Potential, won and realised values are kept separate.
