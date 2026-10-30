"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Tag } from "@/components/Records";
import { useGeography } from "@/components/Geo";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { KINDS } from "@/components/Research";
import { RelationshipsViews } from "@/components/RelationshipsViews";
import { qs } from "@/lib/api";
import { dateOnly } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Row = { id: string; canonical_name: string; kind: string; kind_label: string; country: string | null; country_name: string | null; website: string | null;
             origin: string; airport_iata: string | null; carrier_type: string | null; carrier_type_label: string | null; iata_code: string | null;
             freight_scope: string; freight_scope_label: string; in_cargo_scope: boolean; airports_served: string | null; contact_url: string | null;
             state: string; state_label: string; emails: number; emails_current: number; relationships: number; relationships_current: number; represented_by: number;
             people: number; evidence: number; opportunities: number; best_relevance: number | null; last_researched_at: string | null; verified_at: string | null };
type Page = { items: Row[]; total: number; states: Record<string, string> };

const STATE_TONE: Record<string, string> = { verified: "b-good", awaiting_verification: "b-warn", researched: "b-info", recorded: "b-none" };
const ORIGINS: [string, string][] = [["", "Any origin"], ["discovery", "Found by research"], ["supplied", "Supplied dataset"], ["import", "WFC data import"],
                                     ["manual", "Added by a person"], ["research", "Opportunity research"]];

export default function CompaniesPage() {
  return <Suspense fallback={<Loading what="companies" />}><Companies /></Suspense>;
}

function Companies() {
  const sp = useSearchParams();
  const [kind, setKind] = useState(sp.get("kind") ?? "");
  const [country, setCountry] = useState(sp.get("country") ?? "");
  const [airport, setAirport] = useState(sp.get("airport") ?? "");
  const [origin, setOrigin] = useState(sp.get("origin") ?? "");
  const carrier = sp.get("carrier_type") ?? "";
  const [state, setState] = useState(sp.get("state") ?? "");
  const [q, setQ] = useState(sp.get("q") ?? "");
  const [sort, setSort] = useState(sp.get("sort") ?? "name");
  const [scope, setScope] = useState(sp.get("scope") ?? "cargo");
  const discovery = sp.get("discovery") ?? "";
  const geo = useGeography();
  const r = useApi<Page>(`/companies${qs({ kind, country, airport, origin, carrier_type: carrier, state, q, sort, discovery, scope: scope === "all" ? "" : scope, limit: 200 })}`);
  return (
    <>
      <RelationshipsViews current="companies" />
      <PageHeader eyebrow="Relationships · Companies" title="Who operates here and what can they do"
                  description="Every organisation ATLAS has found in the open market, read from a supplied dataset, or loaded from WFC data: official website, published addresses, locations, services, parent or group, represented airlines or partners, relevant people and the evidence for each fact. Supplied data is shown as awaiting verification until research sources it or a person verifies it; a relevant company is not an opportunity."
                  actions={<Link className="btn btn-primary" href="/discovery">Research companies</Link>} />
      <div className="filters" role="search">
        <label className="field">Search<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, alias, represented airline or code" /></label>
        <label className="field">Kind<select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All kinds</option>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}<option value="authority">Authority or regulator</option><option value="other">Other</option></select></label>
        <label className="field">Country<select className="select" value={country} onChange={(e) => setCountry(e.target.value)}>
          <option value="">Any country</option>{(geo?.countries ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></label>
        <label className="field">Airport (IATA)<input className="input" value={airport} maxLength={3} onChange={(e) => setAirport(e.target.value.toUpperCase())} placeholder="e.g. BRU" /></label>
        <label className="field">Status<select className="select" value={state} onChange={(e) => setState(e.target.value)}>
          <option value="">Any status</option><option value="researched">Researched — not yet verified</option><option value="awaiting_verification">Supplied — awaiting verification</option>
          <option value="verified">Verified</option><option value="unverified">Anything not verified</option></select></label>
        <label className="field">Origin<select className="select" value={origin} onChange={(e) => setOrigin(e.target.value)}>
          {ORIGINS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Freight scope<select className="select" value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="cargo">Air cargo scope (passenger-only excluded)</option><option value="belly">Belly cargo (passenger aircraft)</option>
          <option value="freighter">Freighter cargo</option><option value="mixed">Mixed cargo operations</option><option value="cargo_services">Cargo services (non-airline)</option>
          <option value="unresolved">Unresolved</option><option value="passenger_only">Passenger-only (outside scope)</option><option value="all">Everything</option></select></label>
        <label className="field">Sort by<select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="name">Name (A–Z)</option><option value="relevance">Best relevance to a brief</option><option value="recent">Most recently updated</option></select></label>
      </div>
      {discovery && <p className="small muted">Showing the companies of one research run. <Link href="/companies">Show all companies</Link></p>}
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="companies" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? (
        <Empty title="No companies match">Use <Link href="/discovery">Discover → Companies</Link> to research a country, region or airport, or load a supplied list under <Link href="/data-sources">Data sources</Link>.</Empty>
      ) : (
        <TableWrap label="Companies">
          <table>
            <thead><tr><th>Company</th><th>Kind / freight scope</th><th>Country / airports</th><th>Status</th><th>Website</th><th className="num">E-mail</th><th className="num">Represents</th><th className="num">People</th><th className="num">Evidence</th><th className="num">Opportunities</th></tr></thead>
            <tbody>{r.data.items.map((o) => (
              <tr key={o.id}>
                <td><Link href={`/companies/${o.id}`}>{o.canonical_name}</Link>{o.best_relevance !== null && <div className="small muted">relevance {o.best_relevance}/100</div>}</td>
                <td className="small">{o.kind_label}<div className={o.in_cargo_scope ? "muted" : "action-error"}>{o.freight_scope_label}</div>{o.iata_code && <div className="muted">{o.iata_code}</div>}</td>
                <td className="small">{o.country_name ?? <span className="muted">not established</span>}{(o.airports_served || o.airport_iata) && <div className="muted">{o.airports_served ?? o.airport_iata}</div>}</td>
                <td><Tag text={o.state_label} tone={STATE_TONE[o.state]} />
                  <div className="small muted">{o.verified_at ? `verified ${dateOnly(o.verified_at)}` : o.last_researched_at ? `researched ${dateOnly(o.last_researched_at)}` : ""}</div></td>
                <td className="small">{o.website ? <a href={o.website} target="_blank" rel="noreferrer noopener">{o.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}</a> : <span className="muted">—</span>}</td>
                <td className="num">{o.emails}{o.emails > 0 && o.emails_current < o.emails && <span className="muted small">{o.emails - o.emails_current} supplied</span>}</td>
                <td className="num">{o.relationships}{o.relationships > 0 && o.relationships_current < o.relationships && <span className="muted small">{o.relationships - o.relationships_current} supplied</span>}
                  {o.represented_by > 0 && <span className="muted small">represented by {o.represented_by}</span>}</td>
                <td className="num">{o.people}</td><td className="num">{o.evidence}</td><td className="num">{o.opportunities}</td>
              </tr>
            ))}</tbody>
          </table>
        </TableWrap>
      ))}
      {r.data && <p className="small muted">{r.data.total} compan{r.data.total === 1 ? "y" : "ies"}. WFC airline agreements and forwarder figures stay under <Link href="/airlines-forwarders">Airlines and Forwarders</Link>.</p>}
    </>
  );
}
