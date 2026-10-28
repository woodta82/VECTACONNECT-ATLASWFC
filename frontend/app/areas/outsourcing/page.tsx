"use client";

import Link from "next/link";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { AreaStatus, type DataSource, SourcesLine } from "@/components/Ui";
import { dateTime, deadline, type DeadlineInfo } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Data = { status: string; gaps: string[]; method: string; sources?: DataSource[];
              demand: { rank?: number; rank_reason?: string; missing?: string[];  opportunity_id: string; title: string; service: string | null; countries: string[]; deadline_utc: string | null; deadline: DeadlineInfo | null;
                        qualification_status: string; evidence: string | null; gap: string | null;
                        matches: { operating_company: string; station: string | null; readiness: string; blockers: string[]; unknowns: string[] }[] }[];
              not_live?: { opportunity_id: string; title: string; why: string }[] };

export default function Outsourcing() {
  const r = useApi<Data>("/modules/outsourcing-training");
  return (
    <>
      <PageHeader eyebrow="Capability areas · Outsourcing and training" title="Verified demand matched to WFC resources"
                  description="Demand comes from supported tenders for handling, data processing, accounting, invoicing, collections and training. Each is matched to WFC companies on verified capability, station, delivery date and current credentials."
                  actions={<Link className="btn" href="/discovery">Search for demand</Link>} />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="demand" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <>
        <AreaStatus status={r.data.status} gaps={r.data.gaps} />
        <SourcesLine sources={r.data.sources} dateTime={dateTime} />
        {r.data.demand.length > 0 ? (
          <TableWrap label="Demand and matches">
            <table><thead><tr><th>Demand</th><th>Service · countries</th><th>Deadline</th><th>WFC match</th></tr></thead>
              <tbody>{r.data.demand.map((d) => (
                <tr key={d.opportunity_id}>
                  <td>{d.rank ? `${d.rank}. ` : ""}<Link href={`/opportunities/${d.opportunity_id}`}>{d.title}</Link> <Badge value={d.qualification_status} />{d.rank_reason && <span className="muted small">{d.rank_reason}{d.missing && d.missing.length > 0 ? ` · missing: ${d.missing.join("; ")}` : ""}</span>}</td>
                  <td>{d.service ?? "Service not established"}<span className="muted small">{d.countries.join(", ")}</span></td>
                  <td>{deadline(d.deadline_utc, null, d.deadline)}</td>
                  <td className="small">{d.gap ?? d.matches.map((m) => (
                    <div key={`${m.operating_company}-${m.station}`}><Badge value={m.readiness} /> {m.operating_company}{m.station ? ` at ${m.station}` : " (company level)"}
                      {(m.blockers.length > 0 || m.unknowns.length > 0) && <span className="muted"> · {[...m.blockers, ...m.unknowns].join("; ")}</span>}</div>
                  ))}</td>
                </tr>
              ))}</tbody></table>
          </TableWrap>
        ) : r.data.status === "ok" && <Empty title="No verified demand" />}
        {(r.data.not_live ?? []).length > 0 && (
          <details className="small"><summary>{r.data.not_live!.length} record(s) not shown as live demand</summary>
            <ul>{r.data.not_live!.map((n) => <li key={n.opportunity_id}><Link href={`/opportunities/${n.opportunity_id}`}>{n.title}</Link>: {n.why}</li>)}</ul>
          </details>
        )}
        <p className="muted small">{r.data.method}</p>
      </>}
    </>
  );
}
