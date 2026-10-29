"use client";

import { useState } from "react";
import { Badge, Empty, ErrorState, type Insight, InsightMeta, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote } from "@/components/Ui";
import { api, qs } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Row = { rank?: number; rank_reason?: string; missing?: string[]; id: string; exception_type: string; severity: string; description: string; status: string; deadline_utc: string | null;
             opened_at: string; resolved_at: string | null; customer: string | null; operating_company: string | null;
             owner_person_id: string | null; owner: string | null };
type Page = { items: Row[]; total: number; insight: Insight };
type Lookups = { people: { id: string; full_name: string; is_internal: boolean; operating_company: string | null }[] };

export default function ServicePage() {
  const [status, setStatus] = useState("active");
  const r = useApi<Page>(`/service/exceptions${qs({ status, limit: 100 })}`);
  const lk = useApi<Lookups>("/reference/lookups");
  const a = useAction();
  const [note, setNote] = useState("");
  const internal = (lk.data?.people ?? []).filter((p) => p.is_internal);
  const noteOk = note.trim().length >= 3;

  return (
    <>
      <PageHeader eyebrow="Service Intelligence" title="Reservations, supervision and post-flight exceptions"
                  description="One active exception per underlying problem, with one alert and one task. Owners are descriptive records in the shared workspace. Acknowledging and resolving require a note; the full history is kept." />
      <div className="filters">
        <label className="field">Status
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="active">Active</option><option value="resolved">Resolved</option><option value="">All</option>
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 280px" }}>Note (required to acknowledge or resolve)
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} />
        </label>
      </div>
      <ActionNote state={a} />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="exceptions" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? (
        r.data.insight.sources.some((s) => s.status === "not_connected")
          ? <Empty title="Not connected">No exception feed or import has been loaded. This is not the same as zero exceptions.</Empty>
          : <Empty title="No exceptions in this view" />
      ) : (
        <TableWrap label="Operational exceptions">
          <table>
            <thead><tr><th>Severity</th><th>Type</th><th>Description</th><th>Customer · company</th><th>Deadline</th><th>Status</th><th>Owner</th><th /></tr></thead>
            <tbody>{r.data.items.map((e) => (
              <tr key={e.id}>
                <td><Badge value={e.severity} />{e.rank_reason && <span className="muted small" title={e.rank_reason}>#{e.rank}{e.missing && e.missing.length > 0 ? ` · missing: ${e.missing.join("; ")}` : ""}</span>}</td><td>{e.exception_type.replace(/_/g, " ")}</td><td>{e.description}</td>
                <td>{e.customer ?? "—"}<span className="muted small">{e.operating_company ?? ""}</span></td>
                <td>{dateTime(e.deadline_utc)}</td><td><Badge value={e.status} /></td>
                <td>{e.status === "resolved" ? (e.owner ?? "—") : (
                  <select className="select" aria-label={`Owner for ${e.description}`} value={e.owner_person_id ?? ""} disabled={a.busy}
                          onChange={(ev) => a.run(() => api.post(`/service/exceptions/${e.id}/owner`, { person_id: ev.target.value || null }), "Owner updated").then(r.reload)}>
                    <option value="">Unassigned</option>
                    {internal.map((p) => <option key={p.id} value={p.id}>{p.full_name}{p.operating_company ? ` (${p.operating_company})` : ""}</option>)}
                  </select>)}</td>
                <td className="actions">{e.status === "open" && (
                  <button className="btn" type="button" disabled={!noteOk || a.busy}
                          onClick={() => a.run(() => api.post(`/service/exceptions/${e.id}/acknowledge`, { note }), "Acknowledged").then(() => { setNote(""); r.reload(); })}>Acknowledge</button>)}
                  {e.status !== "resolved" && (
                  <button className="btn" type="button" disabled={!noteOk || a.busy}
                          onClick={() => a.run(() => api.post(`/service/exceptions/${e.id}/resolve`, { note }), "Exception resolved; its task was closed and history kept").then(() => { setNote(""); r.reload(); })}>Resolve</button>)}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </TableWrap>
      ))}
      {r.data && <InsightMeta insight={r.data.insight} />}
    </>
  );
}
