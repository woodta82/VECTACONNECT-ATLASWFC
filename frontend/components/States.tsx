"use client";

import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { dateTime, label } from "@/lib/format";

export function Loading({ what = "data", rows = 4 }: { what?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">Loading {what}…</span>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ marginBottom: 10, width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state">
      <strong>{title}</strong>
      {children}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  if (error.status === 401) {
    return (
      <div className="state state-error" role="alert">
        <strong>Signed out</strong>
        Your session has ended. Sign in again to continue.
      </div>
    );
  }
  return (
    <div className="state state-error" role="alert">
      <strong>Could not load this view</strong>
      {error.message}
      {error.requestId && <div className="small" style={{ marginTop: 6 }}>Reference: {error.requestId}</div>}
      {onRetry && (
        <div style={{ marginTop: 12 }}>
          <button className="btn" onClick={onRetry} type="button">Try again</button>
        </div>
      )}
    </div>
  );
}

export function StaleBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="notice" role="status">
      Showing the last data loaded; the latest refresh failed.{" "}
      <button className="btn btn-ghost small" type="button" onClick={onRetry}>Retry</button>
    </div>
  );
}

export function NotConnected({ dataset, sourceOfTruth }: { dataset: string; sourceOfTruth?: string }) {
  return (
    <div className="state">
      <strong>Not connected</strong>
      No {label(dataset).toLowerCase()} data has been loaded{sourceOfTruth ? ` from ${sourceOfTruth}` : ""}. This is not
      zero performance. Import a file under Data Sources and Imports to populate this view.
    </div>
  );
}

export type Insight = {
  scope: string;
  period: string | null;
  generated_at: string;
  sources: { dataset: string; status: "loaded" | "stale" | "not_connected"; last_success_at: string | null;
             source_of_truth?: string; refresh?: string }[];
  gaps: string[];
};

const STATUS_BADGE: Record<string, string> = { loaded: "b-good", stale: "b-warn", not_connected: "b-none" };

/** Every insight states its scope, period, last refresh, sources and gaps. */
export function InsightMeta({ insight }: { insight: Insight | null | undefined }) {
  if (!insight) return null;
  const notConnected = insight.sources.filter((s) => s.status === "not_connected").length;
  // Progressive disclosure: provenance detail is one click away; data gaps always stay visible.
  return (
    <div className="meta" aria-label="Data scope and provenance">
      <details className="tech-note">
        <summary>
          Data scope and provenance · {insight.sources.length} dataset(s){notConnected ? `, ${notConnected} not connected` : ""} · generated {dateTime(insight.generated_at)}
        </summary>
        <div className="meta-detail">
          <span><b>Scope:</b> {insight.scope}</span>
          <span><b>Period:</b> {insight.period ?? "All loaded data"}</span>
          {insight.sources.map((s) => (
            <span key={s.dataset}>
              <b>{label(s.dataset)}:</b>{" "}
              <span className={`badge ${STATUS_BADGE[s.status] ?? "b-none"}`}>{s.status === "not_connected" ? "Not connected" : label(s.status)}</span>
              {s.last_success_at ? ` refreshed ${dateTime(s.last_success_at)}` : ""}
              {s.source_of_truth ? <span className="small"> · source: {s.source_of_truth}</span> : null}
              {s.refresh ? <span className="small"> · {s.refresh}</span> : null}
            </span>
          ))}
        </div>
      </details>
      {insight.gaps.length > 0 && (
        <div style={{ flexBasis: "100%" }}>
          <b>Gaps:</b>
          <ul>{insight.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        </div>
      )}
    </div>
  );
}

const TONE: Record<string, string> = {
  pass: "b-good", supported: "b-good", ready: "b-good", approved_for_pursuit: "b-good", ready_for_review: "b-info", qualified_opportunity: "b-good",
  won: "b-good", resolved: "b-good", covered: "b-good", feasible: "b-good", verified: "b-good", succeeded: "b-good", healthy: "b-good", configured: "b-info",
  unknown: "b-none", incomplete: "b-warn", invalidated: "b-warn", contradictory: "b-warn", partially_read: "b-warn", info: "b-info", "date unknown": "b-warn", review_required: "b-warn", unverified: "b-warn", unverified_lead: "b-warn", gap: "b-info",
  market_signal: "b-info", research_item: "b-none", insufficient_evidence: "b-none", unresolved: "b-warn", open: "b-warn", queued: "b-none",
  fail: "b-bad", blocked: "b-bad", contradicted: "b-bad", expired: "b-bad", lost: "b-bad", risk_alert: "b-bad", infeasible: "b-bad",
  cancelled: "b-bad", dead: "b-bad", failed: "b-bad", not_connected: "b-none", degraded: "b-warn", critical: "b-bad", high: "b-bad", medium: "b-warn", low: "b-none",
  // network development: fit results, item types and statuses
  strong: "b-good", partial: "b-info", weak: "b-warn", coverage_gap: "b-warn", partner: "b-info", referral: "b-info",
  acquisition_research: "b-none", assessing: "b-info", parked: "b-none", closed: "b-none",
  // discovery, review and imports
  completed: "b-good", running: "b-info", results: "b-good", no_relevant_results: "b-none", no_sources: "b-none",
  partial_coverage: "b-warn", source_failure: "b-bad", extracted: "b-good", manual: "b-info",
  budget_refused: "b-warn", proposed: "b-warn", confirmed: "b-good", corrected: "b-info", rejected: "b-bad", unsupported: "b-bad",
  not_applicable: "b-none", dismissed: "b-none", merged: "b-info", kept_separate: "b-none", scope: "b-good", issuer_only: "b-warn",
  worldwide: "b-info", revised: "b-info", awarded: "b-none", ok: "b-good", insufficient_data: "b-none", loaded: "b-good", stale: "b-warn",
  skipped: "b-none", pending: "b-none", withdrawn: "b-none", superseded: "b-none", acknowledged: "b-info", owner_changed: "b-info",
  internal_record: "b-good", committed: "b-good", reversed: "b-none", validated: "b-info", scored: "b-info",
  approved: "b-good", true: "b-good", false: "b-none", no_claims: "b-none",
  excluded: "b-bad", passenger: "b-bad", cargo: "b-good", mixed: "b-warn", unclear: "b-warn", historical: "b-none",
  not_freight: "b-bad", conflicting: "b-warn", freight_candidate: "b-warn", announced: "b-warn", historical_record: "b-none",
};

export function Badge({ value }: { value: string | null | undefined }) {
  const v = value ?? "unknown";
  return <span className={`badge ${TONE[v] ?? "b-none"}`}>{v === "not_connected" ? "Not connected" : label(v)}</span>;
}

export function Stat({ label: l, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-label">{l}</div>
      <div className="stat-value">{value}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  );
}

/** Horizontally scrollable, keyboard-focusable table container. */
export function TableWrap({ label: l, children }: { label: string; children: ReactNode }) {
  return (
    <div className="table-wrap" role="region" aria-label={l} tabIndex={0}>
      {children}
    </div>
  );
}
