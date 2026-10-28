"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useState, type FormEvent } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { OpportunityPicker, type PickedOpportunity } from "@/components/OpportunityPicker";
import { ActionNote, type ClaimField, FieldList, PassageViewer, Provenance, ReasonAction, Section } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateOnly, dateTime, deadline, label, money, moduleLabel, humanText, type DeadlineInfo, deadlineNotes } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Opp = { id: string; title: string; module: string; commercial_stage: string; qualification_status: string; classification: string | null;
             tender_status: string | null; tender_status_basis: string | null; freight_scope: string | null; tender_ref: string | null; identity_basis: string | null; deadline_utc: string | null; deadline_source_tz: string | null; deadline_info: DeadlineInfo | null;
             operating_company_id: string | null; operating_company: string | null; service_id: string | null; service: string | null;
             station_code: string | null; delivery_start: string | null; required_credentials: string[]; owner_person_id: string | null;
             owner: string | null; organisation: string | null; gaps: string[] | null; origin_ref: string | null; notes: string | null; signal_id: string | null;
             tender_state: { status: string; history: { at: string | null; field: string; from: string | null; to: string }[]; reasons: string[];
                             status_verified_at?: string | null; status_asserted_at?: string | null; status_date_known?: boolean; retrieved_at?: string | null;
                             published_at?: string | null; status_conflict?: string | null } | null;
             review_flags?: { flag: string; claim_id: string; from: string; to: string; reason: string; version: number; at: string; previous_review_status?: string }[] };
type Evidence = { claim_id: string; claim_type: string; status: string; review_status: string; tender_ref: string | null; stance: string; quote: string;
                  assessed_by: string; assessed_at?: string | null; excluded_at: string | null; location?: string | null; document_version?: string | null;
                  original_url?: string | null; text_retained?: boolean | null; review_note?: string | null;
                  document_id: string; title: string | null; canonical_url: string; published_at: string | null;
                  retrieved_at: string; language: string | null; summary_en: string | null; summary_is_translation: boolean; family_key: string | null;
                  source_name: string | null; authority: string | null; authenticity: string | null; fields: ClaimField[] | null };
type Factor = { code: string; value: number | null; anchor: string | null; weight: string; rationale: string | null; gate: boolean };
type Detail = {
  opportunity: Opp;
  checks: { check_code: string; result: string; blocking: boolean; rationale: string }[];
  overrides: { id: string; check_code: string; override_result: string; reason: string; created_at: string; expires_at: string | null; revoked_at: string | null }[];
  history: { field: string; from_value: string | null; to_value: string; reason: string | null; changed_at: string }[];
  evidence: Evidence[];
  geography: { country_code: string; name: string; role: string; support: string }[];
  assessments: { dimension: string; score: string | null; coverage: string; status: string; factors: Factor[]; version: string; provisional: boolean }[];
  value: { currency: string | null; airline_revenue: string | null; wfc_remuneration: string | null; incremental_costs: string | null;
           guarantee_exposure: string | null; duration_months: number | null; basis: string; assumptions: { text: string; source: string; source_date: string }[] } | null;
  contribution: { status: string; retained_contribution: string | null; currency: string | null; reasons: string[] } | null;
  referrals: { id: string; status: string; from_company: string; to_company: string }[];
  competing: { id: string; title: string; module: string }[];
};
type Lookups = { companies: { id: string; name: string }[]; services: { id: string; code: string; name: string }[];
                 airports: { iata_code: string; name: string; country: string }[]; people: { id: string; full_name: string; is_internal: boolean }[] };

const NEXT_STAGES: Record<string, string[]> = {
  new: ["reviewing", "deferred", "lost"], reviewing: ["qualified", "deferred", "lost"], qualified: ["pursuing", "deferred", "lost"],
  pursuing: ["proposal", "deferred", "lost"], proposal: ["negotiation", "won", "lost", "deferred"], negotiation: ["won", "lost", "deferred"],
  deferred: ["reviewing"], won: [], lost: [], expired: [],
};
const COMMERCIAL_CHECKS = ["eligibility", "scope", "owner_assigned", "commercial_terms"];

export default function OpportunityDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const r = useApi<Detail>(id ? `/opportunities/${id}` : null);
  const l = useApi<Lookups>("/reference/lookups");
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="opportunity" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body d={r.data} lookups={l.data} reload={r.reload} />}
    </>
  );
}

function Body({ d, lookups, reload }: { d: Detail; lookups: Lookups | null; reload: () => void }) {
  const o = d.opportunity;
  const families = new Set(d.evidence.filter((e) => e.stance === "supports" && !e.excluded_at).map((e) => e.family_key ?? e.document_id));
  const proposed = [...new Set(d.evidence.filter((e) => e.review_status === "proposed").map((e) => e.claim_id))];
  const a = useAction();
  return (
    <div className="stack">
      <PageHeader eyebrow={`Opportunities · ${moduleLabel(o.module)}`} title={o.title}
                  description={`${o.organisation ?? "Organisation not established"}${o.tender_ref ? ` · reference ${o.tender_ref}` : ""} · deadline ${deadline(o.deadline_utc, o.deadline_source_tz, o.deadline_info)}`}
                  actions={<Link className="btn" href="/opportunities">All opportunities</Link>} />
      {deadlineNotes(o.deadline_info).length > 0 && (
        <div className="notice" role="note"><strong>Deadline precision.</strong>{" "}{deadlineNotes(o.deadline_info).join(" ")}</div>
      )}
      {(o.freight_scope === "passenger" || o.freight_scope === "not_freight") && (
        <div className="notice" role="status" data-testid="excluded-notice"><strong>Excluded from the freight pipeline.</strong> {o.freight_scope === "passenger" ? "This is a passenger-only mandate" : "The notice excludes cargo or asks for work outside the freight scope"}; it is kept as evidence and never qualifies. A reviewer can correct the freight scope on the evidence if the reading is wrong.</div>
      )}
      {(o.freight_scope === "mixed" || o.freight_scope === "unclear" || o.freight_scope === "conflicting") && (
        <div className="notice" role="status" data-testid="candidate-notice"><strong>Freight candidate — not a qualified freight opportunity.</strong> The notice does not establish that the work concerns freight ({o.freight_scope}). Review the freight scope on the evidence before any work.</div>
      )}
      {o.tender_state?.status_conflict && (
        <div className="notice" role="status" data-testid="status-conflict-notice"><strong>Status conflict — review.</strong> {o.tender_state.status_conflict.replace(/\.?$/, ".")} Retrieval order never decides which statement is current; the record is not actionable until a person confirms it.</div>
      )}
      {o.tender_status === "announced" && (
        <div className="notice" role="status" data-testid="announced-notice"><strong>Announced — current status unverified.</strong> The notice establishes that the procurement exists; nothing states that applications are still being accepted. It is not counted as live.</div>
      )}
      {(o.tender_status === "unverified" || o.tender_status === "historical") && (
        <div className="notice" role="status" data-testid="status-notice"><strong>Status not verified.</strong> {(o.tender_status_basis ?? "The open status is not confirmed by a current source").replace(/\.?$/, ".")} No closing date has been assumed; confirm with the issuer before any work.</div>
      )}
      <div className="grid grid-4">
        <div className="stat"><div className="stat-label">Classification</div><div style={{ marginTop: 8 }}><Badge value={o.classification ?? "internal_record"} /></div></div>
        <div className="stat"><div className="stat-label">Tender status</div><div style={{ marginTop: 8 }} data-testid="tender-status"><Badge value={o.tender_status ?? "unknown"} /></div>{o.tender_status_basis && <div className="stat-note">{o.tender_status_basis}</div>}
          {o.tender_state && (
            <div className="stat-note" data-testid="status-dates">Status last stated: {o.tender_state.status_verified_at ? dateTime(o.tender_state.status_verified_at) : (["open", "revised", "unverified"].includes(o.tender_state.status) ? "date unknown" : "—")}
              {o.tender_state.status_asserted_at && o.tender_state.status_asserted_at !== o.tender_state.status_verified_at ? ` · first stated ${dateTime(o.tender_state.status_asserted_at)}` : ""}
              {o.tender_state.retrieved_at ? ` · last retrieved ${dateTime(o.tender_state.retrieved_at)} (retrieval does not verify status)` : ""}</div>
          )}</div>
        <div className="stat"><div className="stat-label">Freight scope</div><div style={{ marginTop: 8 }} data-testid="freight-scope"><Badge value={o.freight_scope ?? "unclear"} /></div></div>
        <div className="stat"><div className="stat-label">Qualification</div><div style={{ marginTop: 8 }}><Badge value={o.qualification_status} /></div><div className="stat-note">Stage: {label(o.commercial_stage)}</div></div>
      </div>
      {o.review_flags && o.review_flags.length > 0 && (
        <div className="notice" role="note" data-testid="review-flags"><strong>Flagged for review after a re-check:</strong>{" "}
          {o.review_flags.map((f, i) => <span key={i}>{label(f.flag)}{f.from || f.to ? ` (${f.from ?? "—"} → ${f.to ?? "—"})` : ""}{f.reason ? `: ${f.reason}` : ""}{i < o.review_flags!.length - 1 ? " · " : ""}</span>)}
        </div>
      )}
      <Section title="Geography">
        {d.geography.length === 0 ? <p className="muted">No country established by the evidence.</p> : (
          <ul className="chips">{d.geography.map((g) => (
            <li key={`${g.country_code}-${g.role}`} className="chip">{g.name} · {g.role.replace("_", " ")}{g.support !== "supported" && g.support !== "internal_record" ? " (unverified)" : ""}</li>
          ))}</ul>
        )}
        {o.gaps && o.gaps.length > 0 && <div className="notice" style={{ marginTop: 12 }}><strong>Gaps:</strong> {o.gaps.join(" · ")}</div>}
        {o.notes && <p className="muted small">{o.notes}</p>}
      </Section>

      <Section title={`Evidence (${families.size} independent announcement famil${families.size === 1 ? "y" : "ies"})`}
               actions={proposed.length > 0 ? (
                 <button className="btn btn-primary" type="button" disabled={a.busy}
                         onClick={async () => { for (const c of proposed) await a.run(() => api.post(`/claims/${c}/confirm`, { note: "reviewed on the opportunity page" })); reload(); }}>
                   Confirm {proposed.length} AI-proposed claim{proposed.length === 1 ? "" : "s"}
                 </button>) : undefined}>
        <p className="muted small">Each field is a fact only if its own quote, found verbatim in the document, states it. Syndicated copies count once; contradicting evidence stays visible. A verdict is a rule result, never a confidence score, and does not by itself verify the fact.</p>
        {(o.review_flags ?? []).filter((f) => f.flag === "eligibility_revalidated").length > 0 && (
          <div className="notice" role="status">
            <strong>Re-checked eligibility evidence.</strong> {(o.review_flags ?? []).filter((f) => f.flag === "eligibility_revalidated").map((f, i) => (
              <span key={i}>An earlier &quot;{label(f.from)}&quot; verdict (validation rules v{f.version - 1}) was withdrawn on {dateTime(f.at)}: now &quot;{label(f.to)}&quot; — {f.reason}.{f.previous_review_status ? ` Previous reviewer decision: ${label(f.previous_review_status)} (kept in the audit history).` : ""} </span>
            ))}Confirm or correct the claim in Evidence Review.
          </div>
        )}
        <ActionNote state={a} />
        {d.evidence.length === 0 ? <Empty title={o.origin_ref ? "Derived from internal records" : "No evidence linked"}>{o.origin_ref ?? ""}</Empty> : d.evidence.map((e, i) => (
          <article key={`${e.claim_id}-${e.document_id}-${i}`} className="claim-card">
            <div className="inline">
              <strong>{label(e.claim_type)}</strong> <Badge value={e.status} /> <Badge value={e.review_status} /> <Badge value={e.stance} />
              <span className="muted small">{e.source_name} ({e.authority?.replace("_", " ")}) · authenticity {e.authenticity ?? "unknown"} · {e.published_at ? `published ${dateTime(e.published_at)}` : `publication date unknown · retrieved ${dateTime(e.retrieved_at)}`}{e.excluded_at ? " · excluded" : ""}</span>
            </div>
            <p className="small"><span className="muted">Source wording: </span><q>{e.quote}</q> <Link href={`/review/documents/${e.document_id}`}>Open document</Link></p>
            <Provenance e={e} dateTime={dateTime} />
            <PassageViewer documentId={e.document_id} quote={e.quote} location={e.location} get={(path) => api.get(path)} />
            {e.summary_en && <p className="small muted">{e.summary_is_translation ? "English summary (translation): " : ""}{e.summary_en}</p>}
            <FieldList fields={e.fields} />
          </article>
        ))}
        {o.tender_state && o.tender_state.history.length > 0 && (
          <>
            <h3 className="small" style={{ marginTop: 14 }}>Tender history (authoritative sources)</h3>
            <ul className="small">{o.tender_state.history.map((h, i) => (
              <li key={i}>{h.at ? dateTime(h.at) : "date unknown"}: {h.field} {h.from ? `${humanText(h.from)} → ` : ""}{humanText(h.to)}</li>
            ))}</ul>
          </>
        )}
      </Section>

      <Qualification d={d} reload={reload} />
      <ScopeForm o={o} lookups={lookups} onDone={reload} />
      <Priority d={d} />
      <Economics d={d} lookups={lookups} onDone={reload} />
      <Section title="History">
        {d.history.length === 0 ? <Empty title="No changes recorded" /> : (
          <TableWrap label="History"><table><thead><tr><th>When</th><th>What</th><th>Change</th><th>Reason</th></tr></thead>
            <tbody>{d.history.map((h, i) => (
              <tr key={i}><td>{dateTime(h.changed_at)}</td><td>{label(h.field)}</td>
                <td>{h.from_value ? `${h.field === "deadline" ? deadlineHistory(h.from_value) : label(h.from_value)} → ` : ""}{h.field === "deadline" ? deadlineHistory(h.to_value) : h.field === "scope" ? humanText(h.to_value) : label(h.to_value)}</td>
                <td className="small">{h.reason}</td></tr>
            ))}</tbody></table></TableWrap>
        )}
      </Section>
    </div>
  );
}

function Qualification({ d, reload }: { d: Detail; reload: () => void }) {
  const o = d.opportunity;
  const a = useAction();
  const [code, setCode] = useState("eligibility");
  const [result, setResult] = useState("pass");
  const [reason, setReason] = useState("");
  const [expires, setExpires] = useState("");
  async function override(e: FormEvent) {
    e.preventDefault();
    const r = await a.run(() => api.post(`/opportunities/${o.id}/overrides`, { check_code: code, result, reason, expires_at: expires ? `${expires}T23:59:59Z` : null }),
                          "Recorded; qualification recomputed");
    if (r) { setReason(""); reload(); }
  }
  return (
    <Section title="Qualification">
      <TableWrap label="Qualification checks">
        <table><thead><tr><th>Check</th><th>Evidence result</th><th>Judgement</th><th>Blocking</th><th>Rationale</th></tr></thead>
          <tbody>{d.checks.map((c) => {
            const j = d.overrides.find((x) => !x.revoked_at && x.check_code === c.check_code && (!x.expires_at || new Date(x.expires_at) > new Date()));
            return (
            <tr key={c.check_code}><td>{label(c.check_code)}{COMMERCIAL_CHECKS.includes(c.check_code) ? <span className="muted small">commercial judgement</span> : <span className="muted small">factual</span>}</td>
              <td><Badge value={c.result} /></td><td>{j ? <Badge value={j.override_result} /> : <span className="muted">—</span>}</td><td>{c.blocking ? "Yes" : "No"}</td><td className="small">{humanText(c.rationale)}</td></tr>
            );
          })}</tbody></table>
      </TableWrap>
      {d.overrides.filter((x) => !x.revoked_at).length > 0 && (
        <p className="small muted">Recorded judgements: {d.overrides.filter((x) => !x.revoked_at).map((x) => `${label(x.check_code)} → ${x.override_result} (“${x.reason}”${x.expires_at ? `, until ${dateOnly(x.expires_at)}` : ""})`).join("; ")}</p>
      )}
      <form onSubmit={override} className="form-grid" style={{ marginTop: 12 }}>
        <label className="field">Commercial check
          <select className="select" value={code} onChange={(e) => setCode(e.target.value)}>{COMMERCIAL_CHECKS.map((c) => <option key={c} value={c}>{label(c)}</option>)}</select></label>
        <label className="field">Judgement
          <select className="select" value={result} onChange={(e) => setResult(e.target.value)}><option value="pass">Pass</option><option value="fail">Fail</option><option value="review_required">Review required</option></select></label>
        <label className="field">Valid until (optional)<input className="input" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} /></label>
        <label className="field wide">Reason (at least 10 characters; factual checks cannot be overridden)
          <input className="input" value={reason} onChange={(e) => setReason(e.target.value)} minLength={10} required /></label>
        <div className="actions"><button className="btn" type="submit" disabled={a.busy || reason.trim().length < 10}>Record judgement</button></div>
      </form>
      <div className="actions" style={{ marginTop: 12 }}>
        {o.qualification_status === "ready_for_review" && (
          <ReasonAction label="Approve for pursuit" tone="primary" busy={a.busy}
                        onSubmit={(reason) => a.run(() => api.post(`/opportunities/${o.id}/approve`, { reason }), "Approved for pursuit").then(reload)} />
        )}
        {(NEXT_STAGES[o.commercial_stage] ?? []).map((s) => (
          <ReasonAction key={s} label={`Move to ${label(s)}`} busy={a.busy} minLength={3}
                        onSubmit={(reason) => a.run(() => api.post(`/opportunities/${o.id}/stage`, { to: s, reason }), `Moved to ${label(s)}`).then(reload)} />
        ))}
      </div>
      <ActionNote state={a} />
    </Section>
  );
}

function ScopeForm({ o, lookups, onDone }: { o: Opp; lookups: Lookups | null; onDone: () => void }) {
  const [company, setCompany] = useState(o.operating_company_id ?? "");
  const [service, setService] = useState(o.service_id ?? "");
  const [station, setStation] = useState(o.station_code ?? "");
  const [delivery, setDelivery] = useState(o.delivery_start ?? "");
  const [creds, setCreds] = useState((o.required_credentials ?? []).join(", "));
  const [owner, setOwner] = useState(o.owner_person_id ?? "");
  const a = useAction();
  async function save(e: FormEvent) {
    e.preventDefault();
    await a.run(() => api.post<{ qualification_status: string }>(`/opportunities/${o.id}/scope`, {
      operating_company_id: company || null, service_id: service || null, station_code: station || null, delivery_start: delivery || null,
      required_credentials: creds.split(",").map((c) => c.trim().toUpperCase()).filter(Boolean) }),
      (x) => `Scope saved; qualification is now ${label(x.qualification_status)}`);
    onDone();
  }
  const people = lookups?.people ?? [];
  return (
    <Section title="Scope and owner">
      <p className="muted small">Capability is resolved from the capability register for this company, service and station on the delivery date. A station-specific record covers only that station; with no station set, only company-wide records count.</p>
      <form onSubmit={save} className="form-grid">
        <label className="field">Operating company
          <select className="select" value={company} onChange={(e) => setCompany(e.target.value)}><option value="">Not assigned</option>
            {lookups?.companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="field">Service
          <select className="select" value={service} onChange={(e) => setService(e.target.value)}><option value="">Not assigned</option>
            {lookups?.services.map((s) => <option key={s.id} value={s.id}>{s.code}: {s.name}</option>)}</select></label>
        <label className="field">Delivery station
          <select className="select" value={station} onChange={(e) => setStation(e.target.value)}><option value="">Not set (company level)</option>
            {lookups?.airports.map((s) => <option key={s.iata_code} value={s.iata_code}>{s.iata_code}: {s.name} ({s.country})</option>)}</select></label>
        <label className="field">Delivery start<input className="input" type="date" value={delivery} onChange={(e) => setDelivery(e.target.value)} /></label>
        <label className="field wide">Required credentials (comma-separated, in addition to the service&apos;s own)
          <input className="input" value={creds} onChange={(e) => setCreds(e.target.value)} placeholder="e.g. IATA_CARGO_AGENT, IATA_DGR" /></label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy}>Save scope</button></div>
      </form>
      <div className="form-grid" style={{ marginTop: 14 }}>
        <label className="field">Owner (a recorded person, not a login)
          <select className="select" value={owner} onChange={(e) => setOwner(e.target.value)}><option value="">Unassigned</option>
            {people.map((p) => <option key={p.id} value={p.id}>{p.full_name}{p.is_internal ? "" : " (external)"}</option>)}</select></label>
        <div className="actions" style={{ alignItems: "flex-end" }}>
          <button className="btn" type="button" disabled={a.busy}
                  onClick={() => a.run(() => api.post(`/opportunities/${o.id}/owner`, { person_id: owner || null }), "Owner saved").then(onDone)}>Save owner</button>
        </div>
      </div>
      <ActionNote state={a} />
    </Section>
  );
}

function Priority({ d }: { d: Detail }) {
  if (d.assessments.length === 0) {
    return <Section title="Priority"><p className="muted small">This capability area is ordered by transparent rules rather than a score (see Settings → Prioritisation).</p></Section>;
  }
  return (
    <Section title={`Priority (${d.assessments[0]?.version ?? ""}${d.assessments[0]?.provisional ? ", provisional weights" : ""})`}>
      <p className="muted small">Four separate dimensions, never combined and not a probability of winning. Unknown factors reduce coverage; risk scores high when risk is LOW. Evidence confidence is a machine-generated score of how many independent sources agree; it is not a verification of any fact — only the per-field verdicts and a reviewer&apos;s confirmation above establish what the evidence states.</p>
      <div className="dim-grid">
        {["attractiveness", "evidence_confidence", "readiness", "risk"].map((dim) => {
          const x = d.assessments.find((s) => s.dimension === dim);
          return (
            <div key={dim} className="stat">
              <div className="stat-label">{label(dim)}</div>
              <div className="stat-value">{x?.status === "scored" ? Number(x.score).toFixed(0) : "—"}</div>
              <div className="stat-note">{x ? `${label(x.status)} · coverage ${(Number(x.coverage) * 100).toFixed(0)}%` : "not assessed"}</div>
            </div>
          );
        })}
      </div>
      <details style={{ marginTop: 10 }}>
        <summary className="small">Factors and rationale</summary>
        <TableWrap label="Priority factors"><table><thead><tr><th>Dimension</th><th>Factor</th><th>Value</th><th>Rationale</th></tr></thead>
          <tbody>{d.assessments.map((x) => (
            <Fragment key={x.dimension}>{x.factors.map((f) => (
              <tr key={`${x.dimension}-${f.code}`}><td>{label(x.dimension)}</td><td>{label(f.code)}{f.gate ? " (gate)" : ""}</td>
                <td>{f.value === null ? "Unknown" : `${f.value}/4: ${f.anchor}`}</td><td className="small">{f.rationale}</td></tr>
            ))}</Fragment>
          ))}</tbody></table></TableWrap>
      </details>
    </Section>
  );
}

function Economics({ d, lookups, onDone }: { d: Detail; lookups: Lookups | null | undefined; onDone: () => void }) {
  const [refTo, setRefTo] = useState("");
  const [competeWith, setCompeteWith] = useState<PickedOpportunity | null>(null);
  const [dupOf, setDupOf] = useState<PickedOpportunity | null>(null);
  const [dupReason, setDupReason] = useState("");
  const v = d.value;
  const [f, setF] = useState({ currency: v?.currency ?? "", airline_revenue: v?.airline_revenue ?? "", wfc_remuneration: v?.wfc_remuneration ?? "",
                               incremental_costs: v?.incremental_costs ?? "", guarantee_exposure: v?.guarantee_exposure ?? "",
                               duration_months: v?.duration_months ? String(v.duration_months) : "", basis: v?.basis ?? "unknown",
                               assumption: v?.assumptions?.[0]?.text ?? "", assumption_source: v?.assumptions?.[0]?.source ?? "",
                               assumption_date: v?.assumptions?.[0]?.source_date ?? "" });
  const a = useAction();
  const n = (s: string) => (s.trim() === "" ? null : s.trim());
  async function save(e: FormEvent) {
    e.preventDefault();
    await a.run(() => api.post(`/opportunities/${d.opportunity.id}/value`, {
      currency: n(f.currency)?.toUpperCase() ?? null, airline_revenue: n(f.airline_revenue), wfc_remuneration: n(f.wfc_remuneration),
      incremental_costs: n(f.incremental_costs), guarantee_exposure: n(f.guarantee_exposure), duration_months: f.duration_months ? Number(f.duration_months) : null,
      basis: f.basis, assumptions: f.basis === "scenario" && f.assumption ? [{ text: f.assumption, source: f.assumption_source, source_date: f.assumption_date }] : [] }),
      "Commercial values saved");
    onDone();
  }
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  return (
    <Section title="Economics">
      <p className="muted small">Airline revenue is not WFC contribution. Retained contribution = WFC remuneration − incremental costs, only on contract terms or a labelled, dated scenario; otherwise it stays unqualified. Amounts keep their currency.</p>
      {d.contribution && (
        <p><Badge value={d.contribution.status} /> Retained contribution: {d.contribution.retained_contribution ? money(d.contribution.retained_contribution, d.contribution.currency) : "Unqualified"}
          <span className="muted small"> {d.contribution.reasons.join("; ")}</span></p>
      )}
      <form onSubmit={save} className="form-grid">
        <label className="field">Basis<select className="select" value={f.basis} onChange={set("basis")}>
          <option value="unknown">Unknown (unqualified)</option><option value="contract">Contract terms</option><option value="scenario">Labelled scenario</option></select></label>
        <label className="field">Currency (ISO 4217)<input className="input" value={f.currency} onChange={set("currency")} maxLength={3} placeholder="USD" /></label>
        <label className="field">Airline revenue<input className="input" inputMode="decimal" value={f.airline_revenue} onChange={set("airline_revenue")} /></label>
        <label className="field">WFC remuneration<input className="input" inputMode="decimal" value={f.wfc_remuneration} onChange={set("wfc_remuneration")} /></label>
        <label className="field">Incremental costs<input className="input" inputMode="decimal" value={f.incremental_costs} onChange={set("incremental_costs")} /></label>
        <label className="field">Contractual exposure (guarantees)<input className="input" inputMode="decimal" value={f.guarantee_exposure} onChange={set("guarantee_exposure")} /></label>
        <label className="field">Duration (months)<input className="input" type="number" min={0} value={f.duration_months} onChange={set("duration_months")} /></label>
        {f.basis === "scenario" && <>
          <label className="field wide">Scenario assumption<input className="input" value={f.assumption} onChange={set("assumption")} required /></label>
          <label className="field">Assumption source<input className="input" value={f.assumption_source} onChange={set("assumption_source")} required /></label>
          <label className="field">Source date<input className="input" type="date" value={f.assumption_date} onChange={set("assumption_date")} required /></label>
        </>}
        <div className="actions"><button className="btn" type="submit" disabled={a.busy}>Save economics</button></div>
      </form>
      <ActionNote state={a} />
      {d.competing.length > 0 && <p className="small muted">Competes with: {d.competing.map((c) => c.title).join(", ")} (only the largest counts in pipeline totals).</p>}
      {d.referrals.length > 0 && <p className="small muted">Referrals: {d.referrals.map((x) => `${x.from_company} → ${x.to_company} (${x.status})`).join("; ")}.
        {d.referrals.some((x) => x.status === "accepted" || x.status === "closed") && " Pipeline reports count this opportunity once, for the company that accepted the referral."}</p>}
      <div className="filters">
        <label className="field">Refer to another WFC company
          <select className="select" value={refTo} onChange={(e) => setRefTo(e.target.value)}>
            <option value="">Choose…</option>
            {lookups?.companies.filter((c) => c.id !== d.opportunity.operating_company_id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <button className="btn" type="button" disabled={a.busy || !refTo || !d.opportunity.operating_company_id}
                title={d.opportunity.operating_company_id ? undefined : "Assign the responsible company first"}
                onClick={() => a.run(() => api.post("/referrals", { opportunity_id: d.opportunity.id, from_company: d.opportunity.operating_company_id, to_company: refTo }), "Referral recorded").then((ok) => { if (ok) { setRefTo(""); onDone(); } })}>
          Refer
        </button>
        <OpportunityPicker label="Competing alternative" excludeId={d.opportunity.id} value={competeWith} onChange={setCompeteWith} />
        <button className="btn" type="button" disabled={a.busy || !competeWith}
                onClick={() => competeWith && a.run(() => api.post(`/opportunities/${d.opportunity.id}/competition`, { with_opportunity_id: competeWith.id }), "Grouped as competing alternatives; only the largest counts").then((ok) => { if (ok) { setCompeteWith(null); onDone(); } })}>
          Group as alternatives
        </button>
        <OpportunityPicker label="Same tender as" excludeId={d.opportunity.id} value={dupOf} onChange={setDupOf} />
        <label className="field">Why
          <input className="input" value={dupReason} onChange={(e) => setDupReason(e.target.value)} placeholder="e.g. corrigendum to this RFP" />
        </label>
        <button className="btn" type="button" disabled={a.busy || !dupOf || dupReason.trim().length < 5}
                onClick={() => dupOf && a.run(() => api.post("/merge-candidates", { opportunity_id: d.opportunity.id, other_opportunity_id: dupOf.id, reason: dupReason.trim() }),
                                     "Sent to merge review; nothing is merged until it is decided in Evidence Review").then((ok) => { if (ok) { setDupOf(null); setDupReason(""); } })}>
          Propose as duplicate
        </button>
        {d.competing.length > 0 && <button className="btn" type="button" disabled={a.busy}
                onClick={() => a.run(() => api.post(`/opportunities/${d.opportunity.id}/competition`, { with_opportunity_id: null }), "Removed from competing group").then(onDone)}>Remove from group</button>}
      </div>
    </Section>
  );
}

/** Deadline history holds the deadline AS STATED ("2026-11-30 (date only; …)", "2026-11-30 17:00 EAT");
 *  rows written before precision was kept hold an ISO instant. Never re-render a stated deadline as a timestamp. */
function deadlineHistory(v: string): string {
  if (v === "unknown") return "Unknown";
  return /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(v) ? dateTime(v) : v;
}
