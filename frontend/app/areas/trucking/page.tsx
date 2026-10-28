"use client";

import { useState } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, AreaStatus, type DataSource, type Recommendation, RecommendationCard, SourcesLine } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateOnly, dateTime } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Data = { status: string; gaps: string[]; method: string; ship_date?: string; sources?: DataSource[];
              stations: { station: string; name: string; country: string | null; feasible: number; unresolved: number; gap: string | null;
                          recommendation?: Recommendation;
                          options: { provider: string | null; gateway: string; connection: string; destination: string | null; result: string; reason: string;
                                     connects_on: string | null; transit_minutes: number | null; cutoff_minutes: number | null }[] }[] };

export default function Trucking() {
  const [day, setDay] = useState(new Date().toISOString().slice(0, 10));
  const r = useApi<Data>(`/modules/trucking?ship_date=${day}`);
  const a = useAction();
  return (
    <>
      <PageHeader eyebrow="Capability areas · Trucking and gateways" title="Offline stations and feasible gateway connections"
                  description="For a ship date, every road feeder from an offline station is checked against the connections at its gateway: it must run that day, arrive before the cutoff and connect within two days. Unknown transit time or cutoff is reported as unresolved, never feasible." />
      <div className="filters"><label className="field">Ship date<input className="input" type="date" value={day} onChange={(e) => setDay(e.target.value)} /></label></div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="trucking" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <>
        <AreaStatus status={r.data.status} gaps={r.data.gaps} />
        <SourcesLine sources={r.data.sources} dateTime={dateTime} />
        <ActionNote state={a} />
        {r.data.stations.length > 0 ? r.data.stations.map((s) => (
          <section key={s.station} className="panel">
            <h2>{s.name} ({s.station}) <Badge value={s.feasible ? "feasible" : s.unresolved ? "unresolved" : "infeasible"} /></h2>
            {s.recommendation && (
              <RecommendationCard r={s.recommendation} title={`Coverage from ${s.station}`} busy={a.busy}
                                  onCreate={() => a.run(() => api.post("/modules/trucking/opportunity", { key: s.recommendation!.key, ship_date: day }),
                                                        "Opportunity created for review").then(r.reload)} />
            )}
            {s.gap ? <p className="muted">{s.gap}</p> : (
              <TableWrap label={`Connections from ${s.station}`}>
                <table><thead><tr><th>Feeder</th><th>Gateway → connection</th><th>Result</th><th>Why</th></tr></thead>
                  <tbody>{s.options.map((o, i) => (
                    <tr key={i}><td>{o.provider ?? "Provider"}<span className="muted small">{o.transit_minutes ?? "?"} min transit</span></td>
                      <td>{o.gateway} → {o.connection}{o.destination ? ` to ${o.destination}` : ""}<span className="muted small">cutoff {o.cutoff_minutes ?? "unknown"} min</span></td>
                      <td><Badge value={o.result} />{o.connects_on && <span className="muted small">{dateOnly(o.connects_on)}</span>}</td>
                      <td className="small">{o.reason}</td></tr>
                  ))}</tbody></table>
              </TableWrap>
            )}
          </section>
        )) : r.data.status === "ok" && <Empty title="No offline stations" />}
        <p className="muted small">{r.data.method}</p>
      </>}
    </>
  );
}
