"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { OpportunityTechnical } from "@/components/OpportunityTechnical";
import { CoverageTag, StatusTag, Tag, TypeTag } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateOnly, dateTime, deadline, label, type DeadlineInfo } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";
import { ResearchFile } from "@/components/ResearchFile";

type Evidence = { claim_id: string; claim_type: string; quote: string; review_status: string; source_name: string | null; title: string | null;
                  canonical_url: string; published_at: string | null; retrieved_at: string; summary_en: string | null; excluded_at: string | null };
type Base = { opportunity: { id: string; title: string; module: string; organisation: string | null; tender_ref: string | null; tender_status_basis: string | null;
                             deadline_utc: string | null; deadline_source_tz: string | null; deadline_info: DeadlineInfo | null; signal_id: string | null;
                             tender_state: { published_at?: string | null } | null };
              evidence: Evidence[]; geography: { country_code: string; name: string; role: string; support: string }[] };
type Role = { role_title: string | null; organisation: string | null; role_status: string; affiliation: string; affiliation_label: string; binding: string;
              source: string; quote: string | null };
type Person = { id: string; full_name: string; role_title: string | null; organisation: string | null; organisation_id: string | null; state: string;
                state_label: string; role_on_opportunity?: string; relevance_basis?: string; link_status?: string; linkedin_search_url?: string;
                linkedin_profile_url: string | null; relationship_owner: string | null; last_verified_at: string | null; possible_routes: number; roles?: Role[] };
type Org = { id: string; name: string; kind: string; country: string | null; website: string | null; newsroom_url: string | null; leadership_url: string | null;
             involvement: string };
type Search = { organisation: string; role: string; country: string; url: string; kind: string };
type WebSearch = { purpose: string; query: string; status: string; results: number; link: string; reason?: string };
type Doc = { id: string; origin: string; url: string | null; title: string | null; organisation: string | null; page_kind: string; found_via: string | null;
             status: string; status_reason: string | null; sections_total: number; sections_read: number; ai_status: string; ai_sections_read: number;
             people_found: number };
type Coverage = { documents: number; read: number; queued: number; failed: number; skipped: number; sections_total: number; sections_read: number;
                  ai_sections_read: number; ai_connected: boolean; remaining: string[]; not_searched: string[]; limits_hit?: string[];
                  searches_run: number; searches_not_run: number; searches_failed: number; duplicates_flagged?: number };
type LatestRun = { started_at: string; methods: string[]; unavailable: { method: string; reason: string }[]; candidates_found: number;
                   outcome: string | null; coverage: Coverage | Record<string, never>; searches: WebSearch[] };
type RouteRow = { id: string; target_person_id: string; target: string; introducer: string; wfc_holder_label: string | null; connection_basis: string;
                  evidence_url: string | null; willingness_basis: string | null; status: string };
type RelRow = { id: string; person_id: string; person: string; holder_label: string; nature: string; basis: string; status: string };
type Rel = { organisations: Org[]; people: Person[]; people_at_organisation: Person[]; coverage: string; coverage_label: string; searches: Search[];
             target_roles: { key: string; label: string }[]; latest_research: LatestRun | null; gaps: string[]; actions: string[]; linkedin_integration: string;
             documents: Doc[]; relationships: RelRow[]; routes_available: RouteRow[]; routes_possible: RouteRow[]; duplicates: { id: string }[];
             engagements: { id: string; occurred_at: string; kind: string; summary: string; person: string | null; person_id: string | null; owner_label: string | null }[] };
type Intel = { interpretation: { label: string; text: string; unconfirmed: string[]; category: string; record_type_label: string };
               priority_reason: string; review_state: string | null; relationships: Rel; notes: { id: string; body: string; author_label: string | null; created_at: string }[];
               workspace: { progress: string; progress_label: string; closed_reason: string | null; saved: boolean; owner_label: string | null; next_action: string | null;
                            next_action_due: string | null; record_type: string; record_type_label: string; tender_status: string | null; tender_status_label: string | null } };
type Found = { person_id: string; name: string; role: string | null; role_status: string; organisation: string | null; affiliation_label: string;
               new: boolean; source: string | null; method: string };
type Research = { outcome: string; methods: string[]; unavailable: { method: string; reason: string }[]; found: Found[]; coverage: Coverage;
                  web_searches: WebSearch[]; searches: Search[]; gaps: string[]; actions: string[] };

const STATE_TONE: Record<string, string> = { existing_relationship: "b-good", introduction_available: "b-good", identity_confirmed: "b-info", research_candidate: "b-warn" };
const OUTCOME: Record<string, [string, string]> = {
  people_found: ["People found in the sources read", "b-good"],
  no_people_found: ["No people found in the sources read", "b-info"],
  incomplete: ["Research incomplete", "b-warn"],
};
const ORIGIN_LABEL: Record<string, string> = { opportunity_source: "Source of this opportunity", user_url: "Page added by the team", user_document: "Document added by the team",
                                               search_result: "Web search result", organisation_page: "Organisation page", followed_link: "Linked from the organisation's site",
                                               guessed_page: "Guessed address" };
const DOC_STATUS: Record<string, [string, string]> = { read: ["Read", "b-good"], partial: ["Partly read", "b-warn"], queued: ["Not read yet", "b-warn"],
                                                      failed: ["Could not fetch", "b-bad"], skipped: ["Skipped", "b-none"] };
const PROGRESS: [string, string][] = [["new", "New"], ["reviewing", "Reviewing"], ["pursuing", "Pursuing"], ["on_hold", "On hold"], ["closed", "Closed"]];
const ROLE_LABEL: Record<string, string> = { procurement_contact: "Procurement contact", commercial_leader: "Commercial leader", decision_maker: "Decision maker (recorded by a person)",
                                             department_lead: "Department lead", regional_representative: "Regional representative", partner: "Partner",
                                             named_in_source: "Named in the source", unknown: "Role on this opportunity not established" };

export default function OpportunityPage() {
  const { id = "" } = useParams<{ id: string }>();
  const base = useApi<Base>(id ? `/opportunities/${id}` : null);
  const intel = useApi<Intel>(id ? `/opportunities/${id}/intelligence` : null);
  const reload = () => { base.reload(); intel.reload(); };
  return (
    <>
      {(base.stale || intel.stale) && <StaleBanner onRetry={reload} />}
      {(base.status === "loading" || intel.status === "loading") && <Loading what="opportunity" />}
      {base.status === "error" && !base.data && <ErrorState error={base.error} onRetry={reload} />}
      {intel.status === "error" && !intel.data && <ErrorState error={intel.error} onRetry={reload} />}
      {base.data && intel.data && <Body id={id} b={base.data} i={intel.data} reload={reload} />}
    </>
  );
}

function Body({ id, b, i, reload }: { id: string; b: Base; i: Intel; reload: () => void }) {
  const o = b.opportunity;
  const ws = i.workspace;
  const rel = i.relationships;
  const a = useAction();
  const [research, setResearch] = useState<Research | null>(null);
  const evidence = b.evidence.filter((e) => !e.excluded_at);
  const sources = [...new Map(evidence.map((e) => [e.canonical_url, e])).values()];
  const countries = [...new Set(b.geography.filter((g) => g.support !== "unverified").map((g) => g.name))];
  const incomplete = rel.latest_research?.outcome === "incomplete";

  async function runResearch(mode: "start" | "continue") {
    const out = await a.run(() => api.post<Research>(`/opportunities/${id}/research`, { mode }), mode === "start" ? "Research run finished" : "Research continued");
    if (out) { setResearch(out); reload(); }
  }
  return (
    <div className="stack">
      <PageHeader eyebrow={`Opportunities · ${i.interpretation.category}`} title={o.title}
                  description={`${o.organisation ?? "Organisation not established"}${o.tender_ref ? ` · reference ${o.tender_ref}` : ""}`}
                  actions={<>
                    <button type="button" className="btn btn-primary" disabled={a.busy} onClick={() => runResearch("start")}>Research relationships</button>
                    {incomplete && <button type="button" className="btn" disabled={a.busy} onClick={() => runResearch("continue")}>Continue research</button>}
                    <button type="button" className="btn" disabled={a.busy}
                            onClick={() => a.run(() => api.post(`/opportunities/${id}/saved`, { saved: !ws.saved }), ws.saved ? "Removed from saved" : "Saved").then(reload)}>
                      {ws.saved ? "Saved ✓" : "Save"}</button>
                    <a className="btn" href={`/api/opportunities/${id}/export.md`}>Export brief</a>
                  </>} />
      <div className="small"><TypeTag r={{ record_type: ws.record_type, record_type_label: ws.record_type_label }} />{" "}
        <StatusTag r={{ tender_status: ws.tender_status, tender_status_label: ws.tender_status_label }} />{" "}
        <Tag text={`Progress: ${ws.progress_label}`} tone="b-info" />{" "}<CoverageTag coverage={rel.coverage} label={rel.coverage_label} />
        {i.review_state && <span className="muted"> · {i.review_state}</span>}</div>
      <ActionNote state={a} />
      {research && <ResearchResult r={research} />}
      <ResearchFile oppId={id} onChanged={reload} />

      <div className="grid grid-2">
        <section className="panel" aria-label="What is happening">
          <p className="question">What is happening?</p>
          <dl className="kv">
            <dt>Source facts</dt><dd>{sources[0]?.summary_en ?? (sources.length ? `${sources.length} source document(s) below` : "No source document: record from WFC data or added by the team")}</dd>
            <dt>Organisation</dt><dd>{o.organisation ?? "Not established"}</dd>
            <dt>Geography</dt><dd>{countries.join(", ") || "Not established by the source"}</dd>
            <dt>Source date</dt><dd>{o.tender_state?.published_at ? dateOnly(o.tender_state.published_at) : sources[0]?.published_at ? dateOnly(sources[0].published_at) : "Not stated"}</dd>
            <dt>Stated deadline</dt><dd>{o.deadline_utc || o.deadline_info ? deadline(o.deadline_utc, o.deadline_source_tz, o.deadline_info) : "Not stated"}</dd>
            <dt>Tender status</dt><dd>{ws.tender_status_label ?? "n/a"}{o.tender_status_basis && <div className="small muted">{o.tender_status_basis}</div>}</dd>
          </dl>
          {sources.length > 0 && (
            <ul className="list-plain small" aria-label="Sources">{sources.slice(0, 4).map((e) => (
              <li key={e.canonical_url}>“{e.quote.slice(0, 220)}{e.quote.length > 220 ? "…" : ""}” <span className="muted">— {e.source_name ?? "source"},{" "}
                <a href={e.canonical_url} target="_blank" rel="noreferrer noopener">{e.title ?? e.canonical_url}</a>
                {e.published_at ? `, published ${dateOnly(e.published_at)}` : ", publication date not stated"}{e.review_status === "proposed" ? " · not yet reviewed" : ""}</span></li>
            ))}</ul>
          )}
        </section>
        <section className="panel interpretation" aria-label="Why it could matter">
          <p className="question">Why could it matter to WFC?</p>
          <p className="fact-label">{i.interpretation.label}</p>
          <p>{i.interpretation.text}</p>
          {i.interpretation.unconfirmed.length > 0 && (
            <><p className="fact-label">What remains unconfirmed</p><ul>{i.interpretation.unconfirmed.map((u) => <li key={u} className="small">{u}</li>)}</ul></>
          )}
          <p className="small"><b>Priority:</b> {i.priority_reason}</p>
        </section>
      </div>

      <section className="panel" aria-label="Organisations involved">
        <p className="question">Which organisations are involved?</p>
        {rel.organisations.length === 0 ? <Empty title="No organisation established yet" /> : (
          <ul className="list-plain">{rel.organisations.map((g) => (
            <li key={g.id}><Link href={`/companies/${g.id}`}>{g.name}</Link> <span className="muted small">· {g.involvement}{g.country ? ` · ${g.country}` : ""}</span>
              <div className="small">Research pages: {[["website", g.website], ["newsroom", g.newsroom_url], ["leadership page", g.leadership_url]]
                .filter(([, u]) => u).map(([l, u]) => <span key={l as string}><a href={u as string} target="_blank" rel="noreferrer noopener">{l}</a> </span>)}
                {!g.website && !g.newsroom_url && !g.leadership_url && <span className="muted">none recorded, so its own pages are not read</span>}</div>
              <ResearchPagesForm org={g} onSaved={reload} /></li>
          ))}</ul>
        )}
      </section>

      <section className="panel" aria-label="Who appears relevant">
        <div className="panel-head"><p className="question">Who appears relevant?</p><AddPerson id={id} onAdded={reload} /></div>
        {rel.people.length === 0 ? <Empty title="No people identified yet">Use Research relationships, or add a person you know is relevant.</Empty> : (
          <div role="region" aria-label="Relevant people">
            <PeopleTable title="Confirmed identities" rows={rel.people.filter((p) => p.state !== "research_candidate")} id={id} busy={a.busy}
                         empty="No identity confirmed yet: confirm a candidate on their page (with how it was confirmed)."
                         onLink={(pid, status, msg) => a.run(() => api.post(`/opportunities/${id}/people`, { person_id: pid, status }), msg).then(reload)} />
            <PeopleTable title="Research candidates" rows={rel.people.filter((p) => p.state === "research_candidate")} id={id} busy={a.busy}
                         empty="No unconfirmed candidates."
                         onLink={(pid, status, msg) => a.run(() => api.post(`/opportunities/${id}/people`, { person_id: pid, status }), msg).then(reload)} />
            <p className="small muted">A title or organisation is shown only where a source passage binds it to the person; otherwise it reads &ldquo;not established&rdquo;.
              Being named does not make anyone a decision maker.</p>
          </div>
        )}
        {rel.duplicates.length > 0 && <p className="small"><Tag text={`${rel.duplicates.length} possible duplicate(s)`} tone="b-warn" /> Same name, organisation not
          established or different: <Link href="/relationships#duplicates">review them</Link> (nothing is merged automatically).</p>}
        {rel.people_at_organisation.length > 0 && (
          <p className="small">Also known at {rel.organisations[0]?.name}: {rel.people_at_organisation.map((p) => (
            <span key={p.id}><Link href={`/relationships/${p.id}`}>{p.full_name}</Link> ({p.state_label}) </span>))}</p>
        )}
      </section>

      <div className="grid grid-2">
        <section className="panel" aria-label="Existing relationships">
          <p className="question">What existing relationship is recorded?</p>
          {rel.relationships.length === 0 ? <p className="muted">None recorded. A relationship is recorded on the person&apos;s page, with who holds it and how it is known.</p> : (
            <ul className="list-plain">{rel.relationships.map((r) => (
              <li key={r.id}><Link href={`/relationships/${r.person_id}`}>{r.person}</Link> <span className="small muted">· held by {r.holder_label} · {label(r.nature)}
                {r.status !== "current" ? ` · ${r.status}` : ""}</span><div className="small">{r.basis}</div></li>))}</ul>
          )}
        </section>
        <section className="panel" aria-label="Introduction routes">
          <p className="question">Who could introduce us?</p>
          {rel.routes_available.length === 0 && rel.routes_possible.length === 0 ? <p className="muted">No introduction route recorded. A route is available only when the introducer&apos;s relationship and willingness are confirmed.</p> : <>
            {rel.routes_available.length > 0 && <><p className="fact-label">Confirmed introductions</p><ul className="list-plain" aria-label="Confirmed introductions">{rel.routes_available.map((r) => (
              <li key={r.id}><Link href={`/relationships/${r.target_person_id}`}>{r.target}</Link> via {r.introducer} <Tag text={r.status === "available" ? "Introduction available" : label(r.status)} tone="b-good" />
                <div className="small muted">{r.connection_basis} · willingness: {r.willingness_basis}</div></li>))}</ul></>}
            {rel.routes_possible.length > 0 && <><p className="fact-label">Possible routes (not confirmed)</p><ul className="list-plain" aria-label="Possible routes">{rel.routes_possible.map((r) => (
              <li key={r.id}><Link href={`/relationships/${r.target_person_id}`}>{r.target}</Link> via {r.introducer} <Tag text="Possible route, not confirmed" tone="b-warn" />
                <div className="small muted">{r.connection_basis}</div></li>))}</ul></>}
          </>}
        </section>
      </div>

      <ResearchCoverage id={id} rel={rel} onChanged={reload} />

      <section className="panel" aria-label="Relationship gaps">
        <p className="question">What relationship information is missing?</p>
        <RelationshipImpact id={id} />
        <ul>{rel.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
        {rel.actions.length > 0 && <><p className="fact-label">Useful next actions</p><ul>{rel.actions.map((x) => <li key={x}>{x}</li>)}</ul></>}
        <p className="fact-label">Targeted LinkedIn searches ({rel.linkedin_integration}). These are searches, not contacts.</p>
        <ul className="list-plain small">{rel.searches.map((s) => (
          <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer noopener">{s.role} · {s.organisation}{s.country ? ` · ${s.country}` : ""}</a></li>))}</ul>
        {rel.latest_research && <p className="muted small">Last researched {dateTime(rel.latest_research.started_at)}
          {rel.latest_research.outcome ? ` (${OUTCOME[rel.latest_research.outcome]?.[0].toLowerCase() ?? rel.latest_research.outcome})` : ""} using{" "}
          {rel.latest_research.methods.map(methodLabel).join(", ") || "no method"};
          not available: {rel.latest_research.unavailable.map((u) => methodLabel(u.method)).join(", ") || "none"}.</p>}
      </section>

      <Workspace id={id} i={i} reload={reload} />

      <TechnicalDetails id={id} reload={reload} />
    </div>
  );
}

/** Collapsed by default so validation detail never fills the page; a link with ?detail=technical opens it. */
function TechnicalDetails({ id, reload }: { id: string; reload: () => void }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (new URLSearchParams(window.location.search).get("detail") === "technical") setOpen(true); }, []);
  return (
      <details className="panel" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
        <summary>Technical detail: evidence checks, qualification, prioritisation factors and full history</summary>
        {open && <div style={{ marginTop: 12 }}><OpportunityTechnical id={id} onChanged={reload} /></div>}
      </details>
  );
}

function ResearchResult({ r }: { r: Research }) {
  const [text, tone] = OUTCOME[r.outcome] ?? [r.outcome, "b-none"];
  return (
    <div className="notice" role="status" aria-label="Research result">
      <strong><Tag text={text} tone={tone} /> {r.found.length} finding(s) in this run{r.found.length === 0 && r.outcome === "people_found" ? " (people found earlier are listed below)" : ""},
        from {r.methods.map(methodLabel).join(", ") || "no available method"}.</strong>
      {r.found.length > 0 && <ul className="small">{r.found.map((f, n) => (
        <li key={n}><Link href={`/relationships/${f.person_id}`}>{f.name}</Link>{f.role ? `, ${f.role}${f.role_status !== "current" ? ` (${f.role_status})` : ""}` : ", title not established"}
          {" · "}{f.organisation ? `${f.organisation} (${f.affiliation_label.toLowerCase()})` : "organisation not established"} · {f.method}{f.source ? `: ${f.source}` : ""}
          {f.new ? "" : " (already known)"}</li>))}</ul>}
      {r.outcome === "incomplete" && <div className="small"><b>Still to do:</b> {[...r.coverage.remaining, ...(r.coverage.limits_hit ?? [])].join("; ")}. Choose Continue research.</div>}
      <div className="small muted">Not searched: {r.coverage.not_searched.join("; ")}.</div>
      <div className="small muted">Found people are research candidates until a person confirms who they are. Being named in a source does not make someone a decision maker.</div>
    </div>
  );
}

type Impact = { scored: boolean; reason?: string; score?: number; band_label?: string; relationship_points?: number; relationship_max?: number; headroom?: number;
                explanation?: string; people_judged?: number; people_linked?: number };
/** How much of the opportunity's score its relationship position accounts for (ATLAS v1.0 "impact on success", 29 Oct 2026). */
function RelationshipImpact({ id }: { id: string }) {
  const r = useApi<Impact>(`/relationships/impact/${id}`);
  if (!r.data) return null;
  if (!r.data.scored) return <p className="small muted" aria-label="Relationship impact">Not scored: {r.data.reason}.</p>;
  const d = r.data;
  return (
    <div className="small" aria-label="Relationship impact" style={{ marginBottom: 10 }}>
      <b>Relationship share of the score:</b> {d.relationship_points} of {d.relationship_max} points (score {d.score}, {d.band_label}); {d.headroom} more available.
      <span className="muted"> {d.people_judged} of {d.people_linked} linked people judged as stakeholders. {d.explanation}</span>
    </div>
  );
}

function PeopleTable({ title, rows, empty, busy, onLink }: { title: string; rows: Person[]; id: string; empty: string; busy: boolean;
                                                              onLink: (pid: string, status: string, msg: string) => void }) {
  return (
    <>
      <p className="fact-label">{title} ({rows.length})</p>
      {rows.length === 0 ? <p className="small muted">{empty}</p> : (
        <TableWrap label={title}>
          <table><thead><tr><th>Person</th><th>Evidenced title and organisation</th><th>Role on this opportunity</th><th>Status</th><th>Why relevant (evidence)</th><th>LinkedIn</th><th /></tr></thead>
            <tbody>{rows.map((p) => (
              <tr key={p.id} className={p.link_status === "not_relevant" ? "muted" : undefined}>
                <td><Link href={`/relationships/${p.id}`}>{p.full_name}</Link><div className="small muted">{personLine(p)}</div></td>
                <td className="small">{(p.roles ?? []).length === 0 ? <span className="muted">No title or organisation bound by a source</span> : (
                  <ul className="list-plain">{(p.roles ?? []).slice(0, 3).map((r, n) => (
                    <li key={n} title={r.quote ?? r.binding}>{r.role_title ?? "title not stated"}{r.role_status !== "current" ? ` (${r.role_status})` : ""}
                      {" · "}{r.organisation ?? "organisation not established"}{r.organisation ? <span className="muted"> · {r.affiliation_label.toLowerCase()}</span> : null}
                      {r.source === "before_upgrade" ? <span className="muted"> · recorded before the evidence rules</span> : null}</li>))}</ul>)}</td>
                <td className="small">{ROLE_LABEL[p.role_on_opportunity ?? "unknown"]}</td>
                <td><Tag text={p.state_label} tone={STATE_TONE[p.state]} />{p.link_status === "not_relevant" && <div className="small">marked not relevant</div>}</td>
                <td className="small">{p.relevance_basis}</td>
                <td className="small">{p.linkedin_profile_url ? <a href={p.linkedin_profile_url} target="_blank" rel="noreferrer noopener">Confirmed profile</a>
                  : <a href={p.linkedin_search_url} target="_blank" rel="noreferrer noopener">Search LinkedIn</a>}</td>
                <td className="actions">{p.link_status !== "not_relevant" ? (
                  <button type="button" className="btn btn-small" disabled={busy} onClick={() => onLink(p.id, "not_relevant", "Marked not relevant")}>Not relevant</button>
                ) : (
                  <button type="button" className="btn btn-small" disabled={busy} onClick={() => onLink(p.id, "relevant", "Restored")}>Restore</button>
                )}</td>
              </tr>
            ))}</tbody></table>
        </TableWrap>
      )}
    </>
  );
}

function ResearchCoverage({ id, rel, onChanged }: { id: string; rel: Rel; onChanged: () => void }) {
  const run = rel.latest_research;
  const cov = (run?.coverage ?? {}) as Partial<Coverage>;
  const searches = run?.searches ?? [];
  const [text, tone] = run?.outcome ? (OUTCOME[run.outcome] ?? [run.outcome, "b-none"]) : ["Not researched yet", "b-none"];
  return (
    <section className="panel" aria-label="Research coverage">
      <div className="panel-head"><p className="question">Research coverage</p><Tag text={text} tone={tone} /></div>
      {run && <p className="small">{cov.read ?? 0} of {cov.documents ?? 0} document(s) and page(s) read; {cov.sections_read ?? 0} of {cov.sections_total ?? 0} section(s) read by
        the rules; {cov.ai_connected ? `${cov.ai_sections_read ?? 0} section(s) read by the configured AI extractor` : "the configured AI extractor is not connected"};
        {" "}{cov.failed ?? 0} could not be fetched; {cov.skipped ?? 0} skipped; {cov.queued ?? 0} still to read.</p>}
      {(cov.remaining ?? []).length > 0 && <><p className="fact-label">Remaining work</p><ul className="small">{(cov.remaining ?? []).concat(cov.limits_hit ?? []).map((x) => <li key={x}>{x}</li>)}</ul></>}
      {(cov.not_searched ?? []).length > 0 && <><p className="fact-label">Not searched</p><ul className="small">{(cov.not_searched ?? []).map((x) => <li key={x}>{x}</li>)}</ul></>}
      {searches.length > 0 && <>
        <p className="fact-label">Web searches</p>
        <ul className="list-plain small" aria-label="Web searches">{searches.map((s) => (
          <li key={s.query}>{s.purpose}: <code>{s.query}</code> · {s.status === "run" ? `searched, ${s.results} result(s)` : s.status === "failed" ? `failed (${s.reason})` : "not searched by ATLAS"}
            {" · "}<a href={s.link} target="_blank" rel="noreferrer noopener">open this search yourself</a></li>))}</ul></>}
      {rel.documents.length > 0 && (
        <TableWrap label="Documents and pages">
          <table><thead><tr><th>Document or page</th><th>How it was found</th><th>Status</th><th>Sections read</th><th>People</th></tr></thead>
            <tbody>{rel.documents.map((d) => {
              const [st, stTone] = DOC_STATUS[d.status] ?? [d.status, "b-none"];
              return (
                <tr key={d.id}>
                  <td>{d.url ? <a href={d.url} target="_blank" rel="noreferrer noopener">{d.title ?? d.url}</a> : (d.title ?? "Document")}
                    <div className="small muted">{ORIGIN_LABEL[d.origin] ?? d.origin}{d.organisation ? ` · ${d.organisation}` : ""}</div></td>
                  <td className="small">{d.found_via ?? "—"}</td>
                  <td><Tag text={st} tone={stTone} />{d.status_reason && <div className="small muted">{d.status_reason}</div>}</td>
                  <td className="small">{d.sections_total ? `rules ${d.sections_read}/${d.sections_total}` : "—"}
                    {d.sections_total ? ` · AI ${d.ai_status === "not_connected" ? "not connected" : `${d.ai_sections_read}/${d.sections_total}`}` : ""}</td>
                  <td className="num">{d.people_found}</td>
                </tr>
              );
            })}</tbody></table>
        </TableWrap>
      )}
      <AddResearchSource id={id} onAdded={onChanged} />
    </section>
  );
}

function AddResearchSource({ id, onAdded }: { id: string; onAdded: () => void }) {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    let ok;
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      if (title) fd.append("title", title);
      ok = await a.run(() => api.post(`/opportunities/${id}/research/documents`, fd), "Document added: it is read at the next research run");
    } else {
      ok = await a.run(() => api.post(`/opportunities/${id}/research/sources`, url ? { url, title: title || null } : { text, title: title || null }),
                       url ? "Page added: it is read at the next research run" : "Document added: it is read at the next research run");
    }
    if (ok) { setUrl(""); setTitle(""); setText(""); setFile(null); onAdded(); }
  }
  return (
    <form className="form-grid" onSubmit={submit} aria-label="Add a page or document for research">
      <p className="fact-label" style={{ gridColumn: "1 / -1" }}>Add a relevant page or document (company announcement, press release, biography, market report)</p>
      <label className="field">Page URL<input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" /></label>
      <label className="field">Title (optional)<input className="input" value={title} onChange={(e) => setTitle(e.target.value)} /></label>
      <label className="field">Or a document (PDF, HTML or text)<input className="input" type="file" accept=".pdf,.html,.htm,.txt,.md"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
      <label className="field" style={{ gridColumn: "1 / -1" }}>Or paste the document text<textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} /></label>
      <div className="actions"><button className="btn" type="submit" disabled={a.busy || (!url && !text.trim() && !file) || (!!url && !/^https?:\/\/\S+$/.test(url))}>Add for research</button></div>
      <ActionNote state={a} />
    </form>
  );
}

function ResearchPagesForm({ org, onSaved }: { org: Org; onSaved: () => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ website: org.website ?? "", newsroom_url: org.newsroom_url ?? "", leadership_url: org.leadership_url ?? "" });
  const a = useAction();
  const ok = (u: string) => !u || /^https?:\/\/\S+$/.test(u);
  if (!open) return <><button type="button" className="btn btn-small" onClick={() => setOpen(true)} aria-label={`Research pages for ${org.name}`}>
    {org.website || org.newsroom_url || org.leadership_url ? "Edit research pages" : "Add research pages"}</button><ActionNote state={a} /></>;
  return (
    <form className="form-grid" aria-label={`Research pages for ${org.name}`} onSubmit={async (e) => { e.preventDefault();
      if (await a.run(() => api.post(`/organisations/${org.id}/research-pages`, { website: f.website || null, newsroom_url: f.newsroom_url || null,
                                                                                leadership_url: f.leadership_url || null }), "Research pages saved")) { setOpen(false); onSaved(); } }}>
      <label className="field">Website<input className="input" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://…" /></label>
      <label className="field">Newsroom or press page<input className="input" value={f.newsroom_url} onChange={(e) => setF({ ...f, newsroom_url: e.target.value })} /></label>
      <label className="field">Leadership or team page<input className="input" value={f.leadership_url} onChange={(e) => setF({ ...f, leadership_url: e.target.value })} /></label>
      <div className="actions"><button className="btn btn-small" type="submit" disabled={a.busy || !ok(f.website) || !ok(f.newsroom_url) || !ok(f.leadership_url)}>Save research pages</button>
        <button className="btn btn-ghost btn-small" type="button" onClick={() => setOpen(false)}>Cancel</button></div>
      <ActionNote state={a} />
    </form>
  );
}

function AddPerson({ id, onAdded }: { id: string; onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ full_name: "", role_title: "", organisation_label: "", relevance_basis: "", source_url: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { ...f, source_url: f.source_url || null, organisation_label: f.organisation_label || null, role_title: f.role_title || null,
                   source_note: f.source_url ? null : "added by a reviewer" };
    if (await a.run(() => api.post(`/opportunities/${id}/people`, body), "Person added as a research candidate")) {
      setF({ full_name: "", role_title: "", organisation_label: "", relevance_basis: "", source_url: "" }); setOpen(false); onAdded();
    }
  }
  if (!open) return <button type="button" className="btn btn-small" onClick={() => setOpen(true)}>Add a person</button>;
  return (
    <form className="form-grid" onSubmit={submit} aria-label="Add a person">
      <label className="field">Full name<input className="input" required minLength={3} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
      <label className="field">Role or title<input className="input" value={f.role_title} onChange={(e) => setF({ ...f, role_title: e.target.value })} /></label>
      <label className="field">Organisation<input className="input" value={f.organisation_label} onChange={(e) => setF({ ...f, organisation_label: e.target.value })} /></label>
      <label className="field">Why relevant<input className="input" value={f.relevance_basis} onChange={(e) => setF({ ...f, relevance_basis: e.target.value })} placeholder="e.g. named as contact on the tender page" /></label>
      <label className="field">Source URL (optional)<input className="input" value={f.source_url} onChange={(e) => setF({ ...f, source_url: e.target.value })} /></label>
      <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy}>Add</button>
        <button className="btn btn-ghost" type="button" onClick={() => setOpen(false)}>Cancel</button></div>
      <ActionNote state={a} />
    </form>
  );
}

function Workspace({ id, i, reload }: { id: string; i: Intel; reload: () => void }) {
  const ws = i.workspace;
  const a = useAction();
  const [owner, setOwner] = useState(ws.owner_label ?? "");
  const [action, setAction] = useState(ws.next_action ?? "");
  const [due, setDue] = useState(ws.next_action_due ?? "");
  const [note, setNote] = useState("");
  return (
    <section className="panel" aria-label="Progress and next action">
      <p className="question">Track progress</p>
      <div className="filters">
        <div className="field">Progress
          <div className="segmented" role="group" aria-label="Progress">
            {PROGRESS.map(([k, l]) => (
              <button key={k} type="button" aria-pressed={ws.progress === k} disabled={a.busy}
                      onClick={() => a.run(() => api.post(`/opportunities/${id}/progress`, { to: k }), `Progress: ${l}`).then(reload)}>{l}</button>
            ))}
          </div>
          <span className="small muted">Tender status is kept separately: {ws.tender_status_label ?? "n/a"}.</span>
        </div>
        <form className="inline" onSubmit={(e) => { e.preventDefault(); a.run(() => api.post(`/opportunities/${id}/owner-label`, { owner }), "Owner set").then(reload); }}>
          <label className="field">Owner (descriptive)<input className="input" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="e.g. WFC Kenya commercial lead" /></label>
          <button className="btn btn-small" type="submit" disabled={a.busy}>Set owner</button>
        </form>
      </div>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); a.run(() => api.post(`/opportunities/${id}/next-action`, { action, due: due || null }), "Next action saved").then(reload); }}>
        <label className="field" style={{ flex: "2 1 300px" }}>Next action<input className="input" value={action} onChange={(e) => setAction(e.target.value)} /></label>
        <label className="field">Due<input className="input" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></label>
        <button className="btn" type="submit" disabled={a.busy}>Save next action</button>
      </form>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); a.run(() => api.post(`/opportunities/${id}/notes`, { body: note }), "Note added").then((ok) => { if (ok) { setNote(""); reload(); } }); }}>
        <label className="field" style={{ flex: "2 1 300px" }}>Add a note<input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <button className="btn" type="submit" disabled={a.busy || note.trim().length < 2}>Add note</button>
      </form>
      <ActionNote state={a} />
      {i.notes.length > 0 && <ul className="list-plain small" aria-label="Notes">{i.notes.map((n) => (
        <li key={n.id}>{n.body} <span className="muted">· {n.author_label ?? "shared workspace"} · {dateTime(n.created_at)}</span></li>))}</ul>}
      {i.relationships.engagements.length > 0 && <>
        <p className="fact-label">Relationship activity on this opportunity</p>
        <ul className="list-plain small">{i.relationships.engagements.map((e) => (
          <li key={e.id}>{dateTime(e.occurred_at)} · {label(e.kind)} with {e.person_id ? <Link href={`/relationships/${e.person_id}`}>{e.person}</Link> : "—"}: {e.summary}
            {e.owner_label ? <span className="muted"> · {e.owner_label}</span> : null}</li>))}</ul></>}
      <p className="small muted">Nothing is sent from ATLAS: outreach is done by people, outside the system.</p>
    </section>
  );
}

const METHOD_LABEL: Record<string, string> = { source_documents: "the source documents", configured_extractor: "the configured AI extractor",
                                               organisation_website: "organisation websites", organisation_pages: "the organisations' own pages",
                                               reviewer_sources: "pages and documents added by the team", web_search: "authorised web search",
                                               rules: "the evidence rules", linkedin_profiles: "LinkedIn profiles" };
function methodLabel(m: string): string {
  return METHOD_LABEL[m] ?? label(m).toLowerCase();
}

/** The person's title and organisation: the confirmed record fields, else the first evidenced role (with its status). */
function personLine(p: Person): string {
  if (p.role_title || p.organisation) return `${p.role_title ?? "role not established"} · ${p.organisation ?? "organisation not established"}`;
  const r = (p.roles ?? []).find((x) => x.role_status !== "former");
  if (!r) return "role not established · organisation not established";
  return `${r.role_title ?? "role not established"}${r.role_status !== "current" ? ` (${r.role_status})` : ""} · ${r.organisation ?? "organisation not established"}`;
}
