"use client";

import { useEffect, useState } from "react";
import {
  api,
  REGION_LABELS,
  VERTICAL_LABELS,
  type Opportunity,
  type RegionInfo,
  type RegionKey,
  type SavedSearch,
} from "@/lib/api";
import PageHeader from "../components/PageHeader";
import ScoreBadge from "../components/ScoreBadge";

type CompareData = { region: string; count: number; value: number; avg_score: number | null };

export default function RegionalSearchPage() {
  const [regions, setRegions] = useState<Record<RegionKey, RegionInfo> | null>(null);
  const [region, setRegion] = useState<RegionKey>("mena");
  const [market, setMarket] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Opportunity[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [saveName, setSaveName] = useState("");
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>([]);

  const [compareA, setCompareA] = useState<RegionKey>("mena");
  const [compareB, setCompareB] = useState<RegionKey>("uk_ireland");
  const [comparison, setComparison] = useState<Record<string, CompareData> | null>(null);

  useEffect(() => {
    loadRegions();
    api.savedSearches().then(setSavedSearches).catch(() => {});
  }, []);

  function loadRegions() {
    setError(null);
    api.regions().then(setRegions).catch((e) => setError(e instanceof Error ? e.message : "Failed to load regions"));
  }

  async function runSearch() {
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const opps = await api.regionalSearch(region, query.trim(), market || undefined);
      setResults(opps);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function saveSearch() {
    if (!saveName.trim() || !query.trim()) return;
    const created = await api.createSavedSearch(
      saveName.trim(),
      region,
      query.trim(),
      null,
      market || undefined
    );
    setSavedSearches((prev) => [created, ...prev]);
    setSaveName("");
  }

  async function runComparison() {
    const result = await api.compareRegions(compareA, compareB);
    setComparison(result as unknown as Record<string, CompareData>);
  }

  return (
    <div>
      <PageHeader
        eyebrow="Regional Search"
        title="Precision, market by market"
        description="Anchored locally, reaching globally. Select a region, describe what you're looking for in plain language, and ATLAS searches it live."
      />

      <div className="panel p-5 mb-5">
        <fieldset>
          <legend className="field-label mb-2">Region</legend>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Region">
            {regions &&
              (Object.keys(regions) as RegionKey[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setRegion(r)}
                  role="radio"
                  aria-checked={region === r}
                  className={`pill ${region === r ? "pill-active" : ""}`}
                >
                  {REGION_LABELS[r]}
                </button>
              ))}
          </div>
        </fieldset>
        {regions && (
          <p className="text-xs text-muted mt-3">Markets: {regions[region]?.markets.join(", ")}</p>
        )}

        <div className="grid gap-3 md:grid-cols-3 mt-4">
          <div className="field">
            <label htmlFor="market" className="field-label">Specific market</label>
            <input
              id="market"
              value={market}
              onChange={(e) => setMarket(e.target.value)}
              placeholder="Optional"
              className="input"
            />
          </div>
          <div className="field md:col-span-2">
            <label htmlFor="query" className="field-label">Search query</label>
            <input
              id="query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. stadium hospitality tenders closing in Q4"
              className="input"
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
            />
          </div>
        </div>
        <div className="flex items-center gap-3 mt-4">
          <button onClick={runSearch} disabled={searching || !query.trim()} className="btn btn-primary">
            {searching ? "Searching…" : "Search now"}
          </button>
          <span className="text-xs text-muted">Live web search — usually 30–90 seconds.</span>
        </div>

        <div className="mt-4 pt-4 border-t flex flex-wrap items-end gap-3">
          <div className="field">
            <label htmlFor="save-name" className="field-label">Saved search name</label>
            <input
              id="save-name"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Optional"
              className="input"
              style={{ padding: "0.45rem 0.6rem", fontSize: "0.8rem" }}
            />
          </div>
          <button onClick={saveSearch} className="btn btn-secondary">
            Save this search
          </button>
        </div>
      </div>

      {error && (
        <div className="panel p-5 mb-6" style={{ borderColor: "var(--danger)" }} role="alert">
          <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
            Something went wrong
          </p>
          <p className="text-sm text-muted mb-3">{error}</p>
          <button onClick={loadRegions} className="btn btn-secondary text-xs">
            Try again
          </button>
        </div>
      )}

      {results && (
        <div className="panel p-5 mb-5">
          <h2 className="text-sm font-semibold text-main mb-3">Results ({results.length} new)</h2>
          {results.length === 0 ? (
            <p className="text-sm text-muted">No new opportunities found for this query — try broadening it.</p>
          ) : (
            <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
              {results.map((o) => (
                <li key={o.id} className="py-3 first:pt-0 last:pb-0">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm text-main font-medium">{o.title}</p>
                      <p className="text-xs text-muted mt-1">
                        {o.vertical ? VERTICAL_LABELS[o.vertical] : "—"} · {o.market ?? "—"}
                        {o.deadline ? ` · deadline ${o.deadline}` : ""}
                      </p>
                      <p className="text-sm text-muted mt-2">{o.summary}</p>
                    </div>
                    <ScoreBadge score={o.alignment_score} size="sm" />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {savedSearches.length > 0 && (
        <div className="panel p-5 mb-5">
          <h2 className="text-sm font-semibold text-main mb-3">Saved searches</h2>
          <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
            {savedSearches.map((s) => (
              <li key={s.id} className="flex items-center justify-between text-sm py-2 first:pt-0 last:pb-0">
                <div>
                  <span className="text-main font-medium">{s.name}</span>
                  <span className="text-muted"> — {REGION_LABELS[s.region]} — &ldquo;{s.query_text}&rdquo;</span>
                </div>
                <span className="badge badge-neutral">Saved</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel p-5">
        <h2 className="text-sm font-semibold text-main mb-3">Compare two markets</h2>
        <div className="flex flex-wrap items-end gap-3 mb-4">
          <div className="field">
            <label htmlFor="compare-a" className="field-label">Market A</label>
            <select id="compare-a" value={compareA} onChange={(e) => setCompareA(e.target.value as RegionKey)} className="input">
              {regions &&
                (Object.keys(regions) as RegionKey[]).map((r) => (
                  <option key={r} value={r}>{REGION_LABELS[r]}</option>
                ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="compare-b" className="field-label">Market B</label>
            <select id="compare-b" value={compareB} onChange={(e) => setCompareB(e.target.value as RegionKey)} className="input">
              {regions &&
                (Object.keys(regions) as RegionKey[]).map((r) => (
                  <option key={r} value={r}>{REGION_LABELS[r]}</option>
                ))}
            </select>
          </div>
          <button onClick={runComparison} className="btn btn-secondary">
            Compare
          </button>
        </div>
        {comparison && (
          <div className="grid grid-cols-2 gap-6 text-sm">
            {["a", "b"].map((key) => {
              const data = comparison[key];
              if (!data) return null;
              return (
                <div key={key}>
                  <p className="text-main font-medium mb-2">{REGION_LABELS[data.region as RegionKey] ?? data.region}</p>
                  <p className="text-muted">Opportunities: {data.count}</p>
                  <p className="text-muted">Value: ${Math.round(data.value).toLocaleString()}</p>
                  <p className="text-muted">Avg. score: {data.avg_score ?? "—"}</p>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
