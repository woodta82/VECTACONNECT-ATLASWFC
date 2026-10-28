"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, ReasonAction, Tabs } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Queue = {
  documents: { id: string; title: string | null; canonical_url: string; retrieved_at: string; language: string | null; extraction_status: string;
               extraction_detail: string | null; source_name: string | null; authority: string | null }[];
  claims: { claim_id: string; claim_type: string; status: string; subject_label: string | null; tender_ref: string | null; document_id: string;
            quote: string | null; unsupported_fields: number; review_fields?: number; signal_title: string | null; created_at: string }[];
  rejections: { id: string; document_id: string; reason: string; created_at: string; title: string | null; canonical_url: string }[];
  merges: { id: string; entity_type: string; left_label: string | null; right_label: string | null; reason: string; score: string | null }[];
  conflicts: { claim_id: string; field: string; values: string[]; signal_title: string | null }[];
  fields: { field_id: string; field: string; value: string; support: string; reason: string; quote: string | null; assessed_by: string; validation_version: number;
            claim_id: string; claim_type: string; review_status: string; subject_label: string | null; tender_ref: string | null; location: string | null;
            document_id: string; document_title: string | null; canonical_url: string; retrieved_at: string; document_version: string | null;
            signal_title: string | null; opportunity_id: string | null }[];
};
type Tab = "fields" | "claims" | "documents" | "rejections" | "merges" | "conflicts";

export default function ReviewPage() {
  const r = useApi<Queue>("/review");
  const [tab, setTab] = useState<Tab>("fields");
  const a = useAction();
  const q = r.data;
  return (
    <>
      <PageHeader eyebrow="Review" title="Evidence review queue"
                  description="AI output is a proposal. Confirm, correct or reject claims; add claims to documents the extractor could not process; decide look-alike tenders. Every field you enter is checked against the document text the same way." />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="review queue" />}
      {r.status === "error" && !q && <ErrorState error={r.error} onRetry={r.reload} />}
      {q && (
        <section className="panel">
          <Tabs label="Review queue" value={tab} onChange={setTab} tabs={[
            { id: "fields", label: "Unresolved fields", count: (q.fields ?? []).length },
            { id: "claims", label: "Claims to confirm", count: q.claims.length },
            { id: "documents", label: "Documents to extract", count: q.documents.length },
            { id: "rejections", label: "Rejected output", count: q.rejections.length },
            { id: "merges", label: "Possible duplicates", count: q.merges.length },
            { id: "conflicts", label: "Conflicting fields", count: q.conflicts.length },
          ]} />
          <ActionNote state={a} />
          {tab === "fields" && ((q.fields ?? []).length === 0 ? <Empty title="No unresolved material fields">Every status, deadline, eligibility, geography, reference, service and freight-scope field on a live claim is supported by its quote.</Empty> : (
            <>
              <p className="muted small">Each material field the rules could not establish from its own quote, with the reason and the source passage. It stays here, and out of summaries, scores and exports, until a reviewer confirms, corrects or rejects the claim on the document page.</p>
              <TableWrap label="Unresolved fields">
                <table>
                  <thead><tr><th>Field</th><th>Extracted value</th><th>Verdict and reason</th><th>Source passage</th><th>Where</th><th /></tr></thead>
                  <tbody>{(q.fields ?? []).map((f) => (
                    <tr key={f.field_id}>
                      <td>{label(f.field)}<span className="muted small">{label(f.claim_type)}{f.tender_ref ? ` · ${f.tender_ref}` : ""}{f.subject_label ? ` · ${f.subject_label}` : ""}</span></td>
                      <td className="small">{f.value}</td>
                      <td><Badge value={f.support} /><span className="muted small">{f.reason} · rules v{f.validation_version} · {f.assessed_by === "human" ? "entered by a reviewer" : f.assessed_by === "rule" ? "rule check" : "extracted by AI"}</span></td>
                      <td className="small">{f.quote ? <q>{f.quote}</q> : <span className="muted">no quote</span>}<span className="muted small">{f.location ?? "location not recorded"}{f.document_version ? ` · version ${f.document_version.slice(0, 12)}` : ""} · retrieved {dateTime(f.retrieved_at)}</span></td>
                      <td className="small">{f.signal_title ?? "—"}{f.opportunity_id ? <> · <Link href={`/opportunities/${f.opportunity_id}`}>opportunity</Link></> : null}</td>
                      <td className="actions"><Link className="btn" href={`/review/documents/${f.document_id}`}>Open document</Link></td>
                    </tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            </>
          ))}
          {tab === "claims" && (q.claims.length === 0 ? <Empty title="No AI-proposed claims waiting" /> : (
            <TableWrap label="Claims to confirm">
              <table>
                <thead><tr><th>Claim</th><th>Quote</th><th>Fields</th><th>Signal</th><th /></tr></thead>
                <tbody>{q.claims.map((c) => (
                  <tr key={c.claim_id}>
                    <td>{label(c.claim_type)}<span className="muted small">{c.subject_label ?? "subject not established"}{c.tender_ref ? ` · ${c.tender_ref}` : ""}</span>
                      <Badge value={c.status} /></td>
                    <td className="small"><q>{c.quote}</q></td>
                    <td>{c.unsupported_fields > 0 ? <Badge value="unsupported" /> : (c.review_fields ?? 0) > 0 ? <Badge value="review_required" /> : <Badge value="supported" />}
                      <span className="muted small">{c.unsupported_fields} unsupported · {c.review_fields ?? 0} need review</span></td>
                    <td className="small">{c.signal_title ?? "—"}</td>
                    <td className="actions">
                      <Link className="btn" href={`/review/documents/${c.document_id}`}>Open</Link>
                      <button className="btn btn-primary" type="button" disabled={a.busy}
                              onClick={() => a.run(() => api.post(`/claims/${c.claim_id}/confirm`, { note: "" }), "Claim confirmed").then(r.reload)}>Confirm</button>
                      <ReasonAction label="Reject" tone="danger" busy={a.busy}
                                    onSubmit={(note) => a.run(() => api.post(`/claims/${c.claim_id}/reject`, { note }), "Claim rejected").then(r.reload)} />
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
          {tab === "documents" && (q.documents.length === 0 ? <Empty title="No documents waiting for extraction" /> : (
            <TableWrap label="Documents to extract">
              <table>
                <thead><tr><th>Document</th><th>Source</th><th>Retrieved</th><th>Extraction</th><th /></tr></thead>
                <tbody>{q.documents.map((d) => (
                  <tr key={d.id}>
                    <td>{d.title ?? d.canonical_url}<span className="muted small">{d.canonical_url}{d.language ? ` · ${d.language}` : ""}</span></td>
                    <td>{d.source_name}<span className="muted small">{d.authority?.replace("_", " ")}</span></td>
                    <td>{dateTime(d.retrieved_at)}</td>
                    <td><Badge value={d.extraction_status} /><span className="muted small">{d.extraction_detail}</span></td>
                    <td><Link className="btn" href={`/review/documents/${d.id}`}>Review</Link></td>
                  </tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
          {tab === "rejections" && (q.rejections.length === 0 ? <Empty title="No rejected extraction output" /> : (
            <TableWrap label="Rejected extraction output">
              <table>
                <thead><tr><th>Reason</th><th>Document</th><th>When</th><th /></tr></thead>
                <tbody>{q.rejections.map((x) => (
                  <tr key={x.id}>
                    <td>{x.reason}</td>
                    <td><Link href={`/review/documents/${x.document_id}`}>{x.title ?? x.canonical_url}</Link></td>
                    <td>{dateTime(x.created_at)}</td>
                    <td className="actions">
                      <ReasonAction label="Dismiss" busy={a.busy} minLength={3}
                                    onSubmit={(note) => a.run(() => api.post(`/rejections/${x.id}/resolve`, { status: "dismissed", note }), "Dismissed").then(r.reload)} />
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
          {tab === "merges" && (q.merges.length === 0 ? <Empty title="No possible duplicates" /> : (
            <TableWrap label="Possible duplicates">
              <table>
                <thead><tr><th>Record A</th><th>Record B</th><th>Why flagged</th><th>Decision</th></tr></thead>
                <tbody>{q.merges.map((m) => (
                  <tr key={m.id}>
                    <td>{m.left_label}<span className="muted small">{m.entity_type}</span></td><td>{m.right_label}</td>
                    <td className="small">{m.reason}{m.score && ` (similarity ${m.score})`}</td>
                    <td className="actions">
                      <ReasonAction label="Same: merge" busy={a.busy} tone="primary"
                                    onSubmit={(note) => a.run(() => api.post(`/merge-candidates/${m.id}/decide`, { decision: "merged", note }), "Merged").then(r.reload)} />
                      <ReasonAction label="Different: keep separate" busy={a.busy}
                                    onSubmit={(note) => a.run(() => api.post(`/merge-candidates/${m.id}/decide`, { decision: "kept_separate", note }), "Kept separate").then(r.reload)} />
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
          {tab === "conflicts" && (q.conflicts.length === 0 ? <Empty title="No conflicting fields" /> : (
            <TableWrap label="Conflicting fields">
              <table>
                <thead><tr><th>Signal</th><th>Field</th><th>Values stated by different documents</th></tr></thead>
                <tbody>{q.conflicts.map((c) => (
                  <tr key={`${c.claim_id}-${c.field}`}><td>{c.signal_title}</td><td>{label(c.field)}</td><td>{c.values.join(" | ")}</td></tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
        </section>
      )}
    </>
  );
}
