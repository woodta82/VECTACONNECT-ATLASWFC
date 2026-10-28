"use client";

import { useId, useMemo, useState } from "react";
import { useApi } from "@/lib/useApi";
import { Chips } from "./Ui";

export type Country = { code: string; name: string; un_region: string | null; un_subregion: string | null };
export type Region = { code: string; name: string; kind: string; countries: number };
type Geo = { countries: Country[]; regions: Region[]; members: { region_code: string; country_code: string }[] };

let cache: Geo | null = null;

/** Countries and regions from /reference/geography (ISO 3166-1, UN M49, economic groupings, custom). */
export function useGeography() {
  const r = useApi<Geo>(cache ? null : "/reference/geography");
  if (r.data) cache = r.data;
  return cache ?? r.data;
}

/** Searchable multi-select of countries. */
export function CountryPicker({ value, onChange, max, label = "Countries" }: {
  value: string[]; onChange: (v: string[]) => void; max?: number; label?: string;
}) {
  const geo = useGeography();
  const [q, setQ] = useState("");
  const id = useId();
  const names = useMemo(() => new Map((geo?.countries ?? []).map((c) => [c.code, c.name])), [geo]);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s || !geo) return [];
    // Rank: exact ISO code, then names starting with the text, then names containing it ("KE" → Kenya, not Cocos (Keeling)).
    const rank = (c: Country) => (c.code.toLowerCase() === s ? 0 : c.name.toLowerCase().startsWith(s) ? 1 : c.name.toLowerCase().includes(s) ? 2 : 9);
    return geo.countries.filter((c) => !value.includes(c.code) && rank(c) < 9)
      .sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name)).slice(0, 8);
  }, [q, geo, value]);
  const full = max !== undefined && value.length >= max;
  function add(code: string) {
    onChange(max === 1 ? [code] : [...value, code]);
    setQ("");
  }
  return (
    <div className="picker">
      <label className="field" htmlFor={id}>
        {label}
        <input id={id} className="input" value={q} onChange={(e) => setQ(e.target.value)} disabled={full && max !== 1}
               placeholder={full && max !== 1 ? "Maximum selected" : "Type a country name or ISO code"} autoComplete="off"
               role="combobox" aria-expanded={matches.length > 0} aria-controls={`${id}-list`}
               onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) { e.preventDefault(); add(matches[0].code); } }} />
      </label>
      {matches.length > 0 && (
        <ul id={`${id}-list`} className="picker-list" role="listbox">
          {matches.map((c) => (
            <li key={c.code} role="option" aria-selected={false}>
              <button type="button" onClick={() => add(c.code)}>{c.name} <span className="muted small">{c.code} · {c.un_subregion}</span></button>
            </li>
          ))}
        </ul>
      )}
      <Chips label={`Selected ${label.toLowerCase()}`} items={value.map((c) => `${names.get(c) ?? c} (${c})`)}
             onRemove={(v) => onChange(value.filter((c) => !v.endsWith(`(${c})`)))} />
    </div>
  );
}

export function RegionSelect({ value, onChange, label = "Region", allowEmpty = true }: {
  value: string; onChange: (v: string) => void; label?: string; allowEmpty?: boolean;
}) {
  const geo = useGeography();
  const id = useId();
  const groups = useMemo(() => {
    const out: Record<string, Region[]> = {};
    for (const r of geo?.regions ?? []) (out[r.kind] ??= []).push(r);
    return out;
  }, [geo]);
  const title: Record<string, string> = { economic: "Economic groupings", custom: "Custom regions", un_region: "UN regions", un_subregion: "UN sub-regions" };
  return (
    <label className="field" htmlFor={id}>
      {label}
      <select id={id} className="select" value={value} onChange={(e) => onChange(e.target.value)}>
        {allowEmpty && <option value="">Any region</option>}
        {Object.entries(groups).map(([kind, rs]) => (
          <optgroup key={kind} label={title[kind] ?? kind}>
            {rs.map((r) => <option key={r.code} value={r.code}>{r.name} ({r.countries})</option>)}
          </optgroup>
        ))}
      </select>
    </label>
  );
}

export function countryName(code: string): string {
  return cache?.countries.find((c) => c.code === code)?.name ?? code;
}
