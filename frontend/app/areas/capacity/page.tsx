"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, AreaStatus, type DataSource, type Recommendation, RecommendationCard, SourcesLine } from "@/components/Ui";
import { api, qs } from "@/lib/api";
import { dateTime, num, pct } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Data = { status: string; gaps: string[]; method: string; period?: string; comparison_period?: string; sources?: DataSource[];
              recommendations?: (Recommendation & { lane: string })[];
              lanes: { lane_id: string; lane: string; chargeable_kg: string | null; previous_kg: string | null; trend: string | null; bookings: number;
                       missing_chargeable: number; capacity_changes: { basis: string; type: string; from: string; to: string; change: string | null }[] | null;
                       utilisation: { value: string | null; reason: string | null }; yield_per_kg: Record<string, string | null> | null; yield_note: string | null }[] };

function monthBounds(offset: number) {
  const d = new Date();
  const s = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + offset, 1));
  const e = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + offset + 1, 0));
  return [s.toISOString().slice(0, 10), e.toISOString().slice(0, 10)] as const;
}

export default function Capacity() {
  const [range, setRange] = useState(monthBounds(-1));
  const r = useApi<Data>(`/modules/capacity-lanes${qs({ start: range[0], end: range[1] })}`);
  const a = useAction();
  return (
    <>
      <PageHeader eyebrow="Capability areas · Capacity and trade lanes" title="Directional routes, trends, capacity and yield"
                  description="Each direction is a separate lane. Utilisation compares booked chargeable weight with bookable capacity on the same basis; yield is per currency and never combines currencies."
                  actions={<Link className="btn" href="/lanes">Lane detail</Link>} />
      <div className="filters">
        <label className="field">From<input className="input" type="date" value={range[0]} onChange={(e) => setRange([e.target.value, range[1]])} /></label>
        <label className="field">To<input className="input" type="date" value={range[1]} onChange={(e) => setRange([range[0], e.target.value])} /></label>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="lanes" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <>
        <AreaStatus status={r.data.status} gaps={r.data.gaps} />
        <SourcesLine sources={r.data.sources} dateTime={dateTime} />
        <ActionNote state={a} />
        {(r.data.recommendations ?? []).length > 0 && (
          <section aria-label="Lane recommendations" className="stack">
            <h2>Recommendations</h2>
            {r.data.recommendations!.map((x) => (
              <RecommendationCard key={x.key} r={x} title={x.lane} busy={a.busy}
                                  onCreate={() => a.run(() => api.post("/modules/capacity-lanes/opportunity", { key: x.key, start: range[0], end: range[1] }),
                                                        "Opportunity created for review").then(r.reload)} />
            ))}
          </section>
        )}
        {r.data.lanes.length > 0 ? (
          <TableWrap label="Lanes">
            <table><thead><tr><th>Lane</th><th className="num">Chargeable kg</th><th className="num">Trend</th><th>Capacity change</th><th className="num">Utilisation</th><th>Yield per kg</th></tr></thead>
              <tbody>{r.data.lanes.map((l) => (
                <tr key={l.lane_id}>
                  <td>{l.lane}<span className="muted small">{l.bookings} bookings{l.missing_chargeable ? ` · ${l.missing_chargeable} without weight` : ""}</span></td>
                  <td className="num">{l.chargeable_kg === null ? "No bookings" : num(l.chargeable_kg)}<span className="muted small">prev {l.previous_kg === null ? "—" : num(l.previous_kg)}</span></td>
                  <td className="num">{l.trend === null ? "Not comparable" : pct(l.trend)}</td>
                  <td className="small">{l.capacity_changes ? l.capacity_changes.map((c) => `${c.type} ${c.basis}: ${num(c.from)} → ${num(c.to)} (${pct(c.change)})`).join("; ") : "No series"}</td>
                  <td className="num">{l.utilisation.value === null ? <span className="small">{l.utilisation.reason ?? "Not available"}</span> : pct(l.utilisation.value)}</td>
                  <td className="small">{l.yield_per_kg ? Object.entries(l.yield_per_kg).map(([c, v]) => `${c} ${v ?? "n/a"}`).join(" · ") : "No revenue"}{l.yield_note && <span className="muted"> ({l.yield_note})</span>}</td>
                </tr>
              ))}</tbody></table>
          </TableWrap>
        ) : r.data.status === "ok" && <Empty title="No lanes" />}
        <p className="muted small">{r.data.period} vs {r.data.comparison_period} · {r.data.method}</p>
      </>}
    </>
  );
}
