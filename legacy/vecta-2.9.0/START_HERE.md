# ATLAS v1.0 — Start Here

**Executive Commercial Intelligence Platform for VECTA Sports.**

---

## The one thing to know first

ATLAS is comprehensively built and **has never been executed**. Not lightly
tested — never run. 250 tests written and zero executed, 23 components
never compiled, 9 migrations never applied.

The one tool that *has* run — the calibration harness — found two real bugs
in ninety seconds on its first execution. **Expect failures.** Finding them
now costs an afternoon; finding them later costs a commercial decision.

**Everything starts here:**

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
bash tools/validate_release.sh
```

Writes `VALIDATION_REPORT.txt`. Full sequence in
`docs/DEPLOYMENT_RUNBOOK.md`.

---

## What is in this package

| | |
|---|---|
| Backend | 64 modules, ~16,500 lines (FastAPI, SQLAlchemy 2.0, PostgreSQL) |
| Frontend | 23 components (Next.js 14, TypeScript) |
| Tests | 250, across 7 files |
| Migrations | 9 (Alembic, all with tested downgrade paths) |
| Intelligence models | 7, all documented and explainable |
| Documentation | 21 files |

---

## Documentation — in reading order

**Start with these three**

| Document | Why |
|---|---|
| `docs/DEPLOYMENT_RUNBOOK.md` | Nine stages, two days to running. **Read first.** |
| `docs/V1.0_EXIT_REVIEW.md` | Honest maturity assessment, open risks, V1.1 priorities |
| `docs/OPERATIONS_GUIDE.md` | Running it: config, monitoring, backup, recovery, incidents |

**The intellectual property**

| Document | Why |
|---|---|
| `docs/INTELLIGENCE_MODEL_GOVERNANCE.md` | All 7 models: purpose, inputs, weights, calculation, limitations |
| `docs/PRODUCTION_READINESS_ASSESSMENT.md` | Why this is not yet a release candidate |

**Design history** — `PHASE3_PRODUCT_SPEC_v2.md` (design authority),
`PHASE3_ARCHITECTURE.md`, `PHASE3.1_DESIGN_REVIEW.md`,
`RELEASE_NOTES_v2.9.md`, `SECURITY.md`.

---

## The seven intelligence models

| Code | Model | Question |
|---|---|---|
| EFS | Executive Focus Score | Where should executive time go today? |
| RCI | Relationship Coverage Index | Do we know the right people? |
| CRI | Commercial Readiness Index | Are we genuinely ready to pursue? |
| RMI | Relationship Momentum Index | Are relationships improving or deteriorating? |
| DCS | Decision Confidence Score | Should we believe this recommendation? |
| RHS | Relationship Health Score | How strong is this relationship now? |
| SCE | Scenario Engine | What are the alternatives and their costs? |

**No model is a black box.** Every one exposes its per-factor
contributions, weakest factors, and what would improve the score.

Check them against your own judgement — this runs standalone, no database:

```bash
python3 tools/calibrate_models.py
```

---

## Tooling

| Command | Purpose |
|---|---|
| `tools/validate_release.sh` | Everything. Start here. |
| `tools/verify_imports.py` | Imports resolve; every used name is bound |
| `tools/verify_contract.py` | Backend response shapes match frontend types |
| `tools/calibrate_models.py` | Models vs commercial judgement |
| `tools/demo_end_to_end.py` | Full workflow from a fixture, no AI cost |

Each of the three static gates was written **after** the corresponding bug
shipped. CI (`.github/workflows/validate.yml`) makes them mandatory rather
than optional.

---

## Two things not to lose

**1. The Decision Journal is the only irreplaceable data.** Opportunities
can be re-scanned for a few dollars. The reasoning behind past decisions —
frozen at the time they were made — exists nowhere else. Back it up before
anything else.

**2. One calibration divergence is open and it is yours to decide.**
Executive Focus currently means *"where work remains"*, which is why your
strongest opportunity can score mid-table when nothing is outstanding on
it. The alternative is *"what deserves your eyes"*. Documented in
`V1.0_EXIT_REVIEW.md` §"Open calibration divergences".

---

## Cost model

The daily briefing, all seven models, and the advisor are **computed from
stored data and cost nothing**. The only variable cost is the Anthropic
API, incurred solely when a scan or contact discovery is triggered
manually. This is deliberate — do not relax it without a decision.

---

## The honest position

ATLAS is a well-designed decision platform with genuine IP in its
intelligence models, a consistently defended product identity, and static
gates that have caught real defects repeatedly.

**It has also never been switched on.**

The distance to a working pilot is not months of development. It is one
command, the fixes it surfaces, a week of operational work, and four weeks
of real use generating the outcome data the models need to stop being
hypotheses.
