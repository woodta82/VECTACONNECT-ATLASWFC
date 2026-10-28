"use client";

import Link from "next/link";
import type { Phase2Opportunity } from "@/lib/api";
import { ClassificationBadge, QualificationBadge } from "./Phase2Display";

/**
 * Opportunity card — the Phase 2 list row.
 *
 * Shows all thirteen fields the spec requires, each with a written label.
 * Two are worth noting:
 *
 *  - Risk renders `display_label`, so an opportunity whose risk could not
 *    be established shows "Risk not established" rather than a low number
 *    the backend deliberately suppressed.
 *  - Pursuit Priority shows its restriction inline. A capped score with no
 *    explanation looks like a low-value opportunity, when it is actually
 *    an unassessed one — a materially different thing to a reader
 *    scanning a list.
 */
export default function Phase2OpportunityCard({ opp }: { opp: Phase2Opportunity }) {
  const priority = opp.pursuit_priority;
  const scores = opp.scores ?? {};
  const risk = scores.risk;

  const deadlineLabel = opp.deadline
    ? new Date(opp.deadline).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : "No deadline";

  return (
    <Link href={`/opportunities/${opp.id}`} className="p2-card">
      <div className="p2-card-top">
        <div className="p2-card-badges">
          <ClassificationBadge label={opp.classification_label} value={opp.classification} />
          {opp.qualification && (
            <QualificationBadge state={opp.qualification.state} label={opp.qualification.state_label} />
          )}
          {opp.requires_human_review && (
            <span className="p2-badge p2-badge-review">Needs review</span>
          )}
        </div>
        {priority && (
          <div className="p2-card-priority">
            <span className="p2-priority-score-sm">{priority.final_score}</span>
            <span className="p2-priority-band">{priority.band_label}</span>
          </div>
        )}
      </div>

      <h3 className="p2-card-title">{opp.title}</h3>

      <p className="p2-card-meta">
        <span>{opp.primary_vertical_label ?? "Vertical unassigned"}</span>
        {opp.contributing_vertical_count > 0 && (
          <span> · +{opp.contributing_vertical_count} contributing</span>
        )}
        {opp.primary_commercial_type_label && <span> · {opp.primary_commercial_type_label}</span>}
      </p>

      <div className="p2-card-scores">
        <ScoreChip label="Strategic" score={scores.strategic_alignment} />
        <ScoreChip label="Commercial" score={scores.commercial_attractiveness} />
        <ScoreChip label="Win prob." score={scores.win_probability} />
        {/* Risk: display_label, never the raw number */}
        <div className="p2-chip">
          <span className="p2-chip-label">Risk</span>
          <span className={`p2-chip-value ${risk?.display_score === null ? "p2-chip-unknown" : ""}`}>
            {risk ? risk.display_label : "—"}
          </span>
        </div>
      </div>

      {priority?.is_restricted && (
        <p className="p2-card-restriction">
          Priority restricted (uncapped {priority.uncapped_score}) —{" "}
          {priority.coverage_restricted ? "assessment incomplete" : "not yet qualified"}
        </p>
      )}

      <div className="p2-card-footer">
        <span>{opp.evidence_status?.label ?? "No evidence"}</span>
        <span>{opp.commercial_value?.value_status_label ?? "No value recorded"}</span>
        <span>{deadlineLabel}</span>
      </div>
    </Link>
  );
}

function ScoreChip({ label, score }: { label: string; score: { display_label: string; coverage_percent: number } | undefined }) {
  if (!score) {
    return (
      <div className="p2-chip">
        <span className="p2-chip-label">{label}</span>
        <span className="p2-chip-value p2-chip-unknown">Not scored</span>
      </div>
    );
  }
  return (
    <div className="p2-chip">
      <span className="p2-chip-label">{label}</span>
      <span className="p2-chip-value">{score.display_label}</span>
      <span className="p2-chip-coverage">{score.coverage_percent}%</span>
    </div>
  );
}
