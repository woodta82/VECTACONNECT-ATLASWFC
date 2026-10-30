"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Tag } from "@/components/Records";
import { PersonEmail, type EmailResearch } from "@/components/Research";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { DuplicateReview, type Duplicate } from "@/components/Duplicates";
import { ActionNote } from "@/components/Ui";
import { HealthPanel, JudgementForm, OutreachPanel, type Draft, type Intelligence } from "@/components/Intelligence";
import { api } from "@/lib/api";
import { dateOnly, dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Person = { id: string; full_name: string; role_title: string | null; organisation: string | null; organisation_id: string | null; remit_text: string | null;
                remit_basis: string | null; identity_confirmed_at: string | null; identity_basis: string | null; last_verified_at: string | null;
                linkedin_profile_url: string | null; linkedin_search_url: string; linkedin_role_search_url: string | null; relationship_owner: string | null;
                published_email: string | null; published_email_status: string | null; published_email_source_url: string | null;
                research_status: { email?: EmailResearch } | null; involvement: string; involvement_basis: string | null;
                involvement_org: string | null; involvement_set_by: string;
                notes: string | null; next_action: string | null; next_action_due: string | null; state: string; state_label: string; origin: string;
                merged_into_id: string | null; merged_into_name: string | null };

type Detail = {
  person: Person; gaps: string[];
  evidence: { id: string; supports: string; source_kind: string; document_title: string | null; url: string | null; quote: string | null; note: string | null; observed_at: string; published_at: string | null }[];
  opportunities: { id: string; title: string; record_type: string; progress: string; tender_status: string | null; role_on_opportunity: string; relevance_basis: string; link_status: string }[];
  relationships: { id: string; holder_label: string; nature: string; basis: string; status: string; recorded_at: string }[];
  routes: { id: string; introducer: string; wfc_holder_label: string | null; connection_basis: string; evidence_url: string | null; willingness_confirmed: boolean;
            willingness_basis: string | null; status: string; opportunity_title: string | null; updated_at: string }[];
  engagements: { id: string; occurred_at: string; kind: string; summary: string; owner_label: string | null; outcome: string | null; next_step: string | null;
                 direction: string; opportunity_title: string | null }[];
  intelligence: Intelligence; outreach: Draft[];
  roles: { id: string; role_title: string | null; organisation: string | null; organisation_id: string | null; role_status: string; affiliation: string;
           affiliation_label: string; binding: string; source: string; quote: string | null; url: string | null; document_title: string | null }[];
  duplicates: Duplicate[];
  merges: { id: string; kept_person_id: string; kept_name: string; merged_person_id: string; merged_name: string; merged_at: string; undone_at: string | null; note: string | null }[];
};
const STATE_TONE: Record<string, string> = { existing_relationship: "b-good", introduction_available: "b-good", identity_confirmed: "b-info", research_candidate: "b-warn" };
const NATURES: [string, string][] = [["works_with", "Works with them"], ["former_colleague", "Former colleague"], ["client", "Client relationship"],
                                     ["supplier", "Supplier relationship"], ["partner", "Partner"], ["personal", "Personal"], ["other", "Other"]];

export default function PersonPage() {
  const { id = "" } = useParams<{ id: string }>();
  const r = useApi<Detail>(id ? `/people/${id}` : null);
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="person" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body id={id} d={r.data} reload={r.reload} />}
    </>
  );
}

function Body({ id, d, reload }: { id: string; d: Detail; reload: () => void }) {
  const p = d.person;
  const a = useAction();
  return (
    <div className="stack">
      <PageHeader eyebrow="Relationships" title={p.full_name}
                  description={`${p.role_title ?? "Role not established"} · ${p.organisation ?? "Organisation not established"}`}
                  actions={<Link className="btn" href="/relationships">All people</Link>} />
      <div className="small"><Tag text={p.state_label} tone={STATE_TONE[p.state]} /> <span className="muted">
        {p.last_verified_at ? `last verified ${dateOnly(p.last_verified_at)}` : "never verified"} · found by {label(p.origin)}</span></div>
      <ActionNote state={a} />
      {p.merged_into_id && (
        <div className="notice" role="status" aria-label="Merged record">
          This record was merged into <Link href={`/relationships/${p.merged_into_id}`}>{p.merged_into_name}</Link>. Its evidence, roles, links, relationships,
          routes and engagements now belong to that record. {d.merges.filter((m) => m.merged_person_id === id && !m.undone_at).map((m) => (
            <button key={m.id} type="button" className="btn btn-small" disabled={a.busy}
                    onClick={() => a.run(() => api.post(`/people/merges/${m.id}/undo`), "Merge undone").then(reload)}>Undo merge</button>))}
        </div>
      )}
      {d.duplicates.length > 0 && <DuplicateReview items={d.duplicates} onChanged={reload} title="Possible duplicates of this person" />}
      <section className="panel" aria-label="Titles and organisations">
        <h2>Titles and organisations (with the passage that binds them)</h2>
        {d.roles.length === 0 ? <p className="muted">No source binds a title or organisation to this person yet.</p> : (
          <ul className="list-plain small">{d.roles.map((r) => (
            <li key={r.id}><b>{r.role_title ?? "Title not stated"}</b>{r.role_status !== "current" ? ` (${r.role_status})` : ""} ·{" "}
              {r.organisation_id ? <Link href={`/companies/${r.organisation_id}`}>{r.organisation}</Link> : r.organisation ?? "organisation not established"}
              {r.organisation && <> · <Tag text={r.affiliation_label} tone={r.affiliation === "employee" ? "b-info" : r.affiliation === "unknown" ? "b-none" : "b-warn"} /></>}
              <div className="muted">{r.source === "before_upgrade" ? "Recorded before the evidence rules (28 Oct 2026); no passage attached" : r.binding}
                {r.source === "ai" ? " · proposed by the configured AI extractor and confirmed by the rules" : ""}</div>
              {r.quote && <div>“{r.quote}” <span className="muted">{r.url ? <a href={r.url} target="_blank" rel="noreferrer noopener">{r.document_title ?? r.url}</a> : r.document_title ?? ""}</span></div>}</li>))}</ul>
        )}
      </section>
      <div className="grid grid-2">
        <section className="panel" aria-label="Identity">
          <h2>Identity, role and remit</h2>
          <dl className="kv">
            <dt>Organisation</dt><dd>{p.organisation_id ? <Link href={`/companies/${p.organisation_id}`}>{p.organisation}</Link> : p.organisation ?? "Not established"}</dd>
            <dt>Role</dt><dd>{p.role_title ?? "Not established"}</dd>
            <dt>Geographic remit</dt><dd>{p.remit_text ?? "Not established"}{p.remit_basis && <div className="small muted">{p.remit_basis}</div>}</dd>
            <dt>Involvement</dt><dd><Tag text={INVOLVEMENT[p.involvement] ?? p.involvement} tone={p.involvement === "press_contact" || p.involvement === "external_adviser" ? "b-none" : p.involvement === "unresolved" ? "b-warn" : "b-good"} />
              {p.involvement_org && <span className="small"> · {p.involvement_org}</span>}
              <div className="small muted">{p.involvement_basis ?? "not established"}{p.involvement_set_by === "person" ? " (set by a person — research never changes it)" : ""}
                {(p.involvement === "press_contact" || p.involvement === "external_adviser") && " · kept as an external contact; not counted as a commercial contact"}</div>
              <InvolvementForm id={id} current={p.involvement} reload={reload} /></dd>
            <dt>Identity</dt><dd>{p.identity_confirmed_at ? <>Confirmed {dateOnly(p.identity_confirmed_at)}<div className="small muted">{p.identity_basis}</div></> : "Not confirmed: research candidate"}</dd>
            <dt>Published e-mail</dt><dd><PersonEmail email={p.published_email} status={p.published_email_status} research={p.research_status?.email} source={p.published_email_source_url} />
              <div className="small muted">{p.published_email_status === "under_review" ? "Kept with its evidence; a person decides whether it is this person's address." : "Shown only when a page ties the address to this person; never guessed."}</div></dd>
            <dt>LinkedIn</dt><dd>{p.linkedin_profile_url ? <a href={p.linkedin_profile_url} target="_blank" rel="noreferrer noopener">Confirmed profile</a>
              : <><a href={p.linkedin_search_url} target="_blank" rel="noreferrer noopener">Search for this person</a>{p.linkedin_role_search_url && <> · <a href={p.linkedin_role_search_url} target="_blank" rel="noreferrer noopener">search the role</a></>}
                <div className="small muted">A search, not a confirmed profile.</div></>}</dd>
          </dl>
          {!p.identity_confirmed_at && <ConfirmForm id={id} reload={reload} />}
          <LinkedInForm id={id} current={p.linkedin_profile_url} reload={reload} />
        </section>
        <section className="panel" aria-label="Gaps and next action">
          <h2>Gaps and next action</h2>
          {d.gaps.length ? <ul>{d.gaps.map((g) => <li key={g} className="small">{g}</li>)}</ul> : <p className="muted">No open gaps.</p>}
          <DetailsForm id={id} p={p} reload={reload} />
        </section>
      </div>

      <div className="grid grid-2">
        <HealthPanel i={d.intelligence} />
        <JudgementForm id={id} s={d.intelligence.stakeholder} reload={reload} />
      </div>

      <section className="panel" aria-label="Evidence">
        <h2>Source evidence</h2>
        {d.evidence.length === 0 ? <Empty title="No evidence recorded" /> : (
          <ul className="list-plain small">{groupEvidence(d.evidence).map((e) => (
            <li key={e.id}>{e.supports.map((x) => <Tag key={x} text={label(x)} />)} {e.quote ? `“${e.quote}”` : e.note}
              <span className="muted"> · {e.url ? <a href={e.url} target="_blank" rel="noreferrer noopener">{e.document_title ?? e.url}</a> : e.document_title ?? label(e.source_kind)}
                {e.published_at ? `, published ${dateOnly(e.published_at)}` : ""} · recorded {dateTime(e.observed_at)}{e.quote && e.note ? ` · ${e.note}` : ""}</span></li>))}</ul>
        )}
        <EvidenceForm id={id} reload={reload} />
      </section>

      <section className="panel" aria-label="Linked opportunities">
        <h2>Linked opportunities</h2>
        {d.opportunities.length === 0 ? <Empty title="Not linked to an opportunity" /> : (
          <TableWrap label="Linked opportunities"><table><thead><tr><th>Opportunity</th><th>Role on it</th><th>Why relevant</th><th>Status</th></tr></thead>
            <tbody>{d.opportunities.map((o) => (
              <tr key={o.id}><td><Link href={`/opportunities/${o.id}`}>{o.title}</Link></td><td className="small">{label(o.role_on_opportunity)}</td>
                <td className="small">{o.relevance_basis}</td><td className="small">{label(o.progress)}{o.tender_status ? ` · tender ${o.tender_status}` : ""}{o.link_status === "not_relevant" ? " · marked not relevant" : ""}</td></tr>))}</tbody></table></TableWrap>
        )}
      </section>

      <div className="grid grid-2">
        <section className="panel" aria-label="Existing relationships">
          <h2>Existing relationship</h2>
          {d.relationships.length === 0 ? <p className="muted">None recorded.</p> : (
            <ul className="list-plain small">{d.relationships.map((x) => (
              <li key={x.id}><b>{x.holder_label}</b> · {label(x.nature)} · <Tag text={x.status} tone={x.status === "current" ? "b-good" : "b-none"} />
                <div>{x.basis}</div><span className="muted">recorded {dateOnly(x.recorded_at)}</span>{" "}
                <button type="button" className="link-button" disabled={a.busy}
                        onClick={() => a.run(() => api.post(`/person-relationships/${x.id}/status`, { status: x.status === "current" ? "lapsed" : "current" }), "Updated").then(reload)}>
                  Mark {x.status === "current" ? "lapsed" : "current"}</button></li>))}</ul>
          )}
          <RelationshipForm id={id} reload={reload} />
        </section>
        <section className="panel" aria-label="Introduction routes">
          <h2>Introduction routes</h2>
          {d.routes.length === 0 ? <p className="muted">None recorded.</p> : (
            <ul className="list-plain small">{d.routes.map((x) => (
              <li key={x.id}><b>{x.introducer}</b> <Tag text={label(x.status)} tone={x.status === "available" || x.status === "made" ? "b-good" : x.status === "declined" ? "b-bad" : "b-warn"} />
                <div>Connection: {x.connection_basis}{x.evidence_url && <> (<a href={x.evidence_url} target="_blank" rel="noreferrer noopener">source</a>)</>}</div>
                <div className="muted">{x.willingness_confirmed ? `Willingness confirmed: ${x.willingness_basis}` : "Willingness to introduce not confirmed: a possible route only"}
                  {x.wfc_holder_label ? ` · WFC contact: ${x.wfc_holder_label}` : ""}{x.opportunity_title ? ` · for ${x.opportunity_title}` : ""}</div>
                <RouteStatus route={x} reload={reload} /></li>))}</ul>
          )}
          <RouteForm id={id} reload={reload} />
        </section>
      </div>

      {d.merges.length > 0 && (
        <section className="panel" aria-label="Merge history">
          <h2>Merge history</h2>
          <ul className="list-plain small">{d.merges.map((m) => (
            <li key={m.id}>{m.merged_name} merged into {m.kept_name} on {dateTime(m.merged_at)}{m.note ? ` (${m.note})` : ""}
              {m.undone_at ? <span className="muted"> · undone {dateTime(m.undone_at)}</span> : (
                <> · <button type="button" className="link-button" disabled={a.busy}
                             onClick={() => a.run(() => api.post(`/people/merges/${m.id}/undo`), "Merge undone").then(reload)}>Undo merge</button></>)}</li>))}</ul>
        </section>
      )}

      <section className="panel" aria-label="Engagement history">
        <h2>Engagement history</h2>
        {d.engagements.length === 0 ? <p className="muted">No engagement recorded.</p> : (
          <ul className="list-plain small">{d.engagements.map((e) => (
            <li key={e.id}>{dateTime(e.occurred_at)} · {label(e.kind)} ({e.direction}){e.outcome ? ` · ${label(e.outcome)}` : ""}: {e.summary}
              <span className="muted">{e.owner_label ? ` · ${e.owner_label}` : ""}{e.opportunity_title ? ` · ${e.opportunity_title}` : ""}{e.next_step ? ` · next: ${e.next_step}` : ""}</span></li>))}</ul>
        )}
        <EngagementForm id={id} opportunities={d.opportunities} reload={reload} />
        <p className="small muted">ATLAS records activity; it never sends messages or outreach.</p>
      </section>

      <OutreachPanel id={id} drafts={d.outreach} opportunities={d.opportunities} reload={reload} />
    </div>
  );
}

type Ev = Detail["evidence"][number];
/** One line per passage and source: what it supports is shown as tags, not repeated lines. */
function groupEvidence(items: Ev[]): (Omit<Ev, "supports"> & { supports: string[] })[] {
  const out = new Map<string, Omit<Ev, "supports"> & { supports: string[] }>();
  for (const e of items) {
    const key = `${e.quote ?? e.note}|${e.url ?? e.document_title ?? e.source_kind}`;
    const cur = out.get(key);
    if (cur) { if (!cur.supports.includes(e.supports)) cur.supports.push(e.supports); }
    else out.set(key, { ...e, supports: [e.supports] });
  }
  return [...out.values()];
}

function ConfirmForm({ id, reload }: { id: string; reload: () => void }) {
  const [basis, setBasis] = useState("");
  const [url, setUrl] = useState("");
  const a = useAction();
  return (
    <form className="filters" aria-label="Confirm identity and role" onSubmit={async (e: FormEvent) => { e.preventDefault();
      if (await a.run(() => api.post(`/people/${id}/confirm`, { basis, source_url: url || null }), "Identity and role confirmed")) reload(); }}>
      <label className="field" style={{ flex: "2 1 260px" }}>How was identity and role confirmed?<input className="input" value={basis} onChange={(e) => setBasis(e.target.value)}
        placeholder="e.g. official leadership page lists her as Procurement Manager" /></label>
      <label className="field">Source URL (optional)<input className="input" value={url} onChange={(e) => setUrl(e.target.value)} /></label>
      <button className="btn btn-primary" type="submit" disabled={a.busy || basis.trim().length < 10}>Confirm identity and role</button>
      <ActionNote state={a} />
    </form>
  );
}

function LinkedInForm({ id, current, reload }: { id: string; current: string | null; reload: () => void }) {
  const [url, setUrl] = useState(current ?? "");
  const a = useAction();
  return (
    <form className="filters" aria-label="Confirmed LinkedIn profile" onSubmit={async (e: FormEvent) => { e.preventDefault();
      if (await a.run(() => api.post(`/people/${id}/linkedin`, { url: url || null }), url ? "Profile saved as confirmed" : "Profile cleared")) reload(); }}>
      <label className="field" style={{ flex: "2 1 260px" }}>Confirmed LinkedIn profile (only after checking it is the right person)
        <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.linkedin.com/in/…" /></label>
      <button className="btn" type="submit" disabled={a.busy}>Save profile</button>
      <ActionNote state={a} />
    </form>
  );
}

type DetailField = "organisation" | "role_title" | "remit_text" | "remit_basis" | "relationship_owner" | "next_action" | "next_action_due" | "notes";

function DetailsForm({ id, p, reload }: { id: string; p: Person; reload: () => void }) {
  // Only the reviewer's edits are held here; every other field always shows the server's current value, so a value
  // recorded elsewhere meanwhile (e.g. the relationship owner filled by recording a relationship) is shown and never
  // overwritten by a stale form.
  const [edits, setEdits] = useState<Partial<Record<DetailField, string>>>({});
  const server: Record<DetailField, string> = { organisation: p.organisation ?? "", role_title: p.role_title ?? "", remit_text: p.remit_text ?? "",
                                                remit_basis: p.remit_basis ?? "", relationship_owner: p.relationship_owner ?? "",
                                                next_action: p.next_action ?? "", next_action_due: p.next_action_due ?? "", notes: p.notes ?? "" };
  const value = (k: DetailField) => edits[k] ?? server[k];
  const input = (k: DetailField, labelText: string, type = "text") => (
    <label className="field">{labelText}<input className="input" type={type} value={value(k)} placeholder={k === "organisation" ? "Not established" : undefined}
      onChange={(e) => setEdits({ ...edits, [k]: e.target.value })} /></label>);
  const a = useAction();
  return (
    <form className="form-grid" aria-label="Person details" onSubmit={async (e: FormEvent) => { e.preventDefault();
      const body: Record<string, string | null> = {};
      for (const [k, v] of Object.entries(edits) as [DetailField, string][]) {
        if (v.trim() === server[k]) continue;
        if (k === "organisation") { body.organisation_id = null; body.organisation_label = v.trim() || null; }  // the reviewer's description
        else body[k] = v === "" ? null : v;
      }
      if (await a.run(() => api.post(`/people/${id}`, body), "Saved")) { setEdits({}); reload(); } }}>
      {input("organisation", "Organisation")}
      {input("role_title", "Role or title")}
      {input("remit_text", "Geographic remit")}
      {input("remit_basis", "Remit basis")}
      {input("relationship_owner", "Relationship owner (descriptive)")}
      {input("next_action", "Next action")}
      {input("next_action_due", "Due", "date")}
      <label className="field" style={{ gridColumn: "1 / -1" }}>Notes<textarea className="textarea" value={value("notes")}
        onChange={(e) => setEdits({ ...edits, notes: e.target.value })} /></label>
      <div className="actions"><button className="btn" type="submit" disabled={a.busy}>Save details</button></div>
      <ActionNote state={a} />
    </form>
  );
}

function EvidenceForm({ id, reload }: { id: string; reload: () => void }) {
  const [f, setF] = useState({ supports: "role", url: "", note: "" });
  const a = useAction();
  return (
    <form className="filters" aria-label="Add evidence" onSubmit={async (e: FormEvent) => { e.preventDefault();
      if (await a.run(() => api.post(`/people/${id}/evidence`, { ...f, url: f.url || null }), "Evidence added")) { setF({ supports: "role", url: "", note: "" }); reload(); } }}>
      <label className="field">Supports<select className="select" value={f.supports} onChange={(e) => setF({ ...f, supports: e.target.value })}>
        <option value="identity">Identity</option><option value="role">Role</option><option value="remit">Remit</option><option value="relevance">Relevance</option></select></label>
      <label className="field">Public source URL<input className="input" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="company site, press release, official biography" /></label>
      <label className="field" style={{ flex: "2 1 240px" }}>What it shows<input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></label>
      <button className="btn" type="submit" disabled={a.busy || f.note.trim().length < 3}>Add evidence</button>
      <ActionNote state={a} />
    </form>
  );
}

function RelationshipForm({ id, reload }: { id: string; reload: () => void }) {
  const [f, setF] = useState({ holder: "", nature: "works_with", basis: "" });
  const a = useAction();
  return (
    <form className="form-grid" aria-label="Record an existing relationship" onSubmit={async (e: FormEvent) => { e.preventDefault();
      if (await a.run(() => api.post(`/people/${id}/relationships`, f), "Relationship recorded")) { setF({ holder: "", nature: "works_with", basis: "" }); reload(); } }}>
      <label className="field">Who at WFC holds it<input className="input" value={f.holder} onChange={(e) => setF({ ...f, holder: e.target.value })} /></label>
      <label className="field">Nature<select className="select" value={f.nature} onChange={(e) => setF({ ...f, nature: e.target.value })}>
        {NATURES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      <label className="field" style={{ gridColumn: "1 / -1" }}>How it is known (basis)<input className="input" value={f.basis} onChange={(e) => setF({ ...f, basis: e.target.value })}
        placeholder="e.g. worked together on the 2024 GSSA contract; meet quarterly" /></label>
      <div className="actions"><button className="btn" type="submit" disabled={a.busy || f.holder.trim().length < 2 || f.basis.trim().length < 10}>Record relationship</button></div>
      <ActionNote state={a} />
    </form>
  );
}

function RouteForm({ id, reload }: { id: string; reload: () => void }) {
  const [f, setF] = useState({ introducer_label: "", wfc_holder_label: "", connection_basis: "", evidence_url: "" });
  const a = useAction();
  return (
    <form className="form-grid" aria-label="Add an introduction route" onSubmit={async (e: FormEvent) => { e.preventDefault();
      const body = { ...f, evidence_url: f.evidence_url || null, wfc_holder_label: f.wfc_holder_label || null };
      if (await a.run(() => api.post(`/people/${id}/routes`, body), "Possible route recorded")) { setF({ introducer_label: "", wfc_holder_label: "", connection_basis: "", evidence_url: "" }); reload(); } }}>
      <label className="field">Introducer<input className="input" value={f.introducer_label} onChange={(e) => setF({ ...f, introducer_label: e.target.value })} /></label>
      <label className="field">WFC contact who would ask<input className="input" value={f.wfc_holder_label} onChange={(e) => setF({ ...f, wfc_holder_label: e.target.value })} /></label>
      <label className="field" style={{ gridColumn: "1 / -1" }}>How the introducer knows them<input className="input" value={f.connection_basis} onChange={(e) => setF({ ...f, connection_basis: e.target.value })} /></label>
      <label className="field">Evidence URL (optional)<input className="input" value={f.evidence_url} onChange={(e) => setF({ ...f, evidence_url: e.target.value })} /></label>
      <div className="actions"><button className="btn" type="submit" disabled={a.busy || !f.introducer_label.trim() || f.connection_basis.trim().length < 10}>Record possible route</button></div>
      <p className="small muted" style={{ gridColumn: "1 / -1" }}>Recorded as possible. It becomes available only when the introducer&apos;s willingness is confirmed.</p>
      <ActionNote state={a} />
    </form>
  );
}

function RouteStatus({ route, reload }: { route: { id: string; status: string; willingness_confirmed: boolean }; reload: () => void }) {
  const [basis, setBasis] = useState("");
  const a = useAction();
  const next = route.status === "possible" ? ["available", "declined"] : route.status === "available" ? ["requested", "declined"] : route.status === "requested" ? ["made", "declined"] : [];
  if (!next.length) return null;
  return (
    <div className="filters">
      {!route.willingness_confirmed && <label className="field" style={{ flex: "2 1 240px" }}>How was willingness confirmed?
        <input className="input" value={basis} onChange={(e) => setBasis(e.target.value)} placeholder="e.g. introducer agreed by phone on 28 Oct" /></label>}
      {next.map((s) => (
        <button key={s} type="button" className="btn btn-small" disabled={a.busy}
                onClick={() => a.run(() => api.post(`/routes/${route.id}/status`, { status: s, willingness_basis: basis || null }), `Route ${label(s)}`).then(reload)}>
          Mark {label(s)}</button>))}
      <ActionNote state={a} />
    </div>
  );
}

function EngagementForm({ id, opportunities, reload }: { id: string; opportunities: { id: string; title: string }[]; reload: () => void }) {
  const empty = { kind: "meeting", summary: "", opportunity_id: "", owner_label: "", outcome: "", next_step: "", direction: "outbound" };
  const [f, setF] = useState(empty);
  const a = useAction();
  return (
    <form className="form-grid" aria-label="Record engagement" onSubmit={async (e: FormEvent) => { e.preventDefault();
      const body = { ...f, opportunity_id: f.opportunity_id || null, owner_label: f.owner_label || null, outcome: f.outcome || null, next_step: f.next_step || null };
      if (await a.run(() => api.post(`/people/${id}/engagements`, body), "Engagement recorded")) { setF(empty); reload(); } }}>
      <label className="field">Type<select className="select" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
        {["meeting", "call", "email", "message", "introduction", "event", "proposal", "visit", "note", "other"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</select></label>
      <label className="field">Direction<select className="select" value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}>
        <option value="outbound">WFC reached out</option><option value="inbound">They reached out</option><option value="mutual">Mutual (meeting, event)</option></select></label>
      <label className="field">Opportunity<select className="select" value={f.opportunity_id} onChange={(e) => setF({ ...f, opportunity_id: e.target.value })}>
        <option value="">None</option>{opportunities.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}</select></label>
      <label className="field">Recorded by<input className="input" value={f.owner_label} onChange={(e) => setF({ ...f, owner_label: e.target.value })} /></label>
      <label className="field">Outcome<select className="select" value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value })}>
        <option value="">Not stated</option>{["positive", "neutral", "negative", "no_response", "pending"].map((k) => <option key={k} value={k}>{label(k)}</option>)}</select></label>
      <label className="field" style={{ gridColumn: "1 / -1" }}>Summary<input className="input" value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} /></label>
      <label className="field" style={{ gridColumn: "1 / -1" }}>Next step<input className="input" value={f.next_step} onChange={(e) => setF({ ...f, next_step: e.target.value })} /></label>
      <div className="actions"><button className="btn" type="submit" disabled={a.busy || f.summary.trim().length < 3}>Record engagement</button></div>
      <ActionNote state={a} />
    </form>
  );
}

const INVOLVEMENT: Record<string, string> = { employee: "Employee", appointed_representative: "Appointed representative", external_adviser: "External adviser",
                                              press_contact: "Press / media contact", unresolved: "Involvement not established" };

function InvolvementForm({ id, current, reload }: { id: string; current: string; reload: () => void }) {
  const a = useAction();
  const [inv, setInv] = useState(current);
  const [basis, setBasis] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (await a.run(() => api.post(`/people/${id}/involvement`, { involvement: inv, basis }), "Involvement recorded")) { setBasis(""); reload(); }
  }
  return (
    <details className="small"><summary>Correct the involvement</summary>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">Involvement<select className="select" value={inv} onChange={(e) => setInv(e.target.value)}>
          {Object.entries(INVOLVEMENT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="field">What was checked, and where<input className="input" value={basis} onChange={(e) => setBasis(e.target.value)} minLength={10} required /></label>
        <div className="actions"><button className="btn" type="submit" disabled={a.busy || basis.trim().length < 10}>Save</button></div>
      </form>
      <ActionNote state={a} />
    </details>
  );
}
