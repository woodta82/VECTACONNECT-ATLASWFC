"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { SourceForm, type SourceRow } from "@/components/SourceForm";
import { ActionNote } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime, moduleLabel } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

export default function SourcesPage() {
  const r = useApi<{ items: SourceRow[] }>("/sources?kind=web");
  const a = useAction();
  const [editing, setEditing] = useState<SourceRow | "new" | null>(null);
  return (
    <>
      <PageHeader eyebrow="Data Sources" title="Public sources and schedules"
                  description="Register the official portals, airline newsrooms, procurement searches and trade press that discovery searches. Each source states its authority, country coverage, language and refresh frequency. Sources start disabled until you enable them."
                  actions={<><button className="btn btn-primary" type="button" onClick={() => setEditing("new")}>Add source</button>
                    <Link className="btn" href="/data-sources">Imports and setup</Link></>} />
      {editing && <SourceForm initial={editing === "new" ? null : editing} onDone={() => { setEditing(null); r.reload(); }} onCancel={() => setEditing(null)} />}
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="sources" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      <ActionNote state={a} />
      {r.data && (r.data.items.length === 0 ? <Empty title="No public sources registered">Add the airline newsrooms, procurement portals and trade publications to search.</Empty> : (
        <TableWrap label="Public sources">
          <table>
            <thead><tr><th>Source</th><th>Type / authority</th><th>Coverage</th><th>Refresh</th><th>Health</th><th /></tr></thead>
            <tbody>{r.data.items.map((s) => {
              const failing = s.last_failure_at && (!s.last_success_at || s.last_failure_at > s.last_success_at);
              return (
                <tr key={s.id}>
                  <td><Link href={`/sources/${s.id}`}>{s.name}</Link><span className="muted small">{s.base_url}</span></td>
                  <td>{s.source_type.replace("_", " ")}<span className="muted small">{s.authority.replace("_", " ")}</span></td>
                  <td>{s.global_coverage ? "Global" : s.country_coverage.join(", ") || "Unknown"}
                    <span className="muted small">{s.language ?? "language unknown"} · {s.modules.length ? s.modules.map(moduleLabel).join(", ") : "all areas"}</span></td>
                  <td>{s.refresh_minutes ? `Every ${s.refresh_minutes} min` : "Manual"}{s.schedule && <span className="muted small">next {dateTime(s.schedule.next_run_at)}</span>}</td>
                  <td><Badge value={!s.enabled ? "disabled" : failing ? "failed" : s.last_success_at ? "healthy" : "not_connected"} />
                    <span className="muted small">{failing ? s.last_error : s.last_success_at ? `ok ${dateTime(s.last_success_at)}` : "never run"} · {s.documents} docs</span></td>
                  <td className="actions">
                    <button className="btn" type="button" onClick={() => setEditing(s)}>Edit</button>
                    <button className="btn" type="button" disabled={a.busy}
                            onClick={() => a.run(() => api.post(`/sources/${s.id}/enabled`, { enabled: !s.enabled }), s.enabled ? "Disabled" : "Enabled").then(r.reload)}>
                      {s.enabled ? "Disable" : "Enable"}
                    </button>
                    <button className="btn" type="button" disabled={a.busy || !s.enabled}
                            onClick={() => a.run(() => api.post<{ run_id: string }>(`/sources/${s.id}/run`), (x) => `Run queued (${x.run_id.slice(0, 8)}); see the source page for results`).then(r.reload)}>
                      Run now
                    </button>
                  </td>
                </tr>
              );
            })}</tbody>
          </table>
        </TableWrap>
      ))}
    </>
  );
}

