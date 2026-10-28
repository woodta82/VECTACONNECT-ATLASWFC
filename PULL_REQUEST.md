# Release 3.7.0-wfc.9: nine business workflows end to end, data onboarding for every dataset, qualified-live guard, Netlify front-end configuration

**Branch:** `wfc/spec-completion-2026-10-28` → base `wfc/amendments-2026-10-27c` (release 3.6.0-wfc.8).

This pull request has not been opened yet, because no repository is connected to the build session. To open it, push
the branch and paste in this description.

## Why

This implements the instruction of 28 Oct 2026 (eight items), continuing from `3.6.0-wfc.8` and preserving the
corrected chronology rules. The requirement-by-requirement status is `docs/ACCEPTANCE_MATRIX.md`.

## What changed

1. **The nine business workflows, end to end** (`tests/integration/test_business_workflows.py`). Each original
   capability runs from its inputs (imports, or discovery for airline representation) to a reviewable output, and
   every figure is checked against a value computed independently in the test.
   - New recommendations in `domain/recommendations.py`: capacity and lanes (add capacity / review allotment / monitor /
     insufficient data, with inputs, sources, thresholds and missing inputs), trucking coverage per station, ranked
     technology solution candidates, and network coverage gaps derived from mandates without verified capability.
   - Each can become an opportunity for review, qualified by factual checks (`data_current`, `feasibility`,
     `evidence_measured`) and prioritised on its own facts.
   - Outsourcing demand lists only live, dated, in-scope tenders; the rest are listed apart with the reason.
   - **Defect fixed:** a feeder that does not run on the ship date was reported "insufficient data" when the
     connection cutoff was unknown. It is now infeasible, so the station shows a coverage gap.
2. **Data onboarding for all 19 datasets** (`tests/integration/test_data_onboarding.py`): upload, mapping, validation,
   preview, commit, reconciliation, duplicate handling, correction, and reversal or a refusal naming the re-import
   route.
   - The dataset docs, `FIELDS.md` and the templates are generated from the contracts (`domain/import_docs.py`); a test
     fails on drift. The stale "dry run only / 9 datasets" wording is gone.
   - Each dataset shows what uses it, its refresh requirement, duplicate key, correction route, units and why each
     required field is required: on the import screen and, as "Data used", in every area.
   - **Defect fixed:** a corrected airline name was previewed as an update but only added an alias.
3. **Qualification and prioritisation across all nine areas.**
   - `tests/integration/test_qualified_live_guard.py`: unreviewed AI claims, historical notices, passenger-only
     mandates, self-contradicting notices, cancellation after approval, stale data, recommendations without an action
     and prohibited appointment rights never reach `ready_for_review` or `approved_for_pursuit`. A cross-area invariant
     query finds nothing. No commercial override passes a factual check.
   - Every ordered list (account growth, forwarder sales, capacity, trucking, outsourcing, service exceptions,
     technology, network) carries a rank, the reason with its provisional rule, and missing inputs.
4. **Netlify as the web front end (optional).** `netlify.toml` (frontend base, Node 22, build preflight, `/api/*`
   proxied with Netlify's signed proxy header). The API verifies `x-nf-sign` when `PROXY_SIGNATURE_SECRET` is set.
   `docs/DEPLOYMENT.md` §8 says where the API, worker and PostgreSQL run. **Not deployed:** no site or API host.
5. **Traceability:** brief ¶33 "configurable permissions" is recorded as superseded by the single-login instruction.
6. **Browser journey L** (`e2e/test_journeys_workflows.py`): onboarding rules, a capacity recommendation from data
   imported through the screen, an opportunity created from it, and a derived network gap recorded for review.

No migration: head stays `wfc_0010`.

## Not done, and why

- **Lock files, clean install from them, release gate; official images and `next start`.** Package registries are
  unreachable from the build session, and no repository (`owner/repo`) has been supplied to run the `commit-locks`
  workflow.
- **Real external intelligence.** No `ANTHROPIC_API_KEY` and no authorised source have been supplied. Only
  scripted-extractor measurements exist, and they are kept separate.
- **Live WFC adapters.** No API documentation or credentials have been supplied. All four stay **Not connected**;
  `docs/CONNECTORS_AND_DATASETS.md` lists exactly what each needs.

## Verification

See `BUILD_REPORT.md` §1 (clean export of the verified commit): backend suite, static checks, frontend checks,
migrations and upgrade path, evaluation regression, browser journeys on the process and container stacks.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01SPXPJ55d1gFN6VC7pn838e
