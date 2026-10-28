"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  REGION_LABELS,
  STAGE_LABELS,
  STAGE_ORDER,
  VERTICAL_LABELS,
  type Opportunity,
  type RegionKey,
  type Stage,
  type Vertical,
} from "@/lib/api";
import PageHeader from "../components/PageHeader";
import ScoreBadge from "../components/ScoreBadge";
import OnboardingHint from "../components/OnboardingHint";
import { useToast } from "../components/ToastProvider";
import { downloadCsv } from "@/lib/csv";
import { computeActNowScore } from "@/lib/scoring";

type SavedView = {
  name: string;
  q: string;
  vertical: Vertical | "";
  region: RegionKey | "";
  priorityOnly: boolean;
  minScore: number;
  minValue: number;
  sortBy: string;
};

const SAVED_VIEWS_KEY = "atlas-saved-views-opportunities";

export default function OpportunitiesPage() {
  const { showUndo } = useToast();
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [view, setView] = useState<"list" | "kanban">("list");
  const [q, setQ] = useState("");
  const [vertical, setVertical] = useState<Vertical | "">("");
  const [region, setRegion] = useState<RegionKey | "">("");
  const [priorityOnly, setPriorityOnly] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [minValue, setMinValue] = useState(0);
  const [sortBy, setSortBy] = useState<
    "score_desc" | "score_asc" | "value_desc" | "value_asc" | "deadline_asc" | "act_now"
  >("score_desc");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkStage, setBulkStage] = useState<Stage>("qualified");
  const [bulkApplying, setBulkApplying] = useState(false);
  const [savedViews, setSavedViews] = useState<SavedView[]>([]);
  const [saveViewName, setSaveViewName] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(SAVED_VIEWS_KEY);
      if (raw) setSavedViews(JSON.parse(raw));
    } catch {
      // corrupt or unavailable localStorage — just start with no saved views
    }
  }, []);

  function persistViews(views: SavedView[]) {
    setSavedViews(views);
    try {
      localStorage.setItem(SAVED_VIEWS_KEY, JSON.stringify(views));
    } catch {
      // localStorage unavailable — the view still applies this session, just won't persist
    }
  }

  function saveCurrentView() {
    if (!saveViewName.trim()) return;
    const view: SavedView = { name: saveViewName.trim(), q, vertical, region, priorityOnly, minScore, minValue, sortBy };
    persistViews([...savedViews.filter((v) => v.name !== view.name), view]);
    setSaveViewName("");
  }

  function applyView(view: SavedView) {
    setQ(view.q);
    setVertical(view.vertical);
    setRegion(view.region);
    setPriorityOnly(view.priorityOnly);
    setMinScore(view.minScore);
    setMinValue(view.minValue);
    setSortBy(view.sortBy as typeof sortBy);
  }

  function deleteView(name: string) {
    persistViews(savedViews.filter((v) => v.name !== name));
  }

  function load() {
    return api
      .opportunities({ q: q || undefined, vertical: vertical || undefined, region: region || undefined, priorityOnly })
      .then(setOpportunities)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 8000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, vertical, region, priorityOnly]);

  async function changeStage(id: string, stage: Stage) {
    const previous = opportunities.find((o) => o.id === id);
    await api.updateStage(id, stage);
    load();
    if (previous && previous.stage !== stage) {
      showUndo(`Moved to ${STAGE_LABELS[stage]}`, async () => {
        await api.updateStage(id, previous.stage);
        load();
      });
    }
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll(ids: string[]) {
    setSelected((prev) => (prev.size === ids.length ? new Set() : new Set(ids)));
  }

  async function applyBulkStage() {
    if (selected.size === 0) return;
    setBulkApplying(true);
    const ids = Array.from(selected);
    const previousStages = new Map(ids.map((id) => [id, opportunities.find((o) => o.id === id)?.stage]));
    try {
      await api.bulkUpdateStage(ids, bulkStage);
      setSelected(new Set());
      load();
      showUndo(`Moved ${ids.length} to ${STAGE_LABELS[bulkStage]}`, async () => {
        await Promise.all(
          ids.map((id) => {
            const prevStage = previousStages.get(id);
            return prevStage ? api.updateStage(id, prevStage) : Promise.resolve();
          })
        );
        load();
      });
    } finally {
      setBulkApplying(false);
    }
  }

  const visibleOpportunities = opportunities
    .filter((o) => o.alignment_score >= minScore)
    .filter((o) => (o.value_estimate ?? 0) >= minValue)
    .sort((a, b) => {
      switch (sortBy) {
        case "score_asc":
          return a.alignment_score - b.alignment_score;
        case "value_desc":
          return (b.value_estimate ?? 0) - (a.value_estimate ?? 0);
        case "value_asc":
          return (a.value_estimate ?? 0) - (b.value_estimate ?? 0);
        case "deadline_asc":
          if (!a.deadline) return 1;
          if (!b.deadline) return -1;
          return a.deadline.localeCompare(b.deadline);
        case "act_now":
          return computeActNowScore(b) - computeActNowScore(a);
        default:
          return b.alignment_score - a.alignment_score;
      }
    });

  function exportCsv() {
    downloadCsv(
      `atlas-opportunities-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Title", "Vertical", "Region", "Market", "Organisation", "Value (GBP)", "Deadline", "Stage", "Alignment Score", "Priority"],
      visibleOpportunities.map((o) => [
        o.title,
        o.vertical ? VERTICAL_LABELS[o.vertical] : "",
        o.region ? REGION_LABELS[o.region] : "",
        o.market ?? "",
        o.organisation_name ?? "",
        o.value_estimate ?? "",
        o.deadline ?? "",
        STAGE_LABELS[o.stage],
        o.alignment_score,
        o.priority ? "Yes" : "No",
      ])
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Opportunities"
        title="Full pipeline"
        actions={
          <>
            <button onClick={exportCsv} disabled={visibleOpportunities.length === 0} className="btn btn-secondary">
              Export CSV
            </button>
            <div className="flex rounded-lg overflow-hidden border" style={{ borderColor: "var(--border-strong)" }} role="group" aria-label="View">
              {(["list", "kanban"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  aria-pressed={view === v}
                  className="px-3 py-2 text-xs font-medium capitalize"
                  style={{ background: view === v ? "var(--accent)" : "transparent", color: view === v ? "#fff" : "var(--text-muted)" }}
                >
                  {v}
                </button>
              ))}
            </div>
          </>
        }
      />

      <OnboardingHint id="opportunities">
        Filter, then <strong>save this view</strong> below to jump back to it in one tap next time. Sort by
        &ldquo;Act now&rdquo; to combine score and deadline urgency into one ranking.
      </OnboardingHint>

      {savedViews.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <span className="field-label">Saved views:</span>
          {savedViews.map((v) => (
            <span key={v.name} className="pill flex items-center gap-1.5">
              <button onClick={() => applyView(v)} className="text-xs">
                {v.name}
              </button>
              <button onClick={() => deleteView(v.name)} aria-label={`Delete saved view ${v.name}`} className="text-xs opacity-60 hover:opacity-100">
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <label htmlFor="save-view-name" className="sr-only">Save current filters as a view</label>
        <input
          id="save-view-name"
          value={saveViewName}
          onChange={(e) => setSaveViewName(e.target.value)}
          placeholder="Name this view to save it…"
          className="input"
          style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem", maxWidth: "220px" }}
          onKeyDown={(e) => e.key === "Enter" && saveCurrentView()}
        />
        <button onClick={saveCurrentView} disabled={!saveViewName.trim()} className="btn btn-secondary text-xs">
          Save this view
        </button>
      </div>

      <div className="panel p-3 mb-4 flex flex-wrap items-end gap-3">
        <div className="field flex-1 min-w-[200px]">
          <label htmlFor="opp-search" className="field-label">Search</label>
          <input
            id="opp-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Title or summary…"
            className="input"
          />
        </div>
        <div className="field">
          <label htmlFor="opp-vertical" className="field-label">Vertical</label>
          <select id="opp-vertical" value={vertical} onChange={(e) => setVertical(e.target.value as Vertical | "")} className="input">
            <option value="">All verticals</option>
            {(Object.keys(VERTICAL_LABELS) as Vertical[]).map((v) => (
              <option key={v} value={v}>{VERTICAL_LABELS[v]}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="opp-region" className="field-label">Region</label>
          <select id="opp-region" value={region} onChange={(e) => setRegion(e.target.value as RegionKey | "")} className="input">
            <option value="">All regions</option>
            {(Object.keys(REGION_LABELS) as RegionKey[]).map((r) => (
              <option key={r} value={r}>{REGION_LABELS[r]}</option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm text-main pb-2.5 cursor-pointer">
          <input
            type="checkbox"
            checked={priorityOnly}
            onChange={(e) => setPriorityOnly(e.target.checked)}
            className="h-4 w-4"
          />
          Priority only (70+)
        </label>
        <div className="field">
          <label htmlFor="opp-min-score" className="field-label">Score</label>
          <select id="opp-min-score" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} className="input">
            <option value={0}>Any score</option>
            <option value={40}>40+</option>
            <option value={70}>70+ (Priority)</option>
            <option value={85}>85+</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="opp-min-value" className="field-label">Value</label>
          <select id="opp-min-value" value={minValue} onChange={(e) => setMinValue(Number(e.target.value))} className="input">
            <option value={0}>Any value</option>
            <option value={50000}>$50k+</option>
            <option value={250000}>$250k+</option>
            <option value={1000000}>$1m+</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="opp-sort" className="field-label">Sort by</label>
          <select id="opp-sort" value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)} className="input">
            <option value="score_desc">Score, high to low</option>
            <option value="score_asc">Score, low to high</option>
            <option value="act_now">Act now (score + urgency)</option>
            <option value="value_desc">Value, high to low</option>
            <option value="value_asc">Value, low to high</option>
            <option value="deadline_asc">Deadline, soonest first</option>
          </select>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="panel p-3 mb-4 flex flex-wrap items-center gap-3" style={{ borderColor: "var(--accent)" }}>
          <span className="text-sm text-main font-medium">{selected.size} selected</span>
          <select value={bulkStage} onChange={(e) => setBulkStage(e.target.value as Stage)} className="input" style={{ padding: "0.4rem 0.6rem", fontSize: "0.8rem" }}>
            {STAGE_ORDER.map((s) => (
              <option key={s} value={s}>Move to {STAGE_LABELS[s]}</option>
            ))}
          </select>
          <button onClick={applyBulkStage} disabled={bulkApplying} className="btn btn-primary text-xs">
            {bulkApplying ? "Applying…" : "Apply"}
          </button>
          <button onClick={() => setSelected(new Set())} className="btn btn-secondary text-xs">
            Clear selection
          </button>
        </div>
      )}

      {error && (
        <div className="panel p-5 mb-6" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Couldn&apos;t load opportunities
          </p>
          <p className="text-sm text-muted mb-3">{error}</p>
          <button onClick={load} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      {visibleOpportunities.length === 0 && (
        <div className="panel p-10 text-center text-sm text-muted">
          No opportunities match these filters yet.
        </div>
      )}

      {view === "list" && visibleOpportunities.length > 0 && (
        <div className="panel overflow-hidden overflow-x-auto">
          <table className="data-table">
            <caption className="sr-only">Opportunity pipeline</caption>
            <thead>
              <tr>
                <th scope="col" style={{ width: "2.5rem" }}>
                  <label className="sr-only" htmlFor="select-all-opps">Select all</label>
                  <input
                    id="select-all-opps"
                    type="checkbox"
                    checked={selected.size > 0 && selected.size === visibleOpportunities.length}
                    onChange={() => toggleSelectAll(visibleOpportunities.map((o) => o.id))}
                    className="h-4 w-4"
                  />
                </th>
                <th scope="col">Opportunity</th>
                <th scope="col">Vertical</th>
                <th scope="col">Organisation</th>
                <th scope="col">Region</th>
                <th scope="col">Value</th>
                <th scope="col">Deadline</th>
                <th scope="col">Stage</th>
                <th scope="col">Score</th>
              </tr>
            </thead>
            <tbody>
              {visibleOpportunities.map((o) => (
                <tr key={o.id}>
                  <td>
                    <label className="sr-only" htmlFor={`select-${o.id}`}>Select {o.title}</label>
                    <input
                      id={`select-${o.id}`}
                      type="checkbox"
                      checked={selected.has(o.id)}
                      onChange={() => toggleSelected(o.id)}
                      className="h-4 w-4"
                    />
                  </td>
                  <td>
                    <Link href={`/opportunities/${o.id}`} className="font-medium text-main hover:text-accent">
                      {o.title}
                    </Link>
                  </td>
                  <td className="text-muted">{o.vertical ? VERTICAL_LABELS[o.vertical] : "—"}</td>
                  <td className="text-muted">
                    {o.organisation_id && o.organisation_name ? (
                      <Link href={`/organisations/${o.organisation_id}`} className="hover:text-accent">
                        {o.organisation_name}
                      </Link>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="text-muted">{o.region ? REGION_LABELS[o.region] : "—"}</td>
                  <td className="text-muted">
                    {o.value_estimate ? `$${Math.round(o.value_estimate).toLocaleString()}` : "—"}
                  </td>
                  <td>
                    <DeadlineBadge deadline={o.deadline} />
                  </td>
                  <td>
                    <label className="sr-only" htmlFor={`stage-${o.id}`}>Stage for {o.title}</label>
                    <select
                      id={`stage-${o.id}`}
                      value={o.stage}
                      onChange={(e) => changeStage(o.id, e.target.value as Stage)}
                      className="input"
                      style={{ padding: "0.35rem 0.5rem", fontSize: "0.75rem" }}
                    >
                      {STAGE_ORDER.map((s) => (
                        <option key={s} value={s}>{STAGE_LABELS[s]}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <ScoreBadge score={o.alignment_score} size="sm" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {view === "kanban" && visibleOpportunities.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          {STAGE_ORDER.map((stage) => (
            <div key={stage} className="panel p-3">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted mb-3">{STAGE_LABELS[stage]}</h2>
              <div className="space-y-2.5">
                {visibleOpportunities
                  .filter((o) => o.stage === stage)
                  .map((o) => (
                    <div key={o.id} className="panel-raised p-3">
                      <Link href={`/opportunities/${o.id}`} className="text-sm text-main font-medium hover:text-accent">
                        {o.title}
                      </Link>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-[11px] text-muted">
                          {o.vertical ? VERTICAL_LABELS[o.vertical] : "—"}
                        </span>
                        <ScoreBadge score={o.alignment_score} size="sm" />
                      </div>
                      <label className="sr-only" htmlFor={`kanban-stage-${o.id}`}>Stage for {o.title}</label>
                      <select
                        id={`kanban-stage-${o.id}`}
                        value={o.stage}
                        onChange={(e) => changeStage(o.id, e.target.value as Stage)}
                        className="input mt-2 w-full"
                        style={{ padding: "0.35rem 0.5rem", fontSize: "0.75rem" }}
                      >
                        {STAGE_ORDER.map((s) => (
                          <option key={s} value={s}>{STAGE_LABELS[s]}</option>
                        ))}
                      </select>
                    </div>
                  ))}
                {visibleOpportunities.filter((o) => o.stage === stage).length === 0 && (
                  <p className="text-xs text-muted">No opportunities in this stage.</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DeadlineBadge({ deadline }: { deadline: string | null }) {
  if (!deadline) return <span className="text-muted text-xs">—</span>;
  const days = Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  let color = "var(--text-muted)";
  let label = deadline;
  if (days < 0) {
    color = "var(--danger)";
    label = `${deadline} · overdue`;
  } else if (days <= 7) {
    color = "var(--danger)";
    label = `${deadline} · ${days}d left`;
  } else if (days <= 30) {
    color = "var(--warning)";
    label = `${deadline} · ${days}d left`;
  }
  return (
    <span className="text-xs font-medium" style={{ color }}>
      {label}
    </span>
  );
}
