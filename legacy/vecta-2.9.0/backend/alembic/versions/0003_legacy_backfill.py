"""backfill existing opportunities into the Phase 2 model

Revision ID: 0003_legacy_backfill
Revises: 0002_phase2_model
Create Date: 2026-07-27

Copies every pre-Phase-2 opportunity into the new structure. 0002 created
the tables; this puts the existing data in them.

DESIGN NOTES
============
*Idempotent.* Re-running skips any opportunity that already has a
`legacy_opportunity_data` row. A migration that double-writes evidence on
a retried deploy would be worse than one that fails outright.

*Conservative by default.* Migrated records are NEVER marked Confirmed or
Qualified. Old data was produced by a model with no evidence tiers and no
qualification gate, so it cannot satisfy Phase 2's bar — asserting
otherwise would put unverified records straight into the active pipeline,
which is exactly what Phase 2 exists to prevent. Everything lands as
`unverified_lead` / `verification_required`.

*Estimates stay estimates.* An old `value_estimate` had no source and no
methodology. It is preserved as `is_legacy_unverified=True` with status
`insufficient_evidence` — never reinterpreted as a published figure.

*Old URLs become evidence, not facts.* Each becomes a Tier 4 record with
`url_validation_status='not_reviewed'`, supporting only
`opportunity_existence`. Claiming more would let an unreviewed link
validate assertions nobody checked.
"""
from typing import Sequence, Union
import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision: str = "0003_legacy_backfill"
down_revision: Union[str, None] = "0002_phase2_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MIGRATION_VERSION = "2.9.0"

# Legacy five-vertical enum -> Phase 2 six-vertical taxonomy. The five map
# one-to-one; `intelligence` is new and no legacy row can belong to it, so
# nothing maps onto it automatically.
VERTICAL_MAP = {
    "media": "media",
    "talent": "talent",
    "connect": "connect",
    "experiences": "experiences",
    "pathways": "pathways",
}


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def upgrade() -> None:
    conn = op.get_bind()
    now = _now()

    # Legacy rows may predate the summary requirement. Fall back to the
    # title with a clear marker rather than inventing prose — a reader must
    # be able to tell a real summary from a migration placeholder.
    conn.execute(
        sa.text(
            """
            UPDATE opportunities
               SET summary = COALESCE(NULLIF(TRIM(summary), ''), title)
             WHERE summary IS NULL OR TRIM(summary) = ''
            """
        )
    )

    report = {
        "records_examined": 0,
        "records_migrated": 0,
        "already_migrated_skipped": 0,
        "verticals_mapped": 0,
        "verticals_requiring_review": 0,
        "evidence_records_created": 0,
        "legacy_values_preserved": 0,
        "qualification_records_created": 0,
        "errors": [],
    }

    opportunities = conn.execute(
        sa.text(
            """
            SELECT id, title, vertical, alignment_score, score_breakdown,
                   value_estimate, currency, source_urls
            FROM opportunities
            """
        )
    ).fetchall()
    report["records_examined"] = len(opportunities)

    already = {
        r[0] for r in conn.execute(sa.text("SELECT opportunity_id FROM legacy_opportunity_data")).fetchall()
    }

    for row in opportunities:
        opp_id = row[0]
        if opp_id in already:
            report["already_migrated_skipped"] += 1
            continue

        try:
            title, legacy_vertical = row[1], row[2]
            alignment_score, breakdown = row[3], row[4]
            value_estimate, currency, source_urls = row[5], row[6], row[7]

            # source_urls is a JSON list, not a single URL — each entry
            # becomes its own evidence record so the claim-level model has
            # something real to attach to.
            if isinstance(source_urls, str):
                try:
                    source_urls = json.loads(source_urls) if source_urls.strip() else []
                except (ValueError, TypeError):
                    source_urls = [source_urls] if source_urls.strip() else []
            if not isinstance(source_urls, list):
                source_urls = []

            # --- vertical mapping -------------------------------------
            legacy_key = str(legacy_vertical).lower() if legacy_vertical else None
            primary_vertical = VERTICAL_MAP.get(legacy_key)
            if primary_vertical:
                mapping_status, needs_review = "mapped", False
                report["verticals_mapped"] += 1
            else:
                # Unrecognised or missing — flagged rather than guessed.
                primary_vertical, mapping_status, needs_review = None, "requires_review", True
                report["verticals_requiring_review"] += 1

            # --- legacy snapshot --------------------------------------
            conn.execute(
                sa.text(
                    """
                    INSERT INTO legacy_opportunity_data
                      (id, opportunity_id, legacy_alignment_score, legacy_score_breakdown,
                       legacy_vertical, legacy_value_estimate, legacy_currency,
                       vertical_mapping_status, vertical_requires_review,
                       migration_version, migrated_at, notes)
                    VALUES
                      (:id, :opp, :score, :breakdown, :vertical, :value, :currency,
                       :status, :review, :version, :at, :notes)
                    """
                ),
                {
                    "id": _uuid(), "opp": opp_id,
                    "score": alignment_score, "breakdown": breakdown if breakdown else "{}",
                    "vertical": legacy_key, "value": value_estimate, "currency": currency,
                    "status": mapping_status, "review": needs_review,
                    "version": MIGRATION_VERSION, "at": now,
                    "notes": "Superseded by the four-dimension model — retained for audit only.",
                },
            )
            report["legacy_values_preserved"] += 1

            # --- Phase 2 classification on the opportunity -------------
            conn.execute(
                sa.text(
                    """
                    UPDATE opportunities
                       SET classification = :classification,
                           classification_rationale = :rationale,
                           primary_vertical = :vertical,
                           vertical_rationale = :vrationale,
                           requires_human_review = :review,
                           human_review_reason = :reason
                     WHERE id = :id
                    """
                ),
                {
                    "id": opp_id,
                    # Never Confirmed — pre-Phase-2 data has no evidence tiers.
                    "classification": "unverified_lead",
                    "rationale": (
                        f"Migrated from pre-Phase-2 data ({MIGRATION_VERSION}). The legacy model "
                        "carried no source tiers or verification, so this cannot be classified "
                        "higher until its evidence is reviewed."
                    ),
                    "vertical": primary_vertical,
                    "vrationale": (
                        f"Mapped from legacy vertical '{legacy_key}'." if primary_vertical
                        else "Legacy vertical could not be mapped — needs manual assignment."
                    ),
                    "review": True,
                    "reason": (
                        "Migrated from pre-Phase-2 data: evidence unreviewed, scores not yet "
                        "assessed under the four-dimension model."
                        + ("" if primary_vertical else " Vertical requires manual assignment.")
                    ),
                },
            )

            # --- old source URLs -> Tier 4 unreviewed evidence ---------
            for source_url in source_urls:
                if not source_url or not str(source_url).strip():
                    continue
                evidence_id = _uuid()
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO opportunity_evidence
                          (id, opportunity_id, url, source_tier, evidence_type,
                           no_publication_date_reason, date_accessed, url_validation_status,
                           is_official_source, is_definitive, confidence, notes,
                           created_at, is_manual, is_archived, is_unavailable)
                        VALUES
                          (:id, :opp, :url, 'tier_4', 'other',
                           :nodate, :at, 'not_reviewed',
                           0, 0, 'low', :notes, :at, 0, 0, 0)
                        """
                    ),
                    {
                        "id": evidence_id, "opp": opp_id, "url": str(source_url).strip(),
                        "nodate": "Legacy record — publication date was not captured before Phase 2.",
                        "at": now,
                        "notes": f"Migrated from the legacy source_url field ({MIGRATION_VERSION}). Not yet reviewed.",
                    },
                )
                # Supports only that something exists — nothing more.
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO evidence_claims (id, evidence_id, claim_type, note, created_at)
                        VALUES (:id, :ev, 'opportunity_existence', :note, :at)
                        """
                    ),
                    {
                        "id": _uuid(), "ev": evidence_id, "at": now,
                        "note": "Legacy URL: claim support has not been verified.",
                    },
                )
                report["evidence_records_created"] += 1

            # --- legacy value -> unverified estimate -------------------
            if value_estimate is not None:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO commercial_values
                          (id, opportunity_id, currency, value_status, estimate_methodology,
                           is_legacy_unverified, confidence, updated_at, last_reviewed_at)
                        VALUES
                          (:id, :opp, :currency, 'insufficient_evidence', :method, 1, 'low', :at, NULL)
                        """
                    ),
                    {
                        "id": _uuid(), "opp": opp_id, "currency": currency or "USD", "at": now,
                        "method": (
                            f"Legacy unverified estimate of {value_estimate} carried over from the "
                            "pre-Phase-2 model. No source or methodology was recorded, so it is NOT "
                            "presented as a published or estimated figure."
                        ),
                    },
                )

            # --- qualification: never Qualified ------------------------
            qual_id = _uuid()
            conn.execute(
                sa.text(
                    """
                    INSERT INTO qualification_assessments
                      (id, opportunity_id, state, has_absolute_disqualifier, summary,
                       model_version, evaluated_at, last_reviewed_at)
                    VALUES
                      (:id, :opp, 'verification_required', 0, :summary, '2.0', :at, NULL)
                    """
                ),
                {
                    "id": qual_id, "opp": opp_id, "at": now,
                    "summary": (
                        "Migrated record — not assessed under the Phase 2 qualification gate. "
                        "Requires verification before it can enter the active pipeline."
                    ),
                },
            )
            report["qualification_records_created"] += 1
            report["records_migrated"] += 1

        except Exception as exc:  # noqa: BLE001
            report["errors"].append({"opportunity_id": opp_id, "error": str(exc)})

    _print_report(report)


def _print_report(report: dict) -> None:
    print("\n" + "=" * 62)
    print("ATLAS PHASE 2 LEGACY MIGRATION REPORT")
    print("=" * 62)
    print(f"  Migration version           : {MIGRATION_VERSION}")
    print(f"  Records examined            : {report['records_examined']}")
    print(f"  Records migrated            : {report['records_migrated']}")
    print(f"  Already migrated (skipped)  : {report['already_migrated_skipped']}")
    print(f"  Verticals mapped            : {report['verticals_mapped']}")
    print(f"  Verticals requiring review  : {report['verticals_requiring_review']}")
    print(f"  Evidence records created    : {report['evidence_records_created']}")
    print(f"  Legacy values preserved     : {report['legacy_values_preserved']}")
    print(f"  Qualification records       : {report['qualification_records_created']}")
    print(f"  Errors                      : {len(report['errors'])}")
    for e in report["errors"]:
        print(f"      ! {e['opportunity_id']}: {e['error']}")
    print("-" * 62)
    print("  All migrated records: classification=unverified_lead,")
    print("  qualification=verification_required. None marked Confirmed")
    print("  or Qualified. Legacy scores and values preserved for audit.")
    print("=" * 62 + "\n")


def downgrade() -> None:
    """Removes only what this revision inserted, leaving the Phase 2 tables
    themselves (0002 owns those) and every legacy column untouched."""
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM evidence_claims
             WHERE evidence_id IN (
                SELECT id FROM opportunity_evidence
                 WHERE notes LIKE 'Migrated from the legacy source_url field%'
             )
            """
        )
    )
    conn.execute(
        sa.text("DELETE FROM opportunity_evidence WHERE notes LIKE 'Migrated from the legacy source_url field%'")
    )
    conn.execute(sa.text("DELETE FROM commercial_values WHERE is_legacy_unverified = 1"))
    conn.execute(
        sa.text("DELETE FROM qualification_assessments WHERE summary LIKE 'Migrated record%'")
    )
    conn.execute(sa.text(f"DELETE FROM legacy_opportunity_data WHERE migration_version = '{MIGRATION_VERSION}'"))
    conn.execute(
        sa.text(
            """
            UPDATE opportunities
               SET classification = NULL, classification_rationale = NULL,
                   primary_vertical = NULL, vertical_rationale = NULL,
                   requires_human_review = 0, human_review_reason = NULL
             WHERE classification_rationale LIKE 'Migrated from pre-Phase-2 data%'
            """
        )
    )
