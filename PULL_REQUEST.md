# Release 4.2.0-wfc.13: Control panel, electric cyan brand colour, relationship research

**4.2.0-wfc.13** (third commit) adds the Control panel: live opportunities per region, market, country and capability area,
and a provisional score out of 100 per opportunity with its breakdown (not a probability of winning). Details:
`BUILD_REPORT.md`, first section.

**4.1.1-wfc.12** (second commit) replaces the accent blue with electric cyan `#00E5F2`, with light cyan `#66F2FF` on button
hover, the logo symbol and DYNAMIC MARKET INTELLIGENCE in cyan. In the light theme, text and focus rings use a deeper cyan so they stay readable. Details: `BUILD_REPORT.md`, first section.

## 4.1.0-wfc.11: complete, evidence-backed relationship research

**Branch:** `wfc/relationship-research-2026-10-28` → base `main` of `woodta82/VECTACONNECT-ATLASWFC` (3.7.0-wfc.9 and the
committed locks). The branch is prepared as three commits on top of `main`. It has not been pushed: this session can read
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
