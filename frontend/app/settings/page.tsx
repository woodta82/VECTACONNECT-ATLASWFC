"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote } from "@/components/Ui";
import { useAction } from "@/lib/useAction";
import { ApiError, api, qs } from "@/lib/api";
import { dateTime, label, moduleLabel, money } from "@/lib/format";
import { useApi } from "@/lib/useApi";

type Settings = {
  release: string; customer: string; reporting_timezone: string; ai_kill_switch: boolean;
  budget: { period_month: string; cap_usd: string; warn_at_usd: string; per_run_cap_usd: string; reserved_usd: string; spent_usd: string } | null;
  schedules: { id: string; job_type: string; source: string | null; interval_minutes: number; timezone: string; enabled: boolean; next_run_at: string | null;
               last_success_at: string | null; last_failure_at: string | null }[];
  queue: { status: string; n: number }[];
  jobs: { id: string; job_type: string; status: string; attempts: number; max_attempts: number; last_error: string | null; created_at: string }[];
  models: { module: string; version: string; provisional: boolean; created_at: string }[];
};

export default function SettingsPage() {
  const r = useApi<Settings>("/settings");
  const [msg, setMsg] = useState<string | null>(null);
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg(ok); r.reload(); } catch (e) { setMsg(e instanceof ApiError ? e.message : "Failed"); }
  };
  return (
    <>
      <PageHeader eyebrow="Settings" title="Sources, evidence review, scanning and the shared login"
                  description="The technical controls behind discovery. One shared username and password gives access to the whole workspace." />
      <section className="panel" aria-label="Settings sections">
        <div className="grid grid-3">
          <Link className="chip-link settings-link" href="/sources"><b>Sources</b><span className="small muted">Register, enable and check the public sources discovery reads</span></Link>
          <Link className="chip-link settings-link" href="/review"><b>Evidence review</b><span className="small muted">Confirm or reject extracted claims, merges and unresolved fields</span></Link>
          <a className="chip-link settings-link" href="#scanning"><b>Scanning and AI spend</b><span className="small muted">Schedules, the job queue, budget caps and the kill switch</span></a>
          <Link className="chip-link settings-link" href="/data-sources"><b>WFC data imports (optional)</b><span className="small muted">Bookings, capacity, agreements and other WFC files. Not needed to discover opportunities</span></Link>
          <Link className="chip-link settings-link" href="/areas"><b>Capability analyses (optional)</b><span className="small muted">Account, lane, trucking, technology and network analyses that use imported WFC data</span></Link>
          <Link className="chip-link settings-link" href="/service"><b>Operational exceptions (optional)</b><span className="small muted">Reservation and supervision exceptions from WFC data</span></Link>
        </div>
      </section>
      {msg && <div className="notice notice-info" role="status">{msg}</div>}
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="settings" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (
        <div className="stack">
          <div className="grid grid-2">
            <PasswordPanel />
            <section className="panel">
              <h2>Sessions</h2>
              <p className="muted small">The shared account may be signed in on several devices at once. Signing out everywhere ends every session, including this one.</p>
              <button className="btn btn-danger" type="button" onClick={() => act(() => api.logoutAll(), "All sessions signed out")}>Sign out all sessions</button>
              <dl className="kv" style={{ marginTop: 14 }}>
                <dt>Release</dt><dd>{r.data.release}</dd>
                <dt>Configured for</dt><dd>{r.data.customer}</dd>
                <dt>Reporting time zone</dt><dd>{r.data.reporting_timezone}</dd>
              </dl>
            </section>
          </div>
          <section className="panel" id="scanning">
            <h2>AI spend</h2>
            <dl className="kv">
              <dt>Kill switch</dt><dd><Badge value={r.data.ai_kill_switch ? "blocked" : "ready"} /> {r.data.ai_kill_switch ? "All AI spend is blocked" : "AI calls allowed within budget"}</dd>
              <dt>This month</dt>
              <dd>{r.data.budget ? `${money(r.data.budget.spent_usd, "USD")} settled + ${money(r.data.budget.reserved_usd, "USD")} reserved of ${money(r.data.budget.cap_usd, "USD")} (per-run cap ${money(r.data.budget.per_run_cap_usd, "USD")})` : "No budget set: every AI call is refused"}</dd>
            </dl>
            <div className="actions" style={{ marginTop: 12 }}>
              <button className="btn" type="button" onClick={() => act(() => api.post("/settings/kill-switch", { enabled: !r.data!.ai_kill_switch }), "Kill switch updated")}>
                {r.data.ai_kill_switch ? "Allow AI spend" : "Block all AI spend"}
              </button>
            </div>
            <BudgetForm onSaved={() => { setMsg("Budget saved"); r.reload(); }} />
          </section>
          <SchedulesPanel />
          <JobsPanel />
          <PrioritisationPanel />
        </div>
      )}
    </>
  );
}

function PasswordPanel() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      setMsg("Password changed. Every session has been signed out.");
      window.location.reload();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Could not change password");
    }
  }
  return (
    <section className="panel">
      <h2>Change shared password</h2>
      <form onSubmit={submit} className="stack">
        <label className="field">Current password<input type="password" className="input" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} /></label>
        <label className="field">New password (12+ characters, three character types)<input type="password" className="input" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></label>
        <button className="btn btn-primary" type="submit" disabled={!current || next.length < 12}>Change password</button>
      </form>
      {msg && <p role="status" className="small">{msg}</p>}
    </section>
  );
}

function BudgetForm({ onSaved }: { onSaved: () => void }) {
  const [cap, setCap] = useState("");
  const [warn, setWarn] = useState("");
  const [perRun, setPerRun] = useState("");
  const [err, setErr] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api.post("/settings/budget", { cap_usd: cap, warn_at_usd: warn, per_run_cap_usd: perRun });
      onSaved();
    } catch (x) {
      setErr(x instanceof ApiError ? x.message : "Could not save");
    }
  }
  return (
    <form onSubmit={submit} className="filters" style={{ marginTop: 14 }} aria-label="Monthly budget">
      <label className="field">Monthly cap (USD)<input className="input" inputMode="decimal" value={cap} onChange={(e) => setCap(e.target.value)} /></label>
      <label className="field">Warn at (USD)<input className="input" inputMode="decimal" value={warn} onChange={(e) => setWarn(e.target.value)} /></label>
      <label className="field">Per-run cap (USD)<input className="input" inputMode="decimal" value={perRun} onChange={(e) => setPerRun(e.target.value)} /></label>
      <button className="btn" type="submit" disabled={!cap || !warn || !perRun}>Save budget</button>
      {err && <p role="alert" className="small">{err}</p>}
    </form>
  );
}

type Schedule = { id: string; name: string | null; job_type: string; source: string | null; search: string | null; interval_minutes: number; timezone: string;
                  enabled: boolean; next_run_at: string | null; last_success_at: string | null; last_failure_at: string | null };

function SchedulesPanel() {
  const r = useApi<{ items: Schedule[] }>("/schedules");
  const a = useAction();
  const [edit, setEdit] = useState<Record<string, { interval: string; tz: string; name: string }>>({});
  const save = (s: Schedule, enabled = s.enabled) => {
    const e = edit[s.id] ?? { interval: String(s.interval_minutes), tz: s.timezone, name: s.name ?? "" };
    return a.run(() => api.put(`/schedules/${s.id}`, { interval_minutes: Number(e.interval), timezone: e.tz, enabled, name: e.name || null }), "Schedule saved")
      .then((ok) => { if (ok) { const n = { ...edit }; delete n[s.id]; setEdit(n); r.reload(); } });
  };
  return (
    <section className="panel">
      <h2>Schedules</h2>
      <p className="muted small">Saved country searches and sources run on these schedules through the durable job queue. A schedule never starts a second run while one is in progress; budget and the kill switch apply to every run. Create a schedule from a saved search on <Link href="/discovery">Country Discovery</Link> or by setting a source&apos;s refresh frequency.</p>
      <ActionNote state={a} />
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? <Empty title="No schedules configured" /> : (
        <TableWrap label="Schedules">
          <table>
            <thead><tr><th>Schedule</th><th>Every (minutes)</th><th>Time zone</th><th>Next run</th><th>Last success / failure</th><th /></tr></thead>
            <tbody>{r.data.items.map((s) => {
              const e = edit[s.id] ?? { interval: String(s.interval_minutes), tz: s.timezone, name: s.name ?? "" };
              const set = (k: "interval" | "tz" | "name", v: string) => setEdit({ ...edit, [s.id]: { ...e, [k]: v } });
              return (
                <tr key={s.id}>
                  <td><input className="input" aria-label="Schedule name" value={e.name} placeholder={s.search ?? s.source ?? label(s.job_type)} onChange={(x) => set("name", x.target.value)} />
                    <span className="muted small">{label(s.job_type)}{s.search ? ` · search “${s.search}”` : s.source ? ` · source ${s.source}` : ""}</span></td>
                  <td><input className="input" aria-label="Interval in minutes" inputMode="numeric" value={e.interval} onChange={(x) => set("interval", x.target.value)} style={{ maxWidth: 110 }} /></td>
                  <td><input className="input" aria-label="Time zone" value={e.tz} onChange={(x) => set("tz", x.target.value)} style={{ maxWidth: 170 }} /></td>
                  <td>{s.enabled ? dateTime(s.next_run_at) : <Badge value="disabled" />}</td>
                  <td className="small">{dateTime(s.last_success_at)}<span className="muted">{s.last_failure_at ? `failed ${dateTime(s.last_failure_at)}` : ""}</span></td>
                  <td className="actions">
                    <button className="btn" type="button" disabled={a.busy || !edit[s.id]} onClick={() => save(s)}>Save</button>
                    <button className="btn" type="button" disabled={a.busy} onClick={() => save(s, !s.enabled)}>{s.enabled ? "Disable" : "Enable"}</button>
                  </td>
                </tr>
              );
            })}</tbody>
          </table>
        </TableWrap>
      ))}
    </section>
  );
}

type Job = { id: string; job_type: string; status: string; attempts: number; max_attempts: number; last_error: string | null; created_at: string;
             finished_at: string | null; retry_of: string | null; discovery_run_id: string | null; progress: Record<string, unknown> | null };

function JobsPanel() {
  const [status, setStatus] = useState("");
  const r = useApi<{ items: Job[]; queue: { status: string; n: number }[] }>(`/jobs${qs({ status, limit: 50 })}`);
  const a = useAction();
  return (
    <section className="panel">
      <h2>Job queue</h2>
      <div className="filters">
        <label className="field">Status
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>{["queued", "running", "succeeded", "failed", "dead", "cancelled"].map((v) => <option key={v} value={v}>{label(v)}</option>)}
          </select>
        </label>
        {r.data && <p className="small muted">{r.data.queue.map((q) => `${q.n} ${q.status}`).join(" · ") || "Queue empty"}</p>}
      </div>
      <ActionNote state={a} />
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (r.data.items.length === 0 ? <Empty title="No jobs" /> : (
        <TableWrap label="Jobs">
          <table>
            <thead><tr><th>Created</th><th>Type</th><th>Status</th><th>Attempts</th><th>Last error</th><th /></tr></thead>
            <tbody>{r.data.items.map((j) => (
              <tr key={j.id}>
                <td>{dateTime(j.created_at)}{j.retry_of && <span className="muted small">retry</span>}</td>
                <td>{j.discovery_run_id ? <Link href={`/discovery/runs/${j.discovery_run_id}`}>{label(j.job_type)}</Link> : label(j.job_type)}</td>
                <td><Badge value={j.status} /></td><td>{j.attempts}/{j.max_attempts}</td><td className="small">{j.last_error ?? "—"}</td>
                <td className="actions">
                  {["queued", "running"].includes(j.status) && <button className="btn" type="button" disabled={a.busy}
                    onClick={() => a.run(() => api.post(`/jobs/${j.id}/cancel`), "Job cancelled").then(r.reload)}>Cancel</button>}
                  {["failed", "dead", "cancelled"].includes(j.status) && <button className="btn" type="button" disabled={a.busy}
                    onClick={() => a.run(() => api.post(`/jobs/${j.id}/retry`), "Retry queued").then(r.reload)}>Retry</button>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </TableWrap>
      ))}
    </section>
  );
}

type Factor = { code: string; dimension: string; weight: string; anchors: string[]; gate: boolean };
type Model = { module: string; method: string; version: string; provisional: boolean; min_coverage?: string; factors?: Factor[]; note?: string;
                order?: string[]; why_no_score?: string; missing_data?: string };

function PrioritisationPanel() {
  const r = useApi<{ models: Model[]; note: string }>("/settings/prioritisation");
  return (
    <section className="panel">
      <h2>Prioritisation definitions</h2>
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <>
        <p className="notice">{r.data.note}</p>
        {r.data.models.map((m) => (
          <details key={m.module} className="claim-card">
            <summary><strong>{moduleLabel(m.module)}</strong> · {m.version} · {m.method === "scored" ? `scored${m.provisional ? ", provisional weights" : ""}` : "ordered by rules, not a score"}</summary>
            {m.note && <p className="small">{m.note}</p>}
            {m.factors ? (
              <TableWrap label={`${moduleLabel(m.module)} factors`}>
                <table><thead><tr><th>Dimension</th><th>Factor</th><th className="num">Weight</th><th>Scale (0 → 4)</th></tr></thead>
                  <tbody>{m.factors.map((f) => (
                    <tr key={f.code}><td>{label(f.dimension)}</td><td>{label(f.code)}{f.gate ? " (gate)" : ""}</td><td className="num">{f.weight}</td><td className="small">{f.anchors.join(" → ")}</td></tr>
                  ))}</tbody></table>
              </TableWrap>
            ) : <>
              <ol className="small">{(m.order ?? []).map((x) => <li key={x}>{x}</li>)}</ol>
              <p className="small">{m.why_no_score}</p><p className="muted small">{m.missing_data}</p>
            </>}
            {m.min_coverage && <p className="muted small">A dimension is scored only when at least {Math.round(Number(m.min_coverage) * 100)}% of its weight has data; otherwise it shows Insufficient data.</p>}
          </details>
        ))}
      </>}
    </section>
  );
}
