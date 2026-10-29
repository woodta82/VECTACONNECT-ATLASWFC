# Screens and workflows: VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE

Release 4.4.0-wfc.15 · configured for World Freight Company · one shared username and password.

The product is organised around one journey:

**Discover an opportunity → understand it → research the organisations and relevant people → identify existing
relationships or introduction routes → track progress.**

None of it needs WFC bookings, financial data, operational feeds or a complete capability register.

## Primary screens (six sections)

| Section | What it is for | Main contents |
|---|---|---|
| **Overview** (landing page) | The opportunity desktop | Filters: worldwide, region, one or several countries, opportunity category, organisation, tender status, deadline, progress, relationship coverage. Counts by record type. **Priority opportunities** (list or cards) with the reason for each position. **Upcoming stated deadlines**. **Recently discovered**. **Needs relationship research**. **With an existing relationship or introduction route**. **Relevant people identified recently**. **Saved searches** (with schedule and last run) and **recent changes** |
| **Control panel** | Opportunities per market and the score out of 100 | Same filters as the Overview. Totals (live opportunities, markets, average score, records with a relationship or introduction). **Live opportunities by region** (ring chart; a record counts once in every region it names). **Opportunities by score** (how many records fall in each 10-point range, and the four bands: Strong 75–100, Promising 55–74, Developing 35–54, Early 0–34). **By market** (UN M49 sub-regions) and **By capability area** lists with live counts and average score. **By country** table. **Score per opportunity**: every live record ranked by score, each with a **Breakdown** showing the points for stage (30), time to respond (15), evidence reviewed by a person (16), scope and status clear (4), relationship position (25) and source freshness (10), and the reason for each. Closed, cancelled, awarded, expired and historical records are not scored. The score is a provisional points score, not a probability of winning, and its weights are shown on the page |
| **Opportunities** | Every record, searchable | Tabs: all, tenders and procurements, commercial opportunities, market signals, historical intelligence, out of scope. Same filters, text search, sort by priority, deadline or source date, list or card view, saved-only. Each row: title, organisation, geography, category, source date, stated deadline, status, priority explanation, relationship coverage. **Export CSV** (concise) and **Technical export** |
| **Discover** | Finding opportunities in public information | Search now, or save and schedule monitoring, by one country, several countries, a region or worldwide, with one or more of the nine capability categories and optional keywords or organisation. **The open web is searched by default** (the built-in "Open web" source through the server's search connector): no website needs registering first. Each run lists every public web search it ran (or could not run, with a link to open), every page it read, the results that needed registration, login or payment (labelled, not read, never bypassed, with a search for a public original), what it could not read and what remains. Outcomes stay distinct: results, no relevant results, search not configured, search failure, inaccessible sources, incomplete, partial coverage. A worldwide run never claims completeness. Registered sources remain optional monitoring inputs (Settings → Sources) |
| **Relationships** | People and routes | Everyone found or added, by research status: research candidate, identity and role confirmed, existing relationship, introduction available. Owner, linked opportunities, next action, LinkedIn (search or confirmed profile). **Possible duplicates** to review: records that share a name where the organisation is unknown or differs; merge (keeping every piece of evidence, reversible) or keep apart |
| **Settings** | The technical controls | Sources, evidence review, scanning schedules and the job queue, AI budget caps and kill switch, shared password and sessions. Optional WFC-data tools: data imports, capability analyses, operational exceptions |

Pages reached from these: an **opportunity** (below), a **market signal**, a **person**, an **organisation profile**
(from opportunities and people), a **discovery run**, and the Settings sub-pages.

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
