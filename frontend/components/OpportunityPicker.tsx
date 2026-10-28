"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api } from "@/lib/api";
import { moduleLabel } from "@/lib/format";

export type PickedOpportunity = { id: string; title: string; module: string; operating_company: string | null; organisation: string | null };

/**
 * Searchable opportunity picker (review of 26 Oct 2026, §2): find the other record by title, organisation or
 * tender reference instead of pasting a raw id. Results come from GET /api/opportunities?q=… and exclude
 * the current record. Keyboard: type to search, ArrowDown/ArrowUp to move, Enter to choose, Escape to close.
 */
export function OpportunityPicker({ label, excludeId, value, onChange }: {
  label: string; excludeId: string; value: PickedOpportunity | null; onChange: (v: PickedOpportunity | null) => void;
}) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<PickedOpportunity[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const listId = useId();
  const seq = useRef(0);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setItems([]); setState("idle"); return; }
    const mine = ++seq.current;
    setState("loading");
    const t = window.setTimeout(() => {
      api.get<{ items: PickedOpportunity[] }>(`/opportunities?q=${encodeURIComponent(term)}&limit=8`)
        .then((r) => { if (mine === seq.current) { setItems(r.items.filter((x) => x.id !== excludeId)); setActive(0); setState("idle"); } })
        .catch(() => { if (mine === seq.current) { setItems([]); setState("error"); } });
    }, 250);
    return () => window.clearTimeout(t);
  }, [q, excludeId]);

  function choose(o: PickedOpportunity) {
    onChange(o);
    setQ("");
    setOpen(false);
  }

  if (value) {
    return (
      <div className="field">{label}
        <div className="picked">
          <span><strong>{value.title}</strong> <span className="muted small">{moduleLabel(value.module)}{value.operating_company ? ` · ${value.operating_company}` : ""}</span></span>
          <button className="btn btn-small" type="button" onClick={() => onChange(null)}>Change</button>
        </div>
      </div>
    );
  }
  return (
    <div className="field picker">
      <label htmlFor={`${listId}-input`}>{label}</label>
      <input id={`${listId}-input`} className="input" value={q} role="combobox" aria-expanded={open && items.length > 0} aria-controls={listId}
             aria-autocomplete="list" aria-activedescendant={open && items[active] ? `${listId}-${active}` : undefined}
             placeholder="Search by title, airline or tender reference"
             onChange={(e) => { setQ(e.target.value); setOpen(true); }}
             onFocus={() => setOpen(true)}
             onBlur={() => window.setTimeout(() => setOpen(false), 150)}
             onKeyDown={(e) => {
               if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(i + 1, items.length - 1)); }
               else if (e.key === "ArrowUp") { e.preventDefault(); setActive((i) => Math.max(i - 1, 0)); }
               else if (e.key === "Enter" && open && items[active]) { e.preventDefault(); choose(items[active]); }
               else if (e.key === "Escape") setOpen(false);
             }} />
      {open && q.trim().length >= 2 && (
        <ul className="picker-list" id={listId} role="listbox" aria-label={label}>
          {state === "loading" && <li className="muted small" aria-live="polite">Searching…</li>}
          {state === "error" && <li className="small" role="alert">Search failed. Try again.</li>}
          {state === "idle" && items.length === 0 && <li className="muted small">No other opportunity matches “{q.trim()}”.</li>}
          {items.map((o, i) => (
            <li key={o.id} id={`${listId}-${i}`} role="option" aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); choose(o); }} onMouseEnter={() => setActive(i)}>
              <strong>{o.title}</strong>
              <span className="muted small">{moduleLabel(o.module)}{o.organisation ? ` · ${o.organisation}` : ""}{o.operating_company ? ` · ${o.operating_company}` : ""}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
