"use client";

/**
 * Landing page — the Executive Briefing.
 *
 * Phase 3.1: the daily entry point is the briefing, not the Control
 * Panel. The Control Panel remains available at /control-panel for
 * pipeline analysis, but it answers "what is the state of the data"
 * rather than "what should I do today", so it is no longer the first
 * thing an executive sees.
 */
import Link from "next/link";
import { useEffect, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import {
  api,
  REGION_COLORS,
  REGION_LABELS,
  STAGE_LABELS,
  VERTICAL_COLORS,
  VERTICAL_LABELS,
  type Breakdown,
  type ControlPanelSummary,
  type Interaction,
  type Opportunity,
  type RegionKey,
  type Vertical,
} from "@/lib/api";
import PageHeader from "./components/PageHeader";
import StatCard from "./components/StatCard";
import ScoreBadge from "./components/ScoreBadge";
import OnboardingHint from "./components/OnboardingHint";
import { computeActNowScore } from "@/lib/scoring";
import { formatCompactCurrency } from "@/lib/format";

export default function ControlPanel() {
  const [summary, setSummary] = useState<ControlPanelSummary | null>(null);
  const [priorityAll, setPriorityAll] = useState<Opportunity[]>([]);
  const [latest, setLatest] = useState<Opportunity[]>([]);
  const [tasks, setTasks] = useState<Interaction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  function load() {
    return Promise.all([
      api.controlPanelSummary(),
      api.opportunities({ priorityOnly: true }),
      api.opportunities({ sort: "recent", daysBack: 7 }),
      api.tasks(),
    ])
      .then(([s, p, l, t]) => {
        setSummary(s);
        setPriorityAll(p);
        setLatest(l.slice(0, 8));
        setTasks(t.slice(0, 8));
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);

  async function runGlobalScan() {
    setTriggering(true);
    try {
      await api.triggerGlobalScan();
      await load();
    } finally {
      setTriggering(false);
    }
  }

  async function toggleTaskDone(id: string) {
    await api.markTaskComplete(id, true);
    load();
  }

  const priority = priorityAll.slice(0, 6);

  const topThisWeek = latest
    .slice()
    .sort((a, b) => computeActNowScore(b) - computeActNowScore(a))
    .slice(0, 3);

  const staleOpportunities = priorityAll
    .filter((o) => o.stage !== "won" && o.stage !== "lost")
    .filter((o) => {
      const days = Math.floor((Date.now() - new Date(o.updated_at).getTime()) / (1000 * 60 * 60 * 24));
      return days >= 14;
    })
    .sort((a, b) => new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime())
    .slice(0, 5);

  type WhitespaceSignal = { name: string; avgValue: number; count: number };
  function computeWhitespace(byKey: Record<string, { count: number; value: number }>, labels: Record<string, string>): WhitespaceSignal[] {
    const rows = Object.entries(byKey)
      .filter(([, b]) => b.count > 0)
      .map(([key, b]) => ({ name: labels[key] ?? key, avgValue: b.value / b.count, count: b.count }));
    if (rows.length < 2) return [];
    const avgOfAvgValue = rows.reduce((s, r) => s + r.avgValue, 0) / rows.length;
    const avgCount = rows.reduce((s, r) => s + r.count, 0) / rows.length;
    return rows
      .filter((r) => r.avgValue > avgOfAvgValue && r.count < avgCount)
      .sort((a, b) => b.avgValue - a.avgValue);
  }
  const whitespaceVerticals = summary ? computeWhitespace(summary.by_vertical, VERTICAL_LABELS) : [];
  const whitespaceRegions = summary ? computeWhitespace(summary.by_region, REGION_LABELS) : [];
  const whitespaceSignals = [...whitespaceVerticals, ...whitespaceRegions].slice(0, 4);

  const verticalPieData = summary
    ? (Object.keys(VERTICAL_LABELS) as Vertical[])
        .map((v) => ({ key: v, name: VERTICAL_LABELS[v], value: summary.by_vertical[v]?.value ?? 0, count: summary.by_vertical[v]?.count ?? 0 }))
        .filter((d) => d.value > 0)
    : [];
  const regionPieData = summary
    ? (Object.keys(REGION_LABELS) as RegionKey[])
        .map((r) => ({ key: r, name: REGION_LABELS[r], value: summary.by_region[r]?.value ?? 0, count: summary.by_region[r]?.count ?? 0 }))
        .filter((d) => d.value > 0)
    : [];

  return (
    <div>

      <PageHeader
        eyebrow="Control Panel"
        title="Every opportunity in global sport"
        description="ATLAS sweeps the global sport ecosystem every 7 days across all five VECTA verticals, scores what it finds, and routes it into this pipeline."
        actions={
          <button onClick={runGlobalScan} disabled={triggering} className="btn btn-primary">
            {triggering ? "Starting sweep…" : "Run Global Scan"}
          </button>
        }
      />

      <OnboardingHint id="control-panel">
        <strong>Top 3 this week</strong> combines score and deadline urgency to tell you what to look at first.
        <strong> Needs attention</strong> flags Priority opportunities that haven&apos;t moved stage in 14+ days, so
        nothing valuable quietly goes cold.
      </OnboardingHint>

      {error && (
        <div className="panel p-5 mb-6" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Can&apos;t reach the API
          </p>
          <p className="text-sm text-muted mb-3">
            {process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"} — {error}
          </p>
          <button onClick={load} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
        <StatCard label="Priority opportunities" value={summary ? String(summary.priority_count) : "—"} tone="accent" />
        <StatCard
          label="Pipeline value"
          value={summary ? formatCompactCurrency(summary.pipeline_value) : "—"}
          hint={summary ? `$${Math.round(summary.pipeline_value).toLocaleString()}` : undefined}
        />
        <StatCard
          label="Weighted pipeline"
          value={summary ? formatCompactCurrency(summary.weighted_pipeline_value) : "—"}
          hint="Value × close probability"
        />
        <StatCard label="Deadlines (14 days)" value={summary ? String(summary.upcoming_deadlines_14d) : "—"} />
        <StatCard label="New contacts (7 days)" value={summary ? String(summary.new_contacts_7d) : "—"} />
      </div>

      {topThisWeek.length > 0 && (
        <div
          className="panel p-5 mb-6"
          style={{ borderColor: "var(--accent)", borderWidth: "1.5px", background: "var(--accent-wash)" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="h-2 w-2 rounded-full" style={{ background: "var(--accent)" }} aria-hidden="true" />
            <h2 className="text-base font-bold text-main">Top 3 this week</h2>
          </div>
          <p className="text-xs text-muted mb-3">Score + deadline urgency, from what&apos;s been discovered in the last 7 days — what to look at first.</p>
          <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
            {topThisWeek.map((o) => (
              <OpportunityListItem key={o.id} opportunity={o} showSubmitted />
            ))}
          </ul>
        </div>
      )}

      {summary && (verticalPieData.length > 0 || regionPieData.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <PieCard title="Pipeline value by vertical" data={verticalPieData} colorFor={(key) => VERTICAL_COLORS[key as Vertical]} />
          <PieCard title="Pipeline value by region" data={regionPieData} colorFor={(key) => REGION_COLORS[key as RegionKey]} />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-3">By vertical</h2>
          <div className="space-y-3">
            {summary &&
              (Object.keys(VERTICAL_LABELS) as Vertical[]).map((v) => (
                <BreakdownRow key={v} label={VERTICAL_LABELS[v]} color={VERTICAL_COLORS[v]} breakdown={summary.by_vertical[v]} />
              ))}
          </div>
        </div>
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-3">By region</h2>
          <div className="space-y-3">
            {summary &&
              (Object.keys(REGION_LABELS) as RegionKey[]).map((r) => (
                <BreakdownRow key={r} label={REGION_LABELS[r]} color={REGION_COLORS[r]} breakdown={summary.by_region[r]} />
              ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-1">Needs attention</h2>
          <p className="text-xs text-muted mb-3">Priority opportunities that haven&apos;t moved stage in 14+ days.</p>
          {staleOpportunities.length === 0 ? (
            <p className="text-sm text-muted">Nothing stale — every Priority opportunity has moved recently.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {staleOpportunities.map((o) => {
                const daysStale = Math.floor((Date.now() - new Date(o.updated_at).getTime()) / (1000 * 60 * 60 * 24));
                return (
                  <li key={o.id}>
                    <Link
                      href={`/opportunities/${o.id}`}
                      className="flex items-center justify-between gap-4 py-2.5 first:pt-0 last:pb-0 hover:bg-[var(--panel-raised)] -mx-2 px-2 rounded-lg transition-colors"
                    >
                      <div className="min-w-0">
                        <p className="text-sm text-main font-medium truncate">{o.title}</p>
                        <p className="text-xs mt-0.5" style={{ color: "var(--warning)" }}>
                          {STAGE_LABELS[o.stage] ?? o.stage} · unchanged for {daysStale} days
                        </p>
                      </div>
                      <ScoreBadge score={o.alignment_score} size="sm" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-1">Whitespace signals</h2>
          <p className="text-xs text-muted mb-3">
            Verticals/regions with above-average deal size but below-average volume — likely under-tapped
            relative to the value that&apos;s there.
          </p>
          {whitespaceSignals.length === 0 ? (
            <p className="text-sm text-muted">No clear whitespace signal yet — need more pipeline spread to compare.</p>
          ) : (
            <ul className="space-y-2.5">
              {whitespaceSignals.map((w) => (
                <li key={w.name} className="flex items-center justify-between text-sm">
                  <span className="text-main">{w.name}</span>
                  <span className="text-muted text-xs">
                    {w.count} opp{w.count === 1 ? "" : "s"} · avg ${Math.round(w.avgValue).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-main">Priority opportunities</h2>
            <Link href="/opportunities" className="btn-ghost text-xs">
              View full pipeline →
            </Link>
          </div>
          {priority.length === 0 ? (
            <p className="text-sm text-muted">No Priority opportunities yet — check back after the next sweep.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {priority.map((o) => (
                <OpportunityListItem key={o.id} opportunity={o} />
              ))}
            </ul>
          )}
        </div>

        <div className="panel p-5">
          <div className="flex items-center justify-between mb-1">
            <h2 className="text-sm font-semibold text-main">Latest opportunities</h2>
            <Link href="/opportunities" className="btn-ghost text-xs">
              View full pipeline →
            </Link>
          </div>
          <p className="text-xs text-muted mb-3">Discovered in the last 7 days, newest first.</p>
          {latest.length === 0 ? (
            <p className="text-sm text-muted">Nothing discovered in the last 7 days yet.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {latest.map((o) => (
                <OpportunityListItem key={o.id} opportunity={o} showSubmitted />
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="panel p-5 mt-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-main">Follow-ups due</h2>
          <Link href="/relationships" className="btn-ghost text-xs">
            View directory →
          </Link>
        </div>
        {tasks.length === 0 ? (
          <p className="text-sm text-muted">Nothing outstanding — logged tasks with a due date will show here.</p>
        ) : (
          <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
            {tasks.map((t) => {
              const overdue = t.due_at ? new Date(t.due_at).getTime() < Date.now() : false;
              return (
                <li key={t.id} className="flex items-center justify-between gap-4 py-2.5 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="text-sm text-main font-medium truncate">{t.content}</p>
                    <p className="text-xs mt-0.5" style={{ color: overdue ? "var(--danger)" : "var(--text-muted)" }}>
                      {t.contact_name ? `${t.contact_name} · ` : ""}
                      {t.due_at
                        ? `due ${new Date(t.due_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}${overdue ? " · overdue" : ""}`
                        : ""}
                    </p>
                  </div>
                  <button onClick={() => toggleTaskDone(t.id)} className="btn btn-secondary text-xs shrink-0">
                    Mark done
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

type PieDatum = { key: string; name: string; value: number; count: number };

function PieCard({ title, data, colorFor }: { title: string; data: PieDatum[]; colorFor: (key: string) => string }) {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  // Enforce a minimum visual slice so every category is a distinguishable
  // wedge in the ring — a category with real but small value (e.g. $43m
  // next to a $16.7bn dominant one) would otherwise round to an invisible
  // sliver. The legend below still shows the true value and percentage;
  // this only affects the rendered wedge size, not the numbers shown.
  const MIN_SHARE = 0.045;
  const floor = total * MIN_SHARE;
  const renderData = data.map((d) => ({ ...d, renderValue: total > 0 ? Math.max(d.value, floor) : 1 }));

  return (
    <div className="panel p-5">
      <h2 className="text-sm font-semibold text-main mb-1">{title}</h2>
      <p className="text-xs text-muted mb-3">Share of total pipeline value.</p>
      {data.length === 0 ? (
        <p className="text-sm text-muted">No data yet.</p>
      ) : (
        <>
          <div style={{ width: "100%", height: 190 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie data={renderData} dataKey="renderValue" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
                  {renderData.map((d) => (
                    <Cell key={d.key} fill={colorFor(d.key)} stroke="var(--panel)" strokeWidth={2} />
                  ))}
                </Pie>
                <Tooltip content={<PieTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* A real legend, not the recharts built-in one — every value is
              printed directly so nothing depends on hovering, which doesn't
              work reliably on touch screens. True value/percentage, not the
              visually-floored render value above. */}
          <ul className="space-y-1.5 mt-2">
            {data
              .slice()
              .sort((a, b) => b.value - a.value)
              .map((d) => {
                const rawPct = total > 0 ? (d.value / total) * 100 : 0;
                const pctLabel = rawPct > 0 && rawPct < 1 ? "<1%" : `${Math.round(rawPct)}%`;
                return (
                  <li key={d.key} className="flex items-center justify-between gap-2 text-xs">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: colorFor(d.key) }} aria-hidden="true" />
                      <span className="text-main truncate">{d.name}</span>
                    </span>
                    <span className="text-muted shrink-0">
                      {pctLabel} · ${Math.round(d.value).toLocaleString()}
                    </span>
                  </li>
                );
              })}
          </ul>
        </>
      )}
    </div>
  );
}

function PieTooltip({ active, payload }: { active?: boolean; payload?: { payload: { name: string; value: number; count: number } }[] }) {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0].payload;
  return (
    <div className="panel-raised px-3 py-2" style={{ border: "1px solid var(--border-strong)" }}>
      <p className="text-xs font-semibold text-main">{d.name}</p>
      <p className="text-xs text-muted">
        {d.count} opp{d.count === 1 ? "" : "s"} · ${Math.round(d.value).toLocaleString()}
      </p>
    </div>
  );
}

function BreakdownRow({ label, color, breakdown }: { label: string; color: string; breakdown?: Breakdown }) {
  const count = breakdown?.count ?? 0;
  const value = breakdown?.value ?? 0;
  const avgScore = breakdown?.avg_score ?? null;
  const scoreColor = avgScore == null ? "var(--text-muted)" : avgScore >= 70 ? "var(--success)" : avgScore >= 40 ? "var(--warning)" : "var(--danger)";

  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: color }} aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm text-main font-medium truncate">{label}</p>
          <p className="text-xs text-muted">{count} opp{count === 1 ? "" : "s"}</p>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span
          className="text-xs font-semibold rounded-md px-2 py-1"
          style={{ background: `${color}22`, color }}
        >
          ${Math.round(value).toLocaleString()}
        </span>
        <span
          className="text-xs font-semibold rounded-md px-2 py-1 min-w-[3rem] text-center"
          style={{ background: `${scoreColor}22`, color: scoreColor }}
        >
          {avgScore != null ? `avg ${avgScore}` : "—"}
        </span>
      </div>
    </div>
  );
}

function OpportunityListItem({ opportunity: o, showSubmitted = false }: { opportunity: Opportunity; showSubmitted?: boolean }) {
  const submitted = showSubmitted
    ? new Date(o.created_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : null;
  return (
    <li>
      <Link
        href={`/opportunities/${o.id}`}
        className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0 hover:bg-[var(--panel-raised)] -mx-2 px-2 rounded-lg transition-colors"
      >
        <div className="min-w-0">
          <p className="text-sm text-main font-medium truncate">{o.title}</p>
          <p className="text-xs text-muted mt-0.5">
            {o.vertical ? VERTICAL_LABELS[o.vertical] : "Unclassified"}
            {o.region ? ` · ${REGION_LABELS[o.region]}` : ""}
            {submitted ? ` · submitted ${submitted}` : o.deadline ? ` · deadline ${o.deadline}` : ""}
          </p>
        </div>
        <ScoreBadge score={o.alignment_score} size="sm" />
      </Link>
    </li>
  );
}
