"use client";

import Link from "next/link";
import { useState } from "react";
import { CountryPicker, RegionSelect } from "@/components/Geo";
import { Badge, Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { qs } from "@/lib/api";
import { MODULES } from "@/lib/constants";
import { deadline, label, moduleLabel, type DeadlineInfo } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Row = {
  id: string; module: string; title: string; commercial_stage: string; qualification_status: string; deadline_utc: string | null;
  deadline_source_tz: string | null; deadline_info: DeadlineInfo | null; classification: string | null; operating_company: string | null; organisation: string | null;
  territory: string | null; owner: string | null; countries: string[]; tender_status: string | null; tender_status_basis: string | null; freight_scope: string | null;
  priority: Record<string, { status: string; score: string | null }> | null;
};
type Page = { items: Row[]; total: number; limit: number; offset: number; insight: Insight };

export default function OpportunitiesPage() {
  const [module, setModule] = useState("");
  const [qual, setQual] = useState("");
  const [q, setQ] = useState("");
  const [stage, setStage] = useState("");
  const [countries, setCountries] = useState<string[]>([]);
  const [region, setRegion] = useState("");
  const [offset, setOffset] = useState(0);
  const filters = { module, qualification: qual, stage, q, countries: countries.join(","), region };
  const path = `/opportunities${qs({ ...filters, limit: 50, offset })}`;
  const r = useApi<Page>(path);
  const exportHref = `/api/reports/opportunities.csv${qs(filters)}`;

  return (
    <>
      <PageHeader eyebrow="Opportunities" title="Qualified pipeline and leads"
                  description="Classification, commercial stage and qualification are separate. Geography filters follow the opportunity's scope (delivery, contract territory, lane). Priority dimensions compare only within a capability area. The export carries exactly these filters."
                  actions={<a className="btn" href={exportHref}>Export CSV</a>} />
      <div className="filters" role="search">
        <label className="field">Module
          <select className="select" value={module} onChange={(e) => { setModule(e.target.value); setOffset(0); }}>
            <option value="">All modules</option>
            {MODULES.map((m) => <option key={m} value={m}>{moduleLabel(m)}</option>)}
          </select>
        </label>
        <label className="field">Qualification
          <select className="select" value={qual} onChange={(e) => { setQual(e.target.value); setOffset(0); }}>
            <option value="">Any</option>
            {["incomplete", "blocked", "ready_for_review", "approved_for_pursuit"].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </select>
        </label>
        <label className="field">Stage
          <select className="select" value={stage} onChange={(e) => { setStage(e.target.value); setOffset(0); }}>
            <option value="">Any</option>
            {["new", "reviewing", "qualified", "pursuing", "proposal", "negotiation", "won", "lost", "deferred", "expired"].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </select>
        </label>
        <RegionSelect value={region} onChange={(v) => { setRegion(v); setOffset(0); }} />
        <div style={{ flex: "1 1 240px" }}><CountryPicker value={countries} onChange={(v) => { setCountries(v); setOffset(0); }} /></div>
        <label className="field">Search title
          <input className="input" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} placeholder="e.g. GSSA" />
        </label>
      </div>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="opportunities" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? (
        <Empty title="No opportunities match">Opportunities are created only from supported, authoritative evidence. Market signals stay on the briefing until then.</Empty>
      ) : (
        <>
          <TableWrap label="Opportunities">
            <table>
              <thead><tr><th>Title</th><th>Area</th><th>Countries</th><th>Classification</th><th>Qualification</th><th>Stage</th><th>Deadline</th><th>Priority</th><th>Company / owner</th></tr></thead>
              <tbody>
                {r.data.items.map((o) => (
                  <tr key={o.id}>
                    <td><Link href={`/opportunities/${o.id}`}>{o.title}</Link><div className="muted small">{[o.organisation, o.territory].filter(Boolean).join(" · ")}</div></td>
                    <td>{moduleLabel(o.module)}</td>
                    <td>{o.countries.join(", ") || "—"}</td>
                    <td><Badge value={o.classification ?? "internal_record"} />{o.tender_status && <span className="small" title={o.tender_status_basis ?? undefined}>tender: {label(o.tender_status)}</span>}
                      {o.freight_scope && o.freight_scope !== "cargo" && <span className="small">scope: {label(o.freight_scope)}{o.freight_scope === "passenger" ? " (excluded)" : " (review)"}</span>}</td>
                    <td><Badge value={o.qualification_status} /></td>
                    <td><Badge value={o.commercial_stage} /></td>
                    <td>{deadline(o.deadline_utc, o.deadline_source_tz, o.deadline_info)}</td>
                    <td className="small">{o.priority ? ["attractiveness", "evidence_confidence", "readiness", "risk"].map((d) => {
                      const x = o.priority?.[d];
                      return `${label(d).slice(0, 5)} ${x?.status === "scored" ? Number(x.score).toFixed(0) : "—"}`;
                    }).join(" · ") : "rules"}</td>
                    <td>{o.operating_company ?? "Unassigned"}<span className="muted small">{o.owner ?? "No owner"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
          <div className="actions" style={{ marginTop: 12, justifyContent: "space-between" }}>
            <span className="muted small">{r.data.offset + 1}–{r.data.offset + r.data.items.length} of {r.data.total}</span>
            <span className="actions">
              <button className="btn" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
              <button className="btn" type="button" disabled={offset + 50 >= r.data.total} onClick={() => setOffset(offset + 50)}>Next</button>
            </span>
          </div>
          <InsightMeta insight={r.data.insight} />
        </>
      ))}
    </>
  );
}
