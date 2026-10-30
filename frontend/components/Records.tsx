"use client";

import Link from "next/link";
import { AirportPicker } from "@/components/Airports";
import { CountryPicker, RegionSelect } from "@/components/Geo";
import { TableWrap } from "@/components/States";
import { MODULES } from "@/lib/constants";
import { dateOnly, deadline, moduleLabel, type DeadlineInfo } from "@/lib/format";

export type RecordRow = {
  kind: "opportunity" | "signal"; id: string; record_type: string; record_type_label: string; module: string; category: string; title: string;
  organisation: string | null; organisation_id: string | null; countries: string[]; countries_named: string[]; source_date: string | null;
  deadline_utc: string | null; deadline_at: string | null; deadline_source_tz: string | null; deadline_info: DeadlineInfo | null;
  tender_status: string | null; tender_status_label: string | null; progress: string | null; saved_at: string | null; owner_label: string | null;
  next_action: string | null; coverage: string; coverage_label: string; people: number; priority_reason: string; priority_rank?: number;
  review_state: string | null; created_at: string;
};

export type Filters = { scope: "worldwide" | "region" | "countries"; region: string; countries: string[]; airports: string[]; modules: string; org: string;
                        tender: string; progress: string; coverage: string; deadline_days: string; types: string };
export const EMPTY_FILTERS: Filters = { scope: "worldwide", region: "", countries: [], airports: [], modules: "", org: "", tender: "", progress: "",
                                        coverage: "", deadline_days: "", types: "" };

export function filterQuery(f: Filters): Record<string, string> {
  const q: Record<string, string> = {};
  if (f.scope === "region" && f.region) q.region = f.region;
  if (f.scope === "countries" && f.countries.length) q.countries = f.countries.join(",");
  if (f.airports.length) q.airports = f.airports.join(",");
  for (const k of ["modules", "org", "tender", "progress", "coverage", "deadline_days", "types"] as const) if (f[k]) q[k] = f[k];
  return q;
}

export const RECORD_TYPES: [string, string][] = [
  ["tender", "Tender or procurement"], ["commercial", "Commercial opportunity"], ["market_signal", "Market signal"], ["historical", "Historical intelligence"],
];
const TENDER: [string, string][] = [["open,revised", "Open"], ["announced", "Announced"], ["unverified,contradictory,unknown", "Needs review"],
                                     ["expired", "Expired"], ["cancelled", "Cancelled"], ["awarded", "Awarded"], ["closed", "Closed"]];
const PROGRESS: [string, string][] = [["new", "New"], ["reviewing", "Reviewing"], ["pursuing", "Pursuing"], ["on_hold", "On hold"], ["closed", "Closed"]];
export const COVERAGE: [string, string][] = [["existing_relationship", "Existing relationship"], ["introduction_available", "Introduction available"],
                                             ["people_confirmed", "People confirmed"], ["candidates_only", "Research candidates only"],
                                             ["none", "No relationship research"]];

export function RecordFilters({ value, onChange, showTypes = true }: { value: Filters; onChange: (f: Filters) => void; showTypes?: boolean }) {
  const set = (patch: Partial<Filters>) => onChange({ ...value, ...patch });
  return (
    <div className="panel" role="search" aria-label="Filters">
      <div className="filters">
        <div className="field">Geography
          <div className="segmented" role="group" aria-label="Geography">
            {(["worldwide", "region", "countries"] as const).map((s) => (
              <button key={s} type="button" aria-pressed={value.scope === s} onClick={() => set({ scope: s })}>
                {s === "worldwide" ? "Worldwide" : s === "region" ? "Region" : "Countries"}
              </button>
            ))}
          </div>
        </div>
        {value.scope === "region" && <RegionSelect value={value.region} onChange={(region) => set({ region })} />}
        {value.scope === "countries" && <div style={{ flex: "1 1 260px" }}><CountryPicker value={value.countries} onChange={(countries) => set({ countries })} /></div>}
        <div style={{ flex: "1 1 260px" }}><AirportPicker value={value.airports} onChange={(airports) => set({ airports })} label="Airports (optional)" hint="Any airport: name, IATA, ICAO or city" /></div>
        <label className="field">Category
          <select className="select" value={value.modules} onChange={(e) => set({ modules: e.target.value })}>
            <option value="">All nine categories</option>
            {MODULES.map((m) => <option key={m} value={m}>{moduleLabel(m)}</option>)}
          </select></label>
        <label className="field">Organisation
          <input className="input" value={value.org} onChange={(e) => set({ org: e.target.value })} placeholder="e.g. Example Air" /></label>
      </div>
      <div className="filters">
        {showTypes && (
          <label className="field">Record type
            <select className="select" value={value.types} onChange={(e) => set({ types: e.target.value })}>
              <option value="">All (excluding out-of-scope)</option>
              {RECORD_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select></label>
        )}
        <label className="field">Tender status
          <select className="select" value={value.tender} onChange={(e) => set({ tender: e.target.value })}>
            <option value="">Any</option>{TENDER.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></label>
        <label className="field">Deadline
          <select className="select" value={value.deadline_days} onChange={(e) => set({ deadline_days: e.target.value })}>
            <option value="">Any</option><option value="14">Within 14 days</option><option value="30">Within 30 days</option>
            <option value="90">Within 90 days</option>
          </select></label>
        <label className="field">Progress
          <select className="select" value={value.progress} onChange={(e) => set({ progress: e.target.value })}>
            <option value="">Any</option>{PROGRESS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            <option value="untracked">Not tracked (signals)</option>
          </select></label>
        <label className="field">Relationship coverage
          <select className="select" value={value.coverage} onChange={(e) => set({ coverage: e.target.value })}>
            <option value="">Any</option>{COVERAGE.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select></label>
        <button type="button" className="btn btn-ghost" onClick={() => onChange(EMPTY_FILTERS)}>Clear filters</button>
      </div>
    </div>
  );
}

export function recordHref(r: Pick<RecordRow, "kind" | "id">): string {
  return r.kind === "opportunity" ? `/opportunities/${r.id}` : `/signals/${r.id}`;
}

const COVERAGE_TONE: Record<string, string> = { existing_relationship: "b-good", introduction_available: "b-good", people_confirmed: "b-info",
                                               candidates_only: "b-warn", none: "b-none" };
const TYPE_TONE: Record<string, string> = { tender: "b-info", commercial: "b-good", market_signal: "b-warn", historical: "b-none", excluded: "b-bad" };
const STATUS_TONE: Record<string, string> = { open: "b-good", revised: "b-good", announced: "b-warn", unverified: "b-warn", contradictory: "b-warn",
                                             unknown: "b-none", expired: "b-none", cancelled: "b-bad", awarded: "b-none", closed: "b-none" };

export function Tag({ text, tone }: { text: string; tone?: string }) {
  return <span className={`badge ${tone ?? "b-none"}`}>{text}</span>;
}
export function TypeTag({ r }: { r: Pick<RecordRow, "record_type" | "record_type_label"> }) {
  return <Tag text={r.record_type_label} tone={TYPE_TONE[r.record_type]} />;
}
export function StatusTag({ r }: { r: Pick<RecordRow, "tender_status" | "tender_status_label"> }) {
  return r.tender_status ? <Tag text={r.tender_status_label ?? r.tender_status} tone={STATUS_TONE[r.tender_status]} /> : <span className="muted small">n/a</span>;
}
export function CoverageTag({ coverage, label }: { coverage: string; label: string }) {
  return <Tag text={label} tone={COVERAGE_TONE[coverage]} />;
}
const PROGRESS_LABEL: Record<string, string> = Object.fromEntries(PROGRESS);

function Geo({ r }: { r: RecordRow }) {
  return <>{r.countries_named.length ? r.countries_named.join(", ") : <span className="muted">Not established</span>}</>;
}

export function RecordTable({ rows, label, compact = false }: { rows: RecordRow[]; label: string; compact?: boolean }) {
  return (
    <TableWrap label={label}>
      <table>
        <thead><tr>
          {!compact && <th>#</th>}<th>Opportunity</th><th>Organisation</th><th>Geography</th>
          {!compact && <th>Source date</th>}<th>Stated deadline</th><th>Status</th><th>Relationships</th>{!compact && <th>Why it ranks here</th>}
        </tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={`${r.kind}-${r.id}`}>
            {!compact && <td className="num">{r.priority_rank ?? ""}</td>}
            <td><Link href={recordHref(r)}>{r.title}</Link>
              <div className="small"><TypeTag r={r} />{r.saved_at && <> <Tag text="Saved" tone="b-info" /></>}
                <span className="muted"> · {r.category}</span>
                {r.review_state && <span className="muted"> · {r.review_state}</span>}</div></td>
            <td>{r.organisation ?? <span className="muted">Not established</span>}</td>
            <td><Geo r={r} /></td>
            {!compact && <td className="small">{r.source_date ? dateOnly(r.source_date) : <span className="muted">Not stated</span>}</td>}
            <td className="small">{r.deadline_utc || r.deadline_info ? deadline(r.deadline_utc, r.deadline_source_tz, r.deadline_info) : <span className="muted">Not stated</span>}</td>
            <td><StatusTag r={r} />{r.progress && <div className="small muted">{PROGRESS_LABEL[r.progress]}</div>}</td>
            <td><CoverageTag coverage={r.coverage} label={r.coverage_label} />{r.people > 0 && <div className="small muted">{r.people} people</div>}</td>
            {!compact && <td className="small">{r.priority_reason}</td>}
          </tr>
        ))}</tbody>
      </table>
    </TableWrap>
  );
}

export function RecordCards({ rows }: { rows: RecordRow[] }) {
  return (
    <div className="grid grid-3" aria-label="Opportunity cards">
      {rows.map((r) => (
        <article key={`${r.kind}-${r.id}`} className="panel record-card" aria-label={r.title}>
          <div className="small"><TypeTag r={r} /> <StatusTag r={r} /></div>
          <h3><Link href={recordHref(r)}>{r.title}</Link></h3>
          <dl className="kv small">
            <dt>Organisation</dt><dd>{r.organisation ?? "Not established"}</dd>
            <dt>Geography</dt><dd><Geo r={r} /></dd>
            <dt>Category</dt><dd>{r.category}</dd>
            <dt>Source date</dt><dd>{r.source_date ? dateOnly(r.source_date) : "Not stated"}</dd>
            <dt>Deadline</dt><dd>{r.deadline_utc || r.deadline_info ? deadline(r.deadline_utc, r.deadline_source_tz, r.deadline_info) : "Not stated"}</dd>
          </dl>
          <p className="small"><b>Priority:</b> {r.priority_reason}</p>
          <CoverageTag coverage={r.coverage} label={r.coverage_label} />
        </article>
      ))}
    </div>
  );
}

export function ViewToggle({ value, onChange }: { value: "list" | "cards"; onChange: (v: "list" | "cards") => void }) {
  return (
    <div className="segmented" role="group" aria-label="View">
      <button type="button" aria-pressed={value === "list"} onClick={() => onChange("list")}>List</button>
      <button type="button" aria-pressed={value === "cards"} onClick={() => onChange("cards")}>Cards</button>
    </div>
  );
}
