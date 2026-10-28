"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Badge, Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { dateOnly, dateTime, label, money, num } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Org = {
  organisation: { id: string; canonical_name: string; kind: string; country: string | null; iata_code: string | null; icao_code: string | null; aliases: string[] };
  engagements: { id: string; occurred_at: string; kind: string; summary: string; person: string | null }[];
  agreements?: { id: string; operating_company: string; territories: string[]; services: string[]; effective_from: string | null; effective_to: string | null;
                 exclusivity: string; appointment_rights: string; remuneration_model: string; status: string; notice_date: string | null }[];
  third_party_appointments?: { territory: string; service: string | null; holder: string | null; exclusivity: string; valid_to: string | null }[];
  monthly?: { month: string; currency: string | null; chargeable_kg: string | null; missing_weight: number; revenue: string | null; bookings: number }[];
  insight?: Insight;
};
type Coverage = { cells: { territory: string; service: string; state: string; agreements: string[]; notes: string[] }[]; insight: Insight };
type Review = { comparison: { current: string | null; previous: string | null; year_ago: string | null; change_vs_previous: string | null;
                change_vs_year_ago: string | null; incomplete: boolean; notes: string[] };
                review_item: { figures: Record<string, string | null>; hypotheses: string[] } | null; insight: Insight };

export default function OrganisationPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const r = useApi<Org>(id ? `/organisations/${id}` : null);
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="account" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (
        <div className="stack">
          <PageHeader eyebrow={`Airlines and Forwarders · ${label(r.data.organisation.kind)}`} title={r.data.organisation.canonical_name}
                      description={r.data.organisation.aliases.length ? `Also recorded as: ${r.data.organisation.aliases.join(", ")}` : undefined} />
          {r.data.organisation.kind === "airline" && <AirlineSections id={id} org={r.data} />}
          {r.data.organisation.kind === "forwarder" && <ForwarderSections id={id} org={r.data} />}
          <section className="panel">
            <h2>Engagements</h2>
            {r.data.engagements.length === 0 ? <p className="muted">None recorded.</p> : (
              <ul>{r.data.engagements.map((e) => <li key={e.id}>{dateTime(e.occurred_at)} · {label(e.kind)} · {e.person ?? "—"}: {e.summary}</li>)}</ul>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function AirlineSections({ id, org }: { id: string; org: Org }) {
  const [territories, setTerritories] = useState("");
  const [services, setServices] = useState("");
  const ready = territories.trim() !== "" && services.trim() !== "";
  const cov = useApi<Coverage>(ready ? `/organisations/${id}/coverage${qs({ territories, services })}` : null);
  return (
    <>
      <section className="panel">
        <h2>Representation agreements</h2>
        {(org.agreements ?? []).length === 0 ? <Empty title="No agreements loaded">Import the agreements register to see coverage.</Empty> : (
          <TableWrap label="Agreements">
            <table>
              <thead><tr><th>Company</th><th>Territories</th><th>Services</th><th>Effective</th><th>Notice</th><th>Exclusivity</th><th>Appointment rights</th><th>Status</th></tr></thead>
              <tbody>{(org.agreements ?? []).map((a) => (
                <tr key={a.id}><td>{a.operating_company}</td><td>{a.territories.join(", ")}</td><td>{a.services.join(", ")}</td>
                  <td>{dateOnly(a.effective_from)} – {dateOnly(a.effective_to)}</td><td>{dateOnly(a.notice_date)}</td>
                  <td><Badge value={a.exclusivity} /></td><td><Badge value={a.appointment_rights} /></td><td><Badge value={a.status} /></td></tr>
              ))}</tbody>
            </table>
          </TableWrap>
        )}
      </section>
      <section className="panel">
        <h2>Territory × service coverage</h2>
        <div className="filters">
          <label className="field">Territory codes (comma-separated)<input className="input" value={territories} placeholder="e.g. KE,UG" onChange={(e) => setTerritories(e.target.value)} /></label>
          <label className="field">Service codes (comma-separated)<input className="input" value={services} placeholder="e.g. GSSA" onChange={(e) => setServices(e.target.value)} /></label>
        </div>
        {!ready && <p className="muted small">Enter the territories and services to evaluate.</p>}
        {ready && cov.status === "loading" && <Loading what="coverage" />}
        {cov.status === "error" && !cov.data && <ErrorState error={cov.error} onRetry={cov.reload} />}
        {cov.data && (
          <>
            <TableWrap label="Coverage matrix">
              <table>
                <thead><tr><th>Territory</th><th>Service</th><th>State</th><th>Notes</th></tr></thead>
                <tbody>{cov.data.cells.map((c) => (
                  <tr key={`${c.territory}-${c.service}`}><td>{c.territory}</td><td>{c.service}</td><td><Badge value={c.state} /></td>
                    <td className="small">{[...c.agreements.map((a) => `covered by ${a}`), ...c.notes].join("; ") || "—"}</td></tr>
                ))}</tbody>
              </table>
            </TableWrap>
            <p className="muted small">A gap is a candidate, not a recommendation. Exclusive appointments held elsewhere block; unknown exclusivity or appointment rights require review.</p>
            <InsightMeta insight={cov.data.insight} />
          </>
        )}
      </section>
    </>
  );
}

function ForwarderSections({ id, org }: { id: string; org: Org }) {
  const now = new Date();
  const [month, setMonth] = useState(`${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`);
  const rv = useApi<Review>(`/forwarders/${id}/review${qs({ month })}`);
  return (
    <>
      <section className="panel">
        <h2>Monthly activity (cancelled bookings excluded)</h2>
        {(org.monthly ?? []).length === 0 ? <Empty title="No bookings loaded for this forwarder" /> : (
          <TableWrap label="Monthly activity">
            <table>
              <thead><tr><th>Month</th><th className="num">Bookings</th><th className="num">Chargeable kg</th><th className="num">Missing weight</th><th className="num">Revenue</th></tr></thead>
              <tbody>{(org.monthly ?? []).map((m) => (
                <tr key={`${m.month}-${m.currency}`}><td>{dateOnly(m.month)}</td><td className="num">{m.bookings}</td>
                  <td className="num">{m.missing_weight > 0 ? "Incomplete" : num(m.chargeable_kg)}</td><td className="num">{m.missing_weight}</td>
                  <td className="num">{money(m.revenue, m.currency)}</td></tr>
              ))}</tbody>
            </table>
          </TableWrap>
        )}
        <InsightMeta insight={org.insight} />
      </section>
      <section className="panel">
        <h2>Period review</h2>
        <label className="field" style={{ maxWidth: 220 }}>Month
          <input type="date" className="input" value={month} onChange={(e) => setMonth(e.target.value)} />
        </label>
        {rv.data && (
          <div className="stack">
            <dl className="kv">
              <dt>Chargeable kg (this period)</dt><dd>{num(rv.data.comparison.current)}</dd>
              <dt>Previous month (same days)</dt><dd>{num(rv.data.comparison.previous)}</dd>
              <dt>Same period last year</dt><dd>{num(rv.data.comparison.year_ago)}</dd>
              <dt>Change vs previous</dt><dd>{rv.data.comparison.change_vs_previous === null ? "Not available" : `${(Number(rv.data.comparison.change_vs_previous) * 100).toFixed(1)}%`}</dd>
              <dt>Change vs last year</dt><dd>{rv.data.comparison.change_vs_year_ago === null ? "Not available" : `${(Number(rv.data.comparison.change_vs_year_ago) * 100).toFixed(1)}%`}</dd>
            </dl>
            {rv.data.review_item ? (
              <div className="notice">
                <strong>Review item: declining account</strong>
                <ul>{rv.data.review_item.hypotheses.map((h) => <li key={h}>{h}</li>)}</ul>
                <span className="small">Hypotheses are prompts for a conversation, not findings.</span>
              </div>
            ) : <p className="muted">No review item: the decline threshold is not met against both comparison periods.</p>}
            <InsightMeta insight={rv.data.insight} />
          </div>
        )}
        {rv.status === "error" && !rv.data && <ErrorState error={rv.error} onRetry={rv.reload} />}
      </section>
    </>
  );
}
