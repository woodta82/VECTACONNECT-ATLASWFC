"use client";

import Link from "next/link";
import { useMemo, useState, type FormEvent } from "react";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { Tag } from "@/components/Records";
import { ActionNote, ReasonAction, Section, Tabs } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Dataset = { dataset: string; category: "master" | "operational"; source_of_truth: string; freshness_sla_hours: number | null;
                 retention: string; fields: { name: string; type: string; required: boolean; unit: string | null; description: string; choices: string[];
                                              why_required: string | null }[];
                 commit_supported: boolean; reversible: boolean; freshness: { last_success_at: string | null } | null;
                 refresh: string; duplicate_key: string; correction: string; used_by: string[] };
type Data = {
  connectors: { code: string; name: string; kind: string; status: string; credential_ref: string | null; last_error: string | null;
                capabilities: { notes?: string } }[];
  imports: { id: string; dataset: string; file_name: string; mode: string; status: string; created_at: string; partial: boolean;
             preview_job_id: string | null; committed_as: string | null; totals: { inserted?: number; updated?: number; unchanged?: number; rows_quarantined?: number } }[];
  datasets: Dataset[];
};
type Preview = {
  job_id: string; dataset: string; commit_supported: boolean; reversible: boolean;
  mapping: { mapping: Record<string, string>; unmapped_required: string[]; unused_columns: string[] };
  reconciliation: { rows_read: number; rows_valid: number; rows_quarantined: number; inserted: number; updated: number; unchanged: number;
                    sums: Record<string, Record<string, string>>; file_sha256: string };
  errors: { row_number: number; field: string | null; code: string; message: string }[];
  preview: { row: number; key: string; action: string; values: Record<string, unknown>; previous: Record<string, unknown> | null }[];
};
type Committed = { job_id: string; partial: boolean; partial_note: string | null; opportunities_recomputed: number;
                   reconciliation: Preview["reconciliation"] };

const SETUP_ORDER = ["operating_companies", "airports", "airlines", "territories", "services", "service_requirements", "stations", "contacts"];

export default function DataSourcesPage() {
  const r = useApi<Data>("/data-sources");
  const [tab, setTab] = useState<"setup" | "operational" | "supplied" | "airports" | "history" | "connectors">("setup");
  return (
    <>
      <PageHeader eyebrow="Data Sources and Imports" title="Set up reference data and load operational files"
                  description="Every import follows the same path: upload, map columns, validate, preview the planned inserts and updates, then commit exactly what you reviewed. Bad rows are quarantined with their reasons, never dropped. A fresh installation is set up here without touching the database."
                  actions={<Link className="btn" href="/sources">Public sources</Link>} />
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="data sources" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && (
        <section className="panel">
          <Tabs label="Data sources" value={tab} onChange={setTab} tabs={[
            { id: "setup", label: "Setup (master data)" }, { id: "operational", label: "Operational data" }, { id: "supplied", label: "Supplied lists" }, { id: "airports", label: "Airport directory" },
            { id: "history", label: "Import history", count: r.data.imports.length }, { id: "connectors", label: "Connectors" },
          ]} />
          {tab === "setup" && (
            <>
              <p className="muted small">Load in this order on a fresh installation: {SETUP_ORDER.map(label).join(" → ")}. Later imports refer to these records.</p>
              <ImportWorkflow datasets={r.data.datasets.filter((d) => d.category === "master").sort((a, b) => SETUP_ORDER.indexOf(a.dataset) - SETUP_ORDER.indexOf(b.dataset))} onDone={r.reload} />
            </>
          )}
          {tab === "operational" && <ImportWorkflow datasets={r.data.datasets.filter((d) => d.category === "operational")} onDone={r.reload} />}
          {tab === "supplied" && <SuppliedLists />}
          {tab === "airports" && <AirportDirectory />}
          {tab === "history" && <History rows={r.data.imports} datasets={r.data.datasets} onDone={r.reload} />}
          {tab === "connectors" && (
            <TableWrap label="Connectors">
              <table>
                <thead><tr><th>Connector</th><th>Kind</th><th>Status</th><th>Credential</th><th>Notes</th></tr></thead>
                <tbody>{r.data.connectors.map((c) => (
                  <tr key={c.code}><td>{c.name}</td><td>{label(c.kind)}</td><td><Badge value={c.status} /></td>
                    <td className="small">{c.credential_ref ?? "—"}</td><td className="small">{c.capabilities?.notes ?? c.last_error ?? ""}</td></tr>
                ))}</tbody>
              </table>
            </TableWrap>
          )}
        </section>
      )}
    </>
  );
}

function ImportWorkflow({ datasets, onDone }: { datasets: Dataset[]; onDone: () => void }) {
  const [dataset, setDataset] = useState(datasets[0]?.dataset ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [tz, setTz] = useState("");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Preview | null>(null);
  const [done, setDone] = useState<Committed | null>(null);
  const a = useAction();
  const contract = useMemo(() => datasets.find((d) => d.dataset === dataset), [datasets, dataset]);

  async function runPreview(e?: FormEvent) {
    e?.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (Object.keys(mapping).length) fd.append("mapping", JSON.stringify(mapping));
    if (tz) fd.append("timezone", tz);
    setDone(null);
    const p = await a.run(() => api.post<Preview>(`/imports/${dataset}/preview`, fd), "Preview ready: nothing has been written yet.");
    if (p) { setPreview(p); setMapping(p.mapping.mapping); }
  }
  async function commit() {
    if (!preview) return;
    const c = await a.run(() => api.post<Committed>(`/imports/${preview.job_id}/commit`), "Committed.");
    if (c) { setDone(c); setPreview(null); onDone(); }
  }
  return (
    <div className="stack">
      <form onSubmit={runPreview} className="form-grid">
        <label className="field">Dataset
          <select className="select" value={dataset} onChange={(e) => { setDataset(e.target.value); setPreview(null); setMapping({}); setDone(null); }}>
            {datasets.map((d) => <option key={d.dataset} value={d.dataset}>{label(d.dataset)}{d.freshness?.last_success_at ? "" : " (not loaded)"}</option>)}
          </select></label>
        <label className="field">File (.csv or .xlsx)<input className="input" type="file" accept=".csv,.xlsx" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); }} /></label>
        <label className="field">File time zone (only if times carry no offset)<input className="input" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="e.g. Asia/Dubai" /></label>
        <div className="actions" style={{ alignItems: "flex-end" }}>
          <button className="btn btn-primary" type="submit" disabled={!file || a.busy}>Preview</button>
          <a className="btn" href={`/api/imports/templates/${dataset}.csv`}>Template</a>
        </div>
      </form>
      {contract && (
        <details>
          <summary className="small">Fields for {label(contract.dataset)} · source of truth: {contract.source_of_truth} · {contract.reversible ? "reversible" : "corrected by re-import"}</summary>
          <ul className="small" aria-label="Dataset rules">
            <li><b>Used by:</b> {contract.used_by.join("; ")}</li>
            <li><b>Refresh:</b> {contract.refresh}</li>
            <li><b>Duplicate key:</b> {contract.duplicate_key} (a re-import with the same key updates the record; it never adds a second one)</li>
            <li><b>Corrections:</b> {contract.correction}</li>
            <li><b>Last import:</b> {contract.freshness?.last_success_at ? dateTime(contract.freshness.last_success_at) : "never (Not connected)"}</li>
          </ul>
          <TableWrap label="Dataset fields">
            <table><thead><tr><th>Field</th><th>Type</th><th>Required</th><th>Notes</th></tr></thead>
              <tbody>{contract.fields.map((f) => (
                <tr key={f.name}><td>{f.name}</td><td>{f.type}{f.unit ? ` (${f.unit})` : ""}</td><td>{f.required ? "Yes" : "No"}</td>
                  <td className="small">{f.description}{f.why_required ? `${f.description ? "; " : ""}Required: ${f.why_required}.` : ""}{f.choices.length ? ` One of: ${f.choices.join(", ")}` : ""}</td></tr>
              ))}</tbody></table>
          </TableWrap>
        </details>
      )}
      <ActionNote state={a} />
      {preview && (
        <div className="stack">
          <div className="grid grid-4">
            <div className="stat"><div className="stat-label">Rows read</div><div className="stat-value">{preview.reconciliation.rows_read}</div></div>
            <div className="stat"><div className="stat-label">Will insert</div><div className="stat-value">{preview.reconciliation.inserted}</div></div>
            <div className="stat"><div className="stat-label">Will update</div><div className="stat-value">{preview.reconciliation.updated}</div>
              <div className="stat-note">{preview.reconciliation.unchanged} unchanged</div></div>
            <div className="stat"><div className="stat-label">Quarantined</div><div className="stat-value">{preview.reconciliation.rows_quarantined}</div>
              <div className="stat-note">not imported</div></div>
          </div>
          <Section title="Column mapping">
            {preview.mapping.unmapped_required.length > 0 && <p className="action-error">Required fields not mapped: {preview.mapping.unmapped_required.join(", ")}. Map them and preview again.</p>}
            <div className="form-grid">
              {contract?.fields.map((f) => (
                <label key={f.name} className="field">{f.name}{f.required ? " *" : ""}
                  <select className="select" value={mapping[f.name] ?? ""} onChange={(e) => setMapping({ ...mapping, [f.name]: e.target.value })}>
                    <option value="">(not in file)</option>
                    {[...new Set([...Object.values(preview.mapping.mapping), ...preview.mapping.unused_columns])].map((c) => <option key={c} value={c}>{c}</option>)}
                  </select></label>
              ))}
            </div>
            <div className="actions" style={{ marginTop: 10 }}><button className="btn" type="button" onClick={() => runPreview()} disabled={a.busy}>Preview again with this mapping</button></div>
          </Section>
          {preview.errors.length > 0 && (
            <Section title={`Row errors (${preview.errors.length})`}>
              <TableWrap label="Row errors"><table><thead><tr><th className="num">Row</th><th>Field</th><th>Problem</th></tr></thead>
                <tbody>{preview.errors.map((e, i) => <tr key={i}><td className="num">{e.row_number}</td><td>{e.field ?? "—"}</td><td>{label(e.code)}: {e.message}</td></tr>)}</tbody></table></TableWrap>
            </Section>
          )}
          {preview.preview.length > 0 && (
            <Section title="Planned changes">
              <TableWrap label="Planned changes"><table><thead><tr><th className="num">Row</th><th>Key</th><th>Action</th><th>Values</th></tr></thead>
                <tbody>{preview.preview.slice(0, 50).map((p) => (
                  <tr key={p.row}><td className="num">{p.row}</td><td>{p.key}</td><td><Badge value={p.action} /></td>
                    <td className="small">{Object.entries(p.values).filter(([, v]) => v !== null && v !== "").map(([k, v]) => {
                      const was = p.previous?.[k];
                      return `${k}: ${String(v)}${p.action === "update" && was !== undefined && String(was) !== String(v) ? ` (was ${String(was)})` : ""}`;
                    }).join(" · ")}</td></tr>
                ))}</tbody></table></TableWrap>
              {preview.preview.length > 50 && <p className="muted small">Showing 50 of {preview.preview.length} planned changes.</p>}
            </Section>
          )}
          <div className="actions">
            <button className="btn btn-primary" type="button" onClick={commit} disabled={!preview.commit_supported || a.busy || (preview.reconciliation.inserted + preview.reconciliation.updated === 0)}>
              Commit {preview.reconciliation.inserted + preview.reconciliation.updated} change(s)
            </button>
            <span className="muted small">The commit applies this preview only. If the data changed since, it is refused and you preview again.</span>
          </div>
        </div>
      )}
      {done && (
        <div className={`outcome ${done.partial ? "outcome-warn" : "outcome-good"}`} role="status">
          <strong>{done.partial ? "Partially imported" : "Imported"}</strong>
          {done.reconciliation.inserted} inserted, {done.reconciliation.updated} updated, {done.reconciliation.unchanged} unchanged, {done.reconciliation.rows_quarantined} quarantined.
          {done.partial_note && <div>{done.partial_note}</div>}
          {done.opportunities_recomputed > 0 && <div>{done.opportunities_recomputed} live opportunit{done.opportunities_recomputed === 1 ? "y was" : "ies were"} re-qualified.</div>}
          <div className="small">Reconciliation: {Object.entries(done.reconciliation.sums).map(([f, s]) => `${f} ${Object.entries(s).map(([k, v]) => `${v} ${k}`).join(", ")}`).join("; ") || "no totals for this dataset"} · file SHA-256 {done.reconciliation.file_sha256.slice(0, 12)}…</div>
        </div>
      )}
    </div>
  );
}

function History({ rows, datasets, onDone }: { rows: Data["imports"]; datasets: Dataset[]; onDone: () => void }) {
  const a = useAction();
  const reversible = new Set(datasets.filter((d) => d.reversible).map((d) => d.dataset));
  if (rows.length === 0) return <Empty title="No imports yet" />;
  return (
    <>
      <ActionNote state={a} />
      <TableWrap label="Import history">
        <table>
          <thead><tr><th>When</th><th>Dataset</th><th>File</th><th>Kind</th><th>Status</th><th>Result</th><th /></tr></thead>
          <tbody>{rows.map((j) => (
            <tr key={j.id}>
              <td>{dateTime(j.created_at)}</td><td>{label(j.dataset)}</td><td className="small">{j.file_name}</td>
              <td>{j.mode === "dry_run" ? "Preview" : "Commit"}</td>
              <td><Badge value={j.status} />{j.partial && <Badge value="partial" />}</td>
              <td className="small">{j.totals.inserted ?? 0} ins · {j.totals.updated ?? 0} upd · {j.totals.unchanged ?? 0} same · {j.totals.rows_quarantined ?? 0} quarantined</td>
              <td>{j.mode === "commit" && j.status === "committed" && reversible.has(j.dataset) && (
                <ReasonAction label="Reverse" tone="danger" busy={a.busy}
                              onSubmit={(reason) => a.run(() => api.post(`/imports/${j.id}/reverse`, { reason }), "Reversed").then(onDone)} />
              )}</td>
            </tr>
          ))}</tbody>
        </table>
      </TableWrap>
    </>
  );
}


/* Supplied lists (29 Oct 2026): a station's GSA or airline list as an example of the research output expected everywhere. Preserved row by
   row; every company, address and represented airline from it is marked supplied — awaiting verification — never assumed current. */
type SuppliedImport = { id: string; name: string; filename: string | null; airport_iata: string | null; country: string | null; rows_total: number; organisations: number;
                        relationships: number; contacts: number; imported_at: string; imported_by: string | null; rows_linked: number; organisations_verified: number; notes: string | null };
type SuppliedResult = { id: string; name: string; airport_iata: string | null; country: string | null; rows: number; organisations: number; relationships: number;
                        contacts: number; skipped: string[]; note: string };

function SuppliedLists() {
  const r = useApi<{ items: SuppliedImport[] }>("/supplied-data");
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");
  const [result, setResult] = useState<SuppliedResult | null>(null);
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (name) fd.append("name", name);
    if (notes) fd.append("notes", notes);
    const res = await a.run(() => api.post<SuppliedResult>("/supplied-data", fd), (x) => x.note);
    if (res) { setResult(res); setFile(null); r.reload(); }
  }
  return (
    <div className="stack">
      <p className="muted small">An Excel station list (for example a GSA list for one airport: company, represented airlines, e-mail; and airlines by type) is read as a
        benchmark of the research output expected globally, not as a database and not as a scope. Rows are preserved as supplied; nothing from them is shown as
        current until research sources it (Discover → Companies) or a person verifies it on the company&apos;s page.</p>
      <form className="form-grid" onSubmit={submit}>
        <label className="field">Workbook (.xlsx)<input className="input" type="file" accept=".xlsx,.xlsm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <label className="field">Name (optional)<input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. GSA list BRU (supplied Oct 2026)" /></label>
        <label className="field">Notes (optional)<input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={!file || a.busy}>{a.busy ? "Reading…" : "Load as supplied data"}</button></div>
      </form>
      <ActionNote state={a} />
      {result && (
        <div className="notice notice-info" role="status">{result.name}: {result.rows} row(s) → {result.organisations} compan{result.organisations === 1 ? "y" : "ies"}, {result.relationships} represented-airline
          entries, {result.contacts} address(es), all marked supplied{result.airport_iata ? ` · station ${result.airport_iata}` : ""}.{" "}
          <Link href={`/companies?origin=supplied${result.airport_iata ? `&airport=${result.airport_iata}` : ""}`}>Open the companies</Link>
          {result.skipped.length > 0 && <ul className="small">{result.skipped.map((x) => <li key={x}>{x}</li>)}</ul>}</div>
      )}
      {r.data && (r.data.items.length === 0 ? <Empty title="No supplied list loaded yet" /> : (
        <TableWrap label="Supplied lists">
          <table><thead><tr><th>Loaded</th><th>Name</th><th>Station</th><th className="num">Rows</th><th className="num">Companies</th><th className="num">Verified</th><th className="num">Represented airlines</th><th className="num">Addresses</th></tr></thead>
            <tbody>{r.data.items.map((i) => (
              <tr key={i.id}>
                <td>{dateTime(i.imported_at)}<span className="muted small">{i.imported_by ?? ""}</span></td>
                <td>{i.name}<span className="muted small">{i.filename}</span></td>
                <td>{i.airport_iata ?? "—"}{i.country && <span className="muted small">{i.country}</span>}</td>
                <td className="num">{i.rows_total}</td>
                <td className="num"><Link href={`/companies?origin=supplied${i.airport_iata ? `&airport=${i.airport_iata}` : ""}`}>{i.organisations}</Link></td>
                <td className="num">{i.organisations_verified}</td><td className="num">{i.relationships}</td><td className="num">{i.contacts}</td>
              </tr>))}</tbody></table>
        </TableWrap>
      ))}
    </div>
  );
}


/* The global airport directory (30 Oct 2026): which dataset is loaded, with provenance and refresh date; load or refresh OurAirports' airports.csv
   by upload when the server has no outbound access (tools/load_airports.py downloads it otherwise). */
type DirStatus = { airports: number; maintained_rows: number; maintained: boolean; note: string; using: "seed" | "partial" | "full"; using_label: string;
                   total_records: number; seed_rows: number; full_min_rows: number; cargo_rule: string;
                   dataset: { name: string; source: string; url: string | null; licence: string | null; version: string | null; refreshed_at: string | null; loaded_at: string; rows_loaded: number } | null;
                   datasets: { key: string; name: string; source: string; url: string | null; licence: string | null; version: string | null; refreshed_at: string | null; loaded_at: string; rows_loaded: number; notes: string | null }[] };

function AirportDirectory() {
  const r = useApi<DirStatus>("/airports/status");
  const [file, setFile] = useState<File | null>(null);
  const [version, setVersion] = useState("");
  const [refreshed, setRefreshed] = useState("");
  const a = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (version) fd.append("version", version);
    if (refreshed) fd.append("refreshed_at", refreshed);
    const out = await a.run(() => api.post<{ rows: number }>("/airports/load", fd), (x) => `${x.rows} airport rows loaded`);
    if (out) { setFile(null); r.reload(); }
  }
  return (
    <div className="stack">
      {r.data && (
        <section className="panel" aria-label="Directory in use">
          <div className="panel-head"><h2>Directory in use: {r.data.using_label}</h2><Tag text={r.data.using === "full" ? "Full" : r.data.using === "partial" ? "Partial" : "Seed"} tone={r.data.using === "full" ? "b-good" : "b-warn"} /></div>
          <dl className="kv">
            <dt>Total records</dt><dd>{r.data.total_records.toLocaleString()} <span className="muted small">({r.data.maintained_rows.toLocaleString()} from the maintained dataset, {r.data.seed_rows.toLocaleString()} from the bundled seed)</span></dd>
            <dt>Source</dt><dd>{r.data.dataset ? <>{r.data.dataset.source}{r.data.dataset.licence && <span className="muted small"> · {r.data.dataset.licence}</span>}</> : "—"}</dd>
            <dt>Version</dt><dd>{r.data.dataset?.version ?? <span className="muted">not stated</span>}</dd>
            <dt>Publisher refresh date</dt><dd>{r.data.dataset?.refreshed_at ? dateTime(r.data.dataset.refreshed_at) : <span className="muted">not stated</span>}</dd>
            <dt>Loaded</dt><dd>{r.data.dataset ? dateTime(r.data.dataset.loaded_at) : "—"}</dd>
          </dl>
          <div className={`notice ${r.data.using === "full" ? "notice-info" : ""}`} role="status">{r.data.note}</div>
          <p className="small muted">{r.data.cargo_rule}</p>
        </section>
      )}
      {r.data && (
        <TableWrap label="Reference datasets">
          <table><thead><tr><th>Dataset</th><th>Source and licence</th><th>Version</th><th>Publisher refresh</th><th>Loaded</th><th className="num">Rows</th><th>Notes</th></tr></thead>
            <tbody>{r.data.datasets.map((d) => (
              <tr key={d.key}><td>{d.name}</td><td className="small">{d.source}{d.url && <div><a href={d.url} target="_blank" rel="noreferrer noopener">{d.url}</a></div>}<div className="muted">{d.licence}</div></td>
                <td className="small">{d.version ?? "—"}</td><td className="small">{d.refreshed_at ? dateTime(d.refreshed_at) : <span className="muted">not stated</span>}</td>
                <td className="small">{dateTime(d.loaded_at)}</td><td className="num">{d.rows_loaded}</td><td className="small muted">{d.notes}</td></tr>))}</tbody></table>
        </TableWrap>
      )}
      <form className="form-grid" onSubmit={submit}>
        <label className="field">OurAirports airports.csv<input className="input" type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <label className="field">Dataset version or file date<input className="input" value={version} onChange={(e) => setVersion(e.target.value)} placeholder="e.g. 2026-10-01" /></label>
        <label className="field">Publisher refresh date (ISO)<input className="input" value={refreshed} onChange={(e) => setRefreshed(e.target.value)} placeholder="e.g. 2026-10-01" /></label>
        <div className="actions"><button className="btn btn-primary" type="submit" disabled={!file || a.busy}>{a.busy ? "Loading…" : "Load or refresh the directory"}</button></div>
      </form>
      <p className="small muted">Every row keeps the dataset&apos;s identifier, type and status (closed airports are listed but not offered for selection). Presence in the directory never means an
        airport handles cargo: freight relevance is assessed from evidence, separately from airport selection.</p>
      <ActionNote state={a} />
    </div>
  );
}
