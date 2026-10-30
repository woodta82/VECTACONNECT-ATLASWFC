"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { EMPTY_FILTERS, filterQuery, RecordCards, RecordFilters, RecordTable, type Filters, type RecordRow, ViewToggle } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner } from "@/components/States";
import { Tabs } from "@/components/Ui";
import { qs } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Page = { items: RecordRow[]; total: number; limit: number; offset: number; scope: string; rule: string | null };
type TypeTab = "" | "tender" | "commercial" | "market_signal" | "historical" | "excluded";
const PAGE = 50;

const TABS: TypeTab[] = ["tender", "commercial", "market_signal", "historical", "excluded"];

/* The page opens with the filters in its address (a Dashboard summary, a country link), so a summary opens exactly the records it counts. */
function fromUrl(sp: URLSearchParams): { filters: Filters; tab: TypeTab } {
  const types = sp.get("types") ?? "";
  const tab = (TABS as string[]).includes(types) ? (types as TypeTab) : "";
  const countries = (sp.get("countries") ?? "").split(",").filter(Boolean);
  const region = sp.get("region") ?? "";
  return { tab, filters: { ...EMPTY_FILTERS, scope: region ? "region" : countries.length ? "countries" : "worldwide", region, countries,
                           airports: (sp.get("airports") ?? "").split(",").filter(Boolean), modules: sp.get("modules") ?? "", org: sp.get("org") ?? "",
                           tender: sp.get("tender") ?? "", progress: sp.get("progress") ?? "", coverage: sp.get("coverage") ?? "",
                           deadline_days: sp.get("deadline_days") ?? "", types: tab ? "" : types } };
}

export default function OpportunitiesPage() {
  return <Suspense fallback={<Loading what="opportunities" />}><Opportunities /></Suspense>;
}

function Opportunities() {
  const sp = useSearchParams();
  const [init] = useState(() => fromUrl(sp));
  const [filters, setFilters] = useState<Filters>(init.filters);
  const [tab, setTab] = useState<TypeTab>(init.tab);
  const [live, setLive] = useState(sp.get("live") === "true");
  const [needs, setNeeds] = useState(sp.get("needs") ?? "");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"priority" | "deadline" | "source_date">("priority");
  const [saved, setSaved] = useState(false);
  const [view, setView] = useState<"list" | "cards">("list");
  const [offset, setOffset] = useState(0);
  const params = { ...filterQuery({ ...filters, types: tab || filters.types }), q: q || undefined, sort, saved: saved ? "true" : undefined,
                   live: live ? "true" : undefined, needs: needs || undefined };
  const narrowed = [filters.types && filters.types.split(",").map((t) => t.replace("_", " ")).join(" and "), live && "live only",
                    needs === "attention" && "needing attention (no usable relationship, next action due within 14 days, or research incomplete)",
                    filters.deadline_days && `deadline within ${filters.deadline_days} days`].filter(Boolean);
  const r = useApi<Page>(`/records${qs({ ...params, limit: PAGE, offset })}`);
  const reset = (fn: () => void) => { fn(); setOffset(0); };
  return (
    <>
      <PageHeader eyebrow="Opportunities" title="Every opportunity, signal and historical record"
                  description="Tenders and procurements, commercial opportunities the team is tracking, market signals (potential, not open bids) and historical intelligence, each with its source date, stated deadline, status, priority explanation and relationship coverage."
                  actions={<>
                    <a className="btn" href={`/api/records/export.csv${qs(params)}`}>Export CSV</a>
                    <a className="btn btn-ghost" href={`/api/reports/opportunities.csv${qs({ ...filterQuery(filters), module: filters.modules || undefined })}`}>Technical export (CSV)</a>
                  </>} />
      <RecordFilters value={filters} onChange={(f) => reset(() => setFilters(f))} showTypes={false} />
      {narrowed.length > 0 && (
        <div className="notice notice-info" role="status">Showing {narrowed.join(" · ")}.{" "}
          <Link href="/opportunities" onClick={() => reset(() => { setFilters({ ...filters, types: "", deadline_days: "" }); setLive(false); setNeeds(""); })}>Show all records</Link></div>)}
      <Tabs<TypeTab> label="Record type" value={tab} onChange={(t) => reset(() => setTab(t))} tabs={[
        { id: "", label: "All" }, { id: "tender", label: "Tenders and procurements" }, { id: "commercial", label: "Commercial" },
        { id: "market_signal", label: "Market signals" }, { id: "historical", label: "Historical" }, { id: "excluded", label: "Out of scope" }]} />
      <div className="filters">
        <label className="field">Search<input className="input" value={q} onChange={(e) => reset(() => setQ(e.target.value))}
                                               placeholder="Title, organisation or reference" /></label>
        <label className="field">Sort
          <select className="select" value={sort} onChange={(e) => reset(() => setSort(e.target.value as typeof sort))}>
            <option value="priority">Priority (explained)</option><option value="deadline">Stated deadline</option>
            <option value="source_date">Source date (newest)</option>
          </select></label>
        <label className="field inline"><input type="checkbox" checked={saved} onChange={(e) => reset(() => setSaved(e.target.checked))} /> Saved only</label>
        <div className="field">View<ViewToggle value={view} onChange={setView} /></div>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="opportunities" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? <Empty title="No records match">Change the filters, or run a search under Discover.</Empty> : (
        <div className="stack">
          {view === "list" ? <RecordTable rows={r.data.items} label="Opportunities" /> : <RecordCards rows={r.data.items} />}
          <div className="filters">
            <span className="muted small">{r.data.offset + 1}–{r.data.offset + r.data.items.length} of {r.data.total} · {r.data.scope}</span>
            <button type="button" className="btn" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
            <button type="button" className="btn" disabled={offset + PAGE >= r.data.total} onClick={() => setOffset(offset + PAGE)}>Next</button>
          </div>
          {r.data.rule && <p className="muted small">Priority order: {r.data.rule}. Not a probability of winning.</p>}
        </div>
      ))}
    </>
  );
}
