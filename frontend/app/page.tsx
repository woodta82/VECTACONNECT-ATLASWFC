"use client";

import Link from "next/link";
import { useState } from "react";
import { CountryPicker, RegionSelect } from "@/components/Geo";
import { Badge, Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, Stat, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { dateTime, deadline, label, moduleLabel, type DeadlineInfo } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Briefing = {
  pipeline: { module: string; commercial_stage: string; qualification_status: string; tender_status: string; freight_scope: string; n: number }[];
  deadlines: { id: string; title: string; module: string; deadline_utc: string | null; deadline_source_tz: string | null; deadline_info: DeadlineInfo | null; qualification_status: string; commercial_stage: string }[];
  signals: { id: string; module: string; classification: string; title: string; summary: string | null; gaps: string[]; created_at: string; countries: string[] }[];
  exceptions: { severity: string; n: number }[];
  sources: { id: string; name: string; enabled: boolean; connector_status: string | null; last_success_at: string | null; last_failure_at: string | null }[];
  review: { documents: number; claims: number; rejections: number; merges: number } | null;
  runs: { id: string; status: string; outcome: string | null; search_name: string | null; source_name: string | null; created_at: string;
          countries: string[] | null; coverage_note: string | null; counts: Record<string, number> | null }[];
  geography: string[] | null;
  insight: Insight;
};

export default function BriefingPage() {
  const [countries, setCountries] = useState<string[]>([]);
  const [region, setRegion] = useState("");
  const r = useApi<Briefing>(`/briefing${qs({ days: 14, countries: countries.join(","), region })}`);
  const areas = useApi<{ areas: Record<string, { status: string }> }>("/modules/summary");
  return (
    <>
      <PageHeader eyebrow="Executive Briefing" title="What changed, what is due, what needs a decision"
                  description="Signals, deadlines and operational exceptions across every loaded operating company. Country and region are reporting filters only; they follow each opportunity's scope. Each figure states its scope, period and sources."
                  actions={<Link className="btn btn-primary" href="/discovery">Search countries</Link>} />
      <div className="filters" role="search">
        <RegionSelect value={region} onChange={setRegion} />
        <div style={{ flex: "1 1 260px" }}><CountryPicker value={countries} onChange={setCountries} /></div>
      </div>
      {areas.data && (
        <div className="chips" aria-label="Capability area status">
          {Object.entries(areas.data.areas).map(([k, v]) => (
            <Link key={k} href="/areas" className="chip-link"><span className="small">{moduleLabel(k)}</span> <Badge value={v.status} /></Link>
          ))}
        </div>
      )}
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="briefing" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <BriefingBody b={r.data} />}
    </>
  );
}

function BriefingBody({ b }: { b: Briefing }) {
  // "Live" counts only tenders whose open/revised status an authoritative source STATES; a record whose status is unknown,
  // unverified (old, no closing date) or historical is never counted as open, and passenger-only records are excluded.
  // "Live" counts only cargo-relevant tenders whose open/revised status a source STATES (or whose stated closing date has not
  // passed). Announced-only, unknown, unverified and historical records are never counted as open; freight candidates are
  // counted separately; records excluded from the freight pipeline are not counted at all.
  const excludedScopes = ["passenger", "not_freight"];
  const active = b.pipeline.filter((p) => !["won", "lost", "expired", "deferred"].includes(p.commercial_stage) && !excludedScopes.includes(p.freight_scope));
  const live = active.filter((p) => ["open", "revised"].includes(p.tender_status) && p.freight_scope === "cargo").reduce((a, p) => a + Number(p.n), 0);
  const candidates = active.filter((p) => ["open", "revised"].includes(p.tender_status) && p.freight_scope !== "cargo").reduce((a, p) => a + Number(p.n), 0);
  const unverified = active.filter((p) => ["unknown", "unverified", "historical", "contradictory", "announced"].includes(p.tender_status)).reduce((a, p) => a + Number(p.n), 0);
  const excluded = b.pipeline.filter((p) => excludedScopes.includes(p.freight_scope)).reduce((a, p) => a + Number(p.n), 0);
  const review = b.pipeline.filter((p) => p.qualification_status === "ready_for_review").reduce((a, p) => a + Number(p.n), 0);
  const blocked = b.pipeline.filter((p) => p.qualification_status === "blocked").reduce((a, p) => a + Number(p.n), 0);
  const activeExceptions = b.exceptions.reduce((a, e) => a + Number(e.n), 0);
  const failing = b.sources.filter((s) => s.enabled && s.last_failure_at && (!s.last_success_at || s.last_failure_at > s.last_success_at));
  const exceptionsConnected = b.insight.sources.find((s) => s.dataset === "exceptions")?.status !== "not_connected";
  return (
    <div className="stack">
      {failing.length > 0 && (
        <div className="notice" role="status">
          {failing.length} source{failing.length === 1 ? "" : "s"} failed on the last run: {failing.map((s) => s.name).join(", ")}. Intelligence from them is not live.
        </div>
      )}
      <div className="grid grid-4">
        <Stat label="Live freight tenders" value={live} note={`Cargo-relevant, open or revised status verified by a source · ${candidates} freight candidate(s) awaiting scope review · ${unverified} announced, unknown, unverified or historical (not counted as open)${excluded ? ` · ${excluded} excluded (not freight)` : ""}`} />
        <Stat label="Ready for review" value={review} note="Blocking checks passed; needs human approval" />
        <Stat label="Blocked" value={blocked} note="Expired, conflict or capability failure" />
        {exceptionsConnected ? (
          <Stat label="Active exceptions" value={activeExceptions} note={b.exceptions.length ? b.exceptions.map((e) => `${e.n} ${e.severity}`).join(" · ") : "None active"} />
        ) : (
          <Stat label="Active exceptions" value="Not connected" note="No exception feed or import loaded; this is not zero" />
        )}
      </div>

      {b.review && (
        <div className="grid grid-4">
          <Stat label="Claims awaiting review" value={Number(b.review.claims)} note="Proposed by extraction; not yet confirmed" />
          <Stat label="Documents needing review" value={Number(b.review.documents)} note="Extraction not connected, refused, failed or partial" />
          <Stat label="Rejected extractor output" value={Number(b.review.rejections)} note="Malformed claims recorded for review" />
          <Stat label="Possible duplicates" value={Number(b.review.merges)} note="Merge candidates awaiting a decision" />
        </div>
      )}
      {b.review && Number(b.review.claims) + Number(b.review.documents) + Number(b.review.rejections) + Number(b.review.merges) > 0 && (
        <p className="small"><Link href="/review">Open the evidence review queue</Link></p>
      )}

      <section className="panel">
        <h2>Deadlines in the next 14 days</h2>
        {b.deadlines.length === 0 ? (
          <Empty title="No deadlines in this window">Deadlines appear only when an authoritative source states them.</Empty>
        ) : (
          <TableWrap label="Upcoming deadlines">
            <table>
              <thead><tr><th>Opportunity</th><th>Module</th><th>Deadline</th><th>Qualification</th><th>Stage</th></tr></thead>
              <tbody>
                {b.deadlines.map((d) => (
                  <tr key={d.id}>
                    <td><Link href={`/opportunities/${d.id}`}>{d.title}</Link></td>
                    <td>{label(d.module)}</td>
                    <td>{deadline(d.deadline_utc, d.deadline_source_tz, d.deadline_info)}</td>
                    <td><Badge value={d.qualification_status} /></td>
                    <td><Badge value={d.commercial_stage} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </section>

      <section className="panel">
        <h2>Latest market signals</h2>
        {b.signals.length === 0 ? (
          <Empty title="No signals yet">Enable a public source or import data under Data Sources and Imports.</Empty>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {b.signals.map((s) => (
              <li key={s.id} style={{ padding: "10px 0", borderBottom: "1px solid var(--border)" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                  <Badge value={s.classification} /> <strong>{s.title}</strong>
                  <span className="muted small">{dateTime(s.created_at)}{s.countries?.length ? ` · ${s.countries.join(", ")}` : ""}</span>
                </div>
                {s.summary && <div className="muted small">{s.summary}</div>}
                {s.gaps.length > 0 && <div className="small" style={{ marginTop: 4 }}>Missing: {s.gaps.join("; ")}</div>}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel">
        <h2>Recent discovery runs</h2>
        {b.runs.length === 0 ? <Empty title="No discovery runs yet">Start a country search under Country Discovery.</Empty> : (
          <TableWrap label="Recent discovery runs">
            <table>
              <thead><tr><th>Run</th><th>Countries</th><th>Status</th><th>Outcome</th><th>Started</th></tr></thead>
              <tbody>{b.runs.map((x) => (
                <tr key={x.id}>
                  <td><Link href={`/discovery/runs/${x.id}`}>{x.search_name ?? x.source_name ?? "Ad hoc run"}</Link></td>
                  <td className="small">{Array.isArray(x.countries) && x.countries.length ? x.countries.join(", ") : "Worldwide (source coverage only)"}</td>
                  <td><Badge value={x.status} /></td>
                  <td>{x.outcome ? <Badge value={x.outcome} /> : "—"}<span className="muted small">{x.coverage_note ?? ""}</span></td>
                  <td>{dateTime(x.created_at)}</td>
                </tr>
              ))}</tbody>
            </table>
          </TableWrap>
        )}
      </section>
      <InsightMeta insight={b.insight} />
    </div>
  );
}
