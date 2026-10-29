"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Tag } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, ReasonAction } from "@/components/Ui";
import { KINDS } from "@/components/Research";
import { api } from "@/lib/api";
import { MODULES } from "@/lib/constants";
import { dateOnly, dateTime, label, moduleLabel } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Contact = { id: string; kind: string; value: string; purpose: string | null; status: string; status_label: string; source_url: string | null; source_note: string | null;
                 observed_at: string; verified_at: string | null; evidence_quote: string | null };
type Rel = { id: string; counterparty_id: string | null; counterparty: string | null; counterparty_code: string | null; relationship: string; relationship_label: string;
             territory_countries: string[]; airport_iata: string | null; status: string; status_label: string; basis: string; observed_at: string; verified_at: string | null;
             verified_by_label: string | null; counterparty_carrier_type: string | null; evidence_url: string | null; evidence_quote: string | null };
type Person = { id: string; full_name: string; role_title: string | null; remit_countries: string[]; linkedin_profile_url: string | null; linkedin_search_url: string;
                state: string | null; state_label: string; quote: string | null; source_url: string | null; relationships: number };
type Evidence = { id: string; supports: string; source_kind: string; url: string | null; quote: string | null; note: string | null; observed_at: string;
                  document_title: string | null; supplied_import: string | null };
type Profile = {
  id: string; canonical_name: string; kind: string; kind_label: string; country: string | null; country_name: string | null; website: string | null; origin: string;
  description: string | null; services_text: string | null; locations_text: string | null; parent_group: string | null; airport_iata: string | null; airport_name: string | null;
  carrier_type: string | null; carrier_type_label: string | null; supplied_at: string | null; verified_at: string | null; verification_basis: string | null;
  last_researched_at: string | null; capability_area_labels: string[]; aliases: string[]; iata_code: string | null; state: string; state_label: string;
  people: Person[]; relationships: Rel[]; represented_by: { id: string; agent_id: string; agent: string; agent_country: string | null; relationship: string; status: string; basis: string }[];
  contacts: Contact[]; evidence: Evidence[]; actions: string[]; rule: string; opportunities: number;
  opportunity_list: { id: string; title: string; record_type: string; progress: string | null; origin_interpretation: string | null }[];
  discoveries: { discovery_id: string; brief: string; purpose: string; started_at: string; relevance_score: number }[];
};

const STATE_TONE: Record<string, string> = { verified: "b-good", awaiting_verification: "b-warn", researched: "b-info", recorded: "b-none" };
const STATUS_TONE: Record<string, string> = { supplied: "b-warn", published: "b-info", verified: "b-good", sourced: "b-info", confirmed: "b-good", lapsed: "b-none",
                                              not_established: "b-none" };

export default function CompanyPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const r = useApi<Profile>(id ? `/companies/${id}` : null);
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="company" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Company p={r.data} reload={r.reload} />}
    </>
  );
}

function Company({ p, reload }: { p: Profile; reload: () => void }) {
  const a = useAction();
  const [editing, setEditing] = useState(false);
  const supplied = p.contacts.filter((c) => c.status === "supplied").length + p.relationships.filter((x) => x.status === "supplied").length;
  return (
    <div className="stack">
      <PageHeader eyebrow={`Companies · ${p.kind_label}${p.carrier_type_label ? ` · ${p.carrier_type_label}` : ""}`} title={p.canonical_name}
                  description={[p.country_name ?? "country not established", p.airport_name ? `${p.airport_name} (${p.airport_iata})` : p.airport_iata,
                                p.parent_group ? `part of ${p.parent_group}` : null, p.aliases.length ? `also recorded as ${p.aliases.join(", ")}` : null].filter(Boolean).join(" · ")}
                  actions={<><Tag text={p.state_label} tone={STATE_TONE[p.state]} />
                             {p.kind === "airline" || p.kind === "forwarder" ? <Link className="btn" href={`/airlines-forwarders/${p.id}`}>WFC account view</Link> : null}
                             <button type="button" className="btn" onClick={() => setEditing((v) => !v)}>{editing ? "Close" : "Edit record"}</button></>} />
      {p.state === "awaiting_verification" && (
        <div className="notice" role="status">This record comes from a supplied dataset ({dateOnly(p.supplied_at)}). Its addresses and represented airlines are not assumed current:
          research it (Discover → Companies, organisation &quot;{p.canonical_name}&quot;) to source current evidence, then verify what is confirmed and mark the rest as lapsed.</div>
      )}
      {editing && <EditForm p={p} onDone={() => { setEditing(false); reload(); }} />}

      <div className="grid grid-2">
        <section className="panel" aria-label="Profile">
          <h2>Profile</h2>
          <dl className="kv">
            <dt>Official website</dt><dd>{p.website ? <a href={p.website} target="_blank" rel="noreferrer noopener">{p.website}</a> : <span className="muted">not recorded — record it to read the company&apos;s pages</span>}</dd>
            <dt>What it does</dt><dd>{p.services_text ?? p.description ?? <span className="muted">not stated by any source yet</span>}</dd>
            <dt>Locations</dt><dd>{p.locations_text ?? <span className="muted">not stated</span>}</dd>
            <dt>Parent or group</dt><dd>{p.parent_group ?? <span className="muted">not stated</span>}</dd>
            <dt>Capability areas</dt><dd>{p.capability_area_labels.length ? p.capability_area_labels.join(", ") : <span className="muted">—</span>}</dd>
            {p.iata_code && <><dt>IATA designator</dt><dd>{p.iata_code}</dd></>}
            <dt>Record</dt><dd className="small">origin: {label(p.origin)}{p.last_researched_at ? ` · last researched ${dateTime(p.last_researched_at)}` : ""}
              {p.verified_at ? <> · verified {dateTime(p.verified_at)}: {p.verification_basis}</> : " · not verified"}</dd>
          </dl>
          {p.verified_at ? null : (
            <ReasonAction label="Verify record" tone="primary" minLength={10} busy={a.busy} placeholder="What was checked and where (website, kind, country; the page or source)"
                          onSubmit={(basis) => a.run(() => api.post(`/companies/${p.id}/verify`, { basis }), "Record verified").then(reload)} />
          )}
        </section>
        <section className="panel" aria-label="Next steps">
          <h2>Next steps</h2>
          {p.actions.length === 0 ? <p className="muted small">Nothing outstanding.</p> : <ul className="small">{p.actions.map((x) => <li key={x}>{x}</li>)}</ul>}
          {supplied > 0 && <p className="small muted">{supplied} supplied item(s) awaiting verification.</p>}
          <CreateOpportunity p={p} onDone={reload} />
        </section>
      </div>

      <section className="panel" aria-label="Published contact addresses">
        <div className="panel-head"><h2>Published e-mail addresses</h2><span className="muted small">never used automatically; nothing is sent by ATLAS</span></div>
        {p.contacts.length === 0 ? <Empty title="No published address recorded">Research the company or record its website so its contact page can be read.</Empty> : (
          <TableWrap label="Contact addresses">
            <table><thead><tr><th>Address</th><th>Purpose</th><th>Status</th><th>Where it was published</th><th /></tr></thead>
              <tbody>{p.contacts.map((c) => (
                <tr key={c.id}>
                  <td>{c.value}</td><td className="small">{c.purpose ?? "—"}</td>
                  <td><Tag text={c.status_label} tone={STATUS_TONE[c.status]} />{c.verified_at && <div className="small muted">{dateOnly(c.verified_at)}</div>}</td>
                  <td className="small">{c.source_url ? <a href={c.source_url} target="_blank" rel="noreferrer noopener">{c.source_url}</a> : c.source_note}{c.evidence_quote && <div className="muted">“{c.evidence_quote.slice(0, 140)}”</div>}</td>
                  <td className="actions">{c.status !== "verified" && c.status !== "lapsed" && <>
                    <ReasonAction label="Confirm" minLength={5} busy={a.busy} placeholder="Where the address was confirmed"
                                  onSubmit={(note) => a.run(() => api.post(`/companies/${p.id}/contacts/${c.id}/status`, { status: "verified", note }), "Address confirmed").then(reload)} />
                    <button type="button" className="btn btn-small" disabled={a.busy} onClick={() => a.run(() => api.post(`/companies/${p.id}/contacts/${c.id}/status`, { status: "lapsed", note: "marked as lapsed by a person" }), "Marked as lapsed").then(reload)}>Lapsed</button></>}</td>
                </tr>))}</tbody></table>
          </TableWrap>
        )}
      </section>

      <section className="panel" aria-label="Representation and business relationships">
        <div className="panel-head"><h2>Represented airlines, partners and relationships</h2><span className="muted small">cargo representation is kept apart from passenger ticket-sales mandates</span></div>
        {p.relationships.length === 0 ? <p className="muted small">No representation or partnership stated by any source yet.</p> : (
          <TableWrap label="Relationships">
            <table><thead><tr><th>Counterparty</th><th>Relationship</th><th>Territory / airport</th><th>Status</th><th>Basis</th><th /></tr></thead>
              <tbody>{p.relationships.map((x) => (
                <tr key={x.id}>
                  <td>{x.counterparty_id ? <Link href={`/companies/${x.counterparty_id}`}>{x.counterparty}</Link> : x.counterparty}{x.counterparty_code && <span className="muted small"> {x.counterparty_code}</span>}
                    {x.counterparty_carrier_type && <div className="small muted">{label(x.counterparty_carrier_type)}</div>}</td>
                  <td className="small">{x.relationship_label}</td>
                  <td className="small">{[(x.territory_countries ?? []).join(", "), x.airport_iata].filter(Boolean).join(" · ") || "—"}</td>
                  <td><Tag text={x.status_label} tone={STATUS_TONE[x.status]} />{x.verified_at && <div className="small muted">{dateOnly(x.verified_at)}{x.verified_by_label ? ` · ${x.verified_by_label}` : ""}</div>}</td>
                  <td className="small">{x.basis}{x.evidence_url && <> · <a href={x.evidence_url} target="_blank" rel="noreferrer noopener">source</a></>}</td>
                  <td className="actions">{(x.status === "supplied" || x.status === "sourced") && <>
                    <ReasonAction label="Confirm" minLength={10} busy={a.busy} placeholder="Basis: where it is confirmed and when"
                                  onSubmit={(basis) => a.run(() => api.post(`/companies/${p.id}/relationships/${x.id}/status`, { status: "confirmed", basis }), "Relationship confirmed").then(reload)} />
                    <ReasonAction label="Lapsed" minLength={10} busy={a.busy} placeholder="Basis: why it is no longer current"
                                  onSubmit={(basis) => a.run(() => api.post(`/companies/${p.id}/relationships/${x.id}/status`, { status: "lapsed", basis }), "Marked as lapsed").then(reload)} /></>}</td>
                </tr>))}</tbody></table>
          </TableWrap>
        )}
        {p.represented_by.length > 0 && (
          <p className="small">Represented by: {p.represented_by.map((x) => <span key={x.id}><Link href={`/companies/${x.agent_id}`}>{x.agent}</Link> ({label(x.relationship)}, {label(x.status)}) </span>)}</p>
        )}
      </section>

      <section className="panel" aria-label="Relevant people">
        <div className="panel-head"><h2>Relevant people</h2><Link className="btn btn-small" href="/discovery">Discover people</Link></div>
        {p.people.length === 0 ? <p className="muted small">Nobody recorded at this company yet. Use Discover → People with this organisation named.</p> : (
          <TableWrap label="People">
            <table><thead><tr><th>Person</th><th>Role</th><th>Remit</th><th>Status</th><th>Evidence</th><th>LinkedIn</th></tr></thead>
              <tbody>{p.people.map((x) => (
                <tr key={x.id}>
                  <td><Link href={`/relationships/${x.id}`}>{x.full_name}</Link>{x.relationships > 0 && <div className="small muted">{x.relationships} WFC relationship(s)</div>}</td>
                  <td className="small">{x.role_title ?? <span className="muted">not bound</span>}</td>
                  <td className="small">{(x.remit_countries ?? []).join(", ") || "—"}</td>
                  <td><Tag text={x.state_label} tone={x.state === "research_candidate" || !x.state ? "b-warn" : "b-good"} /></td>
                  <td className="small">{x.quote ? `“${x.quote.slice(0, 120)}”` : ""}{x.source_url && <> <a href={x.source_url} target="_blank" rel="noreferrer noopener">source</a></>}</td>
                  <td className="small">{x.linkedin_profile_url ? <a href={x.linkedin_profile_url} target="_blank" rel="noreferrer noopener">Confirmed profile</a> : <a href={x.linkedin_search_url} target="_blank" rel="noreferrer noopener">Search</a>}</td>
                </tr>))}</tbody></table>
          </TableWrap>
        )}
      </section>

      <section className="panel" aria-label="Opportunities and research">
        <h2>Opportunities from this company</h2>
        {p.opportunity_list.length === 0 ? <p className="muted small">None recorded. A relevant company is not an opportunity until a person records one with the interpretation (Next steps).</p> : (
          <ul className="list-plain small">{p.opportunity_list.map((o) => <li key={o.id}><Link href={`/opportunities/${o.id}`}>{o.title}</Link> <Tag text={label(o.record_type)} tone="b-info" />{o.origin_interpretation && <div className="muted">Interpretation: {o.origin_interpretation}</div>}</li>)}</ul>
        )}
        {p.discoveries.length > 0 && <p className="small muted">Found by: {p.discoveries.map((d) => `${d.brief} (relevance ${d.relevance_score}, ${dateOnly(d.started_at)})`).join("; ")}</p>}
      </section>

      <section className="panel" aria-label="Evidence">
        <h2>Evidence</h2>
        <ul className="list-plain small">{p.evidence.map((e) => (
          <li key={e.id}><Tag text={label(e.supports)} tone="b-none" /> <Tag text={label(e.source_kind)} tone={e.source_kind === "supplied" ? "b-warn" : "b-info"} />{" "}
            {e.quote && <>“{e.quote}” </>}{e.url && <a href={e.url} target="_blank" rel="noreferrer noopener">{e.document_title ?? e.url}</a>}
            {e.note && <span className="muted"> · {e.note}</span>}{e.supplied_import && <span className="muted"> · {e.supplied_import}</span>}<span className="muted"> · {dateTime(e.observed_at)}</span></li>))}</ul>
        <p className="small muted">{p.rule}</p>
      </section>
      <ActionNote state={a} />
    </div>
  );
}

function EditForm({ p, onDone }: { p: Profile; onDone: () => void }) {
  const a = useAction();
  const [f, setF] = useState({ website: p.website ?? "", kind: p.kind, country: p.country ?? "", airport_iata: p.airport_iata ?? "", carrier_type: p.carrier_type ?? "",
                               description: p.description ?? "", services_text: p.services_text ?? "", locations_text: p.locations_text ?? "", parent_group: p.parent_group ?? "", basis: "" });
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { website: f.website || null, kind: f.kind || null, country: f.country || null, airport_iata: f.airport_iata || null, carrier_type: f.carrier_type || null,
                   description: f.description || null, services_text: f.services_text || null, locations_text: f.locations_text || null, parent_group: f.parent_group || null,
                   basis: f.basis || null };
    if (await a.run(() => api.post(`/companies/${p.id}/edit`, body), "Record updated")) onDone();
  }
  return (
    <section className="panel" aria-label="Edit company">
      <h2>Edit record</h2>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">Official website<input className="input" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="https://" /></label>
        <label className="field">Kind<select className="select" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}<option value="authority">Authority or regulator</option><option value="other">Other</option></select></label>
        <label className="field">Country (ISO code)<input className="input" maxLength={2} value={f.country} onChange={(e) => setF({ ...f, country: e.target.value.toUpperCase() })} /></label>
        <label className="field">Airport (IATA)<input className="input" maxLength={3} value={f.airport_iata} onChange={(e) => setF({ ...f, airport_iata: e.target.value.toUpperCase() })} /></label>
        {f.kind === "airline" && (
          <label className="field">Airline type<select className="select" value={f.carrier_type} onChange={(e) => setF({ ...f, carrier_type: e.target.value })}>
            <option value="">Not established</option><option value="passenger_belly">Passenger airline (belly cargo)</option><option value="cargo_only">Cargo-only airline</option>
            <option value="combination">Passenger and freighter</option></select></label>
        )}
        <label className="field">Parent or group<input className="input" value={f.parent_group} onChange={(e) => setF({ ...f, parent_group: e.target.value })} /></label>
        <label className="field" style={{ gridColumn: "1 / -1" }}>Services (as stated by a source)<input className="input" value={f.services_text} onChange={(e) => setF({ ...f, services_text: e.target.value })} /></label>
        <label className="field" style={{ gridColumn: "1 / -1" }}>Locations (as stated)<input className="input" value={f.locations_text} onChange={(e) => setF({ ...f, locations_text: e.target.value })} /></label>
        <label className="field" style={{ gridColumn: "1 / -1" }}>Basis for the change (recorded as evidence)<input className="input" value={f.basis} onChange={(e) => setF({ ...f, basis: e.target.value })} placeholder="e.g. company website, 29 Oct 2026" /></label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy}>Save</button></div>
      </form>
      <ActionNote state={a} />
    </section>
  );
}

function CreateOpportunity({ p, onDone }: { p: Profile; onDone: () => void }) {
  const router = useRouter();
  const a = useAction();
  const [open, setOpen] = useState(false);
  const [module, setModule] = useState("airline_representation");
  const [interp, setInterp] = useState("");
  const [title, setTitle] = useState("");
  if (!open) return <button type="button" className="btn" onClick={() => setOpen(true)}>Record a potential opportunity</button>;
  return (
    <form className="stack" onSubmit={async (e: FormEvent) => { e.preventDefault();
      const r = await a.run(() => api.post<{ id: string; new: boolean; note: string }>(`/companies/${p.id}/opportunities`,
        { module, interpretation: interp.trim(), title: title.trim() || null, country: p.country }), (x) => x.note);
      if (r) { onDone(); router.push(`/opportunities/${r.id}`); } }}>
      <p className="small muted">A researched company is not an opportunity by itself. Say why this company could lead to business; the interpretation is recorded with the opportunity.</p>
      <label className="field">Capability area<select className="select" value={module} onChange={(e) => setModule(e.target.value)}>{MODULES.map((m) => <option key={m} value={m}>{moduleLabel(m)}</option>)}</select></label>
      <label className="field">Title (optional)<input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`${p.canonical_name}: ${moduleLabel(module)}`} /></label>
      <label className="field">Interpretation<textarea className="input" rows={3} minLength={20} required value={interp} onChange={(e) => setInterp(e.target.value)}
        placeholder="e.g. The airline's Rwanda cargo GSSA mandate is stated to lapse in March; WFC could offer representation" /></label>
      <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy || interp.trim().length < 20}>Record opportunity</button>
        <button className="btn btn-ghost" type="button" onClick={() => setOpen(false)}>Cancel</button></div>
      <ActionNote state={a} />
    </form>
  );
}
