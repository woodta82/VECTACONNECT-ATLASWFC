"use client";

import type { Phase2Opportunity } from "@/lib/api";
import QualificationWorkflow from "./QualificationWorkflow";
import {
  AnalysisList,
  ClassificationBadge,
  CommercialValuePanel,
  EvidenceCard,
  PriorityPanel,
  QualificationBadge,
  ScoreBreakdown,
  ScoreTile,
} from "./Phase2Display";

/**
 * Phase 2 opportunity detail.
 *
 * Ordered by what a commercial decision actually needs: what is this and
 * is it real (classification, evidence), what do we actually know versus
 * infer (facts / interpretation / assumptions / gaps), what is it worth,
 * how does it score, and can it be pursued.
 *
 * Facts, interpretation and assumptions are deliberately in separate
 * sections rather than one summary. Merging them is how an assumption
 * gets quoted back later as though it were established.
 */
export default function Phase2OpportunityDetail({ opp }: { opp: Phase2Opportunity }) {
  const scores = opp.scores ?? {};
  const dimensions = [
    "strategic_alignment",
    "commercial_attractiveness",
    "win_probability",
    "risk",
  ] as const;

  return (
    <div className="p2-detail">
      {/* ---------------------------------------------- overview */}
      <section className="p2-section">
        <div className="p2-detail-badges">
          <ClassificationBadge label={opp.classification_label} value={opp.classification} />
          {opp.qualification && (
            <QualificationBadge state={opp.qualification.state} label={opp.qualification.state_label} />
          )}
          {opp.requires_human_review && <span className="p2-badge p2-badge-review">Needs review</span>}
        </div>

        {opp.requires_human_review && opp.human_review_reason && (
          <div className="p2-restriction" role="note">
            <strong>Human review required.</strong> {opp.human_review_reason}
          </div>
        )}

        {opp.summary && <p className="p2-summary">{opp.summary}</p>}

        <dl className="p2-dl">
          <dt>Primary vertical</dt>
          <dd>
            {opp.primary_vertical_label ?? "Unassigned"}
            {opp.vertical_rationale && <span className="p2-note"> — {opp.vertical_rationale}</span>}
          </dd>

          <dt>Contributing verticals</dt>
          <dd>
            {opp.contributing_verticals.length === 0
              ? "None"
              : opp.contributing_verticals.map((v) => v.label).join(", ")}
          </dd>

          <dt>Commercial type</dt>
          <dd>
            {opp.primary_commercial_type_label ?? "—"}
            {opp.secondary_commercial_types && opp.secondary_commercial_types.length > 0 && (
              <span className="p2-note">
                {" "}
                (also {opp.secondary_commercial_types.map((s) => s.label).join(", ")})
              </span>
            )}
          </dd>

          <dt>Route to market</dt>
          <dd>
            {opp.routes_to_market.length === 0
              ? "Unknown"
              : opp.routes_to_market.map((r) => r.label).join(" · ")}
          </dd>

          <dt>Classification basis</dt>
          <dd>{opp.classification_rationale ?? "—"}</dd>
        </dl>
      </section>

      {/* ---------------------------------------------- evidence */}
      <section className="p2-section">
        <h3 className="p2-section-title">
          Evidence <span className="p2-section-note">{opp.evidence_status?.label}</span>
        </h3>
        {opp.evidence.length === 0 ? (
          <p className="p2-empty">No evidence recorded.</p>
        ) : (
          <ul className="p2-evidence-list">
            {opp.evidence.map((e) => (
              <EvidenceCard key={e.id} evidence={e} />
            ))}
          </ul>
        )}
      </section>

      {/* ------------------------ facts / interpretation / assumptions */}
      <AnalysisList
        title="Verified facts"
        items={opp.verified_facts}
        emptyText="No verified facts recorded."
        showVerification
      />
      <AnalysisList
        title="AI interpretation"
        items={opp.ai_interpretation}
        emptyText="No interpretation recorded."
      />
      <AnalysisList
        title="Assumptions"
        items={opp.assumptions}
        emptyText="No assumptions recorded."
      />
      <AnalysisList
        title="Missing information"
        items={opp.missing_information}
        emptyText="Nothing outstanding."
      />
      <AnalysisList
        title="Recommended verification actions"
        items={opp.verification_actions}
        emptyText="No verification actions recommended."
      />

      {/* ---------------------------------------------- value */}
      <section className="p2-section">
        <h3 className="p2-section-title">Commercial value</h3>
        <CommercialValuePanel value={opp.commercial_value} />
      </section>

      {/* ---------------------------------------------- scores */}
      <section className="p2-section">
        <h3 className="p2-section-title">Scores</h3>
        <div className="p2-score-grid">
          {dimensions.map((d) => (scores[d] ? <ScoreTile key={d} score={scores[d]} /> : null))}
        </div>
        <div className="p2-breakdowns">
          {dimensions.map((d) => (scores[d] ? <ScoreBreakdown key={d} score={scores[d]} /> : null))}
        </div>
      </section>

      {/* ---------------------------------------------- priority */}
      <section className="p2-section">
        <h3 className="p2-section-title">Pursuit Priority</h3>
        <PriorityPanel priority={opp.pursuit_priority} />
      </section>

      {/* ---------------------------------------------- qualification */}
      {/* The interactive workflow, not a read-only view: the gate blocks
          progression, so the detail page must also be where it is resolved.
          A page that reports "verification required" with no way to answer
          the checklist is where opportunities go to die. */}
      <section className="p2-section">
        <h3 className="p2-section-title">Qualification</h3>
        <QualificationWorkflow opportunityId={opp.id} />
      </section>

      {/* ---------------------------------------------- overrides */}
      {opp.overrides && opp.overrides.length > 0 && (
        <section className="p2-section">
          <h3 className="p2-section-title">Manual overrides</h3>
          <table className="p2-table">
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Original (AI)</th>
                <th scope="col">Updated</th>
                <th scope="col">Reason</th>
                <th scope="col">When</th>
              </tr>
            </thead>
            <tbody>
              {opp.overrides.map((o, i) => (
                <tr key={i}>
                  <td>{o.field_path}</td>
                  <td>{o.original_value ?? "—"}</td>
                  <td>{o.updated_value ?? "—"}</td>
                  <td className="p2-cell-rationale">{o.reason}</td>
                  <td>{o.created_at ? new Date(o.created_at).toLocaleDateString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {/* ---------------------------------------------- legacy */}
      {opp.legacy && (
        <section className="p2-section p2-section-legacy">
          <h3 className="p2-section-title">Legacy data (pre-Phase 2)</h3>
          <p className="p2-note">{opp.legacy.notice}</p>
          <dl className="p2-dl">
            <dt>Legacy alignment score</dt>
            <dd>{opp.legacy.legacy_alignment_score ?? "—"}</dd>
            <dt>Legacy vertical</dt>
            <dd>
              {opp.legacy.legacy_vertical ?? "—"}
              {opp.legacy.vertical_requires_review && (
                <span className="p2-warn"> — could not be mapped, needs manual assignment</span>
              )}
            </dd>
            <dt>Legacy value estimate</dt>
            <dd>
              {opp.legacy.legacy_value_estimate === null
                ? "—"
                : `${opp.legacy.legacy_currency ?? ""} ${Math.round(
                    opp.legacy.legacy_value_estimate
                  ).toLocaleString()}`}
              <span className="p2-warn"> — unverified, never a published figure</span>
            </dd>
            <dt>Migrated</dt>
            <dd>
              {opp.legacy.migration_version}
              {opp.legacy.migrated_at
                ? ` · ${new Date(opp.legacy.migrated_at).toLocaleDateString()}`
                : ""}
            </dd>
          </dl>
        </section>
      )}
    </div>
  );
}
