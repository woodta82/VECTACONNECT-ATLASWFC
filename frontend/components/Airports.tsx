"use client";

/* The global airport directory (30 Oct 2026): searchable selection by name, IATA, ICAO, city or country, airports without an IATA
   code included; multiple selection. Presence in the directory never means an airport handles cargo. */

import { useEffect, useId, useState } from "react";
import { Chips } from "@/components/Ui";
import { api, qs } from "@/lib/api";

export type Airport = { ident: string; iata: string | null; icao: string | null; name: string; city: string | null; country: string; country_name?: string;
                        type: string; status: string; label: string; source_key?: string };

const cache = new Map<string, Airport>();

export function airportLabel(a: Airport): string {
  return a.label ?? `${a.name} (${a.iata ?? a.icao ?? a.ident})`;
}

export function AirportPicker({ value, onChange, max = 20, label = "Airports", country, hint }: {
  value: string[]; onChange: (v: string[]) => void; max?: number; label?: string; country?: string | null; hint?: string;
}) {
  const [q, setQ] = useState("");
  const [matches, setMatches] = useState<Airport[]>([]);
  const [, bump] = useState(0);
  const id = useId();
  useEffect(() => {
    const s = q.trim();
    if (s.length < 2) { setMatches([]); return; }
    let live = true;
    const t = setTimeout(() => {
      api.get<{ items: Airport[] }>(`/airports${qs({ q: s, country: country || undefined, limit: 8 })}`)
        .then((r) => { if (!live) return; for (const a of r.items) cache.set(a.ident, a); setMatches(r.items.filter((a) => !value.includes(a.ident))); })
        .catch(() => { if (live) setMatches([]); });
    }, 180);
    return () => { live = false; clearTimeout(t); };
  }, [q, country, value]);
  useEffect(() => {
    // labels for idents chosen elsewhere (a saved search, a link): fetched once
    const missing = value.filter((v) => !cache.has(v));
    if (!missing.length) return;
    let live = true;
    Promise.all(missing.map((v) => api.get<Airport>(`/airports/${encodeURIComponent(v)}`).then((a) => cache.set(a.ident, a)).catch(() => null)))
      .then(() => { if (live) bump((n) => n + 1); });
    return () => { live = false; };
  }, [value]);
  const chipLabel = (v: string) => { const a = cache.get(v); return a ? `${a.name} (${a.iata ?? a.icao ?? a.ident})` : v; };
  function add(a: Airport) {
    if (value.length >= max) return;
    cache.set(a.ident, a);
    onChange(max === 1 ? [a.ident] : [...value, a.ident]);
    setQ("");
    setMatches([]);
  }
  return (
    <div className="picker">
      <label className="field" htmlFor={id}>
        {label}
        <input id={id} className="input" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" role="combobox" aria-expanded={matches.length > 0}
               aria-controls={`${id}-list`} placeholder={hint ?? "Airport name, IATA or ICAO code, city or country"}
               onKeyDown={(e) => { if (e.key === "Enter" && matches[0]) { e.preventDefault(); add(matches[0]); } }} />
      </label>
      {matches.length > 0 && (
        <ul id={`${id}-list`} className="picker-list" role="listbox">
          {matches.map((a) => (
            <li key={a.ident} role="option" aria-selected={false}>
              <button type="button" onClick={() => add(a)}>{a.name} <span className="muted small">{[a.iata, a.icao ?? a.ident].filter(Boolean).join(" · ")}{a.iata ? "" : " · no IATA code"} · {a.city ? `${a.city}, ` : ""}{a.country_name ?? a.country}{a.status === "closed" ? " · closed" : ""}</span></button>
            </li>
          ))}
        </ul>
      )}
      <Chips label={`Selected ${label.toLowerCase()}`} items={value.map(chipLabel)} onRemove={(item) => onChange(value.filter((v) => chipLabel(v) !== item))} />
      {value.length === 0 && <p className="small muted">None selected: all airports in the chosen countries or region (worldwide when none is chosen). Selection is a scope, not evidence of cargo operations.</p>}
    </div>
  );
}
