"use client";

import Link from "next/link";
import { Badge, ErrorState, Loading, PageHeader, StaleBanner } from "@/components/States";
import { moduleLabel } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const AREAS: { id: string; href: string; what: string }[] = [
  { id: "airline_representation", href: "/opportunities?module=airline_representation", what: "Discover and qualify GSSA tenders, representation openings and Total Cargo Management opportunities." },
  { id: "account_growth", href: "/areas/account-growth", what: "Territory and service expansion supported by in-force agreements and verified capability." },
  { id: "forwarder_sales", href: "/areas/forwarder-sales", what: "Dormant and declining accounts, quote conversion and account review priority." },
  { id: "capacity_lanes", href: "/areas/capacity", what: "Directional route trends, capacity changes, utilisation and per-currency yield." },
  { id: "service_operations", href: "/service", what: "Reservation, supervision and post-flight exceptions with owners and resolution history." },
  { id: "trucking_gateways", href: "/areas/trucking", what: "Offline stations matched to feasible gateway connections using schedules, transit times and cutoffs." },
  { id: "outsourcing_training", href: "/areas/outsourcing", what: "Verified demand matched to WFC services, resources and current credentials." },
  { id: "technology_solutions", href: "/areas/technology", what: "Digital adoption gaps, booking friction and supported combined-service opportunities." },
  { id: "network_development", href: "/network", what: "Coverage gaps, referrals, partners and acquisition research with supporting evidence." },
];

export default function AreasPage() {
  const r = useApi<{ areas: Record<string, { status: string }> }>("/modules/summary");
  return (
    <>
      <PageHeader eyebrow="Capability areas" title="The nine WFC capability areas"
                  description="Each area shows its own workflow and output. An area whose required data is not loaded says Not connected or Insufficient data rather than showing zero." />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="capability areas" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (
        <div className="grid grid-3">
          {AREAS.map((a) => (
            <Link key={a.id} href={a.href} className="panel area-card">
              <div className="inline"><strong>{moduleLabel(a.id)}</strong> <Badge value={r.data?.areas[a.id]?.status ?? "unknown"} /></div>
              <p className="muted small" style={{ marginBottom: 0 }}>{a.what}</p>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
