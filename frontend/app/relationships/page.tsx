"use client";

import { useState, type FormEvent } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ApiError, api, qs } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Person = { id: string; full_name: string; role_title: string | null; is_internal: boolean; organisation: string | null;
                operating_company: string | null; last_engagement: string | null };
type Task = { id: string; title: string; source_type: string; status: string; due_at_utc: string | null; owner: string | null };

export default function RelationshipsPage() {
  const [q, setQ] = useState("");
  const people = useApi<{ items: Person[]; total: number }>(`/relationships/people${qs({ q, limit: 100 })}`);
  const tasks = useApi<{ items: Task[] }>("/tasks?status=open&limit=100");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [internal, setInternal] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    try {
      await api.post("/relationships/people", { full_name: name, role_title: role || null, is_internal: internal });
      setName("");
      setRole("");
      setMsg("Person added.");
      people.reload();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Could not add");
    }
  }
  async function done(id: string) {
    await api.post(`/tasks/${id}/status`, { status: "done" }).catch(() => undefined);
    tasks.reload();
  }

  return (
    <>
      <PageHeader eyebrow="Relationships" title="People, owners and open tasks"
                  description="Owners and contacts are descriptive records, not logins. Everyone signs in with the shared account." />
      <div className="stack">
        <section className="panel">
          <h2>People</h2>
          <div className="filters"><label className="field">Search<input className="input" value={q} onChange={(e) => setQ(e.target.value)} /></label></div>
          {people.stale && <StaleBanner onRetry={people.reload} />}
          {people.status === "loading" && <Loading what="people" />}
          {people.status === "error" && !people.data && <ErrorState error={people.error} onRetry={people.reload} />}
          {people.data && (people.data.items.length === 0 ? <Empty title="No people recorded" /> : (
            <TableWrap label="People">
              <table>
                <thead><tr><th>Name</th><th>Role</th><th>Organisation</th><th>Last engagement</th></tr></thead>
                <tbody>{people.data.items.map((p) => (
                  <tr key={p.id}><td>{p.full_name}{p.is_internal && <span className="muted small"> (internal)</span>}</td><td>{p.role_title ?? "—"}</td>
                    <td>{p.organisation ?? p.operating_company ?? "—"}</td><td>{dateTime(p.last_engagement)}</td></tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
          <form onSubmit={add} className="filters" style={{ marginTop: 14 }} aria-label="Add person">
            <label className="field">Full name<input className="input" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} /></label>
            <label className="field">Role<input className="input" value={role} onChange={(e) => setRole(e.target.value)} /></label>
            <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal owner
            </label>
            <button className="btn" type="submit" disabled={name.trim().length < 2}>Add person</button>
          </form>
          {msg && <p role="status" className="small">{msg}</p>}
        </section>
        <section className="panel">
          <h2>Open tasks</h2>
          {tasks.status === "loading" && <Loading what="tasks" />}
          {tasks.status === "error" && !tasks.data && <ErrorState error={tasks.error} onRetry={tasks.reload} />}
          {tasks.data && (tasks.data.items.length === 0 ? <Empty title="No open tasks" /> : (
            <TableWrap label="Open tasks">
              <table>
                <thead><tr><th>Task</th><th>Source</th><th>Due</th><th>Owner</th><th /></tr></thead>
                <tbody>{tasks.data.items.map((t) => (
                  <tr key={t.id}><td>{t.title}</td><td><Badge value={t.source_type} /></td><td>{dateTime(t.due_at_utc)}</td><td>{t.owner ?? "Unassigned"}</td>
                    <td><button className="btn" type="button" onClick={() => done(t.id)}>Done</button></td></tr>
                ))}</tbody>
              </table>
            </TableWrap>
          ))}
          <p className="muted small">Tasks from operational exceptions close automatically when the exception is resolved.</p>
        </section>
      </div>
    </>
  );
}
