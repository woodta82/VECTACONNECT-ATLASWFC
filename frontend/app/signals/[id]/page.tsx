"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Tag } from "@/components/Records";
import { ErrorState, Loading, PageHeader, StaleBanner } from "@/components/States";
import { ActionNote } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateOnly } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Detail = {
  record: { id: string; title: string; module: string; classification: string; record_type: string; summary: string | null; gaps: string[];
            tender_ref: string | null; first_published: string | null; opportunity_id: string | null; freight_scope: string | null;
            tender_state: { status?: string; reasons?: string[] } | null };
  geography: { country_code: string; name: string; role: string; support: string }[];
  evidence: { claim_id: string; claim_type: string; quote: string; source_name: string | null; title: string | null; canonical_url: string;
              published_at: string | null; review_status: string; excluded_at: string | null }[];
  interpretation: { label: string; text: string; unconfirmed: string[]; category: string; record_type_label: string };
};

export default function SignalPage() {
  const { id = "" } = useParams<{ id: string }>();
  const r = useApi<Detail>(id ? `/records/signals/${id}` : null);
  const router = useRouter();
  const a = useAction();
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="record" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (() => {
        const s = r.data.record;
        const it = r.data.interpretation;
        const ev = r.data.evidence.filter((e) => !e.excluded_at);
        const countries = [...new Set(r.data.geography.filter((g) => g.support === "supported").map((g) => g.name))];
        return (
          <div className="stack">
            <PageHeader eyebrow={`Opportunities · ${it.category}`} title={s.title}
                        description={`${it.record_type_label}${s.tender_ref ? ` · reference ${s.tender_ref}` : ""}`}
                        actions={s.opportunity_id ? <Link className="btn btn-primary" href={`/opportunities/${s.opportunity_id}`}>Open the tracked opportunity</Link>
                          : s.record_type === "market_signal" ? (
                            <button type="button" className="btn btn-primary" disabled={a.busy}
                                    onClick={async () => { const out = await a.run(() => api.post<{ opportunity_id: string }>(`/records/signals/${id}/track`), "Tracked");
                                                           if (out) router.push(`/opportunities/${out.opportunity_id}`); }}>
                              Track as a commercial opportunity</button>) : undefined} />
            <div className="small"><Tag text={it.record_type_label} tone={s.record_type === "market_signal" ? "b-warn" : "b-none"} />
              {s.tender_state?.status && <> <Tag text={`Status: ${s.tender_state.status}`} /></>}</div>
            <ActionNote state={a} />
            <div className="grid grid-2">
              <section className="panel" aria-label="What is happening">
                <p className="question">What is happening?</p>
                <dl className="kv">
                  <dt>Geography</dt><dd>{countries.join(", ") || "Not established by the source"}</dd>
                  <dt>First published</dt><dd>{s.first_published ? dateOnly(s.first_published) : "Not stated"}</dd>
                  <dt>Evidence</dt><dd>{ev.length} source passage(s)</dd>
                </dl>
                <ul className="list-plain small">{ev.slice(0, 6).map((e) => (
                  <li key={e.claim_id + e.canonical_url}>“{e.quote.slice(0, 260)}” <span className="muted">— {e.source_name ?? "source"},{" "}
                    <a href={e.canonical_url} target="_blank" rel="noreferrer noopener">{e.title ?? e.canonical_url}</a>
                    {e.published_at ? `, published ${dateOnly(e.published_at)}` : ", publication date not stated"}</span></li>))}</ul>
              </section>
              <section className="panel interpretation" aria-label="Why it could matter">
                <p className="question">Why could it matter to WFC?</p>
                <p className="fact-label">{it.label}</p>
                <p>{it.text}</p>
                <p className="fact-label">What remains unconfirmed</p>
                <ul>{it.unconfirmed.map((u) => <li key={u} className="small">{u}</li>)}</ul>
                {s.record_type === "market_signal" && !s.opportunity_id &&
                  <p className="small muted">Tracking it creates a commercial opportunity with this evidence attached, so the team can research the people involved and record progress. It does not make it a tender.</p>}
              </section>
            </div>
          </div>
        );
      })()}
    </>
  );
}
