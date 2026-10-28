"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { label } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Row = { id: string; canonical_name: string; kind: string; country: string | null; iata_code: string | null; icao_code: string | null;
             active_agreements: number; bookings: number };
type Page = { items: Row[]; total: number; limit: number; offset: number };

export default function AccountsPage() {
  const [kind, setKind] = useState("airline");
  const [q, setQ] = useState("");
  const r = useApi<Page>(`/organisations${qs({ kind, q, limit: 100 })}`);
  return (
    <>
      <PageHeader eyebrow="Airlines and Forwarders" title="Accounts, coverage and representation"
                  description="One organisation record per legal or trading entity, with aliases. Airline pages show territory-by-service coverage; forwarder pages show period comparisons." />
      <div className="filters" role="search">
        <label className="field">Type
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
            {["airline", "forwarder", "gssa", "trucking_provider", "airport_operator", "shipper", "other"].map((k) => <option key={k} value={k}>{label(k)}</option>)}
          </select>
        </label>
        <label className="field">Search name or alias
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="accounts" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? (
        <Empty title={`No ${label(kind).toLowerCase()} records loaded`}>Agreements and bookings imports create these records with provenance.</Empty>
      ) : (
        <TableWrap label="Organisations">
          <table>
            <thead><tr><th>Name</th><th>Type</th><th>Country</th><th>IATA / ICAO</th><th className="num">Active agreements</th><th className="num">Bookings</th></tr></thead>
            <tbody>{r.data.items.map((o) => (
              <tr key={o.id}>
                <td><Link href={`/airlines-forwarders/${o.id}`}>{o.canonical_name}</Link></td>
                <td>{label(o.kind)}</td><td>{o.country ?? "—"}</td>
                <td>{[o.iata_code, o.icao_code].filter(Boolean).join(" / ") || "—"}</td>
                <td className="num">{o.active_agreements}</td><td className="num">{o.bookings}</td>
              </tr>
            ))}</tbody>
          </table>
        </TableWrap>
      ))}
    </>
  );
}
