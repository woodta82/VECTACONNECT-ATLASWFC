"use client";

import type {
  Phase2CommercialValue,
  Phase2Evidence,
  Phase2Priority,
  Phase2Score,
} from "@/lib/api";

/**
 * Phase 2 display primitives.
 *
 * Accessibility rule applied throughout: colour is never the only carrier
 * of meaning. Every state also has a written label, because a red border
 * alone tells a colour-blind user (or anyone on a poor screen) nothing,
 * and these states — disqualified, risk-not-established, estimate-not-fact
 * — are exactly the ones where misreading is costly.
 */

// ---------------------------------------------------------------- badges

export function ClassificationBadge({ label, value }: { label: string | null; value: string | null }) {
  if (!label) return <span className="p2-badge p2-badge-muted">Unclassified</span>;
  const tone =
    value === "confirmed_opportunity"
      ? "p2-badge-confirmed"
      : value === "market_signal" || value === "intelligence_watch"
      ? "p2-badge-signal"
      : value === "unverified_lead"
      ? "p2-badge-unverified"
      : "p2-badge-neutral";
  return <span className={`p2-badge ${tone}`}>{label}</span>;
}

export function QualificationBadge({ state, label }: { state: string; label: string }) {
  const tone =
    state === "qualified"
      ? "p2-badge-qualified"
      : state === "disqualified"
      ? "p2-badge-disqualified"
      : state === "conditionally_qualified"
      ? "p2-badge-conditional"
      : "p2-badge-neutral";
  return <span className={`p2-badge ${tone}`}>{label}</span>;
}

export function CoverageBadge({ score }: { score: Phase2Score }) {
  return (
    <span className={`p2-coverage p2-coverage-${score.coverage_band}`}>
      {score.coverage_percent}% · {score.coverage_label}
    </span>
  );
}

// ----------------------------------------------------------- score tile

export function ScoreTile({ score }: { score: Phase2Score }) {
  // When risk is not established the server sends display_score = null.
  // Rendering `score.score` here would resurrect exactly the reassuringly
  // low number the backend suppressed.
  const notEstablished = score.display_score === null;
  return (
    <div className="p2-score-tile">
      <p className="p2-score-label">{score.label}</p>
      <p className={`p2-score-value ${notEstablished ? "p2-score-unknown" : ""}`}>
        {score.display_label}
      </p>
      <CoverageBadge score={score} />
      {score.is_overridden && (
        <p className="p2-score-note">
          Manually overridden (AI: {score.ai_score}) — {score.override_reason}
        </p>
      )}
      {score.confidence && <p className="p2-score-note">Confidence: {score.confidence}</p>}
    </div>
  );
}

export function ScoreBreakdown({ score }: { score: Phase2Score }) {
  const scored = score.factors.filter((f) => f.scored);
  const unscored = score.factors.filter((f) => !f.scored);
  return (
    <div className="p2-breakdown">
      <div className="p2-breakdown-head">
        <h4>{score.label}</h4>
        <span className="p2-score-value-sm">{score.display_label}</span>
      </div>
      <CoverageBadge score={score} />
      {score.rationale && <p className="p2-rationale">{score.rationale}</p>}

      <table className="p2-table">
        <thead>
          <tr>
            <th scope="col">Factor</th>
            <th scope="col">Weight</th>
            <th scope="col">Score</th>
            <th scope="col">Rationale</th>
          </tr>
        </thead>
        <tbody>
          {scored.map((f) => (
            <tr key={f.key}>
              <td>{f.label}</td>
              <td>{Math.round(f.weight * 100)}%</td>
              <td>{f.score}</td>
              <td className="p2-cell-rationale">{f.rationale ?? "—"}</td>
            </tr>
          ))}
          {unscored.map((f) => (
            <tr key={f.key} className="p2-row-unscored">
              <td>{f.label}</td>
              <td>{Math.round(f.weight * 100)}%</td>
              <td>
                <span className="p2-not-assessed">Not assessed</span>
              </td>
              <td className="p2-cell-rationale">—</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="p2-meta">
        Model {score.model_version}
        {score.last_scored_at ? ` · scored ${new Date(score.last_scored_at).toLocaleDateString()}` : ""}
      </p>
    </div>
  );
}

// ------------------------------------------------------ pursuit priority

export function PriorityPanel({ priority }: { priority: Phase2Priority | null }) {
  if (!priority) return <p className="p2-empty">Pursuit Priority not yet calculated.</p>;
  return (
    <div className="p2-priority">
      <div className="p2-priority-head">
        <span className="p2-priority-score">{priority.final_score}</span>
        <span className="p2-badge p2-badge-neutral">{priority.band_label}</span>
      </div>

      {priority.is_restricted && (
        <div className="p2-restriction" role="note">
          <strong>Restricted.</strong> Uncapped score was {priority.uncapped_score}.{" "}
          {priority.restriction_explanation}
        </div>
      )}

      <table className="p2-table">
        <thead>
          <tr>
            <th scope="col">Component</th>
            <th scope="col">Value</th>
            <th scope="col">Weight</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(priority.weights_used).map(([key, weight]) => (
            <tr key={key}>
              <td>{key.replace(/_/g, " ")}</td>
              <td>{key === "inverse_risk" ? priority.inverse_risk : "—"}</td>
              <td>{Math.round(weight * 100)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="p2-meta">
        Base {priority.base_score}
        {priority.urgency_adjustment ? ` · urgency ${priority.urgency_adjustment}` : ""} · model{" "}
        {priority.model_version}
      </p>
    </div>
  );
}

// ------------------------------------------------------------- evidence

export function EvidenceCard({ evidence }: { evidence: Phase2Evidence }) {
  return (
    <li className="p2-evidence">
      <div className="p2-evidence-head">
        <a href={evidence.url} target="_blank" rel="noopener noreferrer" className="p2-evidence-title">
          {evidence.page_title || evidence.url}
        </a>
        <span className="p2-badge p2-badge-neutral">{evidence.source_tier_label}</span>
      </div>
      <p className="p2-evidence-meta">
        {evidence.publisher ?? "Publisher unknown"} ·{" "}
        {evidence.publication_date ?? evidence.no_publication_date_reason ?? "No publication date"}
      </p>
      <p className="p2-evidence-meta">
        URL: {evidence.url_validation_label}
        {evidence.is_official_source ? " · Official source" : ""}
        {evidence.is_definitive ? " · Definitive" : ""} · Confidence: {evidence.confidence}
      </p>
      <div className="p2-claims">
        <span className="p2-claims-label">Supports:</span>
        {evidence.claims_supported.map((c) => (
          <span key={c} className="p2-claim">
            {c.replace(/_/g, " ")}
          </span>
        ))}
      </div>
    </li>
  );
}

// -------------------------------------------------------------- value

export function CommercialValuePanel({ value }: { value: Phase2CommercialValue | null }) {
  if (!value) return <p className="p2-empty">No commercial value recorded.</p>;

  const money = (n: number | null) =>
    n === null ? "—" : `${value.currency} ${Math.round(n).toLocaleString()}`;

  return (
    <div className="p2-value">
      <div className="p2-value-head">
        <span className="p2-badge p2-badge-neutral">{value.value_status_label}</span>
        {/* An estimate must never look like a published figure. */}
        {value.is_estimate && (
          <span className="p2-badge p2-badge-estimate">Estimate — not a published figure</span>
        )}
        {value.is_legacy_unverified && (
          <span className="p2-badge p2-badge-unverified">Legacy, unverified</span>
        )}
      </div>

      <dl className="p2-dl">
        {value.published_contract_value !== null && (
          <>
            <dt>Published contract value</dt>
            <dd>{money(value.published_contract_value)}</dd>
          </>
        )}
        {value.published_programme_value !== null && (
          <>
            <dt>Published wider programme value</dt>
            <dd>
              {money(value.published_programme_value)}
              <span className="p2-warn"> — not the value available to VECTA</span>
            </dd>
          </>
        )}
        {value.estimated_contract_min !== null && (
          <>
            <dt>Estimated available range</dt>
            <dd>
              {money(value.estimated_contract_min)} – {money(value.estimated_contract_max)}
            </dd>
          </>
        )}
        {value.estimated_vecta_revenue !== null && (
          <>
            <dt>Estimated VECTA revenue</dt>
            <dd>{money(value.estimated_vecta_revenue)}</dd>
          </>
        )}
        {value.partner_share_assumption !== null && (
          <>
            <dt>Partner share assumption</dt>
            <dd>{Math.round(value.partner_share_assumption * 100)}%</dd>
          </>
        )}
      </dl>

      {value.estimate_methodology && (
        <p className="p2-methodology">
          <strong>Basis:</strong> {value.estimate_methodology}
        </p>
      )}
    </div>
  );
}

// -------------------------------------------------------- analysis list

export function AnalysisList({
  title,
  items,
  emptyText,
  showVerification = false,
}: {
  title: string;
  items: { id: string; content: string; is_verified: boolean; verification_label: string; claim_type: string | null }[] | undefined;
  emptyText: string;
  showVerification?: boolean;
}) {
  return (
    <section className="p2-section">
      <h3 className="p2-section-title">{title}</h3>
      {!items || items.length === 0 ? (
        <p className="p2-empty">{emptyText}</p>
      ) : (
        <ul className="p2-list">
          {items.map((i) => (
            <li key={i.id} className="p2-list-item">
              <span>{i.content}</span>
              {showVerification && (
                <span
                  className={`p2-badge ${i.is_verified ? "p2-badge-qualified" : "p2-badge-unverified"}`}
                >
                  {i.verification_label}
                  {i.claim_type ? ` · ${i.claim_type.replace(/_/g, " ")}` : ""}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
