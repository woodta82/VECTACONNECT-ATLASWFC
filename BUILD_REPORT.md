# VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE
## Release `4.5.0-wfc.16`, 29 October 2026: four research purposes; company and people intelligence without a tender

Clarification of 29 Oct 2026 (superseding any tender-led reading of the earlier instructions) and the BRU spreadsheet instruction
("Use the attached BRU spreadsheet as an example of the research output required globally — not as the complete database or a
Belgium-only scope … Preserve the spreadsheet's original information as supplied data awaiting verification … Company and people
discovery must work without a tender being present. Include passenger airlines carrying belly cargo; distinguish them from
passenger-ticket-sales mandates. Keep the current design and simple workflow unchanged."). Continues from 4.4.0-wfc.15; nothing is
removed. Design, Poppins, colours, components and the single shared login are unchanged; the public marketing website is not in
this repository and is untouched. Schema `wfc_0015` (additive).

**1. Four independent research purposes within Discover.** "What are you looking for?": Opportunities, Companies, People, Market
intelligence. None needs a tender or opportunity first. Companies and People run through the open-market research pipeline of 4.3
(organisation pages, authorised web search, robots.txt, per-run limits, evidence rules) with the purpose recorded on the discovery
(`contact_discoveries.purpose`); Opportunities and Market intelligence run through the discovery pipeline of 4.4 with the purpose
on the search (`discovery_searches.purpose`). The Relationships page keeps its "Discover contacts" button (People purpose).

**2. A commercial brief.** Every purpose accepts a plain-language research request (up to 600 characters) beside country, region,
worldwide scope, airport and the nine capability categories. The brief's content words narrow the public web queries
(`domain/company_intel.build_purpose_queries`, `domain/open_web.build_market_queries`) without filtering results by its words;
"Keywords" keep their stricter meaning. Public websites, directories, press releases, biographies, reports and accessible documents
are read; tender-platform registration is never a dependency (market intelligence does not use procurement-portal search templates).

**3. Company and people intelligence built directly.** A company result records: official website (only when a page is on a site
carrying the company's name), published e-mail addresses (from the sentence naming the company, a directory entry's contact line,
or the company's own pages — never from the model's memory), locations, services, parent or group (as stated), represented airlines
or partners (from statements such as "GSSA for X and Y"; cargo representation kept apart from passenger ticket-sales mandates and
from representation of unstated scope), relevant individuals (the people the company's pages bind to it, through the unchanged
attribution rules), and evidence per fact (`organisation_evidence`). A name alone creates no record: a legal or trade suffix or a
known name is required, and kind, addresses and representation bind to the subject of the sentence. People results are unchanged
(name, current role, organisation, remit, LinkedIn search or confirmed profile, evidence) and gain the brief. Nothing missing is
invented: a kind, website or country not stated stays "not established". The BRU spreadsheet is the benchmark: a supplied list is
loaded (Data sources → Supplied lists), preserved row by row, and everything from it is marked **supplied — awaiting verification**
(organisations, addresses, represented-airline entries by IATA code; "ALL" records nothing as represented; designators are resolved
from a reference list as a reading aid only). Airlines from the list are typed passenger-belly or cargo-only. Nothing supplied is
assumed current until research sources it or a person verifies it on the company page (verify record; confirm / lapsed per address
and per representation, each with a basis).

**4. Record types kept distinct.** Companies, individuals, representation and business relationships (`organisation_relationships`),
market intelligence (signals), commercial opportunities and tenders are separate, linked records. A researched company leads to a
commercial opportunity only when a person records it with an interpretation (shown on the opportunity, `origin_interpretation`); a
market signal only when a person tracks it (unchanged). Neither becomes a tender.

**5. Qualification appropriate to the result.** Tender deadline and procurement checks apply to tenders only. Companies, people,
partnerships and market signals are never blocked for lacking a deadline, reference or invitation to bid; evidence, freshness,
relevance (a company relevance out of 100 with every point explained: kind 30, geography 25, profile completeness 20, brief terms 15,
evidence 10), duplication (no second record for the same name at the same site; the person duplicate review is unchanged) and
uncertainty controls (supplied / sourced / confirmed / lapsed / not established) apply to every record type.

**6. Control panel.** Six clearly separated summaries at the top — Commercial opportunities, Companies researched, Relevant people
identified, Relationship gaps and next actions, Important market developments, Tender deadlines — each with counts, a few items and
the link that opens the filtered records (`GET /control-panel/summaries`). The analytics below are unchanged and secondary.

**7. The broader workflow, verified** (SIMULATED: fixture pages, a scripted search stand-in and a scripted AI provider; no real site
or key): journey R (`e2e/test_b_research_purposes_journey.py`) in Rwanda, where the fixture holds no tender — company discovery from a
brief (a directory, a GSSA's own site: website, two published addresses, two cargo representations sourced, a passenger ticket-sales
agent recorded separately, two people bound by the leadership page; no opportunity created), the company page (confirm a
representation, verify the record), standalone people discovery with a brief, market intelligence (a route announcement becomes a
market signal with no deadline and no tender status; "Track as a commercial opportunity" available), a supplied BRU-style list
loaded as data awaiting verification (LOT Polish Airlines resolved, an unknown designator kept as written, belly carriers listed),
the six Control-panel summaries opening filtered records, and a commercial opportunity recorded from the company with an
interpretation (counted under opportunities, never under tender deadlines).

**Checks on this release:**
- backend: **1323 passed** (new: `tests/domain/test_company_intel.py`, `tests/sql/test_migration_0015.py`,
  `tests/integration/test_company_intelligence.py`: company discovery in a new country without a tender; people with a brief and
  market research; a supplied list preserved, verified and leading to an opportunity only with an interpretation);
- browser journeys: **34 passed**, including journey R above and every earlier journey;
- type check, lint and ESLint clean.

**Real public-source demonstration: NOT available in this session** (no search or AI key; no outbound access). Every result in the
evidence is SIMULATED. With keys set, the same Discover purposes run against the public web; the limits (queries per run, pages per
run, AI sections per run, monthly budget) apply unchanged. No LinkedIn integration exists: LinkedIn links are searches.

**One shared login**, unchanged. No WFC operational data is needed for any of this.

## Release `4.4.0-wfc.15`, 29 October 2026: open-web discovery as the default

Instruction of 29 Oct 2026 ("Continue from atlas-wfc-4.2.0-wfc.13 … using atlas-vecta-v1.0-FINAL as the functional reference for
public-source discovery"). This release continues from 4.3.0-wfc.14, which already contains the relationship work on top of
4.2.0-wfc.13; nothing of 4.2.0 or 4.3.0 is removed. The design, Poppins, colours, components, Overview, Control panel and
responsive behaviour are unchanged; there is no public marketing website in this repository. Schema `wfc_0014` (additive).

**1–3. Open-web discovery is the default; the journey is unchanged.** The Discover screen keeps its inputs (worldwide, region,
one or several countries; the nine capability categories; optional keywords, organisation or airline; Search now). A built-in
source, "Open web (authorised search)", is planned for every search: the geography and categories become public web searches
(`domain/open_web.py`, named by purpose), the search connector returns public pages, and each page is fetched and read itself
through the existing pipeline (`services/discovery.py`, `web_search` source type). A new country or region needs no website
registered. Registered sources remain optional monitoring inputs; the open-web source cannot be edited or retired, only disabled.
Configuration stays in Settings (search provider and key, AI budget, limits). Two connectors: Brave Search API, or the Claude API's
web search tool (result URLs only).

**2 and 8. Public sources; restricted results.** Queries name tenders and procurement notices, airline and airport sites,
newsrooms and press releases, trade publications, public reports and documents. A result that needs registration, login or
payment (HTTP 401/402/403, or a page that shows only a gate) is labelled, not read and never bypassed; a public original or
corroborating copy is searched for by its title, and the run says whether one was found; other results continue. Each result
page is attributed to its own site, with authority inferred conservatively (government or procurement portal, the organisation's
own site, known trade press, otherwise unverified; `source_documents.doc_family`, `doc_authority`).

**4–5. Openings as well as tenders; the nine areas.** Each area has a formal-notice query and commercial-opening queries (mandates
and appointments, Total Cargo Management, routes and capacity, gateways and road feeder, outsourcing and training, technology,
partnerships and network). Explicit opportunities and market signals stay separate records; the commercial interpretation is
labelled as ATLAS's, with what remains unconfirmed. Nothing is invented. WFC internal data stays optional.

**6–7. Every result connects to relationship research**, unchanged from 4.1–4.3 (sourced candidates, confirmed identities,
recorded relationships, possible routes and gaps shown separately; attribution and duplicate review preserved). Evidence
controls are unchanged; the run page gains "Public web searches" (what was asked, what each returned, what was not run and why)
and "Restricted results".

**Outcomes** stay distinct: results, no relevant results, **search not configured**, **search failure**, **inaccessible sources**
(a flag beside the outcome), incomplete, partial coverage, nothing searched.

**Checks on this release:**
- backend: **1276 passed** (new: `tests/domain/test_open_web.py`, `tests/sql/test_migration_0014.py`,
  `tests/integration/test_open_web_discovery.py`: a country search with no registered website; region and worldwide; no connector;
  failed search; restricted results with corroboration; registered sources beside the open web);
- browser journeys: **33 passed**, including the acceptance journey of item 8 (`e2e/test_a_open_web_journey.py`, run first, before any website is registered):
  one-time server-side configuration, a country and category search, public sources found through web search, originals read, a
  labelled record (unverified publisher) tracked by a person into an opportunity, relationship research, a restricted result that
  does not stop the search, regional and worldwide searches, "nothing relevant found" distinct from the other outcomes, the
  Overview and Control panel showing the results; plus every earlier journey;
- type check, lint and ESLint clean.

**Real public-source demonstration: NOT available in this session.** No search key (Brave or Claude API) and no AI key were
supplied, and this build environment has no outbound access to public sites. Every result in the evidence is SIMULATED: fixture
pages served locally and a scripted search stand-in. To run the real demonstration once keys are set: `tools/live_trial.py`
(opportunities) and `tools/live_research_trial.py` (people) record the queries, pages read, results, limitations and costs.

**One shared login**, unchanged.

## Release `4.3.0-wfc.14`, 29 October 2026: relationships to the ATLAS v1.0 parameters, from the open market

Instruction of 29 Oct 2026: the Relationships section is to work to the parameters of the attached ATLAS v1.0 build
(`atlas-vecta-v1.0-FINAL`: contact discovery from public sources, stakeholder types, decision authority and posture, relationship
health with decay and influence weighting, the five questions, impact on success, outreach drafted by AI and sent by a person), and
relationships are to be based on searching for contacts in the open market relevant to the WFC brief (`ATLAS_WFC_Brief_V2`: the nine
capability areas). Schema `wfc_0013`.

**What is new** (details: `docs/SCREENS_AND_WORKFLOWS.md`, "Relationship intelligence to the ATLAS v1.0 parameters"):
- open-market contact discovery (`POST /contacts/discover`, continue, list, detail) by organisation, countries or region, capability
  area and role focus, through the existing evidence pipeline (organisation pages and their links, authorised search results), with a
  relevance to the brief out of 100 per contact, every point explained (`domain/contact_relevance.py`);
- a second search connector: the Claude API's web search tool (`SEARCH_PROVIDER=anthropic`, uses `ANTHROPIC_API_KEY`); only its
  result URLs are used, then fetched and read like any page;
- stakeholder judgements recorded with a basis (`POST /people/{id}/judgement`); engagement direction and the `no_response` outcome;
- relationship health, momentum, attention and the recommended action, computed on read (`domain/relationship_health.py`,
  `GET /people/{id}/health`), with the ATLAS v1.0 weights and the at-risk cap; shown on the person page, in the directory and the
  CSV export (`GET /people/export.csv`);
- the five questions (`GET /relationships/questions`) and the relationship share of the opportunity score
  (`GET /relationships/impact/{id}`, shown on the opportunity page);
- outreach drafts (`POST /people/{id}/outreach-drafts`, edit, sent or discarded): template from the record; AI rewording accepted
  only when it adds no fact and keeps the substance (`ai/outreach.py`); "sent" is recorded by a person and adds an outbound engagement.

**What is different from ATLAS v1.0, and why**: v1.0 asked an AI researcher with web search for named people and a candid score.
Here the names come only from pages ATLAS fetched and read, with the passage that names them, and the relevance is computed from
recorded facts so that it can be checked. v1.0 stored health; here it is computed on read from the engagement record, so nothing
goes stale. The principle "no relationship strength score" of the 28 Oct refocus is replaced by a health score that is explained
line by line and never changes a research state; win probability is still never computed.

**Checks on this release** (local stack, sample data):
- backend: **1264 passed** (1263 on the first full run plus the health check corrected to `wfc_0013`; new: `tests/domain/test_relationship_health.py`, `tests/unit/test_search_provider_and_outreach.py`,
  `tests/sql/test_migration_0013.py`, `tests/integration/test_open_market_relationships.py`);
- browser journeys: **32 passed**, including the new journey P (discover contacts for Savanna Example Air in Uganda; relevance breakdown; judgement; engagements;
  health; outreach drafted, edited and recorded as sent; the five questions; export), plus every earlier journey and the responsive
  and accessibility pages;
- type check, lint and ESLint clean.

Not done: real sources and keys (the journeys use fixture pages and a simulated search stand-in); WFC has not yet confirmed the
weights of health, relevance or the opportunity score; no authorised LinkedIn integration.

## Release `4.2.0-wfc.13`, 29 October 2026: Control panel (opportunities per market, score out of 100)

Asked for on 29 Oct 2026 from a screenshot of a pipeline dashboard. ATLAS holds no contract values, so the panel counts
opportunities rather than money.

**New screen: Control panel** (`/control-panel`, in the primary navigation after the Overview; same filters as the Overview):
- totals: live opportunities, markets, average score, records with a relationship or introduction, deadlines within 30 days;
- live opportunities by region (ring chart) and by score (10-point ranges and four bands);
- by market (UN M49 sub-regions), by capability area, by country;
- score per opportunity, ranked, each with a breakdown of its points and the reason for each.

**Opportunity score out of 100** (`backend/app/domain/opportunity_score.py`): a transparent points score from facts ATLAS already
holds. Provisional weights: stage 30, relationship position 25, evidence reviewed by a person 16, time to respond 15, source
freshness 10, scope and status clear 4. Closed, cancelled, awarded, expired and historical records are not scored. It is
labelled everywhere as not a probability of winning. It is separate from the versioned four-dimension assessment
(`app.domain.scoring`), which stays uncombined; that assessment is unchanged.

**API:** `GET /control-panel` with the Overview's filter parameters. Market rule: a record naming several countries counts once
in each market it names; a record naming no country is counted under "Country not stated".

**Checks on this release** (local stack, sample data):
- backend: **1225 passed** (`tests/domain/test_control_panel.py` new: score arithmetic, each weakness costs its stated points,
  unscored records, markets counted per region; the relationship integration journey now also checks the panel before and
  after a cancellation);
- browser journeys: **31 passed**, including the new journey O (panel totals, market and country lists, the ranked table, the
  breakdown, a country filter) and the responsive and accessibility pages at seven widths in both themes, now with
  `/control-panel`;
- type check, lint and ESLint clean; the region colours were validated for colour-vision deficiency on both surfaces.

Not done: real data (the screenshots use the journeys' example organisations); WFC has not yet confirmed the weights.

## Release `4.1.1-wfc.12`, 29 October 2026: brand colour change only

The accent blue is replaced by electric cyan, as instructed on 29 Oct 2026:

| Colour | Hex | Where |
|---|---|---|
| Electric cyan | `#00E5F2` | logo symbol (`public/vecta-mark.png`, recoloured with its transparency unchanged), primary buttons, DYNAMIC MARKET INTELLIGENCE, selected tabs and toggles, active navigation, links, focus rings, information badges |
| Light cyan | `#66F2FF` | primary button hover |

Changes:
- text on a cyan fill is now near-black `#0b0b0d`, because white on cyan is unreadable (contrast 12.6:1 on `#00E5F2`, 14.7:1 on `#66F2FF`);
- **light theme only:** cyan on white measures 1.56:1, so links, focus rings and badge text use a deeper cyan, and the logo symbol is darkened. Links and badge text use `#00727A` (5.7:1), focus rings `#00838F` (4.5:1), and the symbol is darkened by a filter. Buttons and fills stay `#00E5F2`.

Unchanged: layout, components, Poppins, the five-section navigation, the backend, the schema (`wfc_0012`) and the data. No blue remains in the application stylesheet (`legacy/` is the untouched VECTA 2.9.0 reference).

"Advantage.", the shipping lanes, the glowing ports and the globe rim do not exist in this repository. They belong to the public marketing website, which is not in this repository and was not touched.

**Checks on this release:**
- type check, lint and ESLint: clean;
- full browser journeys (`tools/run_journeys.sh`): **30 passed**, including responsive and accessibility pages at all widths in both themes and visible keyboard focus;
- screenshots were reviewed in the dark theme, the light theme and the login screen;
- backend code is unchanged from 4.1.0-wfc.11, so its 1220 passing tests were not re-run.

Everything below describes 4.1.0-wfc.11 and still applies.

## Release report: release `4.1.0-wfc.11`, schema `wfc_0012`, validation rules v7, 28 October 2026

This is the only build report. It replaces the report for `4.0.0-wfc.10`. Where an older document disagrees, this report
is current. Requirement-by-requirement classification: `docs/ACCEPTANCE_MATRIX.md` (section S for this release).
Screens and workflows: `docs/SCREENS_AND_WORKFLOWS.md`.

**What this release does.** It completes opportunity-led relationship research. Users can find opportunities and build an
evidence-backed picture of who matters, whom WFC already knows and how to reach the relevant people, without WFC
operational data:
- research reads more than the opportunity's own documents;
- every title and organisation is bound to a person by a source passage, or stays "not established";
- people are never merged on a name alone;
- research says when it is incomplete.

**What it keeps unchanged:**
- the identity VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE;
- Poppins, the colours, the components and the five-section navigation;
- the nine capability areas as categories;
- worldwide, regional and country search;
- the Overview;
- WFC data as optional enrichment;
- one shared login;
- the evidence, freshness, deduplication and uncertainty controls.

This repository contains no public marketing website, so nothing of it was touched. Human approval is still required for
external communications, bookings, pricing and commitments, and **nothing is sent automatically**. No VECTA contacts, deals
or credentials were imported.

### Commit identification

| What | Commit |
|---|---|
| **Verified commit.** Every check in section 1 ran on a clean `git archive` export of it. | `028d52d53e84257979e6f15a51d8a7cb00ce575e` on branch `wfc/relationship-research-2026-10-28`, based on `bd79751` (release 4.0.0-wfc.10) |
| **Release commit.** Adds this report, `PULL_REQUEST.md` and the change manifest. | Recorded in `RELEASE-COMMIT.txt` in the delivered ZIP. `git diff --stat <verified> <release>` shows documentation only. |

### Status: not production-ready

**Met in the software as tested here (sections 0 and 1):**
- Research reads more than the opportunity's documents: the organisations' own pages and the links they offer, pages
  and documents the team adds, and an authorised search connector when one is configured.
- A title or organisation is attached to a person only by a passage that binds them. Unsupported associations stay
  unresolved.
- No merge on a name alone. Possible duplicates are reviewed by a person, and every merge can be undone.
- Long documents are read in resumable sections under the budget controls. "No people found" is distinct from
  "research incomplete".
- The journey runs end to end without WFC imports, in the backend and in the browser.

**Not met:**
- **Real inputs and the configured AI extractor have not been used.** There is no `ANTHROPIC_API_KEY` and no search key.
  The build environment cannot reach public sites, and the web-reading tool available here returns summaries, not
  original documents. Every journey uses synthetic pages, a simulated search provider and a simulated AI provider,
  labelled as such.
- **The real production stack has not been verified on this release.** The lock files are now part of the source. They
  were generated by the repository's own CI on 28 Oct, and that run built the real Next.js app from them. This session
  can read the repository but cannot push to it (the Claude GitHub App is not installed for it), so CI could not run on
  4.1.0-wfc.11.
- **No authorised LinkedIn integration is connected.**

### Result labels

| Label | Meaning |
|---|---|
| **Passed** | Ran here, on the verified commit, and passed. The evidence file is named. |
| **Failed** | Ran here and returned failure, including expected failures. |
| **Simulated** | Ran here with a local stand-in for something external. The result shows only what the stand-in allows. |
| **Unexecuted** | Could not run here. The exact dependency and the way to run the check are given. |

---

## 0. Instruction checklist (third instruction of 28 Oct 2026, eight items)

| # | Item | What was done | Evidence | Result |
|---|---|---|---|---|
| 1 | **Complete opportunity-led research** | Research reads, in order: (1) the opportunity's documents; (2) pages and documents added by the team (URL, upload, or pasted text); (3) the organisations' research pages (website, newsroom, leadership page) and the same-site links they offer to leadership, management, team, board and newsroom pages and relevant news items; (4) authorised web search (Brave Search API, off unless configured), with queries built from the organisation, target roles, country and reference. Fixed addresses are tried only when a site offers no links, and are labelled "guessed address". robots.txt is respected. Without a connector, each search is listed as not run, with a link. | `test_relationship_research.py` (11 tests); journey N | **Passed** with synthetic pages and a simulated search provider; real search **unexecuted** |
| 2 | **Validate who holds each role** | `domain/attribution.py` binds by: the same clause; a possessive; an appointment ("appointed … as", "named … as", "promoted … to"); "whose"; "is/was … at"; "joins … as"; a contact line; a listing on the organisation's own leadership page. Titles are recorded as current, former or incoming. The organisation passage is kept separately where it differs. A title elsewhere in the document is never attached. AI proposals keep a title or organisation only when the quoted passage contains it and the rules confirm the binding. | `tests/domain/test_attribution.py` (20); evaluation sets (section 5) | **Passed** on authored text |
| 3 | **Organisation attribution and identity** | Never the first organisation in a quote. A person's relation to the organisation being researched is recorded as one of: works there, board member, partner, customer, other organisation (quoted or mentioned), not established. Being named on a company's site does not make someone an employee; only a leadership, team or board listing does. Records merge automatically only on the same passage, or the same name at the same known organisation. Otherwise a new record and a possible duplicate for review. A merge lists every moved row and can be undone; evidence is never deleted. | attribution tests; `test_same_name_…_reversible`; `test_same_name_at_the_same_known_organisation…`; `test_migration_0012.py`; journey N (N4, N5) | **Passed** |
| 4 | **Long documents and research coverage** | Documents are read in sections. The rules read every section. The AI extractor reads sections up to a per-run limit, under the budget reservation, and resumes on Continue research. Each document records sections read by the rules and by the extractor, its status (read / skipped with reason / could not fetch / not read yet) and the people found. A section cut to fit the extractor is reported. The outcome is people found, no people found, or incomplete, with what remains. | `test_long_documents_…_resume`, `test_budget_refusal_…`, `test_no_people_found_is_distinct_from_incomplete`; journey N (N1, N2) | **Passed**; AI **simulated** |
| 5 | **Relationships central and evidence-backed** | Each opportunity shows: organisations and their involvement (including partner or customer organisations of linked people); confirmed identities and research candidates in separate lists, each with evidenced titles; recorded relationships (holder, nature, basis); confirmed introductions and possible routes, kept apart; research coverage; gaps and next actions. LinkedIn search links stay separate from confirmed profiles. The brief export includes all of this. | journeys M and N; backend journey | **Passed** |
| 6 | **Simplified workspace preserved** | No change to the nine categories, the geography modes, the Overview, the optional WFC data, the single login or the controls | full backend and browser suites | **Passed** |
| 7 | **Journey with real inputs; failure tests; extractor evaluation** | The journey is proven end to end without imports, on synthetic inputs (section 1). Failure tests cover: wrong role attribution, multiple organisations, same-name people, incomplete research, cancelled opportunities, retained history. For real inputs: `tools/live_research_trial.py` runs research on a deployment and writes a review sheet for a person to check against the originals; `tools/research_eval.py --fetch` measures attribution on authorised original pages. | section 1; sections 4 and 5 | Synthetic: **passed**. Real inputs and the configured extractor: **unexecuted** |
| 8 | **Release foundation** | The locks generated by the repository's `commit-locks` run were carried in; the dependency inputs have not changed since, and the gate passes. CI defects fixed: backend jobs downloaded a lock artifact that only the skipped job produced; schema revisions were hard-coded; failure causes could not be read. Failing steps now publish their log tail as annotations. | `lock-gate.log`; CI run 40655396285 (28 Oct, on 3.7.0-wfc.9 + locks) | Locks **passed**. Clean install and the real stack on this release: **unexecuted** (no push access) |

### The journey (instruction item 7), as run

Country or regional search → relevant opportunity → organisation research → sourced person and role → targeted LinkedIn
search → confirmed profile → recorded relationship or introduction route → updated Overview. It runs without imports.

| Step | Backend (HTTP API, PostgreSQL) | Browser |
|---|---|---|
| Country / regional search finds the opportunity | `test_the_intended_journey_without_wfc_operational_data` (country, region, worldwide) | M1–M3 |
| Organisation research | `test_research_follows_the_organisations_own_links…` | N1–N2 (company site, links followed, robots.txt, search result) |
| Sourced person and role | bindings with passages, current/former/incoming, affiliation | N3, N6 |
| Targeted LinkedIn search → confirmed profile | profile rules (member URL only) | M6–M7 |
| Relationship or introduction route | willingness required for "available" | M7, M7b |
| Updated Overview | step 8 of the backend journey | M8, N (Overview) |
| Without operational imports | asserted: no import job, booking or financial record | — |
| Cancelled opportunity keeps relationships | step 9; the interpretation says it cannot be bid for | M10 |

## 1. Passed checks (verified commit, clean export; PostgreSQL 16, Python 3.13, Node 22, Chromium)

| # | Check | Command | Result | Evidence |
|---|---|---|---|---|
| 1.1 | Lock gate | `tools/check_locks.sh` | **Passed**: the three locks are present and hashed (`locks OK`) | `lock-gate.log` |
| 1.2 | Python lint, types, secret scan | `ruff check app tests ../e2e ../tools`, `mypy app`, `tools/secret_scan.py` | ruff 0 findings; mypy 0 errors (78 files); secret scan 0 findings | `static-checks.log` |
| 1.3 | Backend tests on PostgreSQL | `pytest -q -rs tests` | **1220 passed, 0 failed, 0 skipped (9 min 4 s)**, up from 1147 | `backend-pytest.log`, `backend-junit.xml` |
| 1.4 | Research, attribution, identity, coverage | `tests/integration/test_relationship_research.py`, `tests/domain/test_attribution.py` | 11 + 20 passed | `backend-junit.xml` |
| 1.5 | Migration `wfc_0012` on existing data; idempotent | `tests/sql/test_migration_0012.py` | passed | `backend-junit.xml` |
| 1.6 | TypeScript type check and bundle; lint rules; ESLint 10 | `node verify/build.mjs`, `verify/lint.mjs`, `verify/eslint-core.mjs` | type check passed (46 files, 28 pages); bundle built; 0 lint findings; 0 ESLint problems. The real `next lint` / `next build` with the locked versions ran only in the repository's CI (28 Oct, on 3.7.0-wfc.9): passed | `frontend-checks.log` |
| 1.7 | Migrations, upgrade path, backup/restore | empty database; re-run; non-empty refused; dump/restore; `wfc_0002` → … → `wfc_0011` → head | Head `wfc_0012` (99 tables, 249 countries, 31 regions, 0 re-check jobs). Re-run a no-op. Non-empty database refused (the expected `exit 1`). Dump and restore at `wfc_0012`. Every upgrade step exits 0, including `wfc_0011` → `wfc_0012` | `migrations.log`, `migration-upgrade-path.log` |
| 1.8 | Browser journeys, process stack | `tools/run_journeys.sh` | **30 passed (7 min 50 s), including new journey N; no page errors; the console shows only the four expected 401 responses of signed-out session checks** | `browser/` (screenshots `N1`–`N6`, `M1`–`M10`) |
| 1.9 | Container stack smoke test | `tools/docker_substitute/run.sh` | Build and `up --wait` exit 0. `/health/ready` reports release `4.1.0-wfc.11` and `wfc_0012`. 401 unauthenticated; login and briefing 200; security headers present; jobs succeed after a worker restart | `docker-substitute/report.txt` |
| 1.10 | Browser journeys, container stack | `tools/docker_substitute/run_e2e.sh` | **30 passed (8 min 12 s), including journey N** | `container-journeys/` |
| 1.11 | Extraction evaluation regression, all eight sets | `python -m evaluation.run --split …` | Every summary table and every per-case result identical to 4.0.0-wfc.10 (the extraction rules did not change) | `evaluation/` |
| 1.12 | Attribution evaluation (authored and held-out) | `tools/research_eval.py` | section 5 | `evaluation-people/` |
| 1.13 | Access checks | registries, `docker pull`, keys, push dry run | npm and PyPI do not resolve; Docker Hub 403; GitHub token invalid; `ANTHROPIC_API_KEY` and `SEARCH_API_KEY` not set; push to the repository refused (403: the Claude GitHub App is not installed for it); 28 Oct, 16:43 UTC | `access-check.log`, `real-image-attempt.log` |

**Defects found while building this release, all fixed and tested:**
- **A name could absorb a place or title.** "Country Manager Uganda Paul Ssenyonga" produced a person called "Uganda
  Paul Ssenyonga", and "President Lars Holm" a person whose name began with a title. Names now never start or end with
  a country name, never start with a title word, and never start inside a known organisation name. Seen in the
  screenshot review; regression test added.
- **A title's function was read as an organisation.** "Head of Procurement, Example Port Authority" bound the title
  "Head" and the organisation "Procurement". After "of" or "for", a capitalised phrase now stays part of the title
  unless it is a known organisation or reads as one. Found in the second held-out run (section 5); regression test
  added.
- **One mention could become two records.** The rules quote a whole sentence, while the AI extractor may quote part of
  it, so a single mention produced two person records. The same passage quoted more or less fully is now one mention.
- **Organisation label mismatch.** An organisation recorded as a label equal to an organisation record's name did not
  count as the same organisation. It now does.
- **Navigation links were invisible to research.** The page reader excluded links in navigation, header and footer,
  which is where leadership and newsroom links usually sit. They are now collected separately for research only.
- **Confirmations disappeared.** The research-pages confirmation vanished when its form closed. On the Relationships
  page, the duplicate review's confirmation vanished when the last pair was resolved, because the page swapped in an
  empty panel; the first clean verification run's journey N failed on this race. Both now stay visible.
- **Run summaries read badly.** "0 findings" after a continued run was misleading, and a person whose only evidence is
  an incoming title showed as "role not established". Both are now worded accurately.

## 2. Failed checks

| Check | Result | Why | What makes it pass |
|---|---|---|---|
| `docker pull python:3.13-slim`, `node:22-alpine`, `postgres:16-alpine` | **Failed** (×3): Docker Hub 403 | Official images cannot be fetched from this session | The repository's CI `docker` job |
| CI run 40655396285 (28 Oct, 3.7.0-wfc.9 + locks), jobs `backend-static`, `backend-postgres` | **Failed** at "download artifact python-locks" | Workflow defect: the artifact came only from `commit-locks`, which is skipped once locks are committed | Fixed in this release's `ci.yml` (steps removed) |
| Same run, job `docker` | **Failed** at "Build and start … from the committed locks" | Cause not readable from this session: log downloads are blocked here | This release's CI publishes the failure as an annotation; re-run on push |
| Same run, job `security` | **Failed** at the pip-audit step (findings in the locked Python dependencies) | Which advisories is not readable from this session | This release's CI annotates the findings; review them, then upgrade the pins or record dated exceptions in `tools/audit_exceptions.py` |

## 3. Simulated checks (not production evidence)

| What was simulated | Stand-in | Used by | What the result does **not** show |
|---|---|---|---|
| Company websites, press pages, notices | synthetic fixture site (`backend/tests/fixtures/site/sea-company`, `sea-press`, `people`); synthetic pages in tests | 1.3, 1.4, 1.8, 1.10 | retrieval from real sites, their layouts and wording |
| Web search | fixture stand-in for the Brave Search API (`/search-api/…`); a scripted transport in tests | 1.4, 1.8, 1.10 | real search results |
| AI provider (extraction and people reading) | `tools/fake_ai_provider.py`; scripted transports | 1.3, 1.8, 1.10, 1.11 | the configured extractor's quality and cost |
| Next.js server and official images | verification bundle; substitute images | 1.8–1.10 | `next start` and official builds from the locks |

## 4. Unexecuted checks and outstanding external dependencies (precise)

| Check | Missing dependency | How it gets done |
|---|---|---|
| **CI on 4.1.0-wfc.11: clean install from the locks, backend on PostgreSQL, real Next.js build and journeys against `next start`, container stack, audits** | **Push access for this session to `woodta82/VECTACONNECT-ATLASWFC`** (install the Claude GitHub App for the repository), or a person pushing the branch | Push branch `wfc/relationship-research-2026-10-28` (prepared on top of the repository's `main`). CI runs on push; failures are annotated on the run. |
| **pip-audit findings** (the 28 Oct run failed the Python audit) | The findings themselves (readable on that run's page) | Upgrade the affected pins in `backend/requirements.verified.txt` and regenerate the locks, or record reviewed, dated exceptions |
| **Docker job failure** of the 28 Oct run | The job's log (readable on that run's page) | Re-run on the new release; the cause is now published as an annotation |
| **Relationship research on real public sources** | Authorised sources, the deployment, optionally `SEARCH_PROVIDER=brave` with `SEARCH_API_KEY` on the api | `tools/live_trial.py` (find an opportunity), then `tools/live_research_trial.py` (research it, write `review.csv`); a reviewer marks each binding against the original |
| **Configured AI extractor evaluated on original documents** | `ANTHROPIC_API_KEY`, `AI_MODEL`, prices on api and worker; a budget | as above (the trial uses the extractor when connected); `tools/research_eval.py --fetch` for attribution on original pages |
| **Authorised LinkedIn integration** | A LinkedIn API agreement or Sales Navigator licence, and WFC's decision to use it | Until then, search links plus profiles a person confirms |
| **Deployment** | Railway and Supabase projects | `docs/DEPLOY_RAILWAY_SUPABASE.md` |

## 5. Evaluations (authored text and scripted extractor; not real-world accuracy)

**Who holds which role** (`tools/research_eval.py`, rules only):

| Set | Provenance | People precision | People recall | Titles correct | Status correct | Organisations correct | Unsupported kept unresolved | Wrong bindings |
|---|---|---|---|---|---|---|---|---|
| Authored (tuning) | written during development; rules adjusted on it | 21/21 | 21/21 | 20/20 | 20/20 | 19/19 | 5/5 | 0 |
| First held-out, now tuning | run once, then used for changes | 14/14 | 14/16 | 14/14 | 14/14 | 13/13 | 5/5 | 0 |
| Second held-out, now tuning | run once, then one fix (below) | 11/11 | 11/13 | 11/11 | 11/11 | 10/10 | 5/5 | 0 |

Notes:
- "People recall" counts people a case names without any title or organisation. Research deliberately records no one
  without a binding, so those count as missed by design.
- **First held-out run, once:** precision 8/9 (one false person, "Revenue Management"). Recall: people 8/16, titles
  8/14, organisations 7/13. Zero wrong bindings. The rules were then extended, and that set became tuning.
- **Second held-out run, once:** people precision 11/11. One case bound a wrong title ("Head") and organisation
  ("Procurement"). The first evaluator did not count this; strictly, it was 1 wrong binding. It was fixed afterwards,
  and the run-once report carries the correction.
- The run-once reports are kept as `backend/evaluation/results/*-run-once.*`.

**Extraction regression** (scripted extractor, all eight sets): every summary table and every per-case result is identical to 4.0.0-wfc.10.

## 6. Known limitations

- **Research is bounded per run.** 15 pages and 6 AI sections per run; Continue research reads the rest. A followed
  news item is read but not followed further. Search reads 5 results for each of up to 6 queries.
- **Constructions not yet bound.** Titles stated far from the name, in tables, or across sentences stay unresolved and
  the person is not recorded. This is the cautious side: a reviewer can add the person. See the held-out cases above.
- **Search is only as good as its index.** Only the Brave Search API is implemented.
- **Carried over:** the priority order is provisional; migrations have no downgrade; `backend/Dockerfile` copies
  `tests/` into the image.

## 7. Delivery contents

- **Source ZIP** `atlas-wfc-4.1.0-wfc.11-source.zip`: the repository at the release commit (no `.git`), including the
  lock files, ready to push.
- **Evidence ZIP**: logs, browser screenshots, evaluations, `RELEASE-COMMIT.txt`, the verification script.
- **Prepared branch**: `wfc/relationship-research-2026-10-28` in a clone of `woodta82/VECTACONNECT-ATLASWFC`, one commit
  on top of its `main`. It is not pushed (no access).
