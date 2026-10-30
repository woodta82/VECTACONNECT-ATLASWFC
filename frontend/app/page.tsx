"use client";

/* The Dashboard (30 Oct 2026): the first screen, consolidating the Overview and the Control panel. What deserves attention, what
   changed, who is relevant, what to do next. Four clickable summaries, a compact priority table, a short recent-changes list; the
   geographic visuals as supporting context; score distributions, breakdowns and technical metrics behind an expandable detail.
   Opportunities are shown apart from market signals. */

import Link from "next/link";
import { Fragment, useState } from "react";
import { avg, RegionDonut, ScoreHistogram, slot, type Bucket, type Decile, type RegionRow } from "@/components/Charts";
import { EMPTY_FILTERS, filterQuery, RecordFilters, CoverageTag, Tag, type Filters } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { dateOnly, dateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Row = { id: string; kind: "opportunity" | "signal"; title: string; organisation: string | null; organisation_id: string | null; countries_named: string[];
             airports: string[]; record_type: string; record_type_label: string | null; tender_status_label: string | null; progress: string | null;
             progress_label: string | null; coverage: string; coverage_label: string; deadline_at: string | null; next_action: string;
             next_action_due: string | null; next_action_is_recommendation: boolean; research_incomplete: boolean; research: string; research_label: string; research_tally: string | null;
             priority_reason: string; category: string | null };
type Summary = { key: string; title: string; count: number; detail: string; link: string; secondary?: { label: string; link: string; count: number }[];
                 items: { id: string | null; title: string; detail: string | null; link?: string }[] };
type Change = { changed_at: string; field: string; label: string; from_value: string | null; to_value: string; reason: string | null; opportunity_id: string; title: string };
type Dash = {
  scope: string; airports: { ident: string; label: string }[]; generated_at: string; summaries: Summary[]; priority: Row[]; signals: Row[]; signals_total: number;
  recent_changes: Change[]; recent: Row[];
  geo: { by_region: RegionRow[]; by_country: (Bucket & { code: string | null; country: string; region: string })[]; markets: number };
  detail: { totals: { live: number; tenders_open: number; commercial: number; signals: number; deadline_30_days: number; avg_score: number | null; strong: number;
                      with_relationships: number; markets: number; not_scored: number };
            score_bands: { band: string; label: string; range: string; count: number }[]; score_deciles: Decile[];
            score_components: { key: string; label: string; max: number; avg: number | null }[];
            by_category: (Bucket & { module: string; category: string })[]; by_market: (Bucket & { region: string; market: string })[]; rule: string; market_rule: string };
  rule: string;
};

const TYPE_TONE: Record<string, string> = { tender: "b-info", commercial: "b-good", market_signal: "b-warn" };

export default function DashboardPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const r = useApi<Dash>(`/dashboard${qs(filterQuery(filters))}`);
  return (
    <>
      <PageHeader eyebrow="Dashboard" title="What deserves attention, what changed, who is relevant, what next"
                  description="Live opportunities with their companies, geography, status, relationship position and next action. Discover is where research starts; Opportunities and Relationships hold what it finds."
                  actions={<><Link className="btn" href="/opportunities">All opportunities</Link><Link className="btn btn-primary" href="/discovery">Discover</Link></>} />
      <RecordFilters value={filters} onChange={setFilters} />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="dashboard" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body d={r.data} />}
    </>
  );
}

function Body({ d }: { d: Dash }) {
  return (
    <div className="stack">
      <section className="panel" aria-label="Summaries">
        <div className="grid grid-4 questions">
          {d.summaries.map((x) => (
            <div className="question summary" key={x.key} role="region" aria-label={x.title}>
              <h3><Link href={x.link}>{x.title}</Link> <span className="num">{x.count}</span></h3>
              <p className="small muted">{x.detail}</p>
              {x.items.length > 0 && <ul className="list-plain small">{x.items.map((it, i) => (
                <li key={`${it.id ?? i}`}>{it.id ? <Link href={it.link ?? `/opportunities/${it.id}`}>{it.title}</Link> : it.title}{it.detail && <span className="muted"> · {it.detail}</span>}</li>))}</ul>}
              <p className="small"><Link href={x.link}>Open records</Link>{(x.secondary ?? []).map((sec) => <Fragment key={sec.link}> · <Link href={sec.link}>{sec.label} ({sec.count})</Link></Fragment>)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel" aria-label="Priority list">
        <div className="panel-head"><h2>Priority opportunities</h2><span className="muted small">{d.scope}</span></div>
        {d.priority.length === 0 ? <Empty title="No live opportunities in this scope">Run a search under Discover, or widen the filters.</Empty> : (
          <TableWrap label="Priority table">
            <table>
              <thead><tr><th>Opportunity</th><th>Company</th><th>Country / airport</th><th>Status</th><th>Relationship position</th><th>Next action</th></tr></thead>
              <tbody>{d.priority.map((r) => (
                <tr key={r.id}>
                  <td><Link href={`/opportunities/${r.id}`}>{r.title}</Link><div className="small muted">{r.category}</div>
                    <div className="small"><Tag text={r.research_label} tone={r.research === "complete" ? "b-good" : r.research === "failed" ? "b-bad" : r.research === "incomplete" || r.research === "complete_with_failures" ? "b-warn" : "b-none"} />
                      {r.research_tally && <span className="muted"> {r.research_tally}</span>}</div></td>
                  <td className="small">{r.organisation_id ? <Link href={`/companies/${r.organisation_id}`}>{r.organisation}</Link> : r.organisation ?? <span className="muted">not established</span>}</td>
                  <td className="small">{r.countries_named.join(", ") || <span className="muted">—</span>}{r.airports.length > 0 && <div className="muted">{r.airports.join(", ")}</div>}</td>
                  <td className="small"><Tag text={r.record_type_label ?? r.record_type} tone={TYPE_TONE[r.record_type]} />
                    {r.tender_status_label && <div className="muted">{r.tender_status_label}</div>}{r.progress_label && <div className="muted">{r.progress_label}</div>}
                    {r.deadline_at && <div className="muted">deadline {dateOnly(r.deadline_at)}</div>}</td>
                  <td className="small"><CoverageTag coverage={r.coverage} label={r.coverage_label} /></td>
                  <td className="small">{r.next_action}{r.next_action_is_recommendation && <span className="muted"> (suggested)</span>}{r.next_action_due && <div className="muted">due {dateOnly(r.next_action_due)}</div>}</td>
                </tr>))}</tbody>
            </table>
          </TableWrap>
        )}
        <p className="muted small">{d.rule}</p>
      </section>

      <div className="grid grid-2">
        <section className="panel" aria-label="Market signals">
          <div className="panel-head"><h2>Market signals</h2><Link className="small" href="/opportunities?types=market_signal">All {d.signals_total}</Link></div>
          <p className="small muted">What is changing: routes, appointments, investments, announcements. Not confirmed buying demand; a person tracks one as an opportunity.</p>
          {d.signals.length === 0 ? <p className="muted small">None in this scope.</p> : (
            <ul className="list-plain small">{d.signals.map((s) => <li key={s.id}><Link href={`/signals/${s.id}`}>{s.title}</Link><span className="muted"> · {s.countries_named.join(", ")}{s.category ? ` · ${s.category}` : ""}</span></li>)}</ul>)}
        </section>
        <section className="panel" aria-label="Recent changes">
          <h2>Recent changes</h2>
          {d.recent_changes.length === 0 && d.recent.length === 0 ? <p className="muted small">Nothing changed in the last 14 days.</p> : (
            <ul className="list-plain small">
              {d.recent_changes.slice(0, 6).map((c, i) => <li key={`${c.opportunity_id}-${i}`}><Link href={`/opportunities/${c.opportunity_id}`}>{c.title}</Link><span className="muted"> · {c.label} · {dateTime(c.changed_at)}</span></li>)}
              {d.recent.slice(0, 4).map((r) => <li key={r.id}><Link href={r.kind === "signal" ? `/signals/${r.id}` : `/opportunities/${r.id}`}>{r.title}</Link><span className="muted"> · new {r.record_type_label?.toLowerCase()}</span></li>)}
            </ul>)}
        </section>
      </div>

      {d.detail.totals.live > 0 && (
        <div className="grid grid-2">
          <section className="panel" aria-label="By region">
            <h2>Live opportunities by region</h2>
            <p className="muted small">Supporting context: each live record counts once in every region it names.</p>
            <RegionDonut regions={d.geo.by_region} />
          </section>
          <section className="panel" aria-label="By country">
            <h2>By country</h2>
            <TableWrap label="Live opportunities by country">
              <table>
                <thead><tr><th>Country</th><th className="num">Live</th><th className="num">Open tenders</th><th className="num">Commercial</th><th className="num">Signals</th><th className="num">With relationship</th></tr></thead>
                <tbody>{d.geo.by_country.map((c) => (
                  <tr key={c.code ?? c.country}>
                    <td><span className={`cp-dot s-${slot(c.region)}`} aria-hidden="true" /> {c.code ? <Link href={`/opportunities?countries=${c.code}`}>{c.country}</Link> : c.country}</td>
                    <td className="num">{c.live}</td><td className="num">{c.tenders_open}</td><td className="num">{c.commercial}</td><td className="num">{c.signals}</td><td className="num">{c.with_relationships}</td>
                  </tr>))}</tbody>
              </table>
            </TableWrap>
          </section>
        </div>
      )}

      <details className="panel">
        <summary><b>Score distribution, breakdowns and technical metrics</b> <span className="muted small">— {d.detail.totals.live} live · {d.detail.totals.markets} markets · average score {d.detail.totals.avg_score?.toFixed(1) ?? "not scored"} · {d.detail.totals.strong} strong</span></summary>
        <div className="stack" style={{ marginTop: 12 }}>
          <div className="grid grid-2">
            <section aria-label="Opportunities by score">
              <h3>Opportunities by score</h3>
              <ScoreHistogram deciles={d.detail.score_deciles} />
              <ul className="cp-bands" aria-label="Score bands">{d.detail.score_bands.map((b) => (
                <li key={b.band}><span className={`cp-band cp-band-${b.band}`}>{b.label}</span><span className="muted small">{b.range}</span><b>{b.count}</b></li>))}</ul>
              <div className="cp-weights" aria-label="Average points per part of the score">{d.detail.score_components.map((c) => (
                <div key={c.key} className="cp-weight"><span className="small">{c.label}</span>
                  <span className="cp-meter" aria-hidden="true"><span style={{ width: `${((c.avg ?? 0) / c.max) * 100}%` }} /></span>
                  <span className="small muted">avg {c.avg?.toFixed(1) ?? "–"} of {c.max}</span></div>))}</div>
            </section>
            <section aria-label="By market and capability area">
              <h3>By market</h3>
              <ul className="cp-list">{d.detail.by_market.slice(0, 8).map((m) => (
                <li key={`${m.region}-${m.market}`}><span className={`cp-dot s-${slot(m.region)}`} aria-hidden="true" />
                  <div className="cp-name"><span>{m.market}</span><span className="muted small">{m.live} live · {m.tenders_open} open tenders · {m.region}</span></div>
                  <span className="cp-pill">{m.live}</span><span className="cp-avg">{avg(m.avg_score)}</span></li>))}</ul>
              <h3>By capability area</h3>
              <ul className="cp-list">{d.detail.by_category.map((c) => (
                <li key={c.module}><span className="cp-dot s-accent" aria-hidden="true" />
                  <div className="cp-name"><span>{c.category}</span><span className="muted small">{c.live} live · {c.with_relationships} with a relationship or introduction</span></div>
                  <span className="cp-pill">{c.live}</span><span className="cp-avg">{avg(c.avg_score)}</span></li>))}</ul>
            </section>
          </div>
          <p className="muted small">{d.detail.rule} {d.detail.market_rule}</p>
        </div>
      </details>
    </div>
  );
}
