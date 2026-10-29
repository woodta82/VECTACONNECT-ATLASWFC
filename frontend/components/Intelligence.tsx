"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Tag } from "@/components/Records";
import { ActionNote } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateOnly, dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";

/* ----------------------------------------------------------------- types shared with the Relationships pages */
export type Health = {
  assessed: boolean; score: number | null; band: string | null; band_label: string; at_risk: boolean; at_risk_reason: string | null;
  contributions: { factor: string; label: string; score: number; weight: number; contribution: number; note: string | null }[];
  strongest_factors: string[]; weakest_factors: string[];
  improvement_levers: { factor: string; current: number; potential_gain: number; note: string | null }[]; note?: string;
};
export type Intelligence = {
  health: Health; explanation: string; momentum: { state: string; label: string; explanation: string };
  influence: { score: number; note: string }; attention: number; recommended_action: string;
  live_opportunities: { id: string; title: string; score: number | null }[];
  stakeholder: { type: string; type_label: string; decision_authority: string; decision_authority_label: string; posture: string; posture_label: string;
                 basis: string | null; by: string | null; at: string | null; key_interests: string | null; strategic_account: boolean };
};
export type Draft = { id: string; opportunity_id: string | null; opportunity_title: string | null; channel: string; subject: string | null; body: string;
                      source: string; basis: string[]; status: string; sent_at: string | null; sent_by_label: string | null; sent_note: string | null; created_at: string };

export const STAKEHOLDER_TYPES: [string, string][] = [
  ["unknown", "Not yet judged"], ["economic_buyer", "Economic buyer"], ["budget_holder", "Budget holder"], ["programme_sponsor", "Programme sponsor"],
  ["procurement_authority", "Procurement authority"], ["political_sponsor", "Political sponsor"], ["technical_evaluator", "Technical evaluator"],
  ["technical_influencer", "Technical influencer"], ["adviser", "Adviser"], ["gatekeeper", "Gatekeeper"], ["introducer", "Introducer"],
  ["delivery_partner", "Delivery partner"], ["consultant", "Consultant"]];
export const DECISION_AUTHORITY: [string, string][] = [["unknown", "Not established"], ["final", "Final say"], ["shared", "Shared decision"],
                                                       ["influence", "Influences the decision"], ["none", "No authority"]];
export const POSTURES: [string, string][] = [["unknown", "Not yet judged"], ["champion", "Champion"], ["supportive", "Supportive"], ["neutral", "Neutral"],
                                             ["sceptical", "Sceptical"], ["blocker", "Blocker"]];
export const HEALTH_TONE: Record<string, string> = { strong: "b-good", healthy: "b-good", cooling: "b-warn", weak: "b-bad", dormant: "b-bad" };
export const MOMENTUM_TONE: Record<string, string> = { improving: "b-good", stable: "b-info", new: "b-none", declining: "b-warn", dormant: "b-bad" };

/** The health score with its band, or "Not assessed". */
export function HealthBadge({ score, band, bandLabel, atRisk }: { score: number | null; band: string | null; bandLabel: string; atRisk?: boolean }) {
  if (score === null || band === null) return <span className="muted small">Not assessed</span>;
  return (
    <span className="health-badge">
      <b className="num">{score}</b><span className="muted small">/100</span> <Tag text={bandLabel} tone={HEALTH_TONE[band]} />
      {atRisk && <Tag text="At risk" tone="b-bad" />}
    </span>
  );
}

/* ----------------------------------------------------------------- health panel on the person page */
export function HealthPanel({ i }: { i: Intelligence }) {
  const h = i.health;
  return (
    <section className="panel" aria-label="Relationship health">
      <div className="panel-head"><h2>Relationship health</h2><HealthBadge score={h.score} band={h.band} bandLabel={h.band_label} atRisk={h.at_risk} /></div>
      <p className="small">{i.explanation}</p>
      {h.at_risk && h.at_risk_reason && <p className="notice notice-warn small">{h.at_risk_reason}: the score is capped at 40 until contact is renewed.</p>}
      <div className="grid grid-3 health-facts">
        <div><div className="stat-label">Momentum</div><Tag text={i.momentum.label} tone={MOMENTUM_TONE[i.momentum.state]} /><div className="small muted">{i.momentum.explanation}</div></div>
        <div><div className="stat-label">Influence</div><div><b className="num">{Math.round(i.influence.score)}</b><span className="muted small">/100</span></div><div className="small muted">{i.influence.note}</div></div>
        <div><div className="stat-label">Attention</div><div><b className="num">{i.attention}</b><span className="muted small">/100</span></div><div className="small muted">Where an hour changes an outcome</div></div>
      </div>
      <p className="small"><b>Recommended action:</b> {i.recommended_action}</p>
      {h.assessed ? (
        <>
          <ul className="cp-breakdown-list" aria-label="Health breakdown">
            {h.contributions.map((c) => (
              <li key={c.factor}><span>{c.label}</span><span className="cp-meter" aria-hidden="true"><span style={{ width: `${c.score}%` }} /></span>
                <b className="num">{c.score}</b><span className="muted small">× {Math.round(c.weight * 100)}% = {c.contribution.toFixed(1)}</span>
                <span className="muted small">{c.note}</span></li>))}
          </ul>
          {h.improvement_levers.length > 0 && (
            <p className="small muted">Biggest levers: {h.improvement_levers.map((l) => `${l.factor} (+${l.potential_gain} available: ${l.note})`).join("; ")}.</p>)}
        </>
      ) : <p className="muted small">{h.note}</p>}
      <p className="small muted">Health measures the upkeep of a relationship from recorded engagements and the team&apos;s judgements (recency 24, frequency 16,
        responsiveness 14, meeting outcomes 14, influence 14, opportunity alignment 10, strategic value 8). It is not a probability of winning and never changes the research status.</p>
    </section>
  );
}

/* ----------------------------------------------------------------- stakeholder judgement (recorded by a person, with a basis) */
export function JudgementForm({ id, s, reload }: { id: string; s: Intelligence["stakeholder"]; reload: () => void }) {
  const [f, setF] = useState({ stakeholder_type: s.type, decision_authority: s.decision_authority, posture: s.posture, basis: s.basis ?? "",
                               by_label: s.by ?? "", key_interests: s.key_interests ?? "", strategic_account: s.strategic_account });
  const a = useAction();
  const anything = f.stakeholder_type !== "unknown" || f.decision_authority !== "unknown" || f.posture !== "unknown";
  return (
    <section className="panel" aria-label="Stakeholder judgement">
      <h2>Stakeholder judgement</h2>
      <p className="small muted">Who this person is in the decision, as judged by the team. A title never sets this: record the basis.
        {s.at && <> Last recorded {dateOnly(s.at)}{s.by ? ` by ${s.by}` : ""}.</>}</p>
      <form className="form-grid" onSubmit={async (e: FormEvent) => { e.preventDefault();
        if (await a.run(() => api.post(`/people/${id}/judgement`, { ...f, basis: f.basis || null, by_label: f.by_label || null, key_interests: f.key_interests || null }),
                        "Judgement recorded")) reload(); }}>
        <label className="field">Stakeholder type<select className="select" value={f.stakeholder_type} onChange={(e) => setF({ ...f, stakeholder_type: e.target.value })}>
          {STAKEHOLDER_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Decision authority<select className="select" value={f.decision_authority} onChange={(e) => setF({ ...f, decision_authority: e.target.value })}>
          {DECISION_AUTHORITY.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Posture towards WFC<select className="select" value={f.posture} onChange={(e) => setF({ ...f, posture: e.target.value })}>
          {POSTURES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="field">Judged by<input className="input" value={f.by_label} onChange={(e) => setF({ ...f, by_label: e.target.value })} /></label>
        <label className="field" style={{ gridColumn: "1 / -1" }}>Basis for the judgement<input className="input" value={f.basis} onChange={(e) => setF({ ...f, basis: e.target.value })}
          placeholder="e.g. chairs the tender board according to the RFP; confirmed by the airline's procurement office" /></label>
        <label className="field" style={{ gridColumn: "1 / -1" }}>Key interests<input className="input" value={f.key_interests} onChange={(e) => setF({ ...f, key_interests: e.target.value })} /></label>
        <label className="field inline"><input type="checkbox" checked={f.strategic_account} onChange={(e) => setF({ ...f, strategic_account: e.target.checked })} /> Strategic account for WFC</label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy || (anything && f.basis.trim().length < 10)}>Record judgement</button></div>
        <ActionNote state={a} />
      </form>
    </section>
  );
}

/* ----------------------------------------------------------------- outreach: drafted by ATLAS, sent by a person */
export function OutreachPanel({ id, drafts, opportunities, reload }: { id: string; drafts: Draft[]; opportunities: { id: string; title: string }[]; reload: () => void }) {
  const [f, setF] = useState({ channel: "email", opportunity_id: "", sender_label: "" });
  const a = useAction();
  return (
    <section className="panel" aria-label="Outreach drafts">
      <h2>Outreach drafts</h2>
      <p className="small muted">ATLAS writes a draft from the recorded facts only. A person edits it, sends it from their own account and records that it was sent; nothing is sent by ATLAS.</p>
      <form className="filters" aria-label="Draft outreach" onSubmit={async (e: FormEvent) => { e.preventDefault();
        if (await a.run(() => api.post(`/people/${id}/outreach-drafts`, { ...f, opportunity_id: f.opportunity_id || null, sender_label: f.sender_label || null }), "Draft written")) reload(); }}>
        <label className="field">Channel<select className="select" value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
          <option value="email">Email</option><option value="linkedin_message">LinkedIn message</option><option value="call_notes">Call notes</option></select></label>
        <label className="field">About<select className="select" value={f.opportunity_id} onChange={(e) => setF({ ...f, opportunity_id: e.target.value })}>
          <option value="">General introduction</option>{opportunities.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}</select></label>
        <label className="field">Sender (your name)<input className="input" value={f.sender_label} onChange={(e) => setF({ ...f, sender_label: e.target.value })} /></label>
        <button className="btn btn-primary" type="submit" disabled={a.busy}>Draft outreach</button>
        <ActionNote state={a} />
      </form>
      {drafts.length > 0 && <ul className="list-plain">{drafts.map((d) => <DraftItem key={d.id} d={d} reload={reload} />)}</ul>}
    </section>
  );
}

function DraftItem({ d, reload }: { d: Draft; reload: () => void }) {
  const [body, setBody] = useState(d.body);
  const [subject, setSubject] = useState(d.subject ?? "");
  const [by, setBy] = useState("");
  const [note, setNote] = useState("");
  const a = useAction();
  const editable = d.status === "draft";
  return (
    <li className="draft">
      <div className="small"><Tag text={label(d.channel)} /> <Tag text={d.status === "sent" ? "Sent by a person" : label(d.status)} tone={d.status === "sent" ? "b-good" : d.status === "discarded" ? "b-none" : "b-info"} />
        <span className="muted"> · written {dateTime(d.created_at)} from {d.source === "ai" ? "the recorded facts, reworded by the configured AI (checked to add no fact)" : "the recorded facts (template)"}
          {d.opportunity_title ? ` · about ${d.opportunity_title}` : ""}{d.sent_at ? ` · sent ${dateTime(d.sent_at)} by ${d.sent_by_label}` : ""}</span></div>
      {editable ? (
        <form className="stack" aria-label="Edit draft" onSubmit={async (e: FormEvent) => { e.preventDefault();
          if (await a.run(() => api.post(`/outreach-drafts/${d.id}`, { subject: subject || null, body }), "Draft saved")) reload(); }}>
          {d.channel === "email" && <label className="field">Subject<input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} /></label>}
          <label className="field">Text<textarea className="textarea draft-text" value={body} onChange={(e) => setBody(e.target.value)} /></label>
          <div className="filters">
            <button className="btn" type="submit" disabled={a.busy || body.trim().length < 10}>Save edits</button>
            <label className="field">Sent by<input className="input" value={by} onChange={(e) => setBy(e.target.value)} placeholder="your name" /></label>
            <label className="field">Note<input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="optional" /></label>
            <button className="btn btn-primary" type="button" disabled={a.busy || by.trim().length < 2}
                    onClick={() => a.run(() => api.post(`/outreach-drafts/${d.id}/status`, { status: "sent", by_label: by, note: note || null }), "Recorded as sent; an outbound engagement was added").then(reload)}>
              I sent this</button>
            <button className="btn btn-ghost" type="button" disabled={a.busy}
                    onClick={() => a.run(() => api.post(`/outreach-drafts/${d.id}/status`, { status: "discarded" }), "Draft discarded").then(reload)}>Discard</button>
          </div>
          <ActionNote state={a} />
        </form>
      ) : (
        <details className="small"><summary>Show text</summary>{d.subject && <p><b>{d.subject}</b></p>}<pre className="draft-text">{d.body}</pre></details>
      )}
      <details className="small muted"><summary>Facts it was written from</summary><ul>{d.basis.map((b) => <li key={b}>{b}</li>)}</ul></details>
    </li>
  );
}

/* ----------------------------------------------------------------- compact person line used by the five questions */
export function PersonLine({ p, extra }: { p: { person_id: string; name: string; role: string | null; organisation: string | null; health_score: number | null;
                                                 health_band: string | null; health_band_label: string; at_risk: boolean; stakeholder_label: string }; extra?: string }) {
  return (
    <li>
      <Link href={`/relationships/${p.person_id}`}>{p.name}</Link>
      <span className="muted small"> · {p.role ?? "role not established"}{p.organisation ? ` · ${p.organisation}` : ""} · {p.stakeholder_label}</span>
      <div className="small"><HealthBadge score={p.health_score} band={p.health_band} bandLabel={p.health_band_label} atRisk={p.at_risk} />{extra && <span className="muted"> · {extra}</span>}</div>
    </li>
  );
}
