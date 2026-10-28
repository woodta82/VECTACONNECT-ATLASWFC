"use client";

import { useState } from "react";
import { CountryPicker, RegionSelect } from "@/components/Geo";
import { Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { MODULES } from "@/lib/constants";
import { dateTime, label, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Conversion = { status: "converted"; currency: string; total: string; basis: string[] } | { status: "not_converted"; reason: string };
type Pipeline = { by_currency: Record<string, string>; counted: string[]; excluded: Record<string, string>; unqualified: string[]; note: string;
                 referral_attribution?: Record<string, { company: string | null; referred_from: string | null }>;
                  conversion: Conversion | null; insight: Insight };
type Audit = { items: { id: number; occurred_at: string; event_type: string; session_ref: string | null; entity_type: string | null; entity_id: string | null }[] };
type Companies = { companies: { id: string; name: string }[] };
type Funnel = { channels: { channel: string; events: number; latest: string }[];
                funnel: { status: string; stages: Record<string, number>; conversion: Record<string, string>; limitations: string[] } | null;
                integration_failures: { channel: string; failures: number }[]; insight: Insight };

export default function ReportsPage() {
  const [kind, setKind] = useState("potential");
  const [module, setModule] = useState("");
  const [company, setCompany] = useState("");
  const companies = useApi<Companies>("/capabilities");
  const [countries, setCountries] = useState<string[]>([]);
  const [region, setRegion] = useState("");
  const [reporting, setReporting] = useState("");
  const [fx, setFx] = useState("");
  const [fxApplied, setFxApplied] = useState("");
  const geo = { countries: countries.join(","), region };
  const p = useApi<Pipeline>(`/reports/pipeline${qs({ kind, module, company, ...geo, reporting_currency: reporting.length === 3 ? reporting : "", fx: fxApplied })}`);
  const audit = useApi<Audit>("/audit?limit=50");
  const [channel, setChannel] = useState("");
  const today = new Date().toISOString().slice(0, 10);
  const monthStart = `${today.slice(0, 8)}01`;
  const funnel = useApi<Funnel>(`/technology/funnel${qs({ start: monthStart, end: today, channel })}`);

  return (
    <>
      <PageHeader eyebrow="Reports" title="Pipeline economics and audit"
                  description="Retained contribution only, never airline revenue. Currencies are never combined. Competing alternatives count once. Company filters organise the report; they do not restrict access."
                  actions={<a className="btn" href={`/api/reports/opportunities.csv${qs({ module, company, ...geo })}`}>Export opportunities (CSV)</a>} />
      <div className="filters">
        <label className="field">Value
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="potential">Potential</option><option value="won">Won</option><option value="realised">Realised</option>
          </select>
        </label>
        <label className="field">Module
          <select className="select" value={module} onChange={(e) => setModule(e.target.value)}>
            <option value="">All modules</option>{MODULES.map((m) => <option key={m} value={m}>{label(m)}</option>)}
          </select>
        </label>
        <label className="field">Operating company
          <select className="select" value={company} onChange={(e) => setCompany(e.target.value)}>
            <option value="">All companies</option>
            {companies.data?.companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <RegionSelect value={region} onChange={setRegion} />
        <div style={{ flex: "1 1 240px" }}><CountryPicker value={countries} onChange={setCountries} /></div>
      </div>
      {p.stale && <StaleBanner onRetry={p.reload} />}
      {p.status === "loading" && <Loading what="pipeline" />}
      {p.status === "error" && !p.data && <ErrorState error={p.error} onRetry={p.reload} />}
      {p.data && (
        <section className="panel">
          <h2>Retained contribution by currency</h2>
          {Object.keys(p.data.by_currency).length === 0 ? (
            <Empty title="No qualified values">{p.data.unqualified.length} opportunit{p.data.unqualified.length === 1 ? "y has" : "ies have"} unknown remuneration terms and are shown as unqualified.</Empty>
          ) : (
            <TableWrap label="Contribution by currency">
              <table>
                <thead><tr><th>Currency</th><th className="num">Retained contribution</th></tr></thead>
                <tbody>{Object.entries(p.data.by_currency).map(([c, v]) => <tr key={c}><td>{c}</td><td className="num">{money(v, c)}</td></tr>)}</tbody>
              </table>
            </TableWrap>
          )}
          <form className="filters" aria-label="Currency conversion" onSubmit={(e) => { e.preventDefault(); setFxApplied(fx); }}>
            <label className="field">Combine into (optional)
              <input className="input" value={reporting} maxLength={3} placeholder="e.g. USD" onChange={(e) => setReporting(e.target.value.toUpperCase())} style={{ maxWidth: 110 }} />
            </label>
            <label className="field" style={{ flex: "1 1 320px" }}>Explicit dated rates to that currency (CCY:rate:YYYY-MM-DD:source; …)
              <input className="input" value={fx} placeholder="AED:0.2723:2026-10-26:Central bank fixing" onChange={(e) => setFx(e.target.value)} />
            </label>
            <button className="btn" type="submit" disabled={!reporting}>Apply basis</button>
          </form>
          {p.data.conversion && (p.data.conversion.status === "converted" ? (
            <div className="notice notice-info" role="status">
              Combined: <strong>{money(p.data.conversion.total, p.data.conversion.currency)}</strong> on this basis — {p.data.conversion.basis.join("; ") || "single currency"}.
              Per-currency figures above remain the source of truth.
            </div>
          ) : <div className="notice" role="status">Not combined: {p.data.conversion.reason}</div>)}
          <p className="small muted">{p.data.counted.length} counted · {Object.keys(p.data.excluded).length} excluded as duplicates or competing alternatives · {p.data.unqualified.length} unqualified</p>
          {Object.keys(p.data.referral_attribution ?? {}).length > 0 && (
            <p className="small muted">{Object.keys(p.data.referral_attribution ?? {}).length} referred opportunit{Object.keys(p.data.referral_attribution ?? {}).length === 1 ? "y" : "ies"} attributed to the receiving company: {Object.values(p.data.referral_attribution ?? {}).map((x) => `${x.referred_from ?? "?"} → ${x.company ?? "?"}`).join("; ")}.</p>
          )}
          <details className="tech-note small"><summary>How these totals are counted</summary><p className="muted">{p.data.note}</p></details>
          <InsightMeta insight={p.data.insight} />
        </section>
      )}
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Digital channels and booking funnel (this month)</h2>
        {funnel.status === "loading" && <Loading what="channel data" />}
        {funnel.status === "error" && !funnel.data && <ErrorState error={funnel.error} onRetry={funnel.reload} />}
        {funnel.data && (funnel.data.channels.length === 0 ? (
          <Empty title="Not connected">No digital channel events have been loaded. A booking funnel is never estimated without linked events.</Empty>
        ) : (
          <div className="stack">
            <label className="field" style={{ maxWidth: 260 }}>Channel
              <select className="select" value={channel} onChange={(e) => setChannel(e.target.value)}>
                <option value="">Choose a channel</option>
                {funnel.data.channels.map((c) => <option key={c.channel} value={c.channel}>{c.channel} ({c.events} events)</option>)}
              </select>
            </label>
            {funnel.data.funnel && (funnel.data.funnel.status === "computed" ? (
              <dl className="kv">
                <dt>Quote requests</dt><dd>{funnel.data.funnel.stages.quote_requests}</dd>
                <dt>Quoted</dt><dd>{funnel.data.funnel.stages.quoted} (rate {funnel.data.funnel.conversion.quote_rate})</dd>
                <dt>Booked</dt><dd>{funnel.data.funnel.stages.booked} (rate {funnel.data.funnel.conversion.booking_rate})</dd>
              </dl>
            ) : (
              <div className="notice">Funnel not shown ({label(funnel.data.funnel.status)}): {funnel.data.funnel.limitations.join("; ")}</div>
            ))}
            {funnel.data.integration_failures.length > 0 && (
              <p className="small">Integration failures: {funnel.data.integration_failures.map((f) => `${f.channel} ${f.failures}`).join(" · ")}</p>
            )}
          </div>
        ))}
        {funnel.data && <InsightMeta insight={funnel.data.insight} />}
      </section>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Audit trail (latest 50)</h2>
        {audit.status === "loading" && <Loading what="audit" />}
        {audit.status === "error" && !audit.data && <ErrorState error={audit.error} onRetry={audit.reload} />}
        {audit.data && (
          <TableWrap label="Audit trail">
            <table>
              <thead><tr><th>When</th><th>Event</th><th>Entity</th><th>Session</th></tr></thead>
              <tbody>{audit.data.items.map((a) => (
                <tr key={a.id}><td>{dateTime(a.occurred_at)}</td><td>{label(a.event_type)}</td><td>{a.entity_type ? `${a.entity_type} ${a.entity_id ?? ""}` : "—"}</td><td className="small">{a.session_ref ?? "—"}</td></tr>
              ))}</tbody>
            </table>
          </TableWrap>
        )}
        <p className="muted small">Events are attributed to the shared account and a session reference, not to an individual.</p>
      </section>
    </>
  );
}
