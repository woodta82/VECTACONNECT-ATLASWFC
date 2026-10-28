"use client";

import { useState } from "react";
import { api, type DecisionCard as DecisionCardType } from "@/lib/api";
import StrategicMemory from "./StrategicMemory";

/**
 * Executive Decision Card.
 *
 * Information order is the specification, not a preference:
 *   1. Recommendation  2. Why  3. Executive Focus  4. Risks
 *   5. Cost of Waiting 6. Next Action  7. Supporting Evidence
 *
 * Strategic Alignment, Win Probability and Commercial Value are
 * deliberately BELOW that sequence. They are inputs to the
 * recommendation, and leading with them asks the reader to derive the
 * decision themselves — which is the work ATLAS is meant to have done.
 *
 * Two failures from the usability review are corrected here:
 *
 *  - **The card can now be decided on.** Previously it could recommend
 *    but not receive a decision, which made the dashboard a reading
 *    surface rather than an operating tool.
 *  - **Evidence is visible, not collapsed.** A recommendation shown
 *    without its support is an assertion; the reader should not have to
 *    click to find out whether it rests on anything.
 */
export default function DecisionCard({
  card,
  onOpen,
  onDecided,
}: {
  card: DecisionCardType;
  onOpen?: (id: string) => void;
  onDecided?: (id: string) => void;
}) {
  const [showFactors, setShowFactors] = useState(false);
  const [deciding, setDeciding] = useState(false);
  const [decided, setDecided] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const severity = card.opportunity_cost_of_waiting?.severity ?? "low";
  const evidence = card.supporting_evidence;

  async function decide(decision: string, response: string) {
    setDeciding(true);
    setError(null);
    try {
      await api.recordDecision(card.id, {
        decision,
        response,
        recommended_decision: card.recommended_decision.posture,
        recommendation_rationale: card.why_this_matters ?? undefined,
        recommendation_confidence: card.confidence,
        owner_name: card.owner ?? undefined,
      });
      setDecided(decision);
      onDecided?.(card.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not record the decision");
    } finally {
      setDeciding(false);
    }
  }

  if (decided) {
    return (
      <article className="dc dc-decided" aria-label={`Decided: ${card.title}`}>
        <p className="dc-decided-text">
          <strong>{decided}</strong> recorded for {card.title}
        </p>
        <p className="dc-decided-note">
          Reasoning captured. This will be compared against the outcome.
        </p>
      </article>
    );
  }

  return (
    <article className="dc" aria-label={`Decision required: ${card.title}`}>
      {/* ── 1. RECOMMENDATION ───────────────────────────────────── */}
      <header className="dc-decision">
        <div className="dc-decision-main">
          <span className={`dc-posture dc-posture-${card.recommended_decision.posture}`}>
            {card.recommended_decision.label}
          </span>
          <span className={`dc-confidence dc-confidence-${card.confidence}`}>
            {card.confidence} confidence
          </span>
        </div>
      </header>

      <h3 className="dc-title">{card.title}</h3>
      <p className="dc-meta">
        {card.primary_vertical_label ?? "Vertical unassigned"}
        {card.qualification_label && <> · {card.qualification_label}</>}
      </p>

      {/* ── 2. WHY ──────────────────────────────────────────────── */}
      {card.why_this_matters && <p className="dc-why">{card.why_this_matters}</p>}
      {card.recommended_decision.basis && (
        <p className="dc-basis">{card.recommended_decision.basis}</p>
      )}
      {card.score_reconciliation && (
        <p className="dc-reconciliation" role="note">
          {card.score_reconciliation}
        </p>
      )}

      {/* Strategic Memory — silent unless something moved. Placed here
          because "has this changed since I last looked?" is the question
          that follows "why does this matter?". */}
      <StrategicMemory opportunityId={card.id} compact />

      {/* ── 3. EXECUTIVE FOCUS — explainable, not a black box ───── */}
      <div className="dc-focus-row">
        <div className="dc-focus">
          <span className="dc-focus-score">{card.focus_score}</span>
          <span className="dc-focus-band">{card.focus_band_label}</span>
          {card.focus_delta !== null && card.focus_delta !== 0 && (
            <span className={`dc-delta ${card.focus_delta > 0 ? "dc-up" : "dc-down"}`}>
              {card.focus_delta > 0 ? "▲" : "▼"} {Math.abs(card.focus_delta)} since last review
            </span>
          )}
        </div>
        <button
          type="button"
          className="dc-toggle"
          onClick={() => setShowFactors((v) => !v)}
          aria-expanded={showFactors}
        >
          {showFactors ? "Hide" : "Why this score"}
        </button>
      </div>

      {card.primary_drivers?.length > 0 && (
        <p className="dc-drivers-inline">
          Driven by: {card.primary_drivers.slice(0, 3).join(" · ")}
        </p>
      )}

      {showFactors && (
        <div className="dc-factors">
          <p className="dc-factors-note">
            Executive Focus answers where to spend time today — not how good the
            opportunity is. Supporting metrics:
          </p>
          <div className="dc-scores">
            <Metric label="Strategic" value={card.strategic_alignment} />
            <Metric label="Win prob." value={card.win_probability} />
            <div className="dc-metric">
              <span className="dc-metric-label">Value</span>
              <span className="dc-metric-value dc-metric-sm">
                {card.commercial_value.label}
                {card.commercial_value.is_estimate && (
                  <span className="dc-estimate"> estimate</span>
                )}
              </span>
            </div>
            {card.pursuit_priority !== null && (
              <div className="dc-metric">
                <span className="dc-metric-label">Pursuit Priority</span>
                <span className="dc-metric-value">
                  {card.pursuit_priority}
                  {card.priority_restricted && (
                    <span className="dc-estimate"> restricted</span>
                  )}
                </span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 4. RISKS ────────────────────────────────────────────── */}
      <div className="dc-risks">
        <span className="dc-risk-label">Risk</span>
        <span className={`dc-risk-value ${!card.risk.established ? "dc-metric-unknown" : ""}`}>
          {card.risk.label}
        </span>
        <span className="dc-risk-sep">·</span>
        <span className="dc-risk-label">Relationship</span>
        <span className="dc-risk-value">
          {card.relationship_status.label}
          {card.relationship_status.is_inferred && (
            <span className="dc-inferred" title={card.relationship_status.basis}>
              {" "}
              inferred
            </span>
          )}
        </span>
      </div>

      {card.required_relationships?.some((r) => r.status === "missing") && (
        <p className="dc-gaps">
          Missing:{" "}
          {card.required_relationships
            .filter((r) => r.status === "missing")
            .map((r) => r.label)
            .join(", ")}
        </p>
      )}

      {/* ── 5. COST OF WAITING ──────────────────────────────────── */}
      <div className={`dc-waiting dc-waiting-${severity}`} role="note">
        <strong>Cost of waiting:</strong> {card.opportunity_cost_of_waiting?.summary}
      </div>

      {/* ── 6. NEXT ACTION ──────────────────────────────────────── */}
      <div className="dc-action">
        <p className="dc-action-text">{card.recommended_next_action}</p>
        <div className="dc-action-meta">
          <span>Owner: {card.owner ?? "Unassigned"}</span>
          {card.target_date && (
            <span>
              By{" "}
              {new Date(card.target_date).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })}
            </span>
          )}
          {card.deadline && (
            <span>
              Deadline{" "}
              {new Date(card.deadline).toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })}
            </span>
          )}
        </div>
      </div>

      {/* ── 7. SUPPORTING EVIDENCE — visible, not hidden ────────── */}
      <div className="dc-evidence-inline">
        <span className={`dc-evidence-badge ${evidence.sufficient_for_decision ? "dc-ev-ok" : "dc-ev-weak"}`}>
          {evidence.label}
        </span>
        {evidence.strongest_source && (
          <a
            href={evidence.strongest_source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="dc-evidence-link"
          >
            {evidence.strongest_source.publisher ?? "source"}
          </a>
        )}
        {!evidence.sufficient_for_decision && (
          <span className="dc-evidence-warn">not yet sufficient to confirm</span>
        )}
      </div>

      {/* ── DECIDE ──────────────────────────────────────────────── */}
      <div className="dc-decide">
        <button
          type="button"
          onClick={() => decide(card.recommended_decision.posture, "accepted")}
          disabled={deciding}
          className="dc-btn dc-btn-accept"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={() => decide("defer", "deferred")}
          disabled={deciding}
          className="dc-btn"
        >
          Defer
        </button>
        <button
          type="button"
          onClick={() => decide("decline", "rejected")}
          disabled={deciding}
          className="dc-btn"
        >
          Decline
        </button>
        {onOpen && (
          <button type="button" onClick={() => onOpen(card.id)} className="dc-open">
            Full detail →
          </button>
        )}
      </div>

      {error && (
        <p className="dc-error" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}

function Metric({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="dc-metric">
      <span className="dc-metric-label">{label}</span>
      <span className={`dc-metric-value ${value === null ? "dc-metric-unknown" : ""}`}>
        {value === null ? "Not scored" : value}
      </span>
    </div>
  );
}
