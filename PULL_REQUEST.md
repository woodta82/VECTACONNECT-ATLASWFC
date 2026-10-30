# Release 4.9.0-wfc.20: operational pilot release — contact involvement and pilot kit

**4.9.0-wfc.20** (tenth commit) classifies each person's evidenced involvement (employee, appointed representative, external adviser, press contact, not established) and keeps press contacts and advisers as external contacts outside relationship coverage and ranking, with a one-time re-check and person corrections; extends the browser journey to the full user path; adds the post-deploy check, the pilot workflows and the runbook. Schema `wfc_0019` (additive). Deployment, the full airport load and the real-source pilot were NOT executed (no outbound network in the build session; deployment is from the team's own hosting account, no connector). Details: `docs/REGRESSION_REPORT_4.9.0.md`.


**4.8.0-wfc.19** (ninth commit) makes a matching e-mail local part supporting evidence only, sends unexplained other-domain, supplier and partner addresses to review, marks obsolete / withdrawn / former-employee addresses historical (never a current route) with conflicts shown, re-checks recorded addresses (verified ones untouched); reports stage outcomes truthfully (complete with unresolved failures, failed, incomplete, not run) with consistent counts and an explicit Retry failed; reads pages added after completion; reports the airport directory state in readiness and after failed loads. Schema `wfc_0018` (additive). Full airport load, real-source demonstration and production-stack checks were not executed here. Details: `BUILD_REPORT.md`, `docs/REGRESSION_REPORT_4.8.0.md`.


**4.7.0-wfc.18** (eighth commit) replaces the first-address-in-the-sentence e-mail rule with an attribution rule (own name, explicit statement, contact block, table row; shared mailboxes and third-party press contacts never a person's; ambiguous addresses pending review) and re-checks earlier assignments; replaces the six-organisation slicing with a persisted per-stage work queue (pending work visible, never 'done' while pending); loads the full airport directory at deployment or from a verified import package and says which directory is in use; makes every Dashboard summary open exactly its records and keeps research completeness out of the priority order; proves corrections survive research and contradicting evidence prompts a re-check. Adds `tools/public_source_demo.py` for the real-input demonstration (not executed here: no outbound access or keys). Schema `wfc_0017` (additive). Details: `BUILD_REPORT.md`, `docs/AMENDMENT_CHECKLIST_4.7.0.md`.


**4.6.0-wfc.17** (seventh commit) consolidates the workspace into five sections (Dashboard = Overview + Control panel; Discover;
Opportunities; Relationships = Companies + People; Settings) with old URLs redirected; adds staged, resumable research (identify →
official identity → company → people → relationships → relevance) that enriches the canonical company and person records with
per-field statuses (found / not searched / not found after research / inaccessible / incomplete) and an opportunity research file
(summary first, supporting research below); a maintained global airport directory with provenance (OurAirports loader; bundled seed
of 424 airports until it is loaded) applied to discovery, companies, opportunities and filters; freight-scope labels with passenger-only
excluded from the cargo view; assessment in five separate parts; company duplicate review with reversible merges. Schema `wfc_0016`
(additive). Details: `BUILD_REPORT.md`, first section.

**4.5.0-wfc.16** (sixth commit) adds the four research purposes within Discover (Opportunities, Companies, People, Market
intelligence) against a plain-language brief, with company and people intelligence built directly from public pages — website,
published e-mail, locations, services, parent or group, represented airlines (cargo kept apart from passenger ticket sales),
relevant people and evidence per fact — without any tender; a Companies directory and company page with verification; supplied
station lists (the BRU benchmark) preserved as data awaiting verification; distinct record types with a company → opportunity step
that requires an interpretation; and six separated Control-panel summaries that open filtered records. Schema `wfc_0015`
(additive). Details: `BUILD_REPORT.md`, first section.

**4.4.0-wfc.15** (fifth commit) makes open-web discovery the default: a country, region or worldwide search for the nine
capability categories searches public information directly through the server's search connector, reads every page it finds,
labels restricted results and looks for public originals, and keeps outcomes distinct. Registered sources stay optional. Schema
`wfc_0014` (additive). Details: `BUILD_REPORT.md`, first section.

**4.3.0-wfc.14** (fourth commit) brings the Relationships section to the ATLAS v1.0 parameters with open-market contact discovery
for the WFC capability areas: discovery by organisation, country or region, capability area and role focus; relevance out of 100
per contact; stakeholder judgements; relationship health, momentum and attention; the five questions; the relationship share of
the opportunity score; outreach drafted by ATLAS and sent by a person. Schema `wfc_0013` (additive). Details: `BUILD_REPORT.md`,
first section.

**4.2.0-wfc.13** (third commit) adds the Control panel: live opportunities per region, market, country and capability area,
and a provisional score out of 100 per opportunity with its breakdown (not a probability of winning). Details:
`BUILD_REPORT.md`, first section.

**4.1.1-wfc.12** (second commit) replaces the accent blue with electric cyan `#00E5F2`, with light cyan `#66F2FF` on button
hover, the logo symbol and DYNAMIC MARKET INTELLIGENCE in cyan. In the light theme, text and focus rings use a deeper cyan so they stay readable. Details: `BUILD_REPORT.md`, first section.

## 4.1.0-wfc.11: complete, evidence-backed relationship research

**Branch:** `wfc/relationship-research-2026-10-28` → base `main` of `woodta82/VECTACONNECT-ATLASWFC` (3.7.0-wfc.9 and the
committed locks). The branch is prepared as five commits on top of `main`. It has not been pushed: this session can read
the repository but cannot push to it.

## Why

The third instruction of 28 Oct 2026 asks ATLAS to show, for every opportunity, who matters, whom WFC already knows and
how it might reach the relevant people. The evidence must hold up, and WFC operational data must not be needed. The
design, branding, Poppins, the five-section navigation and the existing functionality are unchanged. This release also
brings in release 4.0.0-wfc.10 (the refocus on discovery and relationship intelligence), which `main` does not have yet.

## What changed

1. **Research reads more:**
   - the organisations' own pages, following their leadership, team, board and newsroom links (same site, robots.txt
     respected; guessed addresses only when a site offers no links, and labelled);
   - pages and documents the team adds;
   - an authorised web search connector (Brave Search API, off unless configured).

   Without a connector, nothing is searched: the queries are listed as not run, with links.
2. **Who holds each role:** a title or organisation is attached to a person only by a passage that binds them. Titles
   are recorded as current, former or incoming. The person's relation to the organisation is shown: works there, board
   member, partner, customer, other organisation, or not established. AI proposals keep a title or organisation only
   when the passage binds it.
3. **Identity:** no merge on a name alone. Possible duplicates are reviewed by a person, and every merge can be undone.
   Evidence is never deleted.
4. **Coverage:**
   - long documents are read in sections, and the AI extractor resumes under the budget;
   - each document shows what was read, skipped or failed;
   - the outcome is people found, no people found, or **incomplete**, with what remains;
   - Continue research picks up the rest.
5. **Opportunity page:**
   - organisations and their involvement;
   - confirmed identities and research candidates, with evidenced titles;
   - relationships;
   - confirmed introductions and possible routes, kept apart;
   - research coverage;
   - gaps and actions.

   The brief export includes all of these.
6. **Migration `wfc_0012`** is additive and idempotent. Existing titles are marked as recorded before the evidence rules.
   Same-name records are queued for review, never merged. Earlier research runs are marked incomplete.
7. **CI:**
   - backend jobs no longer download a lock artifact that only the skipped `commit-locks` job produced;
   - schema revisions are read from the code, not hard-coded;
   - failing steps publish their log tail as annotations, so the cause is readable without downloading logs.
8. **Tools:**
   - `tools/live_research_trial.py`: research on a deployment, with a review sheet for checking against the originals;
   - `tools/research_eval.py`: attribution measured against labelled cases, optionally fetching original pages.

## Not done, and why

- **Real sources, real search and the configured AI extractor:** no keys and no authorised sources were supplied. The
  journeys use synthetic pages and simulated providers, labelled as such.
- **CI on this release:** no push access from the build session. The 28 Oct run on `main` built the real Next.js app from
  the locks. Its Docker and pip-audit failures need their logs, which are readable on GitHub.
- **Authorised LinkedIn integration:** none.

## Verification

See `BUILD_REPORT.md` §1 (clean export of the verified commit) and §5 (evaluations).

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01SPXPJ55d1gFN6VC7pn838e
