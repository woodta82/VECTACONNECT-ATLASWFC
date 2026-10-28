"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, Section } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";
import { SourceForm, type SourceRow } from "@/components/SourceForm";

type Detail = {
  source: SourceRow & { deleted_at: string | null };
  runs: { id: string; status: string; started_at: string; finished_at: string | null; stats: Record<string, unknown>; error: string | null;
          discovery_run_id: string | null; documents: number }[];
  documents: { id: string; title: string | null; canonical_url: string; published_at: string | null; retrieved_at: string; language: string | null;
               extraction_status: string; extraction_detail: string | null; claims: number; open_rejections: number }[];
  schedule: { id: string } | null;
};

export default function SourceDetail() {
  const { id = "" } = useParams<{ id: string }>();
  const r = useApi<Detail>(id ? `/sources/${id}` : null);
  const a = useAction();
  const router = useRouter();
  const [edit, setEdit] = useState(false);
  const d = r.data;
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="source" />}
      {r.status === "error" && !d && <ErrorState error={r.error} onRetry={r.reload} />}
      {d && (
        <div className="stack">
          <PageHeader eyebrow="Source" title={d.source.name} description={`${d.source.base_url} · ${d.source.authority.replace("_", " ")} · ${d.source.enabled ? "enabled" : "disabled"}`}
                      actions={<>
                        <Link className="btn" href="/sources">All sources</Link>
                        <button className="btn" type="button" onClick={() => setEdit(!edit)}>{edit ? "Close editor" : "Edit"}</button>
                        <button className="btn" type="button" disabled={a.busy || !d.source.enabled}
                                onClick={async () => { const x = await a.run(() => api.post<{ run_id: string }>(`/sources/${d.source.id}/run`)); if (x) router.push(`/discovery/runs/${x.run_id}`); }}>
                          Run now
                        </button>
                        <button className="btn btn-danger" type="button" disabled={a.busy}
                                onClick={async () => { const x = await a.run(() => api.del(`/sources/${d.source.id}`), "Source retired"); if (x) router.push("/sources"); }}>
                          Retire
                        </button>
                      </>} />
          <ActionNote state={a} />
          {edit && <SourceForm initial={d.source} onDone={() => { setEdit(false); r.reload(); }} onCancel={() => setEdit(false)} />}
          <Section title="Run history">
            {d.runs.length === 0 ? <Empty title="Never run" /> : (
              <TableWrap label="Run history">
                <table>
                  <thead><tr><th>Started</th><th>Status</th><th className="num">Documents</th><th>Detail</th></tr></thead>
                  <tbody>{d.runs.map((x) => (
                    <tr key={x.id}>
                      <td>{x.discovery_run_id ? <Link href={`/discovery/runs/${x.discovery_run_id}`}>{dateTime(x.started_at)}</Link> : dateTime(x.started_at)}</td>
                      <td><Badge value={x.status} /></td><td className="num">{x.documents}</td><td className="small">{x.error ?? ""}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            )}
          </Section>
          <Section title="Documents retrieved">
            {d.documents.length === 0 ? <Empty title="No documents yet" /> : (
              <TableWrap label="Documents">
                <table>
                  <thead><tr><th>Document</th><th>Published</th><th>Extraction</th><th className="num">Claims</th><th /></tr></thead>
                  <tbody>{d.documents.map((x) => (
                    <tr key={x.id}>
                      <td>{x.title ?? x.canonical_url}<span className="muted small">{x.canonical_url}{x.language ? ` · ${x.language}` : ""}</span></td>
                      <td>{x.published_at ? dateTime(x.published_at) : "Unknown"}</td>
                      <td><Badge value={x.extraction_status} />{x.open_rejections > 0 && <span className="muted small">{x.open_rejections} rejected to review</span>}</td>
                      <td className="num">{x.claims}</td>
                      <td><Link className="btn" href={`/review/documents/${x.id}`}>Review</Link></td>
                    </tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            )}
          </Section>
        </div>
      )}
    </>
  );
}
