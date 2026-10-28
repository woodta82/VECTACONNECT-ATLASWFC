"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  REGION_LABELS,
  VERTICAL_LABELS,
  type Contact,
  type RegionKey,
  type Vertical,
} from "@/lib/api";
import PageHeader from "../components/PageHeader";
import { downloadCsv } from "@/lib/csv";

type SortKey = "relevance" | "recent" | "name";

export default function RelationshipIntelligencePage() {
  const [contacts, setContacts] = useState<Contact[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [region, setRegion] = useState<RegionKey | "">("");
  const [minRelevance, setMinRelevance] = useState(0);
  const [sort, setSort] = useState<SortKey>("relevance");

  const [discoveryOpen, setDiscoveryOpen] = useState(false);
  const [orgName, setOrgName] = useState("");
  const [discoverRegion, setDiscoverRegion] = useState<RegionKey | "">("");
  const [vertical, setVertical] = useState<Vertical | "">("");
  const [roleFocus, setRoleFocus] = useState("");
  const [discovering, setDiscovering] = useState(false);

  function load() {
    return api
      .contacts({ q: q || undefined, region: region || undefined, minRelevance: minRelevance || undefined, sort })
      .then(setContacts)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, region, minRelevance, sort]);

  async function discover() {
    setDiscovering(true);
    setError(null);
    try {
      await api.discoverContacts({
        organisation_name: orgName || undefined,
        region: discoverRegion || undefined,
        vertical: vertical || undefined,
        role_focus: roleFocus || undefined,
      });
      await load();
      setDiscoveryOpen(false);
      setOrgName("");
      setRoleFocus("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Discovery failed");
    } finally {
      setDiscovering(false);
    }
  }

  function exportCsv() {
    if (!contacts) return;
    downloadCsv(
      `atlas-contacts-${new Date().toISOString().slice(0, 10)}.csv`,
      ["Name", "Role", "Organisation", "Region", "Relevance", "Linked opportunity", "Source"],
      contacts.map((c) => [
        c.name,
        c.role ?? "",
        c.organisation_name ?? "",
        c.region ? REGION_LABELS[c.region] : "",
        c.relevance_score,
        c.opportunity_title ?? "",
        c.source,
      ])
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Relationship Intelligence"
        title="Contact directory"
        description="Every contact ATLAS has identified, in one place. Every message is drafted by ATLAS but reviewed, edited and sent by a person."
        actions={
          <>
            <button onClick={exportCsv} disabled={!contacts || contacts.length === 0} className="btn btn-secondary">
              Export CSV
            </button>
            <button onClick={() => setDiscoveryOpen((v) => !v)} aria-expanded={discoveryOpen} className="btn btn-primary">
              {discoveryOpen ? "Close" : "+ Discover new contacts"}
            </button>
          </>
        }
      />

      {discoveryOpen && (
        <div className="panel p-5 mb-5">
          <h2 className="text-sm font-semibold text-main mb-3">Influence-graph search</h2>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="field">
              <label htmlFor="disc-org" className="field-label">Organisation</label>
              <input id="disc-org" value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder="Optional" className="input" />
            </div>
            <div className="field">
              <label htmlFor="disc-region" className="field-label">Region</label>
              <select id="disc-region" value={discoverRegion} onChange={(e) => setDiscoverRegion(e.target.value as RegionKey | "")} className="input">
                <option value="">Any region</option>
                {(Object.keys(REGION_LABELS) as RegionKey[]).map((r) => (
                  <option key={r} value={r}>{REGION_LABELS[r]}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="disc-vertical" className="field-label">Vertical</label>
              <select id="disc-vertical" value={vertical} onChange={(e) => setVertical(e.target.value as Vertical | "")} className="input">
                <option value="">Any vertical</option>
                {(Object.keys(VERTICAL_LABELS) as Vertical[]).map((v) => (
                  <option key={v} value={v}>{VERTICAL_LABELS[v]}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="disc-role" className="field-label">Role focus</label>
              <input id="disc-role" value={roleFocus} onChange={(e) => setRoleFocus(e.target.value)} placeholder="e.g. heads of procurement" className="input" />
            </div>
          </div>
          <button onClick={discover} disabled={discovering} className="btn btn-primary mt-4">
            {discovering ? "Researching…" : "Find contacts"}
          </button>
          <p className="text-xs text-muted mt-2">Live web research — usually 20–60 seconds. Results are added to the directory below.</p>
        </div>
      )}

      {error && (
        <div className="panel p-5 mb-6" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Something went wrong
          </p>
          <p className="text-sm text-muted mb-3">{error}</p>
          <button onClick={load} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      <div className="panel p-3 mb-5 flex flex-wrap items-end gap-3">
        <div className="field flex-1 min-w-[200px]">
          <label htmlFor="contact-search" className="field-label">Search</label>
          <input id="contact-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or role…" className="input" />
        </div>
        <div className="field">
          <label htmlFor="contact-region" className="field-label">Region</label>
          <select id="contact-region" value={region} onChange={(e) => setRegion(e.target.value as RegionKey | "")} className="input">
            <option value="">All regions</option>
            {(Object.keys(REGION_LABELS) as RegionKey[]).map((r) => (
              <option key={r} value={r}>{REGION_LABELS[r]}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="contact-relevance" className="field-label">Relevance</label>
          <select id="contact-relevance" value={minRelevance} onChange={(e) => setMinRelevance(Number(e.target.value))} className="input">
            <option value={0}>Any relevance</option>
            <option value={50}>50+ relevance</option>
            <option value={70}>70+ relevance</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="contact-sort" className="field-label">Sort</label>
          <select id="contact-sort" value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="input">
            <option value="relevance">Relevance</option>
            <option value="recent">Most recent</option>
            <option value="name">Name (A–Z)</option>
          </select>
        </div>
      </div>

      {contacts && contacts.length === 0 && (
        <div className="panel p-10 text-center text-sm text-muted">
          No contacts match these filters yet. Priority opportunities trigger discovery
          automatically, or use &ldquo;Discover new contacts&rdquo; above.
        </div>
      )}

      {contacts && contacts.length > 0 && (
        <div className="panel overflow-hidden overflow-x-auto">
          <table className="data-table">
            <caption className="sr-only">Contact directory</caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Role</th>
                <th scope="col">Organisation</th>
                <th scope="col">Region</th>
                <th scope="col">Linked to</th>
                <th scope="col">Relevance</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/relationships/${c.id}`} className="font-medium text-main hover:text-accent">
                      {c.name}
                    </Link>
                  </td>
                  <td className="text-muted">{c.role ?? "—"}</td>
                  <td className="text-muted">{c.organisation_name ?? "—"}</td>
                  <td className="text-muted">{c.region ? REGION_LABELS[c.region] : "—"}</td>
                  <td className="text-muted text-xs">{c.opportunity_title ?? "—"}</td>
                  <td>
                    <span className="text-accent font-semibold">{c.relevance_score}</span>
                    <span className="text-muted">/100</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
