"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Tag } from "@/components/Records";
import { Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, Tabs } from "@/components/Ui";
import { CountryPicker, useGeography } from "@/components/Geo";
import { DuplicateReview, type Duplicate } from "@/components/Duplicates";
import { HealthBadge, MOMENTUM_TONE, PersonLine, STAKEHOLDER_TYPES } from "@/components/Intelligence";
import { api, qs } from "@/lib/api";
import { dateOnly, dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Person = { id: string; full_name: string; role_title: string | null; organisation: string | null; state: string; state_label: string;
                relationship_owner: string | null; next_action: string | null; next_action_due: string | null; last_verified_at: string | null;
                linkedin_profile_url: string | null; linkedin_search_url: string; opportunities: number; possible_routes: number; last_engagement: string | null;
                stakeholder_type: string; stakeholder_label: string; posture: string; posture_label: string; capability_area_label: string | null;
                health_score: number | null; health_band: string | null; health_band_label: string | null; at_risk: boolean | null; momentum: string | null;
                momentum_state: string | null; attention: number | null; recommended_action: string | null };
type Page = { items: Person[]; total: number; states: Record<string, string>; capability_areas: Record<string, string> };
type StateTab = "" | "research_candidate" | "identity_confirmed" | "existing_relationship" | "introduction_available";
type QPerson = { person_id: string; name: string; role: string | null; organisation: string | null; health_score: number | null; health_band: string | null;
                 health_band_label: string; at_risk: boolean; stakeholder_label: string; why?: string; importance?: number; is_known?: boolean;
                 attention?: number; recommended_action?: string; expected_benefit?: string; momentum?: string };
type Gap = { opportunity_id: string; opportunity_title: string; missing: string; missing_label: string; severity: string; focus: number; why: string;
             recommended_action: string };
type Questions = { who_matters_most: QPerson[]; who_are_we_missing: Gap[]; improving: QPerson[]; at_risk: QPerson[]; where_to_invest_time: QPerson[];
                   totals: { people: number; assessed: number; at_risk: number; not_judged: number }; rule: string };
type Discovery = { id: string; organisation: string | null; countries_named: string[]; region_name: string | null; capability_area_label: string | null;
                   role_focus: string | null; brief: string; status: string; outcome: string | null; people_found: number; runs: number; started_at: string;
                   finished_at: string | null; requested_by_label: string | null; methods: string[] };
type DiscoveryDetail = Discovery & {
  people: { person_id: string; full_name: string; role_title: string | null; organisation: string | null; relevance_score: number; new_record: boolean;
            relevance: { components: { key: string; label: string; points: number; max: number; reason: string }[] }; state_label: string;
            linkedin_search_url: string; source_url: string | null; quote: string | null }[];
  documents: { id: string; origin: string; url: string | null; title: string | null; status: string; status_reason: string | null; found_via: string | null }[];
  searches: { purpose: string; query: string; status: string; results: number; link: string; reason?: string }[];
  unavailable: { method: string; reason: string }[]; actions: string[]; rule: string;
  coverage: { remaining: string[]; not_searched: string[]; limits_hit?: string[] };
};

const STATE_TONE: Record<string, string> = { existing_relationship: "b-good", introduction_available: "b-good", identity_confirmed: "b-info",
                                             research_candidate: "b-warn" };
const OUTCOME_TONE: Record<string, string> = { people_found: "b-good", no_people_found: "b-none", incomplete: "b-warn", not_run: "b-bad" };
const OUTCOME_LABEL: Record<string, string> = { people_found: "People found", no_people_found: "No people found", incomplete: "Incomplete", not_run: "Not run" };
const outcomeLabel = (o: string | null) => OUTCOME_LABEL[o ?? "not_run"] ?? "Running";

export default function RelationshipsPage() {
  const [tab, setTab] = useState<StateTab>("");
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [module, setModule] = useState("");
  const [stype, setStype] = useState("");
  const [sort, setSort] = useState("status");
  const [minHealth, setMinHealth] = useState("");
  const [actions, setActions] = useState(false);
  const [discoverOpen, setDiscoverOpen] = useState(false);
  const [latest, setLatest] = useState<DiscoveryDetail | null>(null);
  const r = useApi<Page>(`/people${qs({ states: tab, q, has_action: actions ? "true" : undefined, country, module, stakeholder_type: stype, sort,
                                        min_health: minHealth, limit: 100 })}`);
  const qu = useApi<Questions>("/relationships/questions");
  const disc = useApi<{ items: Discovery[] }>("/contacts/discoveries?limit=8");
  const areas = r.data?.capability_areas ?? {};
  const exportHref = `/api/people/export.csv${qs({ states: tab, q, country, module, stakeholder_type: stype, sort })}`;
  const reloadAll = () => { r.reload(); qu.reload(); disc.reload(); };
  return (
    <>
      <PageHeader eyebrow="Relationships" title="People, relationships and introduction routes"
                  description="Every person ATLAS has found in the open market or the team has added, with the evidence for who they are, the team's judgement of their part in the decision, the health of the relationship, who at WFC knows them and who could introduce us."
                  actions={<><a className="btn" href={exportHref}>Export CSV</a>
                             <button type="button" className="btn btn-primary" aria-expanded={discoverOpen} onClick={() => setDiscoverOpen((v) => !v)}>
                               {discoverOpen ? "Close" : "Discover contacts"}</button></>} />
      {discoverOpen && <DiscoverForm areas={areas} onDone={(d) => { setLatest(d); reloadAll(); }} />}
      {latest && <DiscoveryResult d={latest} onContinue={async () => { const d = await api.post<DiscoveryDetail>(`/contacts/discoveries/${latest.id}/continue`); setLatest(d); reloadAll(); }} />}

      {qu.data && <FiveQuestions q={qu.data} />}

      <section className="panel" aria-label="Contact directory">
        <div className="panel-head"><h2>Contact directory</h2>{r.data && <span className="muted small">{r.data.total} people</span>}</div>
        <Tabs<StateTab> label="Research status" value={tab} onChange={setTab} tabs={[
          { id: "", label: "Everyone" }, { id: "research_candidate", label: "Research candidates" }, { id: "identity_confirmed", label: "Identity and role confirmed" },
          { id: "existing_relationship", label: "Existing relationship" }, { id: "introduction_available", label: "Introduction available" }]} />
        <div className="filters">
          <label className="field">Search<input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name, role or organisation" /></label>
          <CountrySelect value={country} onChange={setCountry} />
          <label className="field">Capability area<select className="select" value={module} onChange={(e) => setModule(e.target.value)}>
            <option value="">All areas</option>{Object.entries(areas).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label className="field">Stakeholder type<select className="select" value={stype} onChange={(e) => setStype(e.target.value)}>
            <option value="">Any</option>{STAKEHOLDER_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label className="field">Health<select className="select" value={minHealth} onChange={(e) => setMinHealth(e.target.value)}>
            <option value="">Any</option><option value="75">Strong (75+)</option><option value="55">Healthy or better (55+)</option><option value="35">Cooling or better (35+)</option></select></label>
          <label className="field">Sort by<select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="status">Research status</option><option value="attention">Needs attention</option><option value="health">Health</option>
            <option value="name">Name (A–Z)</option><option value="recent">Most recent</option></select></label>
          <label className="field inline"><input type="checkbox" checked={actions} onChange={(e) => setActions(e.target.checked)} /> With a next action</label>
        </div>
        {r.stale && <StaleBanner onRetry={r.reload} />}
        {r.status === "loading" && <Loading what="people" />}
        {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
        {r.data && (r.data.items.length === 0 ? <Empty title="No people match">Use Discover contacts above, open an opportunity and choose Research relationships, or add a person below.</Empty> : (
          <TableWrap label="People">
            <table><thead><tr><th>Person</th><th>Organisation</th><th>Stakeholder</th><th>Research status</th><th>Health</th><th>Momentum</th><th>Owner</th><th>Next action</th><th>LinkedIn</th></tr></thead>
              <tbody>{r.data.items.map((p) => (
                <tr key={p.id}>
                  <td><Link href={`/relationships/${p.id}`}>{p.full_name}</Link><div className="small muted">{p.role_title ?? "role not established"}{p.capability_area_label ? ` · ${p.capability_area_label}` : ""}</div></td>
                  <td>{p.organisation ?? <span className="muted">Not established</span>}</td>
                  <td className="small">{p.stakeholder_label}{p.posture !== "unknown" && <div className="muted">{p.posture_label}</div>}</td>
                  <td><Tag text={p.state_label} tone={STATE_TONE[p.state]} />{p.possible_routes > 0 && p.state !== "introduction_available" &&
                    <div className="small muted">{p.possible_routes} possible route(s)</div>}</td>
                  <td><HealthBadge score={p.health_score} band={p.health_band} bandLabel={p.health_band_label ?? "Not assessed"} atRisk={!!p.at_risk} /></td>
                  <td className="small">{p.momentum_state && p.momentum ? <Tag text={p.momentum} tone={MOMENTUM_TONE[p.momentum_state]} /> : <span className="muted">–</span>}
                    {p.last_engagement && <div className="muted">last {dateOnly(p.last_engagement)}</div>}</td>
                  <td className="small">{p.relationship_owner ?? <span className="muted">Not recorded</span>}</td>
                  <td className="small">{p.next_action ?? <span className="muted">{p.recommended_action ?? "None"}</span>}{p.next_action_due && <div className="muted">due {dateOnly(p.next_action_due)}</div>}</td>
                  <td className="small">{p.linkedin_profile_url ? <a href={p.linkedin_profile_url} target="_blank" rel="noreferrer noopener">Confirmed profile</a>
                    : <a href={p.linkedin_search_url} target="_blank" rel="noreferrer noopener">Search</a>}</td>
                </tr>
              ))}</tbody></table>
          </TableWrap>
        ))}
      </section>

      <Discoveries items={disc.data?.items ?? []} onOpen={async (id) => setLatest(await api.get<DiscoveryDetail>(`/contacts/discoveries/${id}`))} />
      <Duplicates onChanged={r.reload} />
      <AddPerson onAdded={reloadAll} />
    </>
  );
}

function CountrySelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const geo = useGeography();
  return (
    <label className="field">Country<select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Any country</option>{(geo?.countries ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</select></label>
  );
}

/* ----------------------------------------------------------------- the five questions */
function FiveQuestions({ q }: { q: Questions }) {
  return (
    <section className="panel" aria-label="Relationship questions">
      <div className="panel-head"><h2>What the relationship record says</h2>
        <span className="muted small">{q.totals.people} people · {q.totals.assessed} assessed · {q.totals.at_risk} at risk · {q.totals.not_judged} not yet judged</span></div>
      <div className="grid grid-3 questions">
        <div className="question" aria-label="Who matters most">
          <h3>Who matters most</h3>
          <p className="small muted">By commercial consequence, not by how well we know them.</p>
          {q.who_matters_most.length === 0 ? <p className="muted small">Nobody recorded yet.</p> : (
            <ol className="list-plain">{q.who_matters_most.map((p) => <PersonLine key={p.person_id} p={p} extra={`importance ${p.importance} · ${p.why}${p.is_known ? "" : " · never engaged"}`} />)}</ol>)}
        </div>
        <div className="question" aria-label="Who are we missing">
          <h3>Who are we missing</h3>
          <p className="small muted">Live opportunities without the people who decide.</p>
          {q.who_are_we_missing.length === 0 ? <p className="muted small">No gaps on live opportunities.</p> : (
            <ul className="list-plain">{q.who_are_we_missing.slice(0, 6).map((g, i) => (
              <li key={`${g.opportunity_id}-${g.missing}-${i}`}><Tag text={g.missing_label} tone={g.severity === "high" ? "b-bad" : g.severity === "medium" ? "b-warn" : "b-none"} />{" "}
                <Link href={`/opportunities/${g.opportunity_id}`}>{g.opportunity_title}</Link><div className="small muted">{g.why}. {g.recommended_action}</div></li>))}</ul>)}
        </div>
        <div className="question" aria-label="Where to invest time">
          <h3>Where to invest time</h3>
          <p className="small muted">Where an hour changes an outcome: high influence, low or falling health.</p>
          {q.where_to_invest_time.length === 0 ? <p className="muted small">Nothing assessed yet.</p> : (
            <ol className="list-plain">{q.where_to_invest_time.map((p) => <PersonLine key={p.person_id} p={p} extra={`attention ${p.attention} · ${p.recommended_action} · ${p.expected_benefit}`} />)}</ol>)}
        </div>
        <div className="question" aria-label="Relationships at risk">
          <h3>At risk or declining</h3>
          {q.at_risk.length === 0 ? <p className="muted small">None.</p> : (
            <ul className="list-plain">{q.at_risk.map((p) => <PersonLine key={p.person_id} p={p} extra={p.why} />)}</ul>)}
        </div>
        <div className="question" aria-label="Improving relationships">
          <h3>Improving</h3>
          {q.improving.length === 0 ? <p className="muted small">None yet.</p> : (
            <ul className="list-plain">{q.improving.map((p) => <PersonLine key={p.person_id} p={p} extra={p.why} />)}</ul>)}
        </div>
      </div>
      <p className="small muted">{q.rule}</p>
    </section>
  );
}

/* ----------------------------------------------------------------- open-market contact discovery */
function DiscoverForm({ areas, onDone }: { areas: Record<string, string>; onDone: (d: DiscoveryDetail) => void }) {
  const geo = useGeography();
  const [f, setF] = useState({ organisation_name: "", capability_area: "", role_focus: "", region: "", requested_by_label: "" });
  const [countries, setCountries] = useState<string[]>([]);
  const [mode, setMode] = useState<"countries" | "region">("countries");
  const a = useAction();
  const ready = f.organisation_name.trim() || f.role_focus.trim() || (mode === "countries" ? countries.length > 0 : !!f.region);
  return (
    <section className="panel" aria-label="Discover contacts">
      <h2>Discover contacts in the open market</h2>
      <p className="small muted">A search for named people by organisation, country or region, WFC capability area and role focus. ATLAS reads the organisation&apos;s
        own pages and the authorised web search&apos;s results; every contact carries the passage that names them and a relevance to this brief. Public pages only; no
        LinkedIn profile is fetched and nothing is sent.</p>
      <form className="form-grid" onSubmit={async (e: FormEvent) => { e.preventDefault();
        const body = { organisation_name: f.organisation_name || null, capability_area: f.capability_area || null, role_focus: f.role_focus || null,
                       region: mode === "region" ? f.region || null : null, countries: mode === "countries" ? countries : [], requested_by_label: f.requested_by_label || null };
        const d = await a.run(() => api.post<DiscoveryDetail>("/contacts/discover", body), "Discovery run");
        if (d) onDone(d); }}>
        <label className="field">Organisation (optional)<input className="input" value={f.organisation_name} onChange={(e) => setF({ ...f, organisation_name: e.target.value })} placeholder="e.g. Example Air" /></label>
        <label className="field">Capability area<select className="select" value={f.capability_area} onChange={(e) => setF({ ...f, capability_area: e.target.value })}>
          <option value="">Any</option>{Object.entries(areas).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Role focus (optional)<input className="input" value={f.role_focus} onChange={(e) => setF({ ...f, role_focus: e.target.value })} placeholder="e.g. head of procurement" /></label>
        <label className="field">Requested by<input className="input" value={f.requested_by_label} onChange={(e) => setF({ ...f, requested_by_label: e.target.value })} /></label>
        <div className="field" style={{ gridColumn: "1 / -1" }}>Geography
          <div className="segmented" role="group" aria-label="Geography mode">
            <button type="button" aria-pressed={mode === "countries"} onClick={() => setMode("countries")}>Countries</button>
            <button type="button" aria-pressed={mode === "region"} onClick={() => setMode("region")}>Region</button>
          </div>
        </div>
        {mode === "countries" ? <div style={{ gridColumn: "1 / -1" }}><CountryPicker value={countries} onChange={setCountries} max={5} /></div> : (
          <label className="field">Region<select className="select" value={f.region} onChange={(e) => setF({ ...f, region: e.target.value })}>
            <option value="">Choose a region</option>{(geo?.regions ?? []).map((rg) => <option key={rg.code} value={rg.code}>{rg.name}</option>)}</select></label>)}
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy || !ready}>{a.busy ? "Researching…" : "Find contacts"}</button></div>
        <p className="small muted" style={{ gridColumn: "1 / -1" }}>Usually 10–60 seconds. Found people are added to the directory as research candidates.</p>
        <ActionNote state={a} />
      </form>
    </section>
  );
}

function DiscoveryResult({ d, onContinue }: { d: DiscoveryDetail; onContinue: () => Promise<void> }) {
  const [open, setOpen] = useState<string | null>(null);
  const a = useAction();
  return (
    <section className="panel" aria-label="Discovery result">
      <div className="panel-head"><h2>Discovery: {d.brief}</h2><Tag text={outcomeLabel(d.outcome)} tone={OUTCOME_TONE[d.outcome ?? "not_run"]} /></div>
      <p className="small muted">{d.people.length} contact(s) · {d.documents.filter((x) => x.status === "read").length} page(s) read of {d.documents.length} ·{" "}
        {d.searches.filter((s) => s.status === "run").length} search(es) run, {d.searches.filter((s) => s.status === "not_run").length} not run · run {d.runs} time(s)</p>
      {d.actions.length > 0 && <ul className="small">{d.actions.map((x) => <li key={x}>{x}</li>)}</ul>}
      {d.outcome === "incomplete" && <button type="button" className="btn btn-small" disabled={a.busy} onClick={() => a.run(onContinue, "Discovery continued")}>Continue discovery</button>}
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

function Discoveries({ items, onOpen }: { items: Discovery[]; onOpen: (id: string) => void }) {
  if (items.length === 0) return null;
  return (
    <section className="panel" aria-label="Recent discoveries">
      <h2>Recent contact discoveries</h2>
      <ul className="list-plain small">{items.map((d) => (
        <li key={d.id}><button type="button" className="link-button" onClick={() => onOpen(d.id)}>{d.brief}</button>{" "}
          <Tag text={outcomeLabel(d.outcome)} tone={OUTCOME_TONE[d.outcome ?? "not_run"]} />
          <span className="muted"> · {d.people_found} contact(s) · {dateTime(d.started_at)}{d.requested_by_label ? ` · ${d.requested_by_label}` : ""}</span></li>))}</ul>
    </section>
  );
}

function Duplicates({ onChanged }: { onChanged: () => void }) {
  const d = useApi<{ items: Duplicate[] }>("/people/duplicates?status=open");
  if (!d.data) return null;
  return (
    <div id="duplicates" style={{ marginTop: 16 }}>
      {/* always the same component, so its confirmation stays visible after the last pair is resolved */}
      <DuplicateReview items={d.data.items} title="Possible duplicates" onChanged={() => { d.reload(); onChanged(); }} />
    </div>
  );
}

function AddPerson({ onAdded }: { onAdded: () => void }) {
  const [f, setF] = useState({ full_name: "", role_title: "", organisation_label: "", source_url: "" });
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { full_name: f.full_name, role_title: f.role_title || null, organisation_label: f.organisation_label || null,
                   source_url: f.source_url || null, source_note: f.source_url ? null : "added by a reviewer" };
    if (await a.run(() => api.post("/people", body), "Person added as a research candidate")) {
      setF({ full_name: "", role_title: "", organisation_label: "", source_url: "" }); onAdded();
    }
  }
  return (
    <section className="panel" aria-label="Add a person" style={{ marginTop: 16 }}>
      <h2>Add a person</h2>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">Full name<input className="input" required minLength={3} value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
        <label className="field">Role or title<input className="input" value={f.role_title} onChange={(e) => setF({ ...f, role_title: e.target.value })} /></label>
        <label className="field">Organisation<input className="input" value={f.organisation_label} onChange={(e) => setF({ ...f, organisation_label: e.target.value })} /></label>
        <label className="field">Source URL (optional)<input className="input" value={f.source_url} onChange={(e) => setF({ ...f, source_url: e.target.value })} /></label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy}>Add</button></div>
      </form>
      <ActionNote state={a} />
    </section>
  );
}
