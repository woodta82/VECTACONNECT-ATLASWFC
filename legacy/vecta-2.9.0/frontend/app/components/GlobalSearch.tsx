"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { api, type GlobalSearchResult } from "@/lib/api";

export default function GlobalSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GlobalSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
    else {
      setQuery("");
      setResults(null);
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .globalSearch(query.trim())
        .then(setResults)
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  function go(url: string) {
    setOpen(false);
    router.push(url);
  }

  const hasResults =
    results && (results.opportunities.length > 0 || results.contacts.length > 0 || results.organisations.length > 0);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className="flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs text-muted"
        style={{ borderColor: "var(--border-strong)" }}
      >
        <Search size={14} aria-hidden="true" />
        Search
        <span className="ml-2 rounded border px-1.5 py-0.5 text-[10px]" style={{ borderColor: "var(--border-strong)" }} aria-hidden="true">
          ⌘K
        </span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-[100] flex items-start justify-center pt-24 px-4"
          style={{ background: "rgba(0,0,0,0.6)" }}
          onClick={() => setOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Global search"
        >
          <div
            className="w-full max-w-xl rounded-xl overflow-hidden"
            style={{ background: "var(--panel)", border: "1px solid var(--border-strong)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
              <Search size={16} className="text-muted" aria-hidden="true" />
              <label htmlFor="global-search-input" className="sr-only">
                Search opportunities, contacts and organisations
              </label>
              <input
                id="global-search-input"
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search opportunities, contacts, organisations…"
                className="flex-1 bg-transparent text-sm text-main outline-none placeholder:text-muted"
              />
              {loading && <span className="text-xs text-muted">Searching…</span>}
            </div>

            <div className="max-h-[60vh] overflow-y-auto">
              {!query.trim() && (
                <p className="px-4 py-6 text-sm text-muted text-center">Type to search across the whole system.</p>
              )}
              {query.trim() && !loading && !hasResults && (
                <p className="px-4 py-6 text-sm text-muted text-center">No results for &ldquo;{query}&rdquo;.</p>
              )}

              {results && results.opportunities.length > 0 && (
                <ResultGroup label="Opportunities">
                  {results.opportunities.map((r) => (
                    <ResultRow key={r.id} item={r} onSelect={go} />
                  ))}
                </ResultGroup>
              )}
              {results && results.contacts.length > 0 && (
                <ResultGroup label="Contacts">
                  {results.contacts.map((r) => (
                    <ResultRow key={r.id} item={r} onSelect={go} />
                  ))}
                </ResultGroup>
              )}
              {results && results.organisations.length > 0 && (
                <ResultGroup label="Organisations">
                  {results.organisations.map((r) => (
                    <ResultRow key={r.id} item={r} onSelect={go} />
                  ))}
                </ResultGroup>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ResultGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="py-2">
      <p className="px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
      {children}
    </div>
  );
}

function ResultRow({ item, onSelect }: { item: { id: string; title: string; subtitle: string; url: string }; onSelect: (url: string) => void }) {
  return (
    <button
      onClick={() => onSelect(item.url)}
      className="w-full text-left px-4 py-2.5 transition-colors"
      style={{ background: "transparent" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--panel-raised)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <p className="text-sm text-main font-medium">{item.title}</p>
      <p className="text-xs text-muted">{item.subtitle}</p>
    </button>
  );
}
