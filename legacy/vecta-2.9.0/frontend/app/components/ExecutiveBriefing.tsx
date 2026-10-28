"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type AdvisorResponse, type ExecutiveBriefing } from "@/lib/api";
import DecisionCard from "./DecisionCard";
import AdvisorPanel from "./AdvisorPanel";

/**
 * Executive Briefing — the daily landing screen.
 *
 * Designed against one measure: understanding the state of the business
 * in under two minutes, without opening another screen.
 *
 * That drives three choices:
 *  - the header is a DIFF, not a status. What changed comes before what is.
 *  - "Focus today" is capped at three. A list of ten is a list, not a focus.
 *  - when nothing needs attention it says so plainly, because a product
 *    built for short sessions should be willing to say it is finished.
 */
export default function ExecutiveBriefing() {
  const router = useRouter();
  const [briefing, setBriefing] = useState<ExecutiveBriefing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [advisorAnswer, setAdvisorAnswer] = useState<AdvisorResponse | null>(null);
  const [decidedIds, setDecidedIds] = useState<string[]>([]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setBriefing(await api.briefing());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the briefing");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (loading) return <p className="state-loading">Preparing your briefing…</p>;
  if (error) {
    return (
      <div className="state-error" role="alert">
        <span>{error}</span>
        <button onClick={load} className="state-error-action">
          Try again
        </button>
      </div>
    );
  }
  if (!briefing) return null;

  const s = briefing.sections;
  const summary = s["1_executive_summary"];
  const counts = summary.counts;
  const now = new Date(briefing.generated_at);

  return (
    <div className="eb">
      {/* ── header: a diff, not a status ────────────────────────── */}
      <header className="eb-header">
        <div>
          <p className="eb-date">
            {now.toLocaleDateString(undefined, {
              weekday: "long",
              day: "numeric",
              month: "long",
            })}
          </p>
          <h1 className="eb-title">Executive Briefing</h1>
        </div>
        <button onClick={load} className="eb-refresh" title="Refresh — free, no AI cost">
          Refresh
        </button>
      </header>

      {/* ── 1. executive summary ────────────────────────────────── */}
      <section className={`eb-summary ${summary.is_complete ? "eb-summary-clear" : ""}`}>
        <p className="eb-headline">{summary.headline}</p>

        {summary.is_complete ? (
          <p className="eb-complete">{summary.completion_message}</p>
        ) : (
          <div className="eb-counts">
            <Count value={counts.act_now} label="Act now" tone="urgent" />
            <Count value={counts.this_week} label="This week" />
            <Count value={counts.significant_changes} label="Significant changes" />
            <Count value={counts.deadlines_30_days} label="Deadlines ≤30d" />
            <Count value={counts.going_stale} label="Going stale" tone="urgent" />
            <Count value={counts.awaiting_qualification} label="Awaiting qualification" />
          </div>
        )}

        {summary.what_can_wait.length > 0 && (
          <details className="eb-can-wait">
            <summary>{summary.what_can_wait.length} item(s) need no action</summary>
            <ul>
              {summary.what_can_wait.map((w) => (
                <li key={w.id}>
                  <strong>{w.title}</strong> — {w.reason}
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {/* ── 2. today's priorities ───────────────────────────────── */}
      {s["2_todays_priorities"].length > 0 && (
        <section className="eb-section">
          <h2 className="eb-section-title">
            Focus today
            {decidedIds.length > 0 && (
              <span className="eb-progress">
                {decidedIds.length} of {s["2_todays_priorities"].length} decided
              </span>
            )}
          </h2>
          <div className="eb-cards">
            {s["2_todays_priorities"].map((card) => (
              <DecisionCard
                key={card.id}
                card={card}
                onOpen={(id) => router.push(`/opportunities/${id}`)}
                onDecided={(id) => setDecidedIds((prev) => [...prev, id])}
              />
            ))}
          </div>
        </section>
      )}

      {/* ── 3. what changed ─────────────────────────────────────── */}
      {s["3_what_changed"].length > 0 && (
        <section className="eb-section">
          <h2 className="eb-section-title">What changed</h2>
          <ul className="eb-changes">
            {s["3_what_changed"].map((change) => (
              <li key={change.id} className={`eb-change eb-change-${change.materiality}`}>
                <span className="eb-change-summary">{change.summary}</span>
                {change.opportunity_title && (
                  <span className="eb-change-context">{change.opportunity_title}</span>
                )}
                <span className="eb-change-badge">{change.materiality}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── 4. relationships ────────────────────────────────────── */}
      {s["4_relationship_watchlist"].length > 0 && (
        <section className="eb-section">
          <h2 className="eb-section-title">Relationships needing attention</h2>
          <ul className="eb-relationships">
            {s["4_relationship_watchlist"].map((r) => (
              <li key={r.opportunity_id} className="eb-relationship">
                <div>
                  <p className="eb-rel-title">{r.opportunity_title}</p>
                  <p className="eb-rel-action">{r.recommended_engagement}</p>
                  <p className="eb-rel-benefit">{r.expected_commercial_benefit}</p>
                </div>
                <div className="eb-rel-meta">
                  <span>{r.current_strength}</span>
                  {r.last_engagement_days !== null && (
                    <span>{r.last_engagement_days}d since contact</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── 5. market intelligence ──────────────────────────────── */}
      {s["5_market_intelligence"].length > 0 && (
        <section className="eb-section">
          <h2 className="eb-section-title">Market activity</h2>
          <ul className="eb-markets">
            {s["5_market_intelligence"].map((m, i) => (
              <li key={i} className={m.is_priority ? "eb-market-priority" : ""}>
                <span className="eb-market-name">{m.market ?? m.region ?? "Unknown"}</span>
                <span className="eb-market-count">{m.new_opportunities} new</span>
                <span className="eb-market-relevance">{m.relevance}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── 6. risks ────────────────────────────────────────────── */}
      {s["6_executive_risks"].length > 0 && (
        <section className="eb-section">
          <h2 className="eb-section-title">Risks</h2>
          <ul className="eb-risks">
            {s["6_executive_risks"].map((risk, i) => (
              <li key={i} className={`eb-risk eb-risk-${risk.severity}`}>
                <p className="eb-risk-summary">
                  <span className="eb-risk-severity">{risk.severity}</span> {risk.summary}
                </p>
                <p className="eb-risk-detail">
                  <strong>Evidence:</strong> {risk.evidence}
                </p>
                <p className="eb-risk-detail">
                  <strong>Mitigation:</strong> {risk.mitigation}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── 7. advisor ──────────────────────────────────────────── */}
      <section className="eb-section">
        <h2 className="eb-section-title">Ask the advisor</h2>
        <AdvisorPanel onAnswer={setAdvisorAnswer} answer={advisorAnswer} />
      </section>

      {/* ── footer: position, profile, scan ─────────────────────── */}
      <footer className="eb-footer">
        {briefing.profile.completeness_percent < 100 && (
          <p className="eb-profile-warn">
            Commercial Profile {briefing.profile.completeness_percent}% complete.
            {briefing.profile.incomplete_sections.length > 0 && (
              <> Missing: {briefing.profile.incomplete_sections.join(", ")}. </>
            )}
            Incomplete sections fall back to generic defaults.
          </p>
        )}
        <p className="eb-scan">
          {briefing.scanning.last_scan_days_ago === null
            ? "No scan has been run yet."
            : `Last scan ${briefing.scanning.last_scan_days_ago} days ago.`}
          {briefing.scanning.suggest_scan && (
            <> A new scan would cost about ${briefing.scanning.estimated_cost_usd.toFixed(2)}.</>
          )}
        </p>
        <p className="eb-provenance">
          Generated {now.toLocaleTimeString()} · {briefing.ai_calls_used} AI calls · free
        </p>
      </footer>
    </div>
  );
}

function Count({ value, label, tone }: { value: number; label: string; tone?: string }) {
  if (!value) return null;
  return (
    <div className={`eb-count ${tone ? `eb-count-${tone}` : ""}`}>
      <span className="eb-count-value">{value}</span>
      <span className="eb-count-label">{label}</span>
    </div>
  );
}
