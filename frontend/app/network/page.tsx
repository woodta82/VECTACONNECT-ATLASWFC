"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, type DataSource, Section, SourcesLine } from "@/components/Ui";
import { api, qs } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Fit = { result: string; rationale: { covered?: string[]; unsupported?: string[]; notes?: string[] }; assessed_at: string;
             trigger?: string; gaps?: [string, string][]; valid?: boolean; changes?: string[] };
type Row = { id: string; kind: string; title: string; status: string; organisation_id: string | null; organisation: string | null;
             territory: string | null; service: string | null; latest_fit: Fit | null;
             evidence: { signal_id: string; title: string; classification: string }[] };
type Referral = { id: string; status: string; created_at: string; opportunity_id: string; title: string; from_company: string; to_company: string };

const KINDS = ["coverage_gap", "partner", "referral", "acquisition_research"] as const;

type Derived = { status: string; gaps: string[]; sources?: DataSource[]; provisional?: boolean; method?: string;
                 coverage_gaps: { key: string; territory: string; service: string; airlines: string[]; why: string; action: string; candidate_id: string | null }[];
                 candidates: { id: string; kind: string; title: string; rank: number | null; rank_reason: string; missing: string[] }[] };

export default function NetworkPage() {
  const [kind, setKind] = useState("");
  const r = useApi<{ items: Row[]; note: string }>(`/network${qs({ kind })}`);
  const refs = useApi<{ items: Referral[] }>("/referrals");
  const nd = useApi<Derived>("/modules/network-development");
  const a = useAction();
  const [newKind, setNewKind] = useState<(typeof KINDS)[number]>("partner");
  const [title, setTitle] = useState("");
  const [link, setLink] = useState<Record<string, string>>({});
  const [gaps, setGaps] = useState<Record<string, string>>({});

  function parseGaps(text: string): [string, string][] {
    return text.split(/[;,\n]+/).map((g) => g.trim()).filter(Boolean).map((g) => {
      const [t = "", sv = ""] = g.split("/").map((x) => x.trim().toUpperCase());
      return [t, sv] as [string, string];
    }).filter(([t, sv]) => t && sv);
  }

  async function add(e: FormEvent) {
    e.preventDefault();
    const ok = await a.run(() => api.post("/network", { kind: newKind, title }), "Added");
    if (ok) { setTitle(""); r.reload(); }
  }

  return (
    <>
      <PageHeader eyebrow="Network Development" title="Coverage gaps, partners, referrals and acquisition research"
                  description="Acquisition research is kept apart from the sales pipeline and never counted in pipeline totals. Fit assessments use supported claims only; discovered signals can be linked as evidence. No valuations are generated." />
      <div className="filters">
        <label className="field" style={{ maxWidth: 320 }}>Type
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All</option>{KINDS.map((k) => <option key={k} value={k}>{label(k)}</option>)}
          </select>
        </label>
      </div>
      <ActionNote state={a} />
      {nd.data && (
        <Section title="Derived coverage gaps and ranked candidates">
          {nd.data.status !== "ok" ? <div className="state" role="status"><strong>{nd.data.status === "not_connected" ? "Not connected" : "Insufficient data"}</strong>
            {nd.data.gaps.map((g) => <div key={g}>{g}</div>)}</div> : <>
            <SourcesLine sources={nd.data.sources} dateTime={dateTime} />
            {nd.data.coverage_gaps.length === 0 ? <Empty title="No coverage gaps">Every in-force mandate territory and service has a verified capability.</Empty> : (
              <TableWrap label="Coverage gaps">
                <table><thead><tr><th>Territory / service</th><th>Mandates</th><th>Why</th><th>Recommendation</th><th /></tr></thead>
                  <tbody>{nd.data.coverage_gaps.map((g) => (
                    <tr key={g.key}><td>{g.territory} / {g.service}</td><td>{g.airlines.join(", ")}</td><td className="small">{g.why}</td><td className="small">{g.action}</td>
                      <td>{g.candidate_id ? "Recorded below" : (
                        <button className="btn" type="button" disabled={a.busy}
                                onClick={() => a.run(() => api.post("/modules/network-development/gap", { key: g.key }), "Coverage gap recorded").then(() => { nd.reload(); r.reload(); })}>
                          Record for review</button>)}</td></tr>
                  ))}</tbody></table>
              </TableWrap>
            )}
            {nd.data.candidates.length > 0 && (
              <TableWrap label="Ranked candidates">
                <table><thead><tr><th>Rank</th><th>Item</th><th>Why this rank</th><th>Missing</th></tr></thead>
                  <tbody>{nd.data.candidates.map((c) => (
                    <tr key={c.id}><td>{c.rank ?? "Not ranked"}</td><td><Badge value={c.kind} /> {c.title}</td><td className="small">{c.rank_reason}</td>
                      <td className="small">{c.missing.join("; ") || "—"}</td></tr>
                  ))}</tbody></table>
              </TableWrap>
            )}
            {nd.data.provisional && <p className="muted small">Ranking rules are provisional until WFC confirms them. {nd.data.method}</p>}
          </>}
        </Section>
      )}
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="network items" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? <Empty title="Nothing recorded yet" /> : (
        <TableWrap label="Network development">
          <table>
            <thead><tr><th>Type</th><th>Title</th><th>Organisation</th><th>Territory / service</th><th>Latest fit</th><th>Evidence</th><th>Status</th></tr></thead>
            <tbody>{r.data.items.map((n) => (
              <tr key={n.id}>
                <td><Badge value={n.kind} /></td>
                <td>{n.title}</td><td>{n.organisation ?? "—"}</td><td>{[n.territory, n.service].filter(Boolean).join(" / ") || "—"}</td>
                <td>
                  {n.latest_fit ? (
                    <>
                      {n.latest_fit.valid === false ? <Badge value="invalidated" /> : <Badge value={n.latest_fit.result} />}
                      {n.latest_fit.valid === false && <span className="small muted"> (was {label(n.latest_fit.result)})</span>}
                      <div className="small muted">{n.latest_fit.rationale.notes?.join("; ")} · assessed {dateTime(n.latest_fit.assessed_at)}
                        {n.latest_fit.trigger && n.latest_fit.trigger !== "manual" ? ` (reassessed: ${label(n.latest_fit.trigger)})` : ""}</div>
                      {n.latest_fit.valid === false && (
                        <div className="small" role="note">Changed since: {(n.latest_fit.changes ?? []).join("; ")}.{" "}
                          <button className="btn btn-small" type="button" disabled={a.busy}
                                  onClick={() => a.run(() => api.post(`/network/${n.id}/fit/reassess`), "Fit reassessed").then(r.reload)}>Reassess now</button>
                        </div>
                      )}
                    </>
                  ) : "Not assessed"}
                  {n.organisation_id && (
                    <form className="inline" onSubmit={async (ev) => { ev.preventDefault();
                      const ok = await a.run(() => api.post(`/network/${n.id}/fit`, { organisation_id: n.organisation_id, gaps: parseGaps(gaps[n.id] ?? "") }), "Fit assessed");
                      if (ok) { setGaps({ ...gaps, [n.id]: "" }); r.reload(); } }}>
                      <input className="input" aria-label={`Coverage gaps to assess for ${n.title}`} placeholder="Gaps, e.g. KE/GSSA; UG/GSSA"
                             value={gaps[n.id] ?? ""} onChange={(ev) => setGaps({ ...gaps, [n.id]: ev.target.value })} style={{ maxWidth: 200 }} />
                      <button className="btn" type="submit" disabled={a.busy || parseGaps(gaps[n.id] ?? "").length === 0}>Assess</button>
                    </form>
                  )}
                </td>
                <td className="small">
                  {(n.evidence ?? []).map((e) => <div key={e.signal_id}><Badge value={e.classification} /> {e.title}</div>)}
                  <form className="inline" onSubmit={async (ev) => { ev.preventDefault();
                    const ok = await a.run(() => api.post(`/network/${n.id}/evidence`, { signal_id: (link[n.id] ?? "").trim() }), "Evidence linked");
                    if (ok) { setLink({ ...link, [n.id]: "" }); r.reload(); } }}>
                    <input className="input" aria-label={`Signal id to link to ${n.title}`} placeholder="Signal id" value={link[n.id] ?? ""}
                           onChange={(ev) => setLink({ ...link, [n.id]: ev.target.value })} style={{ maxWidth: 160 }} />
                    <button className="btn" type="submit" disabled={a.busy || !(link[n.id] ?? "").trim()}>Link</button>
                  </form>
                </td>
                <td><Badge value={n.status} /></td>
              </tr>
            ))}</tbody>
          </table>
        </TableWrap>
      ))}
      <Section title="Referrals between operating companies">
        {refs.data && (refs.data.items.length === 0 ? <Empty title="No referrals">Refer an opportunity from its page to another WFC company.</Empty> : (
          <TableWrap label="Referrals">
            <table>
              <thead><tr><th>Opportunity</th><th>From → to</th><th>Created</th><th>Status</th><th /></tr></thead>
              <tbody>{refs.data.items.map((x) => (
                <tr key={x.id}>
                  <td><Link href={`/opportunities/${x.opportunity_id}`}>{x.title}</Link></td>
                  <td>{x.from_company} → {x.to_company}</td><td>{dateTime(x.created_at)}</td><td><Badge value={x.status} /></td>
                  <td className="actions">{x.status === "proposed" || x.status === "open" ? (["accepted", "declined"] as const).map((s) => (
                    <button key={s} className="btn" type="button" disabled={a.busy}
                            onClick={() => a.run(() => api.post(`/referrals/${x.id}/status`, { status: s }), `Referral ${s}`).then(refs.reload)}>{label(s)}</button>
                  )) : x.status === "accepted" ? (
                    <button className="btn" type="button" disabled={a.busy}
                            onClick={() => a.run(() => api.post(`/referrals/${x.id}/status`, { status: "closed" }), "Referral closed").then(refs.reload)}>Close</button>
                  ) : null}</td>
                </tr>
              ))}</tbody>
            </table>
          </TableWrap>
        ))}
      </Section>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Add item</h2>
        <form onSubmit={add} className="filters">
          <label className="field">Type
            <select className="select" value={newKind} onChange={(e) => setNewKind(e.target.value as (typeof KINDS)[number])}>
              {KINDS.map((k) => <option key={k} value={k}>{label(k)}</option>)}
            </select>
          </label>
          <label className="field">Title<input className="input" value={title} onChange={(e) => setTitle(e.target.value)} minLength={3} required /></label>
          <button className="btn" type="submit" disabled={a.busy || title.trim().length < 3}>Add</button>
        </form>
      </section>
    </>
  );
}
