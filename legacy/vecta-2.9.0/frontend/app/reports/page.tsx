"use client";

import { useEffect, useState } from "react";
import { api, REGION_LABELS, VERTICAL_LABELS, type HeatmapResponse, type ReportSummary } from "@/lib/api";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import { formatCompactCurrency, formatCompactNumber } from "@/lib/format";

export default function ReportsPage() {
  const [report, setReport] = useState<ReportSummary | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    Promise.all([api.reportSummary(), api.reportHeatmap()])
      .then(([r, h]) => {
        setReport(r);
        setHeatmap(h);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load reports"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      <PageHeader
        eyebrow="Reports"
        title="Pipeline performance"
        description="Win rate, pipeline value and performance by vertical and region — VECTA Sports Commercial Division."
        actions={
          <button onClick={() => window.print()} className="btn btn-primary print:hidden" disabled={!report}>
            Export / Print PDF
          </button>
        }
      />

      {error && (
        <div className="panel p-5 mb-5" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Couldn&apos;t load reports
          </p>
          <p className="text-sm text-muted mb-3">{error}</p>
          <button onClick={load} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      {!error && loading && <p className="text-sm text-muted">Loading…</p>}

      {report && (
        <div className="space-y-5">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Total opportunities" value={String(report.total_opportunities)} />
            <StatCard label="Won" value={String(report.won)} />
            <StatCard label="Win rate" value={report.win_rate != null ? `${Math.round(report.win_rate * 100)}%` : "—"} />
            <StatCard
              label="Pipeline value"
              value={formatCompactCurrency(report.pipeline_value)}
              hint={`$${Math.round(report.pipeline_value).toLocaleString()}`}
            />
          </div>

          <div className="panel p-5">
            <h2 className="text-sm font-semibold text-main mb-1">Weighted pipeline value</h2>
            <p className="text-xs text-muted mb-3">
              Raw value × close probability by stage — a more realistic forecast than the raw total above.
              Discovered 10% · Qualified 25% · Engaged 45% · Proposal 65%. Starting estimates; recalibrate
              once there&apos;s enough Won/Lost history.
            </p>
            <p className="text-3xl font-semibold font-display" style={{ color: "var(--accent-text)" }}>
              {formatCompactCurrency(report.weighted_pipeline_value)}
            </p>
            <p className="text-xs text-muted mt-1">
              ${Math.round(report.weighted_pipeline_value).toLocaleString()} exact
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div className="panel p-5 overflow-x-auto">
              <h2 className="text-sm font-semibold text-main mb-3">Performance by vertical</h2>
              <table className="data-table">
                <caption className="sr-only">Performance by vertical</caption>
                <thead>
                  <tr>
                    <th scope="col">Vertical</th>
                    <th scope="col">Count</th>
                    <th scope="col">Value</th>
                    <th scope="col">Avg. score</th>
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(VERTICAL_LABELS) as (keyof typeof VERTICAL_LABELS)[]).map((v) => {
                    const b = report.by_vertical[v];
                    return (
                      <tr key={v}>
                        <td className="text-main">{VERTICAL_LABELS[v]}</td>
                        <td className="text-muted">{b?.count ?? 0}</td>
                        <td className="text-muted">${Math.round(b?.value ?? 0).toLocaleString()}</td>
                        <td className="text-muted">{b?.avg_score ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="panel p-5 overflow-x-auto">
              <h2 className="text-sm font-semibold text-main mb-3">Performance by region</h2>
              <table className="data-table">
                <caption className="sr-only">Performance by region</caption>
                <thead>
                  <tr>
                    <th scope="col">Region</th>
                    <th scope="col">Count</th>
                    <th scope="col">Value</th>
                    <th scope="col">Avg. score</th>
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(REGION_LABELS) as (keyof typeof REGION_LABELS)[]).map((r) => {
                    const b = report.by_region[r];
                    return (
                      <tr key={r}>
                        <td className="text-main">{REGION_LABELS[r]}</td>
                        <td className="text-muted">{b?.count ?? 0}</td>
                        <td className="text-muted">${Math.round(b?.value ?? 0).toLocaleString()}</td>
                        <td className="text-muted">{b?.avg_score ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {heatmap && (
            <div className="panel p-5 overflow-x-auto">
              <h2 className="text-sm font-semibold text-main mb-1">Region × vertical heatmap</h2>
              <p className="text-xs text-muted mb-4">
                Where value and quality overlap. Colour = average score (green 70+, amber 40–69, red below 40,
                grey if empty). Each cell shows count and pipeline value.
              </p>
              <table className="data-table" style={{ minWidth: "640px" }}>
                <caption className="sr-only">Region by vertical performance heatmap</caption>
                <thead>
                  <tr>
                    <th scope="col">Region</th>
                    {(Object.keys(VERTICAL_LABELS) as (keyof typeof VERTICAL_LABELS)[]).map((v) => (
                      <th key={v} scope="col">{VERTICAL_LABELS[v].replace("VECTA ", "")}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(Object.keys(REGION_LABELS) as (keyof typeof REGION_LABELS)[]).map((r) => (
                    <tr key={r}>
                      <td className="text-main font-medium">{REGION_LABELS[r]}</td>
                      {(Object.keys(VERTICAL_LABELS) as (keyof typeof VERTICAL_LABELS)[]).map((v) => {
                        const cell = heatmap.cells[r]?.[v];
                        const score = cell?.avg_score ?? null;
                        const color = score == null ? "var(--text-muted)" : score >= 70 ? "var(--success)" : score >= 40 ? "var(--warning)" : "var(--danger)";
                        return (
                          <td key={v}>
                            {cell && cell.count > 0 ? (
                              <span
                                className="inline-block rounded-md px-2 py-1 text-xs font-medium whitespace-nowrap"
                                style={{ background: `${color}22`, color }}
                              >
                                {cell.count} · ${formatCompactNumber(cell.value)}
                              </span>
                            ) : (
                              <span className="text-xs text-muted">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="panel p-5">
            <h2 className="text-sm font-semibold text-main mb-1">Commercial ROI on the scanning spend</h2>
            <p className="text-xs text-muted mb-4">
              Estimated, not a real Anthropic invoice figure — calibrate against a few weeks of
              actual billing (see docs/ENVIRONMENT.md — ESTIMATED_COST_PER_SCAN_USD).
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Scans run" value={String(report.total_scans_run)} />
              <StatCard label="Est. scan spend" value={`$${report.estimated_scan_cost_usd.toLocaleString()}`} />
              <StatCard
                label="Cost / priority find"
                value={report.cost_per_priority_opportunity_usd != null ? `$${report.cost_per_priority_opportunity_usd}` : "—"}
                tone="accent"
              />
              <StatCard
                label="Pipeline : cost ratio"
                value={report.pipeline_to_cost_ratio != null ? `${report.pipeline_to_cost_ratio}×` : "—"}
                tone="accent"
              />
            </div>
          </div>

          {Object.keys(report.lost_reasons).length > 0 && (
            <div className="panel p-5">
              <h2 className="text-sm font-semibold text-main mb-1">Why deals are lost</h2>
              <p className="text-xs text-muted mb-3">Captured when an opportunity is moved to Lost.</p>
              <div className="space-y-2">
                {Object.entries(report.lost_reasons)
                  .sort((a, b) => b[1] - a[1])
                  .map(([reason, count]) => {
                    const total = Object.values(report.lost_reasons).reduce((sum, n) => sum + n, 0);
                    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
                    return (
                      <div key={reason}>
                        <div className="flex items-center justify-between text-sm mb-1">
                          <span className="text-main">{reason}</span>
                          <span className="text-muted text-xs">{count} · {pct}%</span>
                        </div>
                        <div className="h-1.5 rounded-full" style={{ background: "var(--panel-raised)" }}>
                          <div className="h-1.5 rounded-full" style={{ width: `${pct}%`, background: "var(--danger)" }} />
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
