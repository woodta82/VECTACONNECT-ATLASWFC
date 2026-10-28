"use client";

import { useState } from "react";
import { Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Lane = { id: string; origin: string; destination: string; chargeable_kg: string | null; actual_kg: string | null; volume_m3: string | null;
              bookings: number; missing_chargeable: number; missing_actual: number; missing_volume: number; undated: number };
type Detail = {
  lane: { origin: string; destination: string };
  chargeable: { value: string | null; reason: string | null };
  actual_weight: { value: string | null; reason: string | null } | null;
  utilisation: { value: string | null; reason: string | null; detail: Record<string, string> };
  revenue: { by_currency: Record<string, string>; reporting_total: string | null; reporting_currency: string | null; missing_revenue: number; reason: string | null };
  capacity: { period_start: string; period_end: string; basis: string; capacity_type: string; amount: string }[];
  insight: Insight;
};

function monthBounds(d = new Date()) {
  const s = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
  const e = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0));
  return [s.toISOString().slice(0, 10), e.toISOString().slice(0, 10)] as const;
}

export default function LanesPage() {
  const [defStart, defEnd] = monthBounds();
  const [start, setStart] = useState<string>(defStart);
  const [end, setEnd] = useState<string>(defEnd);
  const [selected, setSelected] = useState<string | null>(null);
  const [basis, setBasis] = useState("weight_kg");
  const r = useApi<{ items: Lane[]; insight: Insight }>(`/lanes${qs({ start, end })}`);
  const d = useApi<Detail>(selected ? `/lanes/${selected}${qs({ start, end, basis })}` : null);

  return (
    <>
      <PageHeader eyebrow="Trade Lanes and Capacity" title="Directional lanes, bookings and capacity"
                  description="Each direction is its own lane. Utilisation is shown only when capacity is supplied on the same basis, lane and period; otherwise the reason is shown instead of a percentage." />
      <div className="filters">
        <label className="field">From<input type="date" className="input" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="field">To<input type="date" className="input" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <label className="field">Basis
          <select className="select" value={basis} onChange={(e) => setBasis(e.target.value)}>
            <option value="weight_kg">Chargeable weight (kg)</option><option value="volume_m3">Volume (m³)</option>
          </select>
        </label>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="lanes" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? (
        <Empty title="No lanes yet">Lanes are created from imported bookings and capacity with validated IATA airport codes.</Empty>
      ) : (
        <div className="stack">
          <TableWrap label="Lanes">
            <table>
              <thead><tr><th>Lane (origin → destination)</th><th className="num">Bookings</th><th className="num">Chargeable kg</th><th className="num">Actual kg</th><th className="num">Volume m³</th><th /></tr></thead>
              <tbody>{r.data.items.map((l) => (
                <tr key={l.id}>
                  <td>{l.origin} → {l.destination}{l.undated > 0 && <div className="small muted">{l.undated} booking(s) without flight date</div>}</td>
                  <td className="num">{l.bookings}</td>
                  <td className="num">{l.missing_chargeable > 0 ? `Incomplete (${l.missing_chargeable} missing)` : num(l.chargeable_kg)}</td>
                  <td className="num">{l.missing_actual > 0 ? `Incomplete (${l.missing_actual} missing)` : num(l.actual_kg)}</td>
                  <td className="num">{l.missing_volume > 0 ? `Incomplete (${l.missing_volume} missing)` : num(l.volume_m3, 1)}</td>
                  <td><button className="btn" type="button" onClick={() => setSelected(l.id)} aria-pressed={selected === l.id}>Details</button></td>
                </tr>
              ))}</tbody>
            </table>
          </TableWrap>
          <InsightMeta insight={r.data.insight} />
          {selected && d.data && (
            <section className="panel" aria-live="polite">
              <h2>{d.data.lane.origin} → {d.data.lane.destination}</h2>
              <dl className="kv">
                <dt>Booked ({basis === "weight_kg" ? "chargeable kg" : "m³"})</dt><dd>{d.data.chargeable.value !== null ? num(d.data.chargeable.value) : d.data.chargeable.reason}</dd>
                {d.data.actual_weight && (<><dt>Actual weight (kg)</dt><dd>{d.data.actual_weight.value !== null ? num(d.data.actual_weight.value) : d.data.actual_weight.reason}</dd></>)}
                <dt>Utilisation (bookable)</dt><dd>{d.data.utilisation.value !== null ? pct(d.data.utilisation.value) : `Not available: ${d.data.utilisation.reason}`}</dd>
                <dt>Revenue by currency</dt>
                <dd>{Object.keys(d.data.revenue.by_currency).length === 0 ? "None recorded" : Object.entries(d.data.revenue.by_currency).map(([c, v]) => money(v, c)).join(" · ")}
                  {d.data.revenue.missing_revenue > 0 && <div className="muted small">{d.data.revenue.missing_revenue} booking(s) without revenue</div>}</dd>
              </dl>
              <InsightMeta insight={d.data.insight} />
            </section>
          )}
          {selected && d.status === "error" && !d.data && <ErrorState error={d.error} onRetry={d.reload} />}
        </div>
      ))}
    </>
  );
}
