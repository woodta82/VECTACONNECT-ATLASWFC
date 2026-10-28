"use client";

import { Badge, Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { dateOnly, label } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Cap = { id: string; operating_company: string; service_code: string; category: string; station: string | null; status: string;
             verification_owner: string | null; valid_from: string | null; valid_to: string | null; languages: string[] | null; commodity_restrictions: string | null };
type Cred = { id: string; operating_company: string; credential_type: string; holder_description: string | null; issued_on: string | null; expires_on: string | null };
type Feeder = { id: string; provider: string | null; origin_station: string; is_offline: boolean; gateway: string; departure_days: number[] | null;
                departure_time_local: string | null; transit_minutes: number | null; restrictions: string | null };
type Resp = { capabilities: Cap[]; credentials: Cred[]; feeders: Feeder[]; insight: Insight };

function validity(c: Cap): string {
  const today = new Date().toISOString().slice(0, 10);
  if (c.status !== "verified") return c.status;
  if (!c.valid_to) return "review_required";
  return c.valid_to < today ? "expired" : "verified";
}
function credState(c: Cred): string {
  const today = new Date().toISOString().slice(0, 10);
  if (!c.expires_on) return "unknown";
  return c.expires_on < today ? "expired" : "verified";
}

export default function CapabilitiesPage() {
  const r = useApi<Resp>("/capabilities");
  return (
    <>
      <PageHeader eyebrow="Group Capabilities" title="Verified services, stations, credentials and trucking"
                  description="Covers GSSA/TCM, handling, outsourcing (data processing, accounting, invoicing, collections) and training. 'Ready to deliver' needs verified capability with a recorded validity date and unexpired credentials; missing dates are shown as unknown." />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="capabilities" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (
        <div className="stack">
          <section className="panel">
            <h2>Capability register</h2>
            {r.data.capabilities.length === 0 ? <Empty title="Not connected">Import the group capability register.</Empty> : (
              <TableWrap label="Capabilities">
                <table>
                  <thead><tr><th>Company</th><th>Service</th><th>Category</th><th>Station</th><th>State</th><th>Valid</th><th>Verified by</th><th>Languages</th></tr></thead>
                  <tbody>{r.data.capabilities.map((c) => (
                    <tr key={c.id}><td>{c.operating_company}</td><td>{c.service_code}</td><td>{label(c.category)}</td><td>{c.station ?? "Company-wide"}</td>
                      <td><Badge value={validity(c)} /></td><td>{dateOnly(c.valid_from)} – {c.valid_to ? dateOnly(c.valid_to) : "end not recorded"}</td>
                      <td>{c.verification_owner ?? "—"}</td><td>{c.languages?.join(", ") ?? "—"}</td></tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            )}
          </section>
          <section className="panel">
            <h2>Training and credentials</h2>
            {r.data.credentials.length === 0 ? <Empty title="No credentials recorded" /> : (
              <TableWrap label="Credentials">
                <table>
                  <thead><tr><th>Company</th><th>Credential</th><th>Holder</th><th>Issued</th><th>Expires</th><th>State</th></tr></thead>
                  <tbody>{r.data.credentials.map((c) => (
                    <tr key={c.id}><td>{c.operating_company}</td><td>{c.credential_type}</td><td>{c.holder_description ?? "—"}</td>
                      <td>{dateOnly(c.issued_on)}</td><td>{c.expires_on ? dateOnly(c.expires_on) : "Not recorded"}</td><td><Badge value={credState(c)} /></td></tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            )}
          </section>
          <section className="panel">
            <h2>Trucking and gateways</h2>
            {r.data.feeders.length === 0 ? <Empty title="Not connected">Import trucking schedules to see road feeder services.</Empty> : (
              <TableWrap label="Road feeder services">
                <table>
                  <thead><tr><th>Origin station</th><th>Gateway</th><th>Provider</th><th>Days</th><th>Departs</th><th className="num">Transit</th><th>Restrictions</th></tr></thead>
                  <tbody>{r.data.feeders.map((f) => (
                    <tr key={f.id}><td>{f.origin_station}{f.is_offline ? " (offline)" : ""}</td><td>{f.gateway}</td><td>{f.provider ?? "—"}</td>
                      <td>{f.departure_days?.join(", ") ?? "—"}</td><td>{f.departure_time_local ?? "—"}</td>
                      <td className="num">{f.transit_minutes === null ? "Unknown" : `${f.transit_minutes} min`}</td><td>{f.restrictions ?? "—"}</td></tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            )}
            <p className="muted small">A feeder is recommended only when transit time and the gateway connection cutoff are both known; otherwise it is unresolved.</p>
          </section>
          <InsightMeta insight={r.data.insight} />
        </div>
      )}
    </>
  );
}
