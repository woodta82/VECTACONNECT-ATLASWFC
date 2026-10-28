"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, REGION_LABELS, type Organisation, type RegionKey } from "@/lib/api";
import PageHeader from "../components/PageHeader";

const ORG_TYPE_LABELS: Record<string, string> = {
  federation: "Federation",
  club: "Club",
  government: "Government",
  brand: "Brand",
  venue: "Venue",
  other: "Other",
};

export default function OrganisationsPage() {
  const [orgs, setOrgs] = useState<Organisation[] | null>(null);
  const [q, setQ] = useState("");
  const [region, setRegion] = useState<RegionKey | "">("");
  const [error, setError] = useState<string | null>(null);

  function load() {
    return api
      .organisations({ q: q || undefined, region: region || undefined })
      .then((data) => {
        setOrgs(data);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load organisations"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, region]);

  return (
    <div>
      <PageHeader
        eyebrow="Organisations"
        title="Organisation directory"
        description="Federations, clubs, governments, brands and venues discovered through the pipeline — with everything ATLAS knows about each one in one place."
      />

      {error && (
        <div className="panel p-5 mb-5" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Couldn&apos;t load organisations
          </p>
          <p className="text-sm text-muted mb-3">{error}</p>
          <button onClick={load} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      <div className="panel p-3 mb-5 flex flex-wrap items-end gap-3">
        <div className="field flex-1 min-w-[200px]">
          <label htmlFor="org-search" className="field-label">Search</label>
          <input id="org-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Organisation name…" className="input" />
        </div>
        <div className="field">
          <label htmlFor="org-region" className="field-label">Region</label>
          <select id="org-region" value={region} onChange={(e) => setRegion(e.target.value as RegionKey | "")} className="input">
            <option value="">All regions</option>
            {(Object.keys(REGION_LABELS) as RegionKey[]).map((r) => (
              <option key={r} value={r}>{REGION_LABELS[r]}</option>
            ))}
          </select>
        </div>
      </div>

      {orgs && orgs.length === 0 && (
        <div className="panel p-10 text-center text-sm text-muted">
          No organisations match yet — they appear automatically as opportunities are discovered.
        </div>
      )}

      {orgs && orgs.length > 0 && (
        <div className="panel overflow-hidden overflow-x-auto">
          <table className="data-table">
            <caption className="sr-only">Organisation directory</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Type</th>
                <th scope="col">Region</th>
                <th scope="col">Market</th>
                <th scope="col">Opportunities</th>
                <th scope="col">Contacts</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((o) => (
                <tr key={o.id}>
                  <td>
                    <Link href={`/organisations/${o.id}`} className="font-medium text-main hover:text-accent">
                      {o.name}
                    </Link>
                  </td>
                  <td className="text-muted">{ORG_TYPE_LABELS[o.org_type] ?? o.org_type}</td>
                  <td className="text-muted">{o.region ? REGION_LABELS[o.region] : "—"}</td>
                  <td className="text-muted">{o.market ?? "—"}</td>
                  <td className="text-accent font-semibold">{o.opportunity_count}</td>
                  <td className="text-accent font-semibold">{o.contact_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
