"use client";

import Link from "next/link";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import type { ActionState } from "@/lib/useAction";
import { Badge } from "./States";

/** Visible outcome of an action: error (with reference) or confirmation. */
export function ActionNote({ state }: { state: ActionState }) {
  if (state.error) return <p role="alert" className="action-error">{state.error}</p>;
  if (state.ok) return <p role="status" className="action-ok">{state.ok}</p>;
  return null;
}

export function Tabs<T extends string>({ tabs, value, onChange, label }: {
  tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (t: T) => void; label: string;
}) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.id} type="button" role="tab" aria-selected={t.id === value} className="tab" onClick={() => onChange(t.id)}>
          {t.label}{t.count !== undefined && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** An action that needs a written reason, entered inline (no browser dialogs). */
export function ReasonAction({ label, placeholder, minLength = 5, onSubmit, busy, tone }: {
  label: string; placeholder?: string; minLength?: number; busy?: boolean; tone?: "danger" | "primary";
  onSubmit: (reason: string) => Promise<unknown> | void;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const id = useId();
  async function submit(e: FormEvent) {
    e.preventDefault();
    await onSubmit(reason.trim());
    setReason("");
    setOpen(false);
  }
  const cls = `btn ${tone === "danger" ? "btn-danger" : tone === "primary" ? "btn-primary" : ""}`;
  if (!open) return <button type="button" className={cls} onClick={() => setOpen(true)} disabled={busy}>{label}</button>;
  return (
    <form onSubmit={submit} className="reason-form">
      <label htmlFor={id} className="sr-only">{label}: reason</label>
      <input id={id} className="input" autoFocus value={reason} onChange={(e) => setReason(e.target.value)}
             placeholder={placeholder ?? "Reason (recorded in the history)"} minLength={minLength} required />
      <button type="submit" className={cls} disabled={busy || reason.trim().length < minLength}>{label}</button>
      <button type="button" className="btn btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
    </form>
  );
}

export type ClaimField = { field: string; value: string; normalised: string; quote: string | null; support: string; reason: string;
                           assessed_by: string; validation_version?: number | null; rechecked?: boolean | null; previous_support?: string | null };

const ASSESSED: Record<string, string> = { ai_proposed: "extracted by AI (proposal)", rule: "rule check", human: "reviewer" };

/** Per-field validation: each material field with its own quote and verdict. Three kinds of wording are kept apart:
 *  the EXTRACTED value (what the extractor or reviewer wrote), the SOURCE wording (the quote, verbatim from the document)
 *  and, when a reviewer corrected the reading, that is a separate claim marked "reviewer". A verdict is a rule result, not
 *  a confidence score: "supported" means the quote states the value; it does not mean the fact has been verified. */
export function FieldList({ fields }: { fields: ClaimField[] | null | undefined }) {
  if (!fields || fields.length === 0) return <span className="muted small">No structured fields</span>;
  return (
    <ul className="field-list">
      {fields.map((f, i) => (
        <li key={`${f.field}-${i}`}>
          <span className="field-name">{f.field.replace(/_/g, " ")}</span>
          <span className="field-value"><span className="muted small">extracted: </span>{f.value}</span>
          <Badge value={f.support} />
          <span className="muted small field-reason">{f.reason}
            {f.validation_version ? ` · rules v${f.validation_version}` : ""}
            {f.rechecked ? ` · re-checked (was ${f.previous_support ?? "unknown"})` : ""}
            {f.assessed_by ? ` · ${ASSESSED[f.assessed_by] ?? f.assessed_by}` : ""}</span>
          {f.quote && <q className="field-quote"><span className="muted small">source: </span>{f.quote}</q>}
        </li>
      ))}
    </ul>
  );
}

export type EvidenceProvenance = { document_id: string; canonical_url: string; original_url?: string | null; retrieved_at: string; published_at?: string | null;
                                   document_version?: string | null; location?: string | null; assessed_by: string; assessed_at?: string | null;
                                   text_retained?: boolean | null; quote: string; review_status?: string | null; review_note?: string | null };

/** Where a piece of evidence comes from: source URL, retrieval date, document version (content hash) and position. */
export function Provenance({ e, dateTime }: { e: EvidenceProvenance; dateTime: (s: string) => string }) {
  return (
    <dl className="provenance small">
      <dt>Source</dt><dd><a href={e.canonical_url} target="_blank" rel="noreferrer noopener">{e.canonical_url}</a></dd>
      <dt>Retrieved</dt><dd>{dateTime(e.retrieved_at)}{e.text_retained === false ? " · full text not retained (excerpt only)" : ""}</dd>
      {e.document_version && <><dt>Document version</dt><dd><code>{e.document_version.slice(0, 16)}</code> (content hash)</dd></>}
      <dt>Location</dt><dd>{e.location ?? "not recorded"}</dd>
      <dt>Wording</dt><dd>{e.assessed_by === "human" ? "entered by a reviewer" : e.assessed_by === "ai_proposed" ? "extracted by AI; quote copied verbatim from the source" : "rule-derived"}
        {e.assessed_at ? ` · ${dateTime(e.assessed_at)}` : ""}</dd>
      {e.review_status === "corrected" && <><dt>Reviewer</dt><dd>corrected: {e.review_note ?? "see the replacement claim"}</dd></>}
      {e.review_status === "confirmed" && <><dt>Reviewer</dt><dd>confirmed{e.review_note ? `: ${e.review_note}` : ""}</dd></>}
    </dl>
  );
}

type Passage = { found: boolean; how?: string; text_retained: boolean; document_version: string | null; start?: number; end?: number; page?: number | null;
                 before?: string; passage?: string; after?: string; detail?: string };

/** "Open passage": the quote shown in the document's own text with context, located by its recorded position. */
export function PassageViewer({ documentId, quote, location, get }: { documentId: string; quote: string; location: string | null | undefined;
                                                                       get: (path: string) => Promise<Passage> }) {
  const [p, setP] = useState<Passage | null>(null);
  const [open, setOpen] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function load() {
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (p) return;
    try {
      const q = new URLSearchParams({ quote });
      if (location) q.set("location", location);
      setP(await get(`/documents/${documentId}/passage?${q.toString()}`));
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (
    <div className="passage-wrap">
      <button type="button" className="link-button small" onClick={load} aria-expanded={open}>{open ? "Hide passage" : "Open passage"}</button>
      {open && err && <p className="small error">{err}</p>}
      {open && !p && !err && <p className="small muted">Loading passage…</p>}
      {open && p && !p.found && <p className="small muted">{p.detail}</p>}
      {open && p && p.found && (
        <blockquote className="passage" aria-label="Evidence passage">
          <p className="small muted">{p.how}{p.page ? ` · page ${p.page}` : ""} · chars {p.start}-{p.end}{p.document_version ? ` · version ${p.document_version.slice(0, 12)}` : ""}</p>
          <p><span className="muted">{p.before}</span><mark>{p.passage}</mark><span className="muted">{p.after}</span></p>
        </blockquote>
      )}
    </div>
  );
}

export function Chips({ items, onRemove, label }: { items: string[]; onRemove?: (v: string) => void; label: string }) {
  if (items.length === 0) return null;
  return (
    <ul className="chips" aria-label={label}>
      {items.map((c) => (
        <li key={c} className="chip">
          {c}
          {onRemove && <button type="button" aria-label={`Remove ${c}`} onClick={() => onRemove(c)}>×</button>}
        </li>
      ))}
    </ul>
  );
}

export function Section({ title, children, actions, id }: { title: string; children: ReactNode; actions?: ReactNode; id?: string }) {
  return (
    <section className="panel" id={id} aria-labelledby={id ? `${id}-h` : undefined}>
      <div className="panel-head">
        <h2 id={id ? `${id}-h` : undefined}>{title}</h2>
        {actions && <div className="actions">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** "Not connected" / "insufficient data" panel for a capability area. */
export function AreaStatus({ status, gaps }: { status: string; gaps: string[] }) {
  if (status === "ok") {
    return gaps.length ? <div className="notice" role="status">{gaps.join(" · ")}</div> : null;
  }
  return (
    <div className="state" role="status">
      <strong>{status === "not_connected" ? "Not connected" : "Insufficient data"}</strong>
      {gaps.map((g) => <div key={g}>{g}</div>)}
      <div className="small" style={{ marginTop: 8 }}>This is not zero performance: the required data has not been loaded.</div>
    </div>
  );
}

export type DataSource = { dataset: string; status: string; last_success_at: string | null; source_of_truth?: string; refresh?: string };

/** The datasets behind an area: status, last import, source of truth and refresh requirement. */
export function SourcesLine({ sources, dateTime }: { sources: DataSource[] | undefined; dateTime: (s: string) => string }) {
  if (!sources?.length) return null;
  return (
    <details className="small">
      <summary>Data used: {sources.map((s) => `${s.dataset.replaceAll("_", " ")} (${s.status === "not_connected" ? "Not connected" : s.status})`).join(" · ")}</summary>
      <ul>{sources.map((s) => (
        <li key={s.dataset}><b>{s.dataset.replaceAll("_", " ")}</b>: {s.status === "not_connected" ? "Not connected" : s.status}
          {s.last_success_at ? `, last imported ${dateTime(s.last_success_at)}` : ""}{s.source_of_truth ? `; source: ${s.source_of_truth}` : ""}
          {s.refresh ? `; ${s.refresh}` : ""}</li>
      ))}</ul>
    </details>
  );
}

export type Recommendation = {
  key: string; kind: string; action: string | null; why: string; missing?: string[]; provisional?: boolean; strength?: string;
  rank?: number | null; rank_reason?: string; inputs?: Record<string, unknown>; evidence?: Record<string, unknown>;
  thresholds?: Record<string, string>; existing?: string | null;
};

/** One recommendation: what to do, why, what is missing and the inputs and thresholds behind it. */
export function RecommendationCard({ r, title, onCreate, busy }: { r: Recommendation; title: string; onCreate?: () => void; busy?: boolean }) {
  const figures = { ...(r.inputs ?? {}), ...(r.evidence ?? {}) };
  return (
    <article className="panel" aria-label={title}>
      <h3>{r.rank ? `${r.rank}. ` : ""}{title} <span className={`badge ${r.action ? "b-good" : "b-none"}`}>{r.kind.replaceAll("_", " ")}</span>
        {r.strength && <span className="badge b-info">{r.strength}</span>}
        {r.provisional && <span className="badge b-warn" title="Thresholds are provisional until WFC confirms them">provisional thresholds</span>}</h3>
      <p><b>{r.action ?? "No recommendation"}</b></p>
      <p className="small"><b>Why:</b> {r.why}</p>
      {r.rank_reason && <p className="small"><b>Rank:</b> {r.rank_reason}</p>}
      {r.missing && r.missing.length > 0 && <p className="small"><b>Missing:</b> {r.missing.join("; ")}</p>}
      <details className="small"><summary>Inputs and thresholds</summary>
        <ul>{Object.entries(figures).filter(([, v]) => v !== null && v !== undefined && typeof v !== "object").map(([k, v]) => (
          <li key={k}>{k.replaceAll("_", " ")}: {String(v)}</li>))}</ul>
        {r.thresholds && <p>Thresholds: {Object.entries(r.thresholds).map(([k, v]) => `${k.replaceAll("_", " ")} ${v}`).join(" · ")}</p>}
      </details>
      {r.existing ? <Link href={`/opportunities/${r.existing}`}>Open the opportunity</Link>
        : r.action && onCreate && <button className="btn" type="button" disabled={busy} onClick={onCreate}>Create opportunity for review</button>}
    </article>
  );
}
