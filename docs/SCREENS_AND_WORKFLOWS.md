# Screens and workflows: VECTA Connect / ATLAS / DYNAMIC MARKET INTELLIGENCE

Release 4.2.0-wfc.13 · configured for World Freight Company · one shared username and password.

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
| **Discover** | Finding opportunities | Search now, or save and schedule monitoring, by one country, several countries, a region or worldwide, with keywords, an organisation and capability categories. Each run states what it searched, what it could not read and what remains; a worldwide run states that it covers only the configured sources |
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
