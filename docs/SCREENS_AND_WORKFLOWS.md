# Screens and workflows: VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE

Release 4.6.0-wfc.17 · configured for World Freight Company · one shared username and password.

The product is organised around one journey:

**Discover an opportunity → understand it → research the organisations and relevant people → identify existing
relationships or introduction routes → track progress.**

Since 29 Oct 2026 (research purposes), Discover answers four questions independently, with or without any tender: **who operates
here and what can they do** (Companies), **who matters** (People), **what is changing** (Market intelligence) and **where could we
create business** (Opportunities, including formal tenders).

None of it needs WFC bookings, financial data, operational feeds or a complete capability register.

## One workspace (five sections, 30 Oct 2026)

Discover is the research process; Opportunities and Relationships hold the saved results; the Dashboard shows what deserves
attention. The same list is never presented as several different products. Old addresses keep working (`/control-panel` opens the
Dashboard; `/companies` and `/airlines-forwarders` are views under Relationships). No record or history was deleted.

| Section | What it is for | Main contents |
|---|---|---|
| **Dashboard** (landing page) | What deserves attention, what changed, who is relevant, what to do next | Filters: worldwide, region, countries, **airports** (any airport in the directory), category, organisation, record type, tender status, deadline, progress, relationship coverage. **Four clickable summaries**: Priority opportunities, Deadlines approaching, Companies and people researched, Research gaps and next actions — each opens exactly the records it counts (the Opportunities page reads the summary's filters, including `live=true` and `needs=attention`, and says what it is showing). **Priority table**: opportunity, company, country / airport, status, relationship position, next action (a suggested action is marked as such), and the research state as its own tag (not started / incomplete / complete) — research completeness never moves an opportunity up; a fuller profile or a published e-mail is not a stronger opportunity. **Market signals** in their own panel, never mixed with opportunities ("not confirmed buying demand"). **Recent changes**. Supporting context: live opportunities by region (ring) and by country. **Expandable detail**: score distribution and bands, average points per part of the score, by market, by capability area (the former Control panel analytics). The order is a provisional points view, not a probability of winning |
| **Discover** | Start research and see its progress | **What are you looking for?** Opportunities, Companies, People or Market intelligence, against a plain-language brief; none needs a tender or opportunity first. Geography: worldwide, region, countries, plus **airports chosen from the global directory** (name, IATA, ICAO or city; airports without an IATA code included; several at once; "all airports in this country" is the country scope). Companies: kinds of organisation; results with website, published e-mail, represented airlines (cargo kept apart from passenger ticket sales), people, evidence and the **assessment in separate parts** (fit with the brief, source evidence, research completeness, relationship position, opportunity status). Opportunities and Market intelligence: saved searches, schedules and runs as before, every run listing what it searched, read, could not read and what remains |
| **Opportunities** | Saved commercial opportunities and linked market signals | Tabs and filters as before, plus airports. The **opportunity page** opens with the **research file** (below) |
| **Relationships** | Companies and People as two connected views | A **Companies / People** switch at the top. **Companies**: every organisation found in the open market, read from a supplied list or loaded from WFC data; filters by kind, country, airport (office, station or served), status, origin and **freight scope** (air cargo scope by default — passenger-only excluded; belly cargo, freighter, mixed, cargo services, unresolved, passenger-only, everything); sort by name, fit or recency. **People**: everyone found or added, by research status, with health, owner, next action and LinkedIn (search or confirmed profile); possible duplicates to review |
| **Settings** | Technical controls and optional data tools | Sources, evidence review, scanning schedules and the job queue, AI budget caps and kill switch, shared password and sessions. Data sources: WFC imports (optional), **Supplied lists** (station lists preserved as data awaiting verification), **Airport directory** (which dataset is loaded, provenance, version and refresh date; load or refresh OurAirports' `airports.csv` by upload, or `tools/load_airports.py` where the server has outbound access) |

## The company page (one canonical record)

Discovery, opportunity research, relationship research and staged research all update the same company record; the same company
never needs a separate profile per screen. The page shows: official website **with the basis for believing it official** (the page
names the organisation and the site name matches — similarity alone is never proof), contact page, freight scope with its basis,
what it does, offices and locations, **airports** (office, station it operates, airport served from elsewhere, hub, gateway, each
with status and basis), parent or group, capability areas; **Research progress** (the six stages and the status of every profile
field: found / not searched yet / not found after research / source inaccessible / research incomplete, with the date); published
e-mail addresses with department, status and where each was published; represented airlines, partners and relationships (supplied /
sourced / confirmed / lapsed / not established, with basis); relevant people with role, remit, **published e-mail (never guessed)**,
status and evidence; opportunities recorded from the company with the interpretation; every evidence passage with its source and
date; **possible duplicates** (reviewed by a person; merges re-point every piece of evidence and are reversible). Actions: **Research
this company** (staged, resumable), verify record, confirm or mark lapsed per address, representation and airport, edit with a basis,
record a potential opportunity with the interpretation.

## The person page

Name, organisation (linking to the canonical company record), current role and remit with their evidence; identity confirmation;
**published professional e-mail** where a page states one beside the name (otherwise: not searched yet / not found after research —
never guessed); LinkedIn search or confirmed profile; relationship history, engagements, introduction routes and next action.

## Staged, resumable research (30 Oct 2026)

**Identify → resolve official identity → research company → research relevant people → connect relationships → assess commercial
relevance.** Runs from an opportunity (Research file → Deep research) or a company (Research this company). Each stage ends done,
incomplete (a limit was reached: continue), failed (the error is recorded), not run (no connector, no pages) or not applicable.
When a website or contact route is missing after the first pass, a targeted follow-up search runs (`"<name>" official website`,
`"<name>" contact`) before the field is called "not found after research". A counterparty that comes to light on a company page
joins the queues of the stages that concern it. Query, page and budget limits are kept; unfinished work is disclosed and continuation
never duplicates a record.

**The work queue (amendment, 30 Oct 2026).** Each organisation-scoped stage (official identity, company, people, relevance) works through a
persisted queue of organisations (`research_stage_items`), at most six per stage per run. The rest stay **pending**, visible on the company
page (Research progress → Work queue) and in the research file; the stage shows "6 of 9 organisation(s) done, 3 pending" and is never
**done** while one is pending. Continue research takes the pending ones first — never the first six again.

**Person e-mail ownership (4.8.0).** An address is a person's only when the page ties it to that individual: it stands in the same sentence
with nobody else named between; it sits in the person's labelled contact block; it is in a table row naming only that person; or it is
named as the replacement of that person's withdrawn address. A local part that matches the person's name is shown as **supporting
evidence only** — on its own the address is a candidate pending review (a supplier's or partner's namesake looks the same). An address
on another domain than the organisation's is assigned only when the passage explains the relationship (subsidiary, appointed agent or
GSA, adviser or consultant); otherwise it is pending review with "investigate the relationship". Supplier, partner and third-party press
contacts are never a person's at the company. When two people of the same name are recorded, the passage must also name the person's
organisation. Shared and departmental mailboxes are company contacts.

**Involvement (4.9.0).** Every person carries an evidenced involvement: **employee**, **appointed representative** (GSA / GSSA, appointed
agent), **external adviser**, **press / media contact** or **involvement not established**. A third-party press contact named in an
announcement — or the company's own communications officer named as the media contact — is kept with the actual role and organisation as
an **external contact**: shown in the research file under "External contacts (not commercial contacts)", never counted in relationship
coverage, never ranked, never listed as a gap to chase. A commercial role named "for more information" (Head of Cargo Sales) stays a
commercial contact. The person page shows the involvement and its basis; **Correct the involvement** records a person's decision, which
research never changes.

**Contact currency (4.8.0).** Wording that an address is obsolete, replaced, withdrawn, not monitored or a former employee's ("Do not use …
no longer valid") marks it **historical**: kept as evidence and shown struck through, never offered as a current route; the replacement
named alongside is current. When one source presents an address as current and another as obsolete, the conflict is shown (**Sources
conflict — review before use**) and nothing is assigned until a person decides. "Published" never means deliverable: published addresses
are labelled "deliverability not verified". An address a person verified is never changed by research; a contradicting source adds a
re-check note.

**Stage outcomes and retry (4.8.0).** Each stage ends **Complete**, **Complete with unresolved failures**, **Incomplete** (pending work),
**Failed** or **Not run**; the research file, the company page and the Dashboard show the same overall state and completed / failed /
pending counts. **Continue research** processes pending work only; **Retry failed** re-queues only the organisations that failed (the reason
of the last failure is kept), reads their failed pages again and re-runs the stages blocked by the failure — completed work is not repeated.
A result page that could not be read is a failure to retry, never "not found after research".

## The research file (opportunity page)

A concise summary first — what is happening and its source evidence; why it is relevant to WFC (labelled as ATLAS interpretation);
organisations involved and their roles; geographic and airport scope (opportunity airports kept apart from company airports);
services and freight capability categories; named people, current roles, geographic responsibilities, published e-mail and LinkedIn
route; website, LinkedIn and e-mail routes per company; existing representation, partner and relationship evidence; what remains
uncertain (every gap, field by field); a practical next action — then the supporting research: per company the field statuses and
every evidence passage, the pages read and the searches run. The file is the record, not a longer AI summary.

## Assessment in separate parts (30 Oct 2026)

Shown separately and never added into one number: **fit with the research brief** (kind, geography and airport, freight scope, the
brief's words), **strength of source evidence** (independent documents, own-site facts, supplied-only), **research completeness**
(fields found / not searched / not found after research / inaccessible / incomplete), **relationship position**, **opportunity status
and readiness**. Ranking follows fit, then evidence; an e-mail address or a fuller profile never raises fit; nothing implies a
probability of winning.

## Cargo-industry scope (30 Oct 2026)

Focus: air cargo — GSAs/GSSAs, freight forwarders, handlers, road feeders, gateways and relevant providers. Belly cargo on passenger
aircraft is included. Passenger ticket sales, tourism and passenger-only mandates are outside the scope: such a company is kept as a
record, labelled **passenger-only (outside the freight scope)**, scored 0 for fit and excluded from the cargo view by default. Every
company carries a freight-scope label with its basis: freighter cargo, belly cargo (passenger aircraft), mixed cargo operations, cargo
services (non-airline), passenger-only, or unresolved. Airport selection is a scope and never a judgement of freight relevance; a
company's office, the airports it serves, an airline's route and its representation territory, and a gateway and a final
destination are distinct facts, each with its source.

## The global airport directory (30 Oct 2026)

`airport_directory` (migration wfc_0016): a maintained public dataset — OurAirports `airports.csv` (public domain) — searchable by
name, IATA, ICAO, city and country, including airports without an IATA code, with type, status (closed airports are listed but not
offered), aliases, the dataset's own id, provenance, version and refresh date (`reference_datasets`). A bundled seed of 424 major and
secondary airports loads on a fresh install so an airport can be chosen before the dataset is loaded; the maintained dataset replaces
every seed row it covers. Airport scope applies to discovery (all four purposes), companies (office / station / served), people (through
their companies), opportunities (scope, origin, destination, gateway, station) and the Dashboard filters.

**Which directory is in use (amendment, 30 Oct 2026).** Settings → Data sources → Airport directory shows **Bundled seed only**, **Partial
directory** (a maintained file with fewer than 40,000 rows) or **Full directory**, with source, licence, version, publisher refresh date,
load time and total records. The full file is loaded at deployment (the `airports` step), from a verified import package, or by upload.
The picker searches name, city, country (code or name), IATA and ICAO, and the dataset's own identifier for airports without either;
several can be chosen; choosing none means all airports in the chosen countries or region (worldwide when none). Directory inclusion is
never evidence of cargo operations. After a failed load attempt the page says so ("The last load attempt … FAILED: …") and keeps
the honest status. `/health/ready` reports `airport_directory.full`: a healthy application start is never proof of full airport coverage.

Pages reached from these: an **opportunity** (below), a **market signal**, a **person**, a **company** (from opportunities,
people and Relationships), a **discovery run**, and the Settings sub-pages.

## The opportunity page

Answers seven questions, in order:

1. **What is happening?** Source facts: organisation, geography, source date, stated deadline, tender status and its
   basis, and the source passages with links and publication dates.
2. **Why could it matter to WFC?** ATLAS's interpretation, labelled as interpretation and not a source fact, with what
   remains unconfirmed and the priority explanation.
3. **Which organisations are involved?** The issuer, organisations the evidence is about, and those of linked people,
   each linking to its profile. A website can be recorded here so research can read its public pages.
4. **Who appears relevant?** People with their role on this opportunity, research status, the evidence for why they
   appear relevant, and a LinkedIn search or confirmed profile.
5. **What existing relationship is recorded?**
6. **Who could introduce us?** Available routes, and possible routes not yet confirmed.
7. **What relationship information is missing?** Gaps, useful next actions, and targeted LinkedIn searches by role,
   labelled as searches.

Actions: **Research relationships** (prominent), Save, Export brief (Markdown: evidence, organisations, people, gaps,
next actions). **Track progress**: New → Reviewing → Pursuing → On hold → Closed, kept separate from the tender status
(announced, open, expired, cancelled, awarded, unverified); owner (descriptive), next action and due date, notes, and
relationship activity. **Technical detail** (collapsed): evidence checks, qualification, prioritisation factors and
full history.

## Research purposes and record types (29 Oct 2026)

Six linked record types are kept distinct: **companies** (organisations), **individuals** (people), **representation and business
relationships** (organisation ↔ organisation, with status and basis), **market intelligence** (market signals), **commercial
opportunities** and **tenders**. A relevant company is not automatically an opportunity; a press release is not buying demand; a
person named publicly is not a decision maker until a person judges so. A researched company or a market signal leads to a
commercial opportunity only when a person records it, with the interpretation shown on the opportunity.

Qualification fits the result: tender deadline and procurement checks apply to tenders; companies, people, partnership research
and market signals are never blocked for lacking a submission deadline, procurement reference or invitation to bid. Evidence,
freshness, relevance, duplication and uncertainty controls apply to every record type (every company fact carries its passage or
its supplied-list row; identity is never merged on a name alone; designators are resolved from a reference list as a reading
aid, never as evidence; a supplied address or agreement stays "awaiting verification" until research sources it or a person
verifies it).

Supplied datasets (the BRU benchmark): rows are preserved exactly; GSA rows become GSSA records at the station with supplied
cargo-representation entries per airline code (an "ALL" entry records nothing as represented); airline rows become airline records
typed passenger-belly or cargo-only with supplied station addresses. Nothing from the file is treated as current, complete or a
scope: ATLAS discovers comparable companies independently by country, region and airport.

## Open-web discovery (29 Oct 2026)

**What is searched.** For the selected geography and each selected capability area, ATLAS builds public web searches from what
that area looks like in public information: formal notices first (tenders, RFPs, RFQs, expressions of interest for GSSA and cargo
representation, ground handling and cargo services, road feeder and trucking, outsourcing and training, cargo technology), then
commercial openings (representation mandates and appointments, Total Cargo Management, route launches and capacity, gateway and
road-feeder developments, outsourcing and training demand, technology adoption, partnerships, expansion and network signals).
Keywords and a named organisation or airline narrow every query; the country name is added to each. The results come from
whatever public sites the search returns: airline and airport sites, public tender and procurement pages, government and
institutional procurement portals, newsrooms and press releases, trade publications, public reports and announcements, PDFs and
feed pages. Every result page is fetched and read itself under the existing extraction, validation, freshness, chronology,
cancellation and duplication controls; search snippets are never used as evidence.

**Publisher and authority.** A page found on the open web is attributed to its own site (its host is the publisher), and its
authority is inferred conservatively: a government or procurement portal, the organisation's own recorded website, known trade
press, otherwise unverified. A notice from an unverified publisher is a clearly labelled record stating what is established and
what still needs confirmation (for a tender: "existence not confirmed by an authoritative source"); it becomes an opportunity when
a person tracks it, or when an authoritative or corroborating source confirms it.

**Explicit opportunities and market signals** stay apart: a tender notice is an opportunity record; a press release about a
route, a partnership or an appointment is a market signal with ATLAS's commercial interpretation labelled as such, and with what
remains unconfirmed listed. No budget, deadline, decision maker or demand is ever invented.

**Restricted results.** A result that needs registration, login or payment (an HTTP 401, 402 or 403, or a page that shows only a
gate) is labelled with the restriction, is not read, and is never bypassed. ATLAS then searches for a public original or
corroborating copy by its title; the run shows whether one was found and read. Other results continue. The core workflow needs no
tender-platform membership or subscription.

**Configuration** (Settings, once, server-side): `SEARCH_PROVIDER=brave` with `SEARCH_API_KEY`, or `SEARCH_PROVIDER=anthropic`
using `ANTHROPIC_API_KEY`; `SEARCH_RESULTS_PER_QUERY`; the AI budget. Per run: at most 12 queries per country and 40 per run (the
rest resume from the saved cursor on the next run), and 25 result pages (the rest are queued). Without a connector, the Discover
page says so and runs list every planned search as "not run" with a link; the outcome is "Open-web search not configured", never
"no relevant results".

## Record types

| Type | Meaning |
|---|---|
| Tender or procurement opportunity | A procurement the source says exists, with its status and deadline |
| Commercial opportunity | A potential the team decided to track (for example from a market signal), or one derived from WFC's own data. Never shown as an open bid |
| Market signal | A route launch, investment or market development that may indicate potential. What is unconfirmed is listed |
| Historical intelligence | A cancellation, award or closure of a tender that was not tracked. Never live |

Uncertainty produces a visible review state ("announced; current status not confirmed", "sources conflict", "freight
scope not yet established", "evidence not yet reviewed") rather than hiding the record. Deadline, cancellation,
duplication, geography and evidence-freshness protections are unchanged.

## Relationship intelligence to the ATLAS v1.0 parameters (29 Oct 2026)

The Relationships section works to the parameters of ATLAS v1.0 ("Relationship Intelligence"), applied to WFC's nine capability
areas, with every judgement and score explained from the record.

**Discover contacts in the open market** (Relationships → Discover contacts). A standalone search, not tied to one tender: an
organisation (optional), countries or a region, a WFC capability area (the nine areas of the brief) and a role focus. ATLAS reads
the organisation's own pages (website, newsroom, leadership and the links on them) and the results of the authorised web search
(queries built from the capability area's target roles, appointments and leadership pages), under the same evidence rules as
opportunity research: every contact carries the passage that names them, their title and organisation only when the passage binds
them, and a **relevance to the brief out of 100** (role fit 35, seniority and authority 25, organisation fit 20, geography 10,
evidence strength 10), each point explained. Contacts are research candidates until a person confirms them. Without a search
connector the searches are listed as not run, with links to open; the result says so ("Not run"). Two connectors: the Brave Search
API, or the Claude API's web search tool (only its result URLs are used, never the model's text). No LinkedIn profile is fetched.

**Stakeholder judgement** (person page). Stakeholder type (economic buyer, budget holder, programme sponsor, procurement
authority, political sponsor, technical evaluator or influencer, adviser, gatekeeper, introducer, delivery partner, consultant),
decision authority (final, shared, influence, none) and posture towards WFC (champion to blocker), recorded by a person with a
basis; "not yet judged" is the default and a title never sets it.

**Engagements** now carry a direction (WFC reached out, they reached out, mutual) and an outcome including "no response".

**Relationship health** (person page, directory, export). 0–100 with a band (Strong 75+, Healthy 55–74, Cooling 35–54, Weak
15–34, Dormant), from recency 24, frequency 16, responsiveness 14, meeting outcomes 14, influence 14, opportunity alignment 10,
strategic value 8, with the breakdown and the biggest levers. A high-influence relationship that has gone quiet is capped at 40
and flagged **at risk**. Momentum (new, improving, stable, declining, dormant) compares the last 90 days with the 90 before.
"Not assessed" until an engagement or a judgement is recorded. Health is not a probability of winning and never changes the
research status.

**What the relationship record says** (Relationships, top): who matters most (by commercial consequence), who are we missing
(live opportunities without an economic buyer, budget holder or procurement authority judged, or without the capability area's
target roles confirmed), where to invest time (attention: high influence, low or falling health), at risk or declining,
improving. Each entry says why.

**Relationship share of the score** (opportunity page): how many of the Control panel score's 25 relationship points the
opportunity has, and how many are still available.

**Outreach drafts** (person page). ATLAS writes a draft (email, LinkedIn message or call notes) from the recorded facts only;
the configured AI may reword it and the rewording is accepted only when it adds no fact and keeps the substance. A person edits it,
sends it from their own account and records "I sent this", which adds an outbound engagement awaiting a response. ATLAS sends
nothing.

**Directory**: filters by research status, country, capability area, stakeholder type and health; sort by attention, health,
name or recency; CSV export with health, momentum and the recommended action.

## Relationship research

Started from an opportunity with **Research relationships**; **Continue research** appears when a run is incomplete.
Each run reads, in order, and records every document and page with what happened to it:

1. The **opportunity's own source documents** (where the source permits keeping their text).
2. **Pages and documents the team adds** for this opportunity: a URL (company announcement, press release, official
   biography, market report) or a document (PDF, HTML or text, uploaded or pasted).
3. **The organisations' own pages**: the website, newsroom and leadership page recorded for each organisation on the
   opportunity. Research follows the links those pages offer to leadership, management, team and board pages, the
   newsroom and relevant news items (same site only). Fixed addresses are tried only when a site offers no such links,
   and are labelled "guessed address". robots.txt is respected.
4. **Authorised web search**, when a search connector is configured (the Brave Search API): searches built from the
   organisation, the target roles of the opportunity's category, the country and the tender reference. Without a
   connector nothing is searched: each search is listed as "not searched by ATLAS", with a link to run it yourself.
5. **Targeted LinkedIn searches** by organisation, role and country, labelled as searches. No LinkedIn integration is
   connected; a profile is saved only when a person confirms it.

The evidence rules read every section of every document. The **configured AI extractor**, when connected, reads long
documents section by section under the budget caps; reading stops at the per-run or budget limit and resumes on the next
run. **Research coverage** on the opportunity shows the documents and pages read, skipped (with the reason) and failed,
sections read by the rules and by the extractor, the searches run or not run, the remaining work, and what was not
searched. The outcome is one of: **People found in the sources read**, **No people found in the sources read**, or
**Research incomplete** (with what remains). It is never presented as a complete search of public information.

### Who holds which title

- A person is linked to a title or an organisation only by a passage that binds them: the title or organisation next to
  the name in the same clause ("Jane Doe, Head of Cargo at Example Air"), a possessive ("Example Air's Head of Cargo Jane
  Doe"), an appointment ("Example Air has appointed Jane Doe as Head of Cargo"), "whose", "is/was … at", or a listing on
  the organisation's own leadership page. A title mentioned elsewhere in a document, or an organisation merely mentioned
  in the same sentence, is never attached: the association stays **not established**.
- Each title is recorded as current, former or incoming, with the passage and, where different, a separate passage for
  the organisation.
- The person's relation to the organisation being researched is shown: works at the organisation, board member, partner
  organisation, customer organisation, another organisation (quoted or mentioned), or not established. Being named on
  a company's website does not make someone its employee; only a leadership, team or board listing does.
- A reading proposed by the AI extractor keeps a title or organisation only when the quoted passage contains it and the
  rules confirm the passage binds it to that person.

### Identity

- The same passage (also the identical statement republished in another document of the same opportunity), or the same
  name at the same known organisation, is the same person.
- A name alone never merges records when the organisation is unknown: a new record is created and the pair goes to
  **Possible duplicates** for a person to review. A merge moves evidence, titles, links, relationships, routes and
  engagements to the record kept, lists every moved row, and can be **undone** exactly. A merged record opens with a
  notice and cannot be changed.

### States and routes

- Everyone found starts as a **research candidate**. Being named records involvement, not decision-making authority.
- **Identity and role confirmed** needs a person to record how it was confirmed. Saving a LinkedIn profile accepts only
  a member-profile URL a person has checked.
- **Existing relationship** needs who at WFC holds it, its nature and how it is known.
- **Introduction available** needs the introducer's connection and confirmed willingness. A public association (same
  panel, same press release) is recorded only as a **possible route**.
- The opportunity page shows organisations and their involvement; confirmed identities and research candidates in
  separate lists with their evidenced titles; recorded relationships; confirmed introductions and possible routes; and
  the missing relationships and next actions.
- No win probabilities and no relationship scores. Nothing is sent to anyone.

## Optional WFC data (Settings)

Bookings, quotes, capacity, agreements, capabilities, trucking, finance, channel events and the other import datasets,
the capability analyses that use them, and operational exceptions are kept, with their data and history, under
Settings. They add context (for example a coverage gap) but are never needed to discover opportunities or research
relationships.
