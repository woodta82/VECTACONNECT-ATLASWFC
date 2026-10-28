# Extraction-quality evaluation

Run (needs PostgreSQL, see `tests/sql/pg.py`):

    cd backend
    WFC_TEST_PG="host=127.0.0.1 port=5433 user=atlas" python -m evaluation.run --split all --out evaluation/results

Splits: `tuning`, `heldout2`, `heldout3`, `heldout4`, `heldout5`, `heldout6`, `heldout7`, `genuine`, `all` (sizes and status below).
`run.py` runs every case through the production pipeline on a fresh database, using a synthetic fetcher and a SCRIPTED
extractor. It writes `results-<split>.json` and `report-<split>.md`, broken down by language, capability area and notice
type.

With `--extractor configured`, the same cases run through the configured AI extractor via the production transport
instead. This needs `ANTHROPIC_API_KEY` and `AI_MODEL` in the environment, and optionally `AI_API_BASE_URL`. That
evaluation has **not been run**: there is no key in the build environment, and the harness refuses to start without one.
Scripted results are never evidence of AI extraction quality.

## Sets, provenance and held-out status (as of release 3.7.0-wfc.9; no set was added in this release because the extraction rules did not change)

| Set | Cases | Provenance | Status |
|---|---|---|---|
| `tuning` (`notices.py`) | 32 | authored | Rules were tuned on these. Labels v3 (27 Oct, third instruction): the two t07 status labels now read "not stated", because a "request for proposal" heading establishes that a notice exists, not that it is open. |
| `heldout2` (`notices.py`, j01–j12) | 12 | authored | Run once for 3.2.0-wfc.4, then its failures were fixed. Now a regression set. |
| `heldout3.py` (k01–k20) | 20 | authored | Run once for 3.3.0-wfc.5. One failure (k05 "i.e. Bahrain") was fixed after `heldout4` was written. Now a regression set. |
| `heldout4.py` (m01–m10) | 10 | authored | Run once for 3.3.0-wfc.5. Now a regression set. |
| `heldout5.py` (n01–n18) | 18 | authored | Run once for 3.4.0-wfc.6. Its two findings (the n06 passenger lot dropped before validation; the n12 route-launch area) were named in the fourth instruction and fixed, so it is now a regression set. n06's excluded lot is now named by its lot reference (see the docstring). |
| `heldout6.py` (p01–p17) | 17 | authored, several documents per case where needed | Run once for 3.5.0-wfc.7, and its findings were handled. Now a regression set. |
| `heldout7.py` (q01–q14) | 14 | authored, several documents per case | **Current held-out set.** Written and committed (541dba4) before any rule of the fifth 27 Oct instruction was changed. It covers status transitions (dated terminal statements against undated or later notices, same-day conflicts, dated and undated reopening, new rounds), terminal-only records and contextual evidence. It contains the instruction's own reproduction (q01), so it is not blind on that case. Run once in the release verification; no rule changes afterwards. |
| `genuine.py` (g01–g19) | 19 | genuine public notices, reconstructed | Labels v3: the g07 and g11 status labels now read "not stated", for the same reason as t07. Earlier label versions' results are kept in the release evidence. |

**Genuine notices.** `genuine.py` holds nineteen genuine public notices captured on 27 Oct 2026. The capture tool returns
verbatim quotes and a paraphrased structure, so each document is a **reconstruction** of the notice in its original
form, not the original bytes. The provenance, captured text and manually checked expected results are in
`genuine_sources/`.

Running the configured extractor on the original documents needs an authorised source and an API key. Neither was
available, so that run is outstanding.

## Terminal-only records: labels v4 (27 Oct 2026, fifth instruction, item 4)

A cancellation, award or closure of a tender that is not already tracked is kept as historical intelligence. It becomes
a tender record classified `historical_record`, with its terminal status, outside the actionable pipeline and the live
counts. It is never created as an opportunity. A tracked tender moves to the terminal status.

The labelled sets used to disagree on this. Some labels expected a terminal opportunity (t04, t15, h04, j04, m10);
others expected nothing (g09, k12). All of them now expect a `historical` record. The application was changed to follow
the policy, not to satisfy individual labels.

`previous/labels-v4-rules-v6/` holds the effect of the label change alone, run with the 3.5.0 rules: precision fell where
those rules still created terminal opportunities. The 3.6.0 rules restore it.

## Matching (changed 27 Oct 2026, fourth instruction, item 5)

Gold opportunities are matched by tender reference, or by title when they have none. Records the gold EXCLUDES are now
matched by their tender or lot reference (`ref`), or by their evidence passage (`quote`). Labels written earlier that
name only the airline (`title_contains`) still work, but a record matched to a gold opportunity can no longer count as a
leaked exclusion. Before this change, a passenger lot and a cargo lot of the same airline were confused: heldout5 n06
showed a false "leaked 1".

The harness change was measured on its own, with the release-3.4.0 rules on a clean export (`previous/harness-only/`).
The only figure that moved was heldout5's leaked count, from 1 to 0. `tests/domain/test_evaluation_matching.py` covers
multiple lots and multiple notices of the same airline.

## Metrics and their denominators

Each metric is reported separately, with its own denominator:

- **Relevance accuracy**: correct freight-relevance judgements ÷ every judgement the gold makes. That is each gold
  opportunity whose freight scope the gold asserts (cargo, mixed, unclear, conflicting), plus each record the gold expects
  to be excluded (passenger, not_freight). A gold opportunity the pipeline did not create counts as wrong. "n/a" means
  the set has no such labels.
- **Opportunity precision**: created opportunities that match a gold opportunity ÷ opportunities created.
- **Opportunity recall**: gold opportunities found ÷ gold opportunities.
- **Actionable precision**: live records the pipeline created (open or revised) that match a live gold opportunity ÷
  live records created. A match is by reference, or by title where the gold has no reference. **Actionable recall**:
  live gold opportunities found live ÷ live gold opportunities. Terminal, contradictory, announced, unverified and
  historical records are never actionable.
- **Historical records retained (shown live)**: terminal notices the gold expects to be kept, found as a tender record
  with that terminal status ÷ such notices. The number in brackets counts those wrongly shown live. This is reported
  separately from actionable accuracy.
- **Field accuracy**: correct record values ÷ record values the gold asserts on matched opportunities (status, deadline
  day, deadline precision, service, freight scope).
- **Field completeness**: record values present ÷ record values the gold expects to be present on matched opportunities
  (a stated deadline and its precision, the service, the freight scope). It says nothing about correctness.
- **False 'supported'**: proposed values labelled supported that the notice does NOT state ÷ proposed values the gold marks
  as not stated. This is the safety metric; the target is 0.
- **Missed correct information**: proposed values the notice DOES state that were not labelled supported ÷ proposed values
  the gold marks as stated. These go to review, never to 'supported'. A proposal rejected as a whole because another of
  its fields is wrong is not counted.
- **Complete coverage**: documents fully read by the end ÷ documents. Long documents must first be flagged incomplete.
- **Excluded as not freight (leaked)**: gold exclusions the pipeline excluded ÷ gold exclusions. The figure in brackets
  counts exclusions that became opportunities anyway.

Sample sizes are small. `BUILD_REPORT.md` reports every set with that caveat. Before tuning further rules on new
findings, write a new held-out set first.
