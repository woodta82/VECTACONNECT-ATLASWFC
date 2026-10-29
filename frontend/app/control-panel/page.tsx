"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import { EMPTY_FILTERS, filterQuery, RecordFilters, recordHref, type Filters, Tag } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, Stat, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Bucket = { live: number; tenders_open: number; commercial: number; signals: number; with_relationships: number;
                avg_score: number | null; top_score: number | null };
type Component = { key: string; label: string; points: number; max: number; reason: string };
type Scored = { id: string; kind: "opportunity" | "signal"; title: string; organisation: string | null; record_type: string;
                record_type_label: string; category: string; countries: string[]; countries_named: string[];
                tender_status_label: string | null; coverage_label: string; score: number; band: string; band_label: string;
                components: Component[] };
type Summary = { key: string; title: string; count: number; detail: string; link: string; secondary?: { label: string; link: string; count: number }[];
                 items: { id: string | null; title: string; detail: string | null; link?: string }[] };
type Panel = {
  scope: string; rule: string; market_rule: string;
  totals: { live: number; tenders_open: number; commercial: number; signals: number; deadline_30_days: number; avg_score: number | null;
            strong: number; with_relationships: number; markets: number; not_scored: number };
  by_region: (Bucket & { region: string; share: number })[];
  by_market: (Bucket & { region: string; market: string })[];
  by_country: (Bucket & { code: string | null; country: string; region: string })[];
  by_category: (Bucket & { module: string; category: string })[];
  score_bands: { band: string; label: string; range: string; count: number }[];
  score_deciles: { range: string; count: number }[];
  score_components: { key: string; label: string; max: number; avg: number | null }[];
  scored: Scored[];
};

/** Fixed colour per region (never by rank), so a filter never repaints the regions that remain. */
const REGION_SLOT: Record<string, string> = { Africa: "1", Asia: "2", Europe: "3", Americas: "4", Oceania: "5" };
const slot = (region: string) => REGION_SLOT[region] ?? "none";
const pct = (x: number) => (x > 0 && x < 0.01 ? "<1%" : `${Math.round(x * 100)}%`);
const avg = (v: number | null) => (v === null ? "not scored" : `avg ${v.toFixed(1)}`);

export default function ControlPanelPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const r = useApi<Panel>(`/control-panel${qs(filterQuery(filters))}`);
  return (
    <>
      <PageHeader eyebrow="Control panel" title="Opportunities by market, scored out of 100"
                  description="Live opportunities and market signals per region, market and country, with each opportunity's score out of 100 and how it was reached."
                  actions={<><Link className="btn" href="/opportunities">All opportunities</Link><Link className="btn btn-primary" href="/discovery">Discover</Link></>} />
      <Summaries />
      <RecordFilters value={filters} onChange={setFilters} />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="control panel" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body p={r.data} />}
    </>
  );
}

/** The full system in six separated summaries (29 Oct 2026); each opens the filtered records. The analytics below stay secondary. */
function Summaries() {
  const s = useApi<{ summaries: Summary[] }>("/control-panel/summaries");
  if (!s.data) return null;
  const href = (x: { id: string | null; link?: string }, key: string) =>
    x.link ?? (key === "companies" ? `/companies?country=${x.id}` : key === "market" ? `/signals/${x.id}` : `/opportunities/${x.id}`);
  return (
    <section className="panel" aria-label="System summaries">
      <div className="grid grid-3 questions">
        {s.data.summaries.map((x) => (
          <div className="question" key={x.key} role="region" aria-label={x.title}>
            <h3><Link href={x.link}>{x.title}</Link> <span className="num">{x.count}</span></h3>
            <p className="small muted">{x.detail}</p>
            {x.items.length > 0 && <ul className="list-plain small">{x.items.map((it, i) => (
              <li key={`${it.id ?? i}`}>{it.id ? <Link href={href(it, x.key)}>{it.title}</Link> : it.title}{it.detail && <span className="muted"> · {it.detail}</span>}</li>))}</ul>}
            <p className="small"><Link href={x.link}>Open records</Link>{(x.secondary ?? []).map((sec) => <Fragment key={sec.link}> · <Link href={sec.link}>{sec.label} ({sec.count})</Link></Fragment>)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Body({ p }: { p: Panel }) {
  const t = p.totals;
  if (t.live === 0) {
    return <div className="stack"><Empty title="No live opportunities in this scope">Run a search under Discover, or widen the filters. Closed, cancelled, awarded, expired and historical records are not counted.</Empty></div>;
  }
  return (
    <div className="stack">
      <div className="grid grid-4" aria-label="Totals in scope">
        <Stat label="Live opportunities" value={t.live} note={`${t.tenders_open} open tender${t.tenders_open === 1 ? "" : "s"} · ${t.commercial} commercial · ${t.signals} signal${t.signals === 1 ? "" : "s"}`} />
        <Stat label="Markets" value={t.markets} note={p.scope} />
        <Stat label="Average score" value={<>{t.avg_score?.toFixed(1) ?? "–"}<span className="stat-unit"> / 100</span></>}
              note={`${t.strong} strong (75 or more)`} />
        <Stat label="With a relationship or introduction" value={t.with_relationships} note={`${t.deadline_30_days} with a deadline in 30 days`} />
      </div>

      <div className="grid grid-2">
        <section className="panel" aria-labelledby="cp-regions">
          <h2 id="cp-regions">Live opportunities by region</h2>
          <p className="muted small cp-sub">Each live record counts once in every region it names.</p>
          <RegionDonut regions={p.by_region} />
        </section>
        <section className="panel" aria-labelledby="cp-dist">
          <h2 id="cp-dist">Opportunities by score</h2>
          <p className="muted small cp-sub">How many live records fall in each 10-point range.</p>
          <ScoreHistogram deciles={p.score_deciles} />
          <ul className="cp-bands" aria-label="Score bands">
            {p.score_bands.map((b) => (
              <li key={b.band}><span className={`cp-band cp-band-${b.band}`}>{b.label}</span><span className="muted small">{b.range}</span><b>{b.count}</b></li>
            ))}
          </ul>
        </section>
      </div>

      <div className="grid grid-2">
        <section className="panel" aria-labelledby="cp-markets">
          <h2 id="cp-markets">By market</h2>
          <ul className="cp-list">
            {p.by_market.map((m) => (
              <li key={`${m.region}-${m.market}`}>
                <span className={`cp-dot s-${slot(m.region)}`} aria-hidden="true" />
                <div className="cp-name"><span>{m.market}</span><span className="muted small">{m.live} live · {m.tenders_open} open tenders · {m.region}</span></div>
                <span className="cp-pill">{m.live}</span><span className="cp-avg">{avg(m.avg_score)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel" aria-labelledby="cp-areas">
          <h2 id="cp-areas">By capability area</h2>
          <ul className="cp-list">
            {p.by_category.map((c) => (
              <li key={c.module}>
                <span className="cp-dot s-accent" aria-hidden="true" />
                <div className="cp-name"><span>{c.category}</span><span className="muted small">{c.live} live · {c.with_relationships} with a relationship or introduction</span></div>
                <span className="cp-pill">{c.live}</span><span className="cp-avg">{avg(c.avg_score)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="panel" aria-labelledby="cp-countries">
        <h2 id="cp-countries">By country</h2>
        <TableWrap label="Live opportunities by country">
          <table>
            <thead><tr><th>Country</th><th>Region</th><th className="num">Live</th><th className="num">Open tenders</th><th className="num">Commercial</th>
              <th className="num">Signals</th><th className="num">With relationship</th><th className="num">Average score</th><th className="num">Top score</th></tr></thead>
            <tbody>
              {p.by_country.map((c) => (
                <tr key={c.code ?? c.country}>
                  <td><span className={`cp-dot s-${slot(c.region)}`} aria-hidden="true" /> {c.country}{c.code ? <span className="muted small"> {c.code}</span> : null}</td>
                  <td>{c.region}</td><td className="num">{c.live}</td><td className="num">{c.tenders_open}</td><td className="num">{c.commercial}</td>
                  <td className="num">{c.signals}</td><td className="num">{c.with_relationships}</td>
                  <td className="num">{c.avg_score?.toFixed(1) ?? "–"}</td><td className="num">{c.top_score ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
        <p className="muted small">{p.market_rule}</p>
      </section>

      <ScoredTable p={p} />
    </div>
  );
}

function RegionDonut({ regions }: { regions: Panel["by_region"] }) {
  const total = regions.reduce((s, r) => s + r.live, 0);
  const R = 70, C = 2 * Math.PI * R, GAP = regions.length > 1 ? 3 : 0;
  let offset = 0;
  return (
    <div className="cp-donut-wrap">
      <svg viewBox="0 0 180 180" className="cp-donut" role="img" aria-label={regions.map((r) => `${r.region}: ${r.live}`).join(", ")}>
        <circle cx="90" cy="90" r={R} className="cp-donut-track" />
        {regions.map((r) => {
          const len = (r.live / total) * C;
          const seg = (
            <circle key={r.region} cx="90" cy="90" r={R} className={`cp-seg s-${slot(r.region)}`}
                    strokeDasharray={`${Math.max(len - GAP, 0.5)} ${C}`} strokeDashoffset={-offset} transform="rotate(-90 90 90)">
              <title>{`${r.region}: ${r.live} live (${pct(r.live / total)} of region entries), ${avg(r.avg_score)}`}</title>
            </circle>
          );
          offset += len;
          return seg;
        })}
        <text x="90" y="86" textAnchor="middle" className="cp-donut-num">{total}</text>
        <text x="90" y="106" textAnchor="middle" className="cp-donut-cap">region entries</text>
      </svg>
      <ul className="cp-legend">
        {regions.map((r) => (
          <li key={r.region}><span className={`cp-dot s-${slot(r.region)}`} aria-hidden="true" /><span>{r.region}</span>
            <span className="muted">{pct(r.live / total)} · {r.live} live · {avg(r.avg_score)}</span></li>
        ))}
      </ul>
    </div>
  );
}

function ScoreHistogram({ deciles }: { deciles: Panel["score_deciles"] }) {
  const max = Math.max(1, ...deciles.map((d) => d.count));
  return (
    <div className="cp-hist" role="img" aria-label={deciles.map((d) => `${d.range}: ${d.count}`).join(", ")}>
      {deciles.map((d) => (
        <div key={d.range} className="cp-hcol" title={`Score ${d.range}: ${d.count} record(s)`}>
          <span className="cp-hval">{d.count || ""}</span>
          <span className="cp-hbar" style={{ height: `${(d.count / max) * 100}%` }} />
          <span className="cp-hlab">{d.range.split("–")[0]}</span>
        </div>
      ))}
    </div>
  );
}

function ScoredTable({ p }: { p: Panel }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <section className="panel" aria-labelledby="cp-scored">
      <div className="panel-head"><h2 id="cp-scored">Score per opportunity</h2></div>
      <div className="cp-weights" aria-label="Average points per part of the score">
        {p.score_components.map((c) => (
          <div key={c.key} className="cp-weight">
            <span className="small">{c.label}</span>
            <span className="cp-meter" aria-hidden="true"><span style={{ width: `${((c.avg ?? 0) / c.max) * 100}%` }} /></span>
            <span className="small muted">avg {c.avg?.toFixed(1) ?? "–"} of {c.max}</span>
          </div>
        ))}
      </div>
      <TableWrap label="Scored opportunities">
        <table>
          <thead><tr><th className="num">Score</th><th>Opportunity</th><th>Market</th><th>Relationships</th><th>Details</th></tr></thead>
          <tbody>
            {p.scored.map((s) => (
              <Fragment key={s.id}>
                <tr>
                  <td className="num"><div className="cp-score"><b>{s.score}</b><span className="muted small">/100</span></div>
                    <span className="cp-meter" aria-hidden="true"><span style={{ width: `${s.score}%` }} /></span>
                    <span className={`cp-band cp-band-${s.band}`}>{s.band_label}</span></td>
                  <td><Link href={recordHref(s)}>{s.title}</Link>
                    <div className="small"><Tag text={s.record_type_label} /> <span className="muted">{s.organisation ?? "organisation not established"} · {s.category}</span></div></td>
                  <td>{s.countries_named.join(", ") || "Country not stated"}</td>
                  <td className="small">{s.coverage_label}</td>
                  <td><button type="button" className="btn btn-small" aria-expanded={open === s.id} aria-controls={`cp-b-${s.id}`}
                              onClick={() => setOpen(open === s.id ? null : s.id)}>{open === s.id ? "Hide" : "Breakdown"}</button></td>
                </tr>
                {open === s.id && (
                  <tr id={`cp-b-${s.id}`} className="cp-breakdown"><td colSpan={5}>
                    <ul>{s.components.map((c) => (
                      <li key={c.key}><span>{c.label}</span><b>{c.points} / {c.max}</b><span className="muted">{c.reason}</span></li>
                    ))}</ul>
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </TableWrap>
      <p className="muted small">{p.rule} Weights are provisional until WFC confirms them. {p.totals.not_scored} closed, cancelled, awarded, expired or historical record(s) in this scope are not scored.</p>
    </section>
  );
}
