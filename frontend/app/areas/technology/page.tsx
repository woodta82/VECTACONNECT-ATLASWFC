"use client";

import { useState } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, AreaStatus, type DataSource, type Recommendation, RecommendationCard, Section, SourcesLine } from "@/components/Ui";
import { api, qs } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Data = { status: string; gaps: string[]; method: string; period?: string; sources?: DataSource[];
              solutions?: (Recommendation & { channel?: string; forwarder?: string })[];
              adoption: { forwarder_id: string; forwarder: string; bookings: number; digital_events: number; digital_bookings: number; integration_failures: number; adoption_gap: boolean }[];
              funnels: { channel: string; status: string; stages: Record<string, number>; conversion: Record<string, string>; limitations: string[] }[];
              integration_failures?: { channel: string; failures: number }[];
              combined: { forwarder_id: string; forwarder: string; gateways: string[]; bookings_via_gateways: number }[] };

export default function Technology() {
  const d = new Date();
  const [start, setStart] = useState(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - 1, 1)).toISOString().slice(0, 10));
  const [end, setEnd] = useState(new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 0)).toISOString().slice(0, 10));
  const r = useApi<Data>(`/modules/technology${qs({ start, end })}`);
  const a = useAction();
  return (
    <>
      <PageHeader eyebrow="Capability areas · Technology and solutions" title="Digital adoption, booking friction, combined services"
                  description="Built only from loaded bookings, digital-channel events and road feeder schedules. A funnel whose events cannot be linked says so instead of showing a rate." />
      <div className="filters">
        <label className="field">From<input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="field">To<input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="technology" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <div className="stack">
        <AreaStatus status={r.data.status} gaps={r.data.gaps} />
        <SourcesLine sources={r.data.sources} dateTime={dateTime} />
        <ActionNote state={a} />
        {r.data.status === "ok" && <>
          <Section title="Solution candidates (ranked)">
            {(r.data.solutions ?? []).length === 0 ? <Empty title="No candidates in the period" /> : r.data.solutions!.map((x) => (
              <RecommendationCard key={x.key} r={x} title={x.forwarder ?? x.channel ?? x.kind} busy={a.busy}
                                  onCreate={() => a.run(() => api.post("/modules/technology/opportunity", { key: x.key, start, end }),
                                                        "Opportunity created for review").then(r.reload)} />
            ))}
          </Section>
          <Section title="Digital adoption by forwarder">
            {r.data.adoption.length === 0 ? <Empty title="No forwarder activity in the period" /> : (
              <TableWrap label="Adoption"><table><thead><tr><th>Forwarder</th><th className="num">Bookings</th><th className="num">Digital events</th><th className="num">Integration failures</th><th>Gap</th></tr></thead>
                <tbody>{r.data.adoption.map((x) => (
                  <tr key={x.forwarder_id}><td>{x.forwarder}</td><td className="num">{x.bookings}</td><td className="num">{x.digital_events}</td>
                    <td className="num">{x.integration_failures}</td><td>{x.adoption_gap ? <Badge value="gap" /> : "—"}</td></tr>
                ))}</tbody></table></TableWrap>
            )}
          </Section>
          <Section title="Booking friction by channel">
            {r.data.funnels.length === 0 ? <Empty title="No channels" /> : r.data.funnels.map((f) => (
              <div key={f.channel} className="claim-card">
                <div className="inline"><strong>{f.channel}</strong> <Badge value={f.status} /></div>
                {f.status === "computed" ? (
                  <p className="small">{f.stages.quote_requests} quote requests → {f.stages.quoted} quoted → {f.stages.booked} booked · quote rate {f.conversion.quote_rate} · booking rate {f.conversion.booking_rate}</p>
                ) : null}
                {f.limitations.length > 0 && <p className="muted small">{f.limitations.join("; ")}</p>}
              </div>
            ))}
          </Section>
          <Section title="Combined-service candidates (digital booking + road feeder)">
            {r.data.combined.length === 0 ? <Empty title="No candidates" /> : (
              <TableWrap label="Combined-service candidates"><table><thead><tr><th>Forwarder</th><th>Gateways also served by road feeder</th><th className="num">Bookings via them</th></tr></thead>
                <tbody>{r.data.combined.map((c) => <tr key={c.forwarder_id}><td>{c.forwarder}</td><td>{c.gateways.join(", ")}</td><td className="num">{c.bookings_via_gateways}</td></tr>)}</tbody></table></TableWrap>
            )}
          </Section>
        </>}
        <p className="muted small">{r.data.period} · {r.data.method}</p>
      </div>}
    </>
  );
}
