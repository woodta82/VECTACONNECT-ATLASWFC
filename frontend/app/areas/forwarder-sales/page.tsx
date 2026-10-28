"use client";

import Link from "next/link";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, AreaStatus, type DataSource, SourcesLine } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateOnly, dateTime, num, pct } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Data = { status: string; gaps: string[]; method: string; sources?: DataSource[]; period?: string;
              accounts: { rank?: number; rank_reason?: string; missing?: string[];  key: string; forwarder_id: string; forwarder: string; last_flight: string | null; dormant: boolean; bookings_12m: number;
                          comparison: { current: string | null; previous: string | null; change_vs_previous: string | null; change_vs_year_ago: string | null; notes: string[] };
                          conversion: string | null; decided_quotes: number; lost_on_price: number; review_reasons: string[]; needs_review: boolean; existing: string | null }[] };

export default function ForwarderSales() {
  const r = useApi<Data>("/modules/forwarder-sales");
  const a = useAction();
  return (
    <>
      <PageHeader eyebrow="Capability areas · Forwarder sales" title="Dormant and declining accounts, quote conversion"
                  description="Accounts are ordered for review: those needing review first, dormant accounts next, then by 12-month volume. Reasons are figures from loaded bookings and quotes; hypotheses are labelled as such." />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="forwarder accounts" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <>
        <AreaStatus status={r.data.status} gaps={r.data.gaps} />
        <SourcesLine sources={r.data.sources} dateTime={dateTime} />
        <ActionNote state={a} />
        {r.data.accounts.length > 0 ? (
          <TableWrap label="Forwarder accounts">
            <table><thead><tr><th>Forwarder</th><th>Last flight</th><th className="num">Chargeable kg</th><th className="num">Change</th><th className="num">Conversion (90 days)</th><th>Why review</th><th /></tr></thead>
              <tbody>{r.data.accounts.map((x) => (
                <tr key={x.key}>
                  <td>{x.forwarder}{x.dormant && <> <Badge value="dormant" /></>}<span className="muted small">{x.bookings_12m} bookings in 12 months</span></td>
                  <td>{dateOnly(x.last_flight)}</td>
                  <td className="num">{num(x.comparison.current)}<span className="muted small">prev {num(x.comparison.previous)}</span></td>
                  <td className="num">{pct(x.comparison.change_vs_year_ago ?? x.comparison.change_vs_previous)}</td>
                  <td className="num">{x.conversion === null ? "Not available" : pct(x.conversion)}<span className="muted small">{x.decided_quotes} decided · {x.lost_on_price} lost on price</span></td>
                  <td className="small">{x.review_reasons.join("; ") || "—"}{x.rank && <span className="muted"> · rank {x.rank}: {x.rank_reason}</span>}{x.missing && x.missing.length > 0 && <span className="muted"> · missing: {x.missing.join("; ")}</span>}</td>
                  <td>{x.existing ? <Link href={`/opportunities/${x.existing}`}>Open review</Link> : x.needs_review && (
                    <button className="btn" type="button" disabled={a.busy}
                            onClick={() => a.run(() => api.post("/modules/forwarder-sales/opportunity", { key: x.key }), "Account review created").then(r.reload)}>
                      Create account review
                    </button>)}</td>
                </tr>
              ))}</tbody></table>
          </TableWrap>
        ) : r.data.status === "ok" && <Empty title="No forwarder accounts" />}
        <p className="muted small">{r.data.period} · {r.data.method}</p>
      </>}
    </>
  );
}
