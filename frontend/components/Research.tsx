"use client";

/* Open-market research for companies and people (29 Oct 2026: research purposes within Discover). Shared by the Discover page and
   the Relationships page. A plain-language brief plus geography, airport, capability area and organisation kinds; the result lists
   the companies and people found, each with its evidence and a relevance to the brief. */

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Tag } from "@/components/Records";
import { TableWrap } from "@/components/States";
import { ActionNote } from "@/components/Ui";
import { AirportPicker } from "@/components/Airports";
import { CountryPicker, useGeography } from "@/components/Geo";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";

export type Discovery = { id: string; purpose: "people" | "companies"; purpose_label: string; organisation: string | null; countries_named: string[];
                          region_name: string | null; capability_area_label: string | null; role_focus: string | null; brief: string; brief_text: string | null;
                          airport_iata: string | null; airport_name: string | null; airports: string[]; airport_labels: string[]; status: string; outcome: string | null; people_found: number;
                          organisations_found: number; runs: number; started_at: string; finished_at: string | null; requested_by_label: string | null;
                          methods: string[] };
type Component = { key: string; label: string; points: number; max: number; reason: string };
export type Assessment = {
  fit: { score: number; band: string; reasons: string[] }; evidence: { band: string; documents: number; explanation: string };
  completeness: { score: number; found: number; total: number; explanation: string; fields: { field: string; label: string; status: string }[] };
  relationship: { label: string; explanation: string }; opportunity: { label: string; explanation: string };
  freight_scope: string; freight_scope_label: string; freight_scope_basis: string; explanation: string; rule: string;
};
export const FIELD_STATUS: Record<string, string> = { found: "found", not_searched: "not searched yet", not_found_after_research: "not found after research",
                                                      inaccessible: "source inaccessible", incomplete: "research incomplete", candidate: "candidate — pending review",
                                                      recheck: "changed evidence — re-check", historical: "historical — a source says it is no longer valid",
                                                      conflict: "sources conflict — review" };
export const EMAIL_STATUS: Record<string, string> = { published: "published · deliverability not verified", verified: "verified by a person", lapsed: "lapsed",
                                                      under_review: "under review", historical: "historical — not a current route" };
export type EmailResearch = { status: string; detail?: string; value?: string; basis_label?: string; candidates?: string[] } | undefined;

/* A person's published e-mail with its attribution state (30 Oct 2026): an address is shown as the person's only when the page tied it to
   that individual; 'under review' keeps the value and the evidence but says a person must decide; a candidate is never shown as theirs. */
export function PersonEmail({ email, status, research, source }: { email: string | null; status: string | null; research: EmailResearch; source?: string | null }) {
  if (email && status === "historical") {
    return (<span className="email-review"><s>{email}</s> <span className="small muted">({EMAIL_STATUS.historical}{research?.detail ? `: ${research.detail}` : ""})</span></span>);
  }
  if (email) {
    const review = status === "under_review";
    return (<span className={review ? "email-review" : undefined}>{email} <span className="small muted">({EMAIL_STATUS[status ?? "published"] ?? status}
      {review && research?.detail ? `: ${research.detail}` : research?.basis_label ? ` · ${research.basis_label}` : ""}{source ? <> · <a href={source} target="_blank" rel="noreferrer noopener">source</a></> : null})</span></span>);
  }
  const st = research?.status ?? "not_searched";
  return (<span className="muted">{FIELD_STATUS[st] ?? st}{st === "candidate" && research?.value ? ` (${research.value}: ${research.detail ?? "not assigned"})` : ""}</span>);
}

export function AssessmentParts({ a }: { a: Assessment }) {
  return (
    <ul className="small list-plain" aria-label="Assessment">
      <li><b>Fit with the brief {a.fit.score}/100</b> ({a.fit.band}): {a.fit.reasons.join("; ")}</li>
      <li><b>Source evidence</b>: {a.evidence.explanation}</li>
      <li><b>Research completeness {a.completeness.found}/{a.completeness.total}</b>: {a.completeness.fields.filter((f) => f.status !== "found").map((f) => `${f.label.toLowerCase()} ${FIELD_STATUS[f.status] ?? f.status}`).join("; ") || "every field found"}</li>
      <li><b>Relationship position</b>: {a.relationship.explanation}</li>
      <li><b>Opportunity status</b>: {a.opportunity.explanation}</li>
      <li><b>Freight scope</b>: {a.freight_scope_label} — {a.freight_scope_basis}</li>
      <li className="muted">{a.rule}</li>
    </ul>
  );
}
export type DiscoveredPerson = { person_id: string; full_name: string; role_title: string | null; organisation: string | null; relevance_score: number;
                                 new_record: boolean; relevance: { components: Component[] }; state_label: string; linkedin_search_url: string;
                                 source_url: string | null; quote: string | null };
export type DiscoveredCompany = { organisation_id: string; canonical_name: string; kind: string; kind_label: string; country: string | null; country_name: string | null;
                                  website: string | null; origin: string; airport_iata: string | null; carrier_type_label: string | null; relevance_score: number;
                                  relevance: Assessment; new_record: boolean; emails: { value: string; status: string }[];
                                  relationships: { counterparty: string | null; code: string | null; relationship: string; relationship_label: string; status: string }[];
                                  people: number; evidence: number; quote: string | null; source_url: string | null; services_text: string | null;
                                  locations_text: string | null; parent_group: string | null };
export type DiscoveryDetail = Discovery & {
  people: DiscoveredPerson[]; organisations: DiscoveredCompany[];
  documents: { id: string; origin: string; url: string | null; title: string | null; status: string; status_reason: string | null; found_via: string | null }[];
  searches: { purpose: string; query: string; status: string; results: number; link: string; reason?: string }[];
  unavailable: { method: string; reason: string }[]; actions: string[]; rule: string;
  coverage: { remaining: string[]; not_searched: string[]; limits_hit?: string[] };
};

export const OUTCOME_TONE: Record<string, string> = { people_found: "b-good", companies_found: "b-good", no_people_found: "b-none", no_companies_found: "b-none",
                                                      incomplete: "b-warn", not_run: "b-bad" };
const OUTCOME_LABEL: Record<string, string> = { people_found: "People found", companies_found: "Companies found", no_people_found: "No people found",
                                                no_companies_found: "No companies found", incomplete: "Incomplete", not_run: "Not run" };
export const outcomeLabel = (o: string | null) => OUTCOME_LABEL[o ?? "not_run"] ?? "Running";
const STATUS_TONE: Record<string, string> = { supplied: "b-warn", published: "b-info", verified: "b-good", sourced: "b-info", confirmed: "b-good", lapsed: "b-none",
                                              not_established: "b-none" };
export const KINDS: [string, string][] = [["gssa", "GSA / GSSA"], ["airline", "Airline"], ["forwarder", "Freight forwarder"], ["handler", "Ground or cargo handler"],
                                          ["trucking_provider", "Trucking / road feeder"], ["airport_operator", "Airport operator"], ["technology_provider", "Technology provider"],
                                          ["charter_broker", "Charter broker"], ["integrator", "Integrator"], ["shipper", "Shipper"]];
const EXAMPLES: Record<"companies" | "people", string> = {
  companies: "e.g. Find cargo GSAs operating in East Africa and the airlines they represent",
  people: "e.g. Identify cargo commercial directors in Southeast Asia",
};

export function ResearchForm({ purpose, areas, onDone, compact = false }: {
  purpose: "companies" | "people"; areas: Record<string, string>; onDone: (d: DiscoveryDetail) => void; compact?: boolean;
}) {
  const geo = useGeography();
  const [f, setF] = useState({ brief: "", organisation_name: "", capability_area: "", role_focus: "", region: "", requested_by_label: "" });
  const [kinds, setKinds] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [airports, setAirports] = useState<string[]>([]);
  const [mode, setMode] = useState<"countries" | "region">("countries");
  const a = useAction();
  const ready = f.brief.trim() || f.organisation_name.trim() || f.role_focus.trim() || airports.length > 0 ||
                (mode === "countries" ? countries.length > 0 : !!f.region);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { purpose, brief: f.brief.trim() || null, organisation_name: f.organisation_name || null, capability_area: f.capability_area || null,
                   role_focus: purpose === "people" ? f.role_focus || null : null, region: mode === "region" ? f.region || null : null,
                   countries: mode === "countries" ? countries : [], airports,
                   organisation_kinds: purpose === "companies" ? kinds : [], requested_by_label: f.requested_by_label || null };
    const d = await a.run(() => api.post<DiscoveryDetail>("/contacts/discover", body), "Research run");
    if (d) onDone(d);
  }
  return (
    <section className="panel" aria-label={purpose === "companies" ? "Research companies" : "Discover contacts"}>
      {!compact && <h2>{purpose === "companies" ? "Research companies in the open market" : "Discover contacts in the open market"}</h2>}
      <p className="small muted">
        {purpose === "companies"
          ? "Who operates here and what can they do: GSAs/GSSAs, airlines (including passenger airlines carrying belly cargo), forwarders, handlers, trucking providers, gateways and technology providers. ATLAS reads public directories, the companies' own pages and the authorised web search's results; every company carries the passage that names it, its published addresses and the airlines it is stated to represent. No tender is needed."
          : "Who matters: named people by organisation, country or region, capability area and role focus. ATLAS reads the organisation's own pages and the authorised web search's results; every contact carries the passage that names them and a relevance to this brief. Public pages only; no LinkedIn profile is fetched and nothing is sent."}
      </p>
      <form className="form-grid" onSubmit={submit}>
        <label className="field" style={{ gridColumn: "1 / -1" }}>Research brief (plain language)
          <textarea className="input" rows={2} maxLength={600} value={f.brief} onChange={(e) => setF({ ...f, brief: e.target.value })} placeholder={EXAMPLES[purpose]} />
        </label>
        <label className="field">Organisation (optional)<input className="input" value={f.organisation_name} onChange={(e) => setF({ ...f, organisation_name: e.target.value })} placeholder="e.g. Example Air" /></label>
        <label className="field">Capability area<select className="select" value={f.capability_area} onChange={(e) => setF({ ...f, capability_area: e.target.value })}>
          <option value="">Any</option>{Object.entries(areas).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {purpose === "people" && (
          <label className="field">Role focus (optional)<input className="input" value={f.role_focus} onChange={(e) => setF({ ...f, role_focus: e.target.value })} placeholder="e.g. head of cargo" /></label>
        )}
        <label className="field">Requested by<input className="input" value={f.requested_by_label} onChange={(e) => setF({ ...f, requested_by_label: e.target.value })} /></label>
        <div className="field" style={{ gridColumn: "1 / -1" }}>Geography
          <div className="segmented" role="group" aria-label="Geography mode">
            <button type="button" aria-pressed={mode === "countries"} onClick={() => setMode("countries")}>Countries</button>
            <button type="button" aria-pressed={mode === "region"} onClick={() => setMode("region")}>Region</button>
          </div>
        </div>
        {mode === "countries" ? <div style={{ gridColumn: "1 / -1" }}><CountryPicker value={countries} onChange={setCountries} max={5} label="Countries (all airports in the country unless airports are chosen)" /></div> : (
          <label className="field">Region<select className="select" value={f.region} onChange={(e) => setF({ ...f, region: e.target.value })}>
            <option value="">Choose a region</option>{(geo?.regions ?? []).map((rg) => <option key={rg.code} value={rg.code}>{rg.name}</option>)}</select></label>)}
        <div style={{ gridColumn: "1 / -1" }}><AirportPicker value={airports} onChange={setAirports} label="Airports (optional; any airport in the directory, with or without an IATA code)" /></div>
        {purpose === "companies" && (
          <fieldset className="plain" style={{ gridColumn: "1 / -1" }}>
            <legend className="field">Kinds of organisation (none selected = those the capability area implies)</legend>
            <div className="check-grid">{KINDS.map(([k, l]) => (
              <label key={k}><input type="checkbox" checked={kinds.includes(k)} onChange={(e) => setKinds(e.target.checked ? [...kinds, k] : kinds.filter((x) => x !== k))} /> {l}</label>))}</div>
          </fieldset>
        )}
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy || !ready}>{a.busy ? "Researching…" : purpose === "companies" ? "Find companies" : "Find contacts"}</button></div>
        <p className="small muted" style={{ gridColumn: "1 / -1" }}>Usually 10–60 seconds. {purpose === "companies" ? "Found companies are added to the Companies directory with their evidence; a relevant company is not an opportunity." : "Found people are added to the directory as research candidates."}</p>
        <ActionNote state={a} />
      </form>
    </section>
  );
}

export function ResearchResult({ d, onContinue }: { d: DiscoveryDetail; onContinue: () => Promise<void> }) {
  const [open, setOpen] = useState<string | null>(null);
  const a = useAction();
  return (
    <section className="panel" aria-label="Research result">
      <div className="panel-head"><h2>{d.purpose_label ?? "Research"}: {d.brief}</h2><Tag text={outcomeLabel(d.outcome)} tone={OUTCOME_TONE[d.outcome ?? "not_run"]} /></div>
      <p className="small muted">{d.purpose === "companies" ? `${d.organisations.length} compan${d.organisations.length === 1 ? "y" : "ies"} · ` : ""}{d.people.length} contact(s) ·{" "}
        {d.documents.filter((x) => x.status === "read").length} page(s) read of {d.documents.length} ·{" "}
        {d.searches.filter((s) => s.status === "run").length} search(es) run, {d.searches.filter((s) => s.status === "not_run").length} not run · run {d.runs} time(s)</p>
      {d.actions.length > 0 && <ul className="small">{d.actions.map((x) => <li key={x}>{x}</li>)}</ul>}
      {d.outcome === "incomplete" && <button type="button" className="btn btn-small" disabled={a.busy} onClick={() => a.run(onContinue, "Research continued")}>Continue research</button>}
      {d.organisations.length > 0 && (
        <TableWrap label="Discovered companies">
          <table><thead><tr><th className="num">Fit</th><th>Company</th><th>Kind / scope</th><th>Website and e-mail</th><th>Represents / partners</th><th>People</th><th>Evidence</th><th>Why</th></tr></thead>
            <tbody>{d.organisations.map((o) => (
              <tr key={o.organisation_id}>
                <td className="num"><b>{o.relevance_score}</b><span className="muted small">/100</span></td>
                <td><Link href={`/companies/${o.organisation_id}`}>{o.canonical_name}</Link>
                  <div className="small muted">{[o.country_name, o.airport_iata, o.parent_group ? `part of ${o.parent_group}` : null].filter(Boolean).join(" · ")}{o.new_record ? "" : " · already known"}</div></td>
                <td className="small">{o.kind_label}<div className={o.relevance?.freight_scope === "passenger_only" ? "action-error" : "muted"}>{o.relevance?.freight_scope_label ?? o.carrier_type_label ?? ""}</div></td>
                <td className="small">{o.website ? <a href={o.website} target="_blank" rel="noreferrer noopener">{o.website.replace(/^https?:\/\//, "")}</a> : <span className="muted">website not found</span>}
                  {o.emails.map((e) => <div key={e.value}>{e.value} <Tag text={label(e.status)} tone={STATUS_TONE[e.status]} /></div>)}</td>
                <td className="small">{o.relationships.length === 0 ? <span className="muted">none stated</span> : o.relationships.map((r, i) => (
                  <div key={i}>{r.counterparty ?? r.code} <span className="muted">· {r.relationship_label}</span> <Tag text={label(r.status)} tone={STATUS_TONE[r.status]} /></div>))}</td>
                <td className="num">{o.people}</td>
                <td className="small">{o.quote ? <>“{o.quote.slice(0, 120)}{o.quote.length > 120 ? "…" : ""}”</> : ""}{o.source_url && <> <a href={o.source_url} target="_blank" rel="noreferrer noopener">source</a></>}</td>
                <td><button type="button" className="btn btn-small" aria-expanded={open === o.organisation_id} onClick={() => setOpen(open === o.organisation_id ? null : o.organisation_id)}>{open === o.organisation_id ? "Hide" : "Breakdown"}</button>
                  {open === o.organisation_id && <AssessmentParts a={o.relevance} />}</td>
              </tr>))}</tbody></table>
        </TableWrap>
      )}
      {d.people.length > 0 && (
        <TableWrap label="Discovered contacts">
          <table><thead><tr><th className="num">Relevance</th><th>Person</th><th>Organisation</th><th>Evidence</th><th>Status</th><th>LinkedIn</th><th>Why</th></tr></thead>
            <tbody>{d.people.map((p) => (
              <tr key={p.person_id}>
                <td className="num"><b>{p.relevance_score}</b><span className="muted small">/100</span></td>
                <td><Link href={`/relationships/${p.person_id}`}>{p.full_name}</Link><div className="small muted">{p.role_title ?? "title not bound"}{p.new_record ? "" : " · already known"}</div></td>
                <td className="small">{p.organisation ?? <span className="muted">not established</span>}</td>
                <td className="small">{p.quote ? <>“{p.quote.slice(0, 140)}{p.quote.length > 140 ? "…" : ""}”</> : ""}{p.source_url && <> <a href={p.source_url} target="_blank" rel="noreferrer noopener">source</a></>}</td>
                <td><Tag text={p.state_label} tone="b-warn" /></td>
                <td className="small"><a href={p.linkedin_search_url} target="_blank" rel="noreferrer noopener">Search</a></td>
                <td><button type="button" className="btn btn-small" aria-expanded={open === p.person_id} onClick={() => setOpen(open === p.person_id ? null : p.person_id)}>{open === p.person_id ? "Hide" : "Breakdown"}</button>
                  {open === p.person_id && <ul className="small list-plain">{p.relevance.components.map((c) => <li key={c.key}><b>{c.points}/{c.max}</b> {c.label}: {c.reason}</li>)}</ul>}</td>
              </tr>))}</tbody></table>
        </TableWrap>
      )}
      <details className="small"><summary>What was read and searched</summary>
        <ul className="list-plain">{d.documents.map((x) => <li key={x.id}><Tag text={label(x.status)} tone={x.status === "read" ? "b-good" : x.status === "failed" ? "b-bad" : "b-none"} /> {x.url ? <a href={x.url} target="_blank" rel="noreferrer noopener">{x.title ?? x.url}</a> : x.title}
          <span className="muted"> · {label(x.origin)}{x.found_via ? ` · ${x.found_via}` : ""}{x.status_reason ? ` · ${x.status_reason}` : ""}</span></li>)}</ul>
        <ul className="list-plain">{d.searches.map((s) => <li key={s.query}><Tag text={s.status === "run" ? `run: ${s.results} result(s)` : label(s.status)} tone={s.status === "run" ? "b-good" : "b-warn"} /> {s.purpose}:{" "}
          <a href={s.link} target="_blank" rel="noreferrer noopener">{s.query}</a>{s.reason ? <span className="muted"> · {s.reason}</span> : null}</li>)}</ul>
        <ul className="list-plain muted">{d.unavailable.map((u) => <li key={u.method + u.reason}>{label(u.method)}: {u.reason}</li>)}</ul>
      </details>
      <p className="small muted">{d.rule}</p>
      <ActionNote state={a} />
    </section>
  );
}

export function RecentResearch({ items, onOpen, title = "Recent research" }: { items: Discovery[]; onOpen: (id: string) => void; title?: string }) {
  if (items.length === 0) return null;
  return (
    <section className="panel" aria-label={title}>
      <h2>{title}</h2>
      <ul className="list-plain small">{items.map((d) => (
        <li key={d.id}><Tag text={d.purpose_label ?? label(d.purpose)} tone="b-info" /> <button type="button" className="link-button" onClick={() => onOpen(d.id)}>{d.brief}</button>{" "}
          <Tag text={outcomeLabel(d.outcome)} tone={OUTCOME_TONE[d.outcome ?? "not_run"]} />
          <span className="muted"> · {d.purpose === "companies" ? `${d.organisations_found} compan${d.organisations_found === 1 ? "y" : "ies"} · ` : ""}{d.people_found} contact(s) · {dateTime(d.started_at)}{d.requested_by_label ? ` · ${d.requested_by_label}` : ""}</span></li>))}</ul>
    </section>
  );
}

export type QueueItem = { stage: string; stage_label: string; organisation_id: string; organisation: string; status: string; attempts: number; detail: string | null };

/* The persisted work queue of the organisation-scoped stages: what is pending, attempted, done or failed, so unfinished research is visible. */
export function QueueList({ queue }: { queue: QueueItem[] | undefined }) {
  const open = (queue ?? []).filter((q) => q.status !== "done");
  if (!queue || queue.length === 0) return null;
  const by: Record<string, QueueItem[]> = {};
  for (const q of queue) { const list = by[q.stage] ?? []; list.push(q); by[q.stage] = list; }
  return (
    <details className="small" style={{ marginTop: 8 }}>
      <summary>Work queue: {queue.length} organisation-stage item(s), {open.length} not done</summary>
      <ul className="list-plain small">{Object.entries(by).map(([stage, items]) => (
        <li key={stage}><b>{(items[0]?.stage_label ?? stage).split(" (")[0]}</b>: {items.filter((i) => i.status === "done").length} done, {items.filter((i) => i.status === "pending").length} pending, {items.filter((i) => i.status === "failed").length} failed
          {items.some((i) => i.status !== "done") && <span className="muted"> — {items.filter((i) => i.status !== "done").map((i) => `${i.organisation} (${i.status}${i.detail ? `: ${i.detail}` : ""})`).join("; ")}</span>}</li>))}</ul>
    </details>
  );
}
