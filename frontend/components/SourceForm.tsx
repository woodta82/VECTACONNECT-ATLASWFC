"use client";

import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { MODULES } from "@/lib/constants";
import { moduleLabel } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { CountryPicker } from "./Geo";
import { ActionNote, Section } from "./Ui";

export type SourceRow = {
  id: string; name: string; family: string; base_url: string; authority: string; enabled: boolean; source_type: string;
  country_coverage: string[]; global_coverage: boolean; language: string | null; local_language_permitted: boolean; modules: string[];
  refresh_minutes: number | null; query_template: string | null; max_items: number; retention_permitted: boolean;
  authorisation_note: string | null; notes: string | null; last_success_at: string | null; last_failure_at: string | null;
  last_error: string | null; documents: number;
  schedule: { id: string; interval_minutes: number; enabled: boolean; next_run_at: string | null } | null;
};

export function SourceForm({ initial, onDone, onCancel }: { initial: SourceRow | null; onDone: () => void; onCancel: () => void }) {
  const [f, setF] = useState({
    name: initial?.name ?? "", source_type: initial?.source_type ?? "listing", base_url: initial?.base_url ?? "",
    authority: initial?.authority ?? "official_portal", country_coverage: initial?.country_coverage ?? [], global_coverage: initial?.global_coverage ?? false,
    language: initial?.language ?? "en", local_language_permitted: initial?.local_language_permitted ?? true, modules: initial?.modules ?? [],
    refresh_minutes: initial?.refresh_minutes ? String(initial.refresh_minutes) : "", query_template: initial?.query_template ?? "",
    max_items: String(initial?.max_items ?? 20), retention_permitted: initial?.retention_permitted ?? false,
    authorisation_note: initial?.authorisation_note ?? "", notes: initial?.notes ?? "", enabled: initial?.enabled ?? false,
  });
  const a = useAction();
  const set = (k: keyof typeof f, v: unknown) => setF({ ...f, [k]: v });
  async function submit(e: FormEvent) {
    e.preventDefault();
    const body = { ...f, refresh_minutes: f.refresh_minutes ? Number(f.refresh_minutes) : null, max_items: Number(f.max_items),
                   query_template: f.source_type === "search_template" ? f.query_template : null, language: f.language || null,
                   authorisation_note: f.authorisation_note || null, notes: f.notes || null };
    const r = await a.run(() => (initial ? api.put(`/sources/${initial.id}`, body) : api.post("/sources", body)), "Saved");
    if (r) onDone();
  }
  return (
    <Section title={initial ? `Edit ${initial.name}` : "Add a public source"}>
      <form onSubmit={submit} className="stack">
        <div className="form-grid">
          <label className="field">Name<input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} required minLength={3} /></label>
          <label className="field">Type
            <select className="select" value={f.source_type} onChange={(e) => set("source_type", e.target.value)}>
              <option value="listing">Listing page (follows its article links)</option><option value="rss">RSS / Atom feed</option>
              <option value="search_template">Search URL template (per country / keywords)</option><option value="web_page">Single page</option>
            </select></label>
          <label className="field">Authority
            <select className="select" value={f.authority} onChange={(e) => set("authority", e.target.value)}>
              <option value="official_portal">Official tender / procurement portal</option><option value="company_release">Airline or company release</option>
              <option value="trade_press">Trade press</option><option value="unverified">Unverified</option>
            </select></label>
          <label className="field wide">URL<input className="input" type="url" value={f.base_url} onChange={(e) => set("base_url", e.target.value)} required placeholder="https://" /></label>
          {f.source_type === "search_template" && (
            <label className="field wide">Search URL template (placeholders: {"{country}"} {"{country_name}"} {"{keywords}"} {"{airline}"} {"{organisation}"})
              <input className="input" value={f.query_template} onChange={(e) => set("query_template", e.target.value)} required /></label>
          )}
          <label className="field">Language (BCP 47)<input className="input" value={f.language} onChange={(e) => set("language", e.target.value)} placeholder="en, fr, ar" /></label>
          <label className="field">Refresh frequency (minutes, blank = manual)<input className="input" type="number" min={15} value={f.refresh_minutes} onChange={(e) => set("refresh_minutes", e.target.value)} /></label>
          <label className="field">Items per run<input className="input" type="number" min={1} max={200} value={f.max_items} onChange={(e) => set("max_items", e.target.value)} /></label>
        </div>
        <div className="check-grid">
          <label><input type="checkbox" checked={f.global_coverage} onChange={(e) => set("global_coverage", e.target.checked)} /> Global coverage</label>
          <label><input type="checkbox" checked={f.local_language_permitted} onChange={(e) => set("local_language_permitted", e.target.checked)} /> Local-language documents permitted</label>
          <label><input type="checkbox" checked={f.retention_permitted} onChange={(e) => set("retention_permitted", e.target.checked)} /> Full-text retention permitted</label>
          <label><input type="checkbox" checked={f.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Enabled</label>
        </div>
        {!f.global_coverage && <CountryPicker value={f.country_coverage} onChange={(v) => set("country_coverage", v)} label="Country coverage" />}
        <fieldset className="plain">
          <legend className="field">Capability areas (none = all)</legend>
          <div className="check-grid">{MODULES.map((m) => (
            <label key={m}><input type="checkbox" checked={f.modules.includes(m)} onChange={(e) => set("modules", e.target.checked ? [...f.modules, m] : f.modules.filter((x) => x !== m))} />{moduleLabel(m)}</label>
          ))}</div>
        </fieldset>
        <div className="form-grid">
          <label className="field wide">Permission / terms note<input className="input" value={f.authorisation_note} onChange={(e) => set("authorisation_note", e.target.value)} placeholder="e.g. public RSS, terms reviewed 26 Oct 2026" /></label>
        </div>
        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={a.busy}>{initial ? "Save changes" : "Add source"}</button>
          <button className="btn btn-ghost" type="button" onClick={onCancel}>Cancel</button>
        </div>
        <ActionNote state={a} />
      </form>
    </Section>
  );
}
