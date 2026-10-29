"use client";

import Link from "next/link";
import { useState } from "react";
import { EMPTY_FILTERS, filterQuery, RecordCards, RecordFilters, RecordTable, type Filters, type RecordRow, recordHref, ViewToggle,
         CoverageTag, Tag } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, Stat, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { dateOnly, dateTime, deadline, label, moduleLabel } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Person = { id: string; full_name: string; role_title: string | null; organisation: string | null; state: string; state_label: string;
                updated_at: string; linked: { id: string; title: string }[] | null };
type Saved = { id: string; name: string; geo_mode: string; countries: string[]; regions: string[]; modules: string[]; schedule_minutes: number | null;
               last_run_at: string | null; last_status: string | null; last_run_id: string | null };
type Change = { changed_at: string; field: string; from_value: string | null; to_value: string; reason: string | null; opportunity_id: string; title: string };
type Overview = { scope: string; counts: Record<string, number>; priority: RecordRow[]; recent: RecordRow[]; upcoming_deadlines: RecordRow[];
                  needs_research: RecordRow[]; with_relationships: RecordRow[]; people_recent: Person[]; saved_searches: Saved[];
                  recent_changes: Change[]; rule: string };

const STATE_TONE: Record<string, string> = { existing_relationship: "b-good", introduction_available: "b-good", identity_confirmed: "b-info",
                                             research_candidate: "b-warn" };

export default function OverviewPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [view, setView] = useState<"list" | "cards">("list");
  const r = useApi<Overview>(`/overview${qs(filterQuery(filters))}`);
  return (
    <>
      <PageHeader eyebrow="Overview" title="Global opportunities and the relationships to pursue them"
                  description="Discover an opportunity, understand it, research the organisations and people involved, find an existing relationship or an introduction route, and track progress."
                  actions={<><Link className="btn" href="/discovery">Discover</Link><Link className="btn btn-primary" href="/opportunities">All opportunities</Link></>} />
      <RecordFilters value={filters} onChange={setFilters} />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="overview" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body o={r.data} view={view} setView={setView} />}
    </>
  );
}

function Body({ o, view, setView }: { o: Overview; view: "list" | "cards"; setView: (v: "list" | "cards") => void }) {
  return (
    <div className="stack">
      <div className="grid grid-4" aria-label="Records in scope">
        <Stat label="Tenders and procurements" value={o.counts.tender ?? 0} note={o.scope} />
        <Stat label="Commercial opportunities" value={o.counts.commercial ?? 0} note="tracked potential" />
        <Stat label="Market signals" value={o.counts.market_signal ?? 0} note="potential, unconfirmed" />
        <Stat label="Historical intelligence" value={o.counts.historical ?? 0} note="never shown as live" />
      </div>

      <section className="panel" aria-label="Priority opportunities">
        <div className="panel-head"><h2>Priority opportunities</h2><ViewToggle value={view} onChange={setView} /></div>
        {o.priority.length === 0 ? <Empty title="No live opportunities in this scope">Run a search under Discover, or widen the filters.</Empty>
          : view === "list" ? <RecordTable rows={o.priority} label="Priority list" /> : <RecordCards rows={o.priority} />}
        <p className="muted small">Order: {o.rule}. Not a probability of winning.</p>
      </section>

      <div className="grid grid-2">
        <section className="panel" aria-label="Upcoming deadlines">
          <h2>Upcoming stated deadlines</h2>
          {o.upcoming_deadlines.length === 0 ? <Empty title="No stated deadlines ahead" /> : (
            <ul className="list-plain">{o.upcoming_deadlines.map((r) => (
              <li key={r.id}><Link href={recordHref(r)}>{r.title}</Link>
                <div className="small muted">{deadline(r.deadline_utc, r.deadline_source_tz, r.deadline_info)} · {r.countries_named.join(", ") || "geography not established"}</div></li>
            ))}</ul>
          )}
        </section>
        <section className="panel" aria-label="Recently discovered">
          <h2>Recently discovered</h2>
          {o.recent.length === 0 ? <Empty title="Nothing new in the last 14 days" /> : (
            <ul className="list-plain">{o.recent.map((r) => (
              <li key={`${r.kind}-${r.id}`}><Link href={recordHref(r)}>{r.title}</Link>
                <div className="small"><Tag text={r.record_type_label} /> <span className="muted">{r.organisation ?? "organisation not established"} · found {dateOnly(r.created_at)}</span></div></li>
            ))}</ul>
          )}
        </section>
      </div>

      <div className="grid grid-2">
        <section className="panel" aria-label="Needs relationship research">
          <h2>Needs relationship research</h2>
          {o.needs_research.length === 0 ? <Empty title="Every live opportunity has confirmed people" /> : (
            <ul className="list-plain">{o.needs_research.map((r) => (
              <li key={r.id}><Link href={recordHref(r)}>{r.title}</Link>
                <div className="small"><CoverageTag coverage={r.coverage} label={r.coverage_label} /> <span className="muted">{r.organisation ?? ""}</span></div></li>
            ))}</ul>
          )}
        </section>
        <section className="panel" aria-label="With a relationship or introduction">
          <h2>With an existing relationship or introduction route</h2>
          {o.with_relationships.length === 0 ? <Empty title="No recorded relationship or available introduction yet" /> : (
            <ul className="list-plain">{o.with_relationships.map((r) => (
              <li key={r.id}><Link href={recordHref(r)}>{r.title}</Link>
                <div className="small"><CoverageTag coverage={r.coverage} label={r.coverage_label} /> <span className="muted">{r.organisation ?? ""}</span></div></li>
            ))}</ul>
          )}
        </section>
      </div>

      <section className="panel" aria-label="Relevant people identified recently">
        <h2>Relevant people identified recently</h2>
        {o.people_recent.length === 0 ? <Empty title="No people researched yet">Open an opportunity and choose Research relationships.</Empty> : (
          <TableWrap label="Relevant people">
            <table><thead><tr><th>Person</th><th>Organisation</th><th>Status</th><th>Opportunities</th></tr></thead>
              <tbody>{o.people_recent.map((p) => (
                <tr key={p.id}><td><Link href={`/relationships/${p.id}`}>{p.full_name}</Link><div className="small muted">{p.role_title ?? "role not established"}</div></td>
                  <td>{p.organisation ?? <span className="muted">Not established</span>}</td>
                  <td><Tag text={p.state_label} tone={STATE_TONE[p.state]} /></td>
                  <td className="small">{(p.linked ?? []).map((l) => <div key={l.id}><Link href={`/opportunities/${l.id}`}>{l.title}</Link></div>)}</td></tr>
              ))}</tbody></table>
          </TableWrap>
        )}
      </section>

      <div className="grid grid-2">
        <section className="panel" aria-label="Saved searches">
          <h2>Saved searches</h2>
          {o.saved_searches.length === 0 ? <Empty title="No saved searches">Save a search under Discover to monitor it.</Empty> : (
            <ul className="list-plain">{o.saved_searches.map((s) => (
              <li key={s.id}><Link href={s.last_run_id ? `/discovery/runs/${s.last_run_id}` : "/discovery"}>{s.name}</Link>
                <div className="small muted">{s.geo_mode === "worldwide" ? "Worldwide" : [...s.regions.map(label), ...s.countries].join(", ")}
                  {s.modules.length ? ` · ${s.modules.map(moduleLabel).join(", ")}` : ""} · {s.schedule_minutes ? `every ${Math.round(s.schedule_minutes / 60)} h` : "not scheduled"}
                  {s.last_run_at ? ` · last run ${dateTime(s.last_run_at)} (${label(s.last_status)})` : " · not run yet"}</div></li>
            ))}</ul>
          )}
        </section>
        <section className="panel" aria-label="Recent changes">
          <h2>Recent changes</h2>
          {o.recent_changes.length === 0 ? <Empty title="No changes yet" /> : (
            <ul className="list-plain">{o.recent_changes.map((c, i) => (
              <li key={i}><Link href={`/opportunities/${c.opportunity_id}`}>{c.title}</Link>
                <div className="small muted">{label(c.field)}: {c.from_value ? `${label(c.from_value)} → ` : ""}{label(c.to_value)} · {dateTime(c.changed_at)}</div></li>
            ))}</ul>
          )}
        </section>
      </div>
    </div>
  );
}
