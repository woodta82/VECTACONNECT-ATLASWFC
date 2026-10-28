"use client";

import Link from "next/link";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, AreaStatus, type DataSource, SourcesLine } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Data = { status: string; gaps: string[]; method: string; sources?: DataSource[];
              candidates: { rank?: number; rank_reason?: string; missing?: string[];  key: string; airline: string | null; territory: string; territory_name: string; service: string; operating_company: string;
                            station: string | null; actionable: boolean; blockers: string[]; unknowns: string[]; airline_bookings: number; existing: string | null }[] };

export default function AccountGrowth() {
  const r = useApi<Data>("/modules/account-growth");
  const a = useAction();
  return (
    <>
      <PageHeader eyebrow="Capability areas · Account growth" title="Supported territory and service expansion"
                  description="For each airline WFC already represents, territories where a WFC company holds verified capability for the same service. Appointment rights, third-party appointments, capability validity and credentials are checked; nothing is inferred from public sources." />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="account growth" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <>
        <AreaStatus status={r.data.status} gaps={r.data.gaps} />
        <SourcesLine sources={r.data.sources} dateTime={dateTime} />
        <ActionNote state={a} />
        {r.data.candidates.length > 0 ? (
          <TableWrap label="Expansion candidates">
            <table><thead><tr><th>Airline</th><th>Territory</th><th>Service · company</th><th>Ready?</th><th>Blockers / unknowns</th><th className="num">Bookings</th><th /></tr></thead>
              <tbody>{r.data.candidates.map((c) => (
                <tr key={c.key}>
                  <td>{c.rank ? `${c.rank}. ` : ""}{c.airline}{c.rank_reason && <span className="muted small">{c.rank_reason}</span>}</td><td>{c.territory_name} ({c.territory})</td>
                  <td>{c.service} · {c.operating_company}<span className="muted small">{c.station ? `station ${c.station}` : "company level"}</span></td>
                  <td><Badge value={c.actionable ? "ready" : c.blockers.length ? "blocked" : "review_required"} /></td>
                  <td className="small">{[...c.blockers, ...c.unknowns].join("; ") || "—"}</td>
                  <td className="num">{c.airline_bookings}</td>
                  <td>{c.existing ? <Link href={`/opportunities/${c.existing}`}>Open opportunity</Link> : (
                    <button className="btn" type="button" disabled={a.busy}
                            onClick={() => a.run(() => api.post<{ opportunity_id: string }>("/modules/account-growth/opportunity", { key: c.key }), "Opportunity created").then(r.reload)}>
                      Create opportunity
                    </button>)}</td>
                </tr>
              ))}</tbody></table>
          </TableWrap>
        ) : r.data.status === "ok" && <Empty title="No candidates" />}
        <p className="muted small">{r.data.method}</p>
      </>}
    </>
  );
}
