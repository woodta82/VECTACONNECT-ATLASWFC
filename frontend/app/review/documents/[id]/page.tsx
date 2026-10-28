"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useState, type FormEvent } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner } from "@/components/States";
import { ActionNote, type ClaimField, FieldList, PassageViewer, Provenance, ReasonAction, Section } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Doc = {
  document: { id: string; title: string | null; canonical_url: string; source_name: string | null; authority: string | null; language: string | null;
              published_at: string | null; retrieved_at: string; published_at_source?: string | null; publication_flag?: string | null;
              publication_note?: string | null; extraction_status: string; extraction_detail: string | null; summary_en: string | null;
              summary_is_translation: boolean; text: string; text_is_excerpt: boolean; content_hash?: string | null;
              read_progress: { total: number; done: number[] } | null; status_contradiction: string | null; geography_conflict?: string | null };
  checks: { check_type: string; result: string; detail: string | null }[];
  claims: { claim_id: string; claim_type: string; status: string; review_status: string; review_note: string | null; stance: string; quote: string;
            assessed_by: string; assessed_at?: string | null; location?: string | null; excluded_at: string | null; fields: ClaimField[] | null; signals: { signal_id: string; title: string; classification: string }[] | null }[];
  rejections: { id: string; reason: string; status: string; raw: unknown; created_at: string }[];
};

const CLAIM_TYPES = ["gssa_tender", "service_tender", "tender_deadline", "tender_status", "tender_scope", "eligibility", "route_launch",
                     "route_suspension", "representation_change", "tcm_signal", "capacity_statement", "partnership"];
const FIELDS = ["airline", "organisation", "country", "contract_territory", "issuer_country", "origin", "destination", "tender_ref",
                "procurement_cycle", "status", "deadline", "eligibility", "published_value", "service"];
const HINT: Record<string, string> = {
  deadline: "ISO date-time, e.g. 2026-11-30T17:00", status: "open, revised, cancelled, awarded or closed", country: "Country name or ISO code",
  service: "GSSA, TCM, HANDLING, TRUCKING, DATA_PROCESSING, TRAINING, TECHNOLOGY …", origin: "Airport IATA code or country", destination: "Airport IATA code or country",
};

const PUBLICATION_SOURCE: Record<string, string> = { document_text: "stated in the notice", page: "page metadata", pdf_metadata: "PDF metadata", feed: "feed item" };

export default function DocumentReview() {
  const { id = "" } = useParams<{ id: string }>();
  const r = useApi<Doc>(id ? `/documents/${id}` : null);
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="document" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body d={r.data} reload={r.reload} />}
    </>
  );
}

type ExtractResult = { status: string; detail: string | null; budget_scope?: string | null };

function Body({ d, reload }: { d: Doc; reload: () => void }) {
  const doc = d.document;
  const a = useAction();
  const [runCapped, setRunCapped] = useState(false);
  const [approve, setApprove] = useState("0.50");
  return (
    <div className="stack">
      {doc.publication_flag && (
        <div className="notice" role="status" data-testid="publication-flag"><strong>{doc.publication_flag === "future" ? "Publication date in the future." : "Publication dates disagree."}</strong> {doc.publication_note ?? ""} The date is not used to judge how current the notice is; retrieval time is never used as a publication date.</div>
      )}
      <PageHeader eyebrow={`Review · ${doc.source_name ?? "source"}`} title={doc.title ?? doc.canonical_url}
                  description={`${doc.canonical_url} · retrieved ${dateTime(doc.retrieved_at)}${doc.published_at ? ` · published ${dateTime(doc.published_at)}${doc.published_at_source ? ` (${PUBLICATION_SOURCE[doc.published_at_source] ?? doc.published_at_source})` : ""}` : " · publication date unknown"}`}
                  actions={<><Link className="btn" href="/review">Back to queue</Link>
                    {["not_connected", "budget_refused", "failed", "pending", "incomplete"].includes(doc.extraction_status) && (
                      <button className="btn" type="button" disabled={a.busy}
                              onClick={() => a.run(() => api.post<ExtractResult>(`/documents/${doc.id}/extract`),
                                                   (x) => { setRunCapped(x.budget_scope === "run"); return `Extraction: ${x.status}${x.detail ? ` (${x.detail})` : ""}`; }).then(reload)}>
                        {doc.extraction_status === "incomplete" ? "Continue reading" : "Run AI extraction"}
                      </button>
                    )}</>} />
      <ActionNote state={a} />
      {runCapped && (
        <form className="notice" onSubmit={async (e) => { e.preventDefault();
          const ok = await a.run(() => api.post<ExtractResult>(`/documents/${doc.id}/extract`, { approve_additional_usd: approve }),
                                 (x) => `Extraction: ${x.status}${x.detail ? ` (${x.detail})` : ""}`);
          if (ok) { setRunCapped(false); reload(); } }}>
          <strong>The discovery run that found this document has reached its approved AI ceiling.</strong>{" "}
          Extracting it needs an explicit approval, which raises that run&apos;s ceiling by the amount below and is recorded in the audit log.
          <div className="inline" style={{ marginTop: 8 }}>
            <label className="field">Approve additional (USD)
              <input className="input" inputMode="decimal" value={approve} onChange={(e) => setApprove(e.target.value)} style={{ maxWidth: 120 }} />
            </label>
            <button className="btn" type="submit" disabled={a.busy || !(Number(approve) > 0 && Number(approve) <= 100)}>Approve and extract</button>
          </div>
        </form>
      )}
      <div className="grid grid-2">
        <Section title="Document checks (kept separate)">
          <dl className="kv">
            {d.checks.map((c) => (
              <Fragment key={c.check_type}><dt>{label(c.check_type)}</dt><dd><Badge value={c.result} /> <span className="muted small">{c.detail}</span></dd></Fragment>
            ))}
            <dt>Extraction</dt><dd><Badge value={doc.extraction_status} /> <span className="muted small">{doc.extraction_detail}</span></dd>
            <dt>Read</dt><dd>{doc.read_progress
              ? (doc.read_progress.done.length >= doc.read_progress.total
                  ? `Completely read (${doc.read_progress.total} section${doc.read_progress.total === 1 ? "" : "s"})`
                  : `Partly read: ${doc.read_progress.done.length} of ${doc.read_progress.total} sections. Not checked in full; "Continue reading" resumes at the first unread section.`)
              : "Not read yet"}</dd>
            {doc.status_contradiction && <><dt>Contradiction</dt><dd><Badge value="contradictory" /> {doc.status_contradiction}</dd></>}
            {doc.geography_conflict && <><dt>Geography conflict</dt><dd data-testid="geography-conflict"><Badge value="review_required" /> {doc.geography_conflict}</dd></>}
            <dt>Source authority</dt><dd>{doc.authority?.replace("_", " ") ?? "unknown"}</dd>
            <dt>Language</dt><dd>{doc.language ?? "unknown"}</dd>
          </dl>
          <p className="muted small">Reachability does not establish authenticity; authenticity does not establish that a claim is supported; a supported claim does not establish that a tender is still open.</p>
        </Section>
        <Section title="Document text">
          {doc.summary_en && (
            <p className="notice notice-info">{doc.summary_is_translation ? "English summary (machine translation; the original text below is the evidence): " : "Summary: "}{doc.summary_en}</p>
          )}
          {doc.text_is_excerpt && <p className="muted small">Only an excerpt is stored: the source does not permit retaining full text.</p>}
          <div className="doc-text" tabIndex={0} aria-label="Document text">{doc.text}</div>
        </Section>
      </div>

      <Section title={`Claims (${d.claims.length})`}>
        {d.claims.length === 0 ? <Empty title="No claims yet">Add claims from the text below the document.</Empty> : d.claims.map((c) => (
          <article key={c.claim_id} className="claim-card">
            <div className="inline">
              <strong>{label(c.claim_type)}</strong> <Badge value={c.status} /> <Badge value={c.review_status} />
              <span className="muted small">{c.stance} · {c.assessed_by.replace("_", " ")}{c.excluded_at ? " · excluded" : ""}</span>
            </div>
            <p className="small"><span className="muted">Source wording: </span><q>{c.quote}</q></p>
            <Provenance e={{ document_id: doc.id, canonical_url: doc.canonical_url, retrieved_at: doc.retrieved_at, published_at: doc.published_at,
                             document_version: doc.content_hash, location: c.location, assessed_by: c.assessed_by, assessed_at: c.assessed_at,
                             text_retained: !doc.text_is_excerpt, quote: c.quote, review_status: c.review_status, review_note: c.review_note }} dateTime={dateTime} />
            <PassageViewer documentId={doc.id} quote={c.quote} location={c.location} get={(path) => api.get(path)} />
            <FieldList fields={c.fields} />
            {c.signals && c.signals.length > 0 && <p className="muted small">Signal: {c.signals.map((s) => s.title).join("; ")}</p>}
            {c.review_note && <p className="muted small">Review note: {c.review_note}</p>}
            {!["rejected", "corrected"].includes(c.review_status) && (
              <div className="actions" style={{ marginTop: 8 }}>
                {c.review_status === "proposed" && (
                  <button className="btn btn-primary" type="button" disabled={a.busy}
                          onClick={() => a.run(() => api.post(`/claims/${c.claim_id}/confirm`, { note: "checked against the document" }), "Confirmed").then(reload)}>
                    Confirm
                  </button>
                )}
                <ReasonAction label="Reject" tone="danger" busy={a.busy}
                              onSubmit={(note) => a.run(() => api.post(`/claims/${c.claim_id}/reject`, { note }), "Rejected").then(reload)} />
                <CorrectForm claim={c} docId={doc.id} onDone={reload} />
              </div>
            )}
          </article>
        ))}
      </Section>

      {d.rejections.length > 0 && (
        <Section title="Rejected extraction output">
          <ul className="small">{d.rejections.map((x) => <li key={x.id}><Badge value={x.status} /> {x.reason}</li>)}</ul>
        </Section>
      )}
      <AddClaim docId={doc.id} onDone={reload} />
    </div>
  );
}

function FieldEditor({ fields, setFields }: { fields: Record<string, { value: string; quote: string }>; setFields: (f: Record<string, { value: string; quote: string }>) => void }) {
  const [add, setAdd] = useState("");
  return (
    <div className="stack">
      {Object.entries(fields).map(([k, v]) => (
        <div key={k} className="form-grid">
          <label className="field">{label(k)} value<input className="input" value={v.value} placeholder={HINT[k] ?? ""}
                                                           onChange={(e) => setFields({ ...fields, [k]: { ...v, value: e.target.value } })} /></label>
          <label className="field" style={{ gridColumn: "span 2" }}>Quote stating it (verbatim from the document)
            <input className="input" value={v.quote} onChange={(e) => setFields({ ...fields, [k]: { ...v, quote: e.target.value } })} /></label>
          <button type="button" className="btn btn-ghost" onClick={() => { const n = { ...fields }; delete n[k]; setFields(n); }}>Remove</button>
        </div>
      ))}
      <div className="inline">
        <select className="select" aria-label="Add field" value={add} onChange={(e) => setAdd(e.target.value)} style={{ width: "auto" }}>
          <option value="">Add a field…</option>
          {FIELDS.filter((f) => !(f in fields)).map((f) => <option key={f} value={f}>{label(f)}</option>)}
        </select>
        <button type="button" className="btn" disabled={!add} onClick={() => { setFields({ ...fields, [add]: { value: "", quote: "" } }); setAdd(""); }}>Add field</button>
      </div>
    </div>
  );
}

function AddClaim({ docId, onDone }: { docId: string; onDone: () => void }) {
  const [type, setType] = useState("gssa_tender");
  const [quote, setQuote] = useState("");
  const [tz, setTz] = useState("");
  const [fields, setFields] = useState<Record<string, { value: string; quote: string }>>({});
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await a.run(() => api.post<{ claim_ids: string[]; rejected: string[] }>(`/documents/${docId}/claims`,
      { claim_type: type, quote, deadline_timezone: tz || null, fields }),
      (x) => x.claim_ids.length ? "Claim added; each field was validated against the text (see its verdict above)." : `Not added: ${x.rejected.join("; ")}`);
    if (r && r.claim_ids.length) { setQuote(""); setFields({}); }
    onDone();
  }
  return (
    <Section title="Add a claim from this document">
      <form onSubmit={submit} className="stack">
        <div className="form-grid">
          <label className="field">Claim type
            <select className="select" value={type} onChange={(e) => setType(e.target.value)}>{CLAIM_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}</select>
          </label>
          <label className="field">Deadline time zone (if the deadline is local)<input className="input" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="e.g. Africa/Nairobi" /></label>
          <label className="field wide">Quote that states the claim (copied verbatim)
            <textarea className="textarea" value={quote} onChange={(e) => setQuote(e.target.value)} required minLength={8} /></label>
        </div>
        <FieldEditor fields={fields} setFields={setFields} />
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={a.busy || quote.trim().length < 8}>Add claim</button></div>
        <ActionNote state={a} />
      </form>
    </Section>
  );
}

function CorrectForm({ claim, docId, onDone }: { claim: Doc["claims"][number]; docId: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState<Record<string, { value: string; quote: string }>>(
    Object.fromEntries((claim.fields ?? []).filter((f) => f.field !== "opportunity_type").map((f) => [f.field, { value: f.value, quote: f.quote ?? "" }])));
  const [note, setNote] = useState("");
  const a = useAction();
  if (!open) return <button type="button" className="btn" onClick={() => setOpen(true)}>Correct</button>;
  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await a.run(() => api.post(`/claims/${claim.claim_id}/correct`, { document_id: docId, fields, note }), "Corrected: the original is kept and excluded");
    if (r) { setOpen(false); onDone(); }
  }
  return (
    <form onSubmit={submit} className="stack" style={{ width: "100%" }}>
      <FieldEditor fields={fields} setFields={setFields} />
      <label className="field">Reason for the correction<input className="input" value={note} onChange={(e) => setNote(e.target.value)} minLength={5} required /></label>
      <div className="actions">
        <button className="btn btn-primary" type="submit" disabled={a.busy || note.trim().length < 5}>Save correction</button>
        <button className="btn btn-ghost" type="button" onClick={() => setOpen(false)}>Cancel</button>
      </div>
      <ActionNote state={a} />
    </form>
  );
}
