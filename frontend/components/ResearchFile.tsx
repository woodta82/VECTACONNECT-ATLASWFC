"use client";

/* The opportunity research file (30 Oct 2026, item 3): a concise summary first — what is happening and its evidence, why it is relevant,
   the organisations and their roles, geography and airports, services, named people with routes, representation and relationship
   evidence, what remains uncertain, the next action — with the supporting research below. Staged research enriches the records the
   file reads from; it is never a longer AI summary. */

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Tag } from "@/components/Records";
import { ActionNote } from "@/components/Ui";
import { PersonEmail, QueueList, type EmailResearch, type QueueItem } from "@/components/Research";
import { api } from "@/lib/api";
import { dateOnly, dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Stage = { stage: string; label: string; status: string; status_label: string; detail: string | null; progress: string | null; attempts: number; finished_at: string | null };
type Field = { field: string; label: string; status: string; status_label: string; detail: string | null };
type Company = { id: string; name: string; role: string | null; kind_label: string; country_name: string | null; website: string | null; website_basis: string | null; contact_url: string | null;
                 freight_scope: string; freight_scope_label: string; in_cargo_scope: boolean; state_label: string; verified_at: string | null;
                 emails: { value: string; status: string; status_label?: string; department: string | null; source_url: string | null; current: boolean }[]; airports: { label: string; role: string; status: string }[];
                 offices: string | null; services: string | null; parent_group: string | null; representation: { counterparty: string | null; relationship: string; status: string; basis: string }[];
                 represented_by: { agent: string; agent_id: string; relationship: string; status: string }[]; people: number; research: { found: number; total: number; fields: Field[] };
                 evidence_strength: { band: string; explanation: string }; evidence: { supports: string; quote: string | null; url: string | null; note: string | null; observed_at: string; source_kind: string }[] };
type PersonRow = { id: string; full_name: string; role_title: string | null; organisation: string | null; remit_countries: string[]; state_label: string; role_on_opportunity: string | null;
                   linkedin_profile_url: string | null; linkedin_search_url: string | null; published_email: string | null; email_status: string; published_email_status: string | null; email_research: EmailResearch;
                   involvement_label?: string | null; relationships: number; routes: number;
                   evidence_quote: string | null; source_url: string | null };
export type File = {
  opportunity: { id: string; title: string; record_type: string; record_type_label: string; category: string; progress: string | null; tender_status_label: string | null;
                 origin_interpretation: string | null; next_action: string | null; next_action_due: string | null };
  summary: {
    what: { text: string; sources: { title: string | null; url: string; published_at: string | null }[]; source_count: number };
    why: { text: string | null; label: string | null; unconfirmed: string[]; priority_reason: string };
    organisations: { id: string; name: string; role: string | null; kind_label: string; freight_scope_label: string; in_cargo_scope: boolean }[];
    geography: { countries: string[]; airports: { label: string; role: string; support: string }[]; company_airports: { company: string; label: string; role: string; status: string }[] };
    services: { category: string; service: string | null };
    people: PersonRow[];
    routes: { company: string; website: string | null; contact_page: string | null; emails: { value: string; status: string; status_label?: string; department: string | null; current: boolean }[] }[];
    relationships: { coverage: string; coverage_label: string; recorded: { person: string; holder_label: string; nature: string; status: string }[];
                     routes_available: { target_person: string; introducer_label: string | null; status: string }[]; routes_possible: unknown[];
                     representation: { company: string; counterparty: string | null; relationship: string; status: string }[] };
    uncertain: string[];
    next_action: string;
    external_contacts: { id: string; full_name: string; role_title: string | null; involvement: string; involvement_label: string; organisation: string | null }[];
  };
  stages: Stage[]; queue: QueueItem[]; progress: Progress; companies: Company[];
  supporting: { documents: { id: string; origin: string; url: string | null; title: string | null; status: string; status_reason: string | null; found_via: string | null }[];
                searches: { purpose: string; query: string; status: string; results: number; link: string }[];
                linkedin_searches: { organisation: string; role: string; url: string }[] };
  rule: string;
};

const STAGE_TONE: Record<string, string> = { done: "b-good", done_with_failures: "b-warn", incomplete: "b-warn", failed: "b-bad", not_run: "b-none", not_applicable: "b-none", running: "b-info" };

type Progress = { state: string; state_label: string; tally: string; completed: number; failed: number; pending: number; total: number };
const PROGRESS_TONE: Record<string, string> = { complete: "b-good", complete_with_failures: "b-warn", incomplete: "b-warn", failed: "b-bad", not_run: "b-none" };

export function ResearchFile({ oppId, onChanged }: { oppId: string; onChanged: () => void }) {
  const r = useApi<File>(`/opportunities/${oppId}/research-file`);
  const a = useAction();
  const [showSupport, setShowSupport] = useState(false);
  if (!r.data) return null;
  const f = r.data;
  const s = f.summary;
  const unfinished = f.progress.state === "incomplete";
  const started = f.progress.state !== "not_run";
  const retryable = f.progress.failed > 0 || f.stages.some((x) => x.status === "failed");
  async function run() {
    const out = await a.run(() => api.post(`/opportunities/${oppId}/deep-research`, {}), "Research run");
    if (out) { r.reload(); onChanged(); }
  }
  async function retry() {
    const out = await a.run(() => api.post(`/opportunities/${oppId}/deep-research/retry-failed`, {}), "Retry run");
    if (out) { r.reload(); onChanged(); }
  }
  return (
    <section className="panel" aria-label="Research file">
      <div className="panel-head"><h2>Research file</h2>
        <div className="actions">
          {retryable && <button type="button" className="btn" disabled={a.busy} onClick={retry}>Retry failed ({f.progress.failed || "stage"})</button>}
          <button type="button" className="btn btn-primary" disabled={a.busy} onClick={run}>{a.busy ? "Researching…" : unfinished && started ? "Continue research" : started ? "Research again" : "Deep research"}</button>
        </div></div>
      <p className="small" role="status"><Tag text={f.progress.state_label} tone={PROGRESS_TONE[f.progress.state]} /> <span className="muted">{f.progress.tally} organisation-stage item(s)</span></p>
      <ul className="list-plain small" aria-label="Research stages" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {f.stages.map((x) => <li key={x.stage} title={x.detail ?? ""}><Tag text={`${x.label.split(" (")[0]}: ${x.status_label}${x.progress && x.status !== "done" ? ` (${x.progress})` : ""}`} tone={STAGE_TONE[x.status]} /></li>)}
      </ul>
      <QueueList queue={f.queue} />
      <ActionNote state={a} />

      <div className="grid grid-2" style={{ marginTop: 12 }}>
        <div className="stack">
          <Block q="What is happening, and the evidence">
            <p>{s.what.text}</p>
            <ul className="list-plain small">{s.what.sources.map((d) => <li key={d.url}><a href={d.url} target="_blank" rel="noreferrer noopener">{d.title ?? d.url}</a>{d.published_at && <span className="muted"> · {dateOnly(d.published_at)}</span>}</li>)}
              {s.what.source_count === 0 && <li className="muted">no source document retained</li>}</ul>
          </Block>
          <Block q="Why it is relevant to WFC">
            <p>{s.why.text}</p>
            <p className="small muted">{s.why.label} · {s.why.priority_reason}</p>
          </Block>
          <Block q="Organisations involved and their roles">
            <ul className="list-plain small">{s.organisations.map((o) => <li key={o.id}><Link href={`/companies/${o.id}`}>{o.name}</Link> <span className="muted">· {o.role} · {o.kind_label} · </span><span className={o.in_cargo_scope ? "muted" : "action-error"}>{o.freight_scope_label}</span></li>)}
              {s.organisations.length === 0 && <li className="muted">no organisation established yet</li>}</ul>
          </Block>
          <Block q="Geographic and airport scope">
            <p className="small">{s.geography.countries.join(", ") || <span className="muted">country not established</span>}</p>
            {s.geography.airports.length > 0 && <ul className="list-plain small">{s.geography.airports.map((x, i) => <li key={i}>{x.label} <span className="muted">· {label(x.role)} · {x.support}</span></li>)}</ul>}
            {s.geography.company_airports.length > 0 && <p className="small muted">Company airports (offices, stations, served): {s.geography.company_airports.map((x) => `${x.company}: ${x.label} (${x.role.toLowerCase()})`).join("; ")}</p>}
            {s.geography.airports.length === 0 && s.geography.company_airports.length === 0 && <p className="small muted">no airport stated by any source</p>}
          </Block>
          <Block q="Services and freight capability categories">
            <p className="small">{s.services.category}{s.services.service ? ` · ${s.services.service}` : ""}</p>
          </Block>
        </div>
        <div className="stack">
          <Block q="Named people, roles and geographic responsibilities">
            {s.people.length === 0 ? <p className="small muted">nobody identified yet</p> : (
              <ul className="list-plain small">{s.people.map((p) => (
                <li key={p.id}><Link href={`/relationships/${p.id}`}>{p.full_name}</Link> <span className="muted">· {p.role_title ?? "title not bound"}{p.organisation ? ` · ${p.organisation}` : ""}{p.involvement_label ? ` · ${p.involvement_label}` : ""}{p.remit_countries.length ? ` · ${p.remit_countries.join(", ")}` : ""} · {p.state_label}</span>
                  <div className="muted">e-mail: <PersonEmail email={p.published_email} status={p.published_email_status} research={p.email_research ?? { status: p.email_status }} /> · {p.linkedin_profile_url ? <a href={p.linkedin_profile_url} target="_blank" rel="noreferrer noopener">confirmed LinkedIn profile</a> : p.linkedin_search_url ? <a href={p.linkedin_search_url} target="_blank" rel="noreferrer noopener">LinkedIn search</a> : "no LinkedIn search"}{p.relationships ? ` · ${p.relationships} WFC relationship(s)` : ""}{p.routes ? ` · ${p.routes} route(s)` : ""}</div></li>))}</ul>)}
            {s.external_contacts.length > 0 && <div className="small" style={{ marginTop: 8 }}><b>External contacts (not commercial contacts)</b>
              <ul className="list-plain">{s.external_contacts.map((x) => <li key={x.id}><Link href={`/relationships/${x.id}`}>{x.full_name}</Link>
                <span className="muted"> · {x.involvement_label}{x.organisation ? ` · ${x.organisation}` : ""}{x.role_title ? ` · ${x.role_title}` : ""}</span></li>)}</ul></div>}
          </Block>
          <Block q="Website, LinkedIn and published e-mail routes">
            <ul className="list-plain small">{s.routes.map((x) => <li key={x.company}><b>{x.company}</b>: {x.website ? <a href={x.website} target="_blank" rel="noreferrer noopener">website</a> : <span className="muted">no website found</span>}
              {x.contact_page && <> · <a href={x.contact_page} target="_blank" rel="noreferrer noopener">contact page</a></>}
              {x.emails.some((e) => e.current) ? <> · {x.emails.filter((e) => e.current).map((e) => `${e.value}${e.department ? ` (${e.department})` : ""}`).join(", ")}</> : <span className="muted"> · no current published e-mail</span>}
              {x.emails.some((e) => !e.current) && <div className="small muted">Not current routes: {x.emails.filter((e) => !e.current).map((e) => `${e.value} — ${e.status_label ?? e.status}`).join("; ")}</div>}</li>)}</ul>
          </Block>
          <Block q="Existing representation, partner and relationship evidence">
            <p className="small"><b>{s.relationships.coverage_label}</b></p>
            {s.relationships.representation.length > 0 && <ul className="list-plain small">{s.relationships.representation.map((x, i) => <li key={i}>{x.company}: {x.relationship} — {x.counterparty ?? "counterparty not named"} <span className="muted">({x.status})</span></li>)}</ul>}
            {s.relationships.recorded.length > 0 && <ul className="list-plain small">{s.relationships.recorded.map((x, i) => <li key={i}>{x.person}: {x.holder_label} · {label(x.nature)} <span className="muted">({x.status})</span></li>)}</ul>}
            {s.relationships.routes_available.length > 0 && <p className="small">{s.relationships.routes_available.length} introduction route(s) available</p>}
          </Block>
          <Block q="What remains uncertain">
            {s.uncertain.length === 0 ? <p className="small muted">nothing flagged</p> : <ul className="small">{s.uncertain.map((u) => <li key={u}>{u}</li>)}</ul>}
          </Block>
          <Block q="Next action">
            <p><b>{s.next_action}</b>{f.opportunity.next_action_due && <span className="muted small"> · due {dateOnly(f.opportunity.next_action_due)}</span>}</p>
          </Block>
        </div>
      </div>

      <button type="button" className="btn btn-small" aria-expanded={showSupport} onClick={() => setShowSupport((v) => !v)} style={{ marginTop: 12 }}>
        {showSupport ? "Hide supporting research" : "Supporting research"}</button>
      {showSupport && (
        <div className="stack" style={{ marginTop: 12 }}>
          {f.companies.map((c) => (
            <details key={c.id} className="small">
              <summary><b>{c.name}</b> · {c.kind_label} · {c.freight_scope_label} · research {c.research.found}/{c.research.total} · {c.evidence_strength.explanation}</summary>
              <ul className="list-plain" style={{ marginTop: 6 }}>
                {c.research.fields.map((x) => <li key={x.field}><Tag text={x.status_label} tone={x.status === "found" ? "b-good" : x.status === "not_searched" ? "b-none" : "b-warn"} /> {x.label}{x.detail && x.status !== "found" ? <span className="muted"> · {x.detail}</span> : null}</li>)}
              </ul>
              <ul className="list-plain" style={{ marginTop: 6 }}>{c.evidence.map((e, i) => <li key={i}><Tag text={label(e.supports)} tone="b-none" /> {e.quote ? `“${e.quote.slice(0, 200)}”` : ""} {e.url && <a href={e.url} target="_blank" rel="noreferrer noopener">source</a>}{e.note && <span className="muted"> · {e.note}</span>}<span className="muted"> · {dateTime(e.observed_at)}</span></li>)}</ul>
              <p><Link href={`/companies/${c.id}`}>Open the company record</Link></p>
            </details>))}
          <details className="small"><summary><b>Pages read and searches run</b> · {f.supporting.documents.length} document(s) · {f.supporting.searches.length} search(es)</summary>
            <ul className="list-plain">{f.supporting.documents.map((x) => <li key={x.id}><Tag text={label(x.status)} tone={x.status === "read" ? "b-good" : x.status === "failed" ? "b-bad" : "b-none"} /> {x.url ? <a href={x.url} target="_blank" rel="noreferrer noopener">{x.title ?? x.url}</a> : x.title}<span className="muted"> · {label(x.origin)}{x.found_via ? ` · ${x.found_via}` : ""}{x.status_reason ? ` · ${x.status_reason}` : ""}</span></li>)}</ul>
            <ul className="list-plain">{f.supporting.searches.map((x) => <li key={x.query}><Tag text={x.status === "run" ? `run: ${x.results}` : label(x.status)} tone={x.status === "run" ? "b-good" : "b-warn"} /> {x.purpose}: <a href={x.link} target="_blank" rel="noreferrer noopener">{x.query}</a></li>)}</ul>
          </details>
        </div>
      )}
      <p className="small muted" style={{ marginTop: 8 }}>{f.rule}</p>
    </section>
  );
}

function Block({ q, children }: { q: string; children: ReactNode }) {
  return <div><p className="question">{q}</p>{children}</div>;
}
