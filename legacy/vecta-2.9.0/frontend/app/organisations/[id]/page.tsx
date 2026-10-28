"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, REGION_LABELS, VERTICAL_LABELS, type OrganisationDetail } from "@/lib/api";
import PageHeader from "../../components/PageHeader";
import StatCard from "../../components/StatCard";
import ScoreBadge from "../../components/ScoreBadge";

const ORG_TYPE_LABELS: Record<string, string> = {
  federation: "Federation",
  club: "Club",
  government: "Government",
  brand: "Brand",
  venue: "Venue",
  other: "Other",
};

export default function OrganisationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [org, setOrg] = useState<OrganisationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    api
      .organisation(id)
      .then((o) => {
        setOrg(o);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load organisation"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) {
    return (
      <div className="panel p-5" style={{ borderColor: "var(--danger)" }} role="alert">
        <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
          Couldn&apos;t load this organisation
        </p>
        <p className="text-sm text-muted mb-3">{error}</p>
        <button onClick={load} className="btn btn-secondary text-xs">
          Try again
        </button>
      </div>
    );
  }
  if (!org) return <p className="text-sm text-muted">Loading…</p>;

  const subtitle = [ORG_TYPE_LABELS[org.org_type] ?? org.org_type, org.region ? REGION_LABELS[org.region] : null, org.market]
    .filter(Boolean)
    .join(" · ");

  return (
    <div>
      <PageHeader
        eyebrow="Organisations"
        title={org.name}
        description={subtitle}
        back={{ label: "Back to organisations", href: "/organisations" }}
      />

      <div className="grid grid-cols-2 gap-3 mb-5 max-w-md">
        <StatCard label="Opportunities" value={String(org.opportunity_count)} />
        <StatCard label="Contacts" value={String(org.contact_count)} />
      </div>

      {(org.website || org.linkedin_url) && (
        <div className="panel p-5 mb-5 flex flex-wrap gap-4">
          {org.website && (
            <a href={org.website} target="_blank" rel="noreferrer" className="btn-ghost text-sm -ml-2">
              Website →
            </a>
          )}
          {org.linkedin_url && (
            <a href={org.linkedin_url} target="_blank" rel="noreferrer" className="btn-ghost text-sm">
              LinkedIn →
            </a>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-3">Opportunities</h2>
          {org.opportunities.length === 0 ? (
            <p className="text-sm text-muted">No linked opportunities yet.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {org.opportunities.map((o) => (
                <li key={o.id}>
                  <Link
                    href={`/opportunities/${o.id}`}
                    className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0 hover:text-accent"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-main font-medium truncate">{o.title}</p>
                      <p className="text-xs text-muted">{o.vertical ? VERTICAL_LABELS[o.vertical] : "—"}</p>
                    </div>
                    <ScoreBadge score={o.alignment_score} size="sm" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel p-5">
          <h2 className="text-sm font-semibold text-main mb-3">Contacts</h2>
          {org.contacts.length === 0 ? (
            <p className="text-sm text-muted">No linked contacts yet.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {org.contacts.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/relationships/${c.id}`}
                    className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0 hover:text-accent"
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-main font-medium truncate">{c.name}</p>
                      <p className="text-xs text-muted">{c.role ?? "Role unknown"}</p>
                    </div>
                    <span className="text-xs text-accent font-medium shrink-0">{c.relevance_score}/100</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
