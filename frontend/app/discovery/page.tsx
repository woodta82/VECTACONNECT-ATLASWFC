"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { CountryPicker, RegionSelect } from "@/components/Geo";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, Section } from "@/components/Ui";
import { RecentResearch, ResearchForm, ResearchResult, type Discovery, type DiscoveryDetail } from "@/components/Research";
import { api } from "@/lib/api";
import { MODULES } from "@/lib/constants";
import { dateTime, moduleLabel, money } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type GeoMode = "country" | "countries" | "region" | "worldwide";
type Purpose = "opportunities" | "companies" | "people" | "market";
const PURPOSES: { id: Purpose; label: string; hint: string }[] = [
  { id: "opportunities", label: "Opportunities", hint: "Tenders, mandates, partnerships, expansion, outsourcing, technology requirements and other evidenced commercial openings." },
  { id: "companies", label: "Companies", hint: "GSAs/GSSAs, airlines (passenger belly and cargo-only), forwarders, handlers, trucking providers, gateways and technology providers: who operates here and what they can do." },
  { id: "people", label: "People", hint: "Relevant individuals by company, role, geography and capability: who matters." },
  { id: "market", label: "Market intelligence", hint: "Routes, appointments, representation changes, investments, developments, market reports and emerging demand: what is changing. Never a tender." },
];
type Saved = { id: string; name: string; geo_mode: GeoMode; countries: string[]; regions: string[]; modules: string[]; keywords: string | null;
               purpose?: "opportunities" | "market" | null; brief?: string | null;
               last_run: { id: string; status: string; outcome: string | null; created_at: string } | null; queued_links?: number;
               schedule: { id: string; interval_minutes: number; enabled: boolean; next_run_at: string | null; timezone: string } | null };
type Options = {
  sources: { id: string; name: string; type: string; global: boolean; countries: string[]; modules: string[]; enabled: boolean }[];
  open_web: { connected: boolean; detail: string; provider: string | null; enabled: boolean };
  ai: { connected: boolean; detail: string; estimate_per_document_usd: string | null; kill_switch: boolean;
        budget: { cap_usd: string; spent_usd: string; reserved_usd: string } | null };
  saved: Saved[];
};
type Run = { id: string; search_name: string | null; source_name: string | null; trigger: string; status: string; outcome: string | null;
             created_at: string; finished_at: string | null; countries: string[] | string | null; counts: { matched?: number } | null;
             estimated_cost_usd: string | null; actual_cost_usd: string | null };

const GEO_MODES: { id: GeoMode; label: string }[] = [
  { id: "country", label: "One country" }, { id: "countries", label: "Several countries" }, { id: "region", label: "Region" },
  { id: "worldwide", label: "Worldwide" },
];

export default function DiscoveryPage() {
  const o = useApi<Options>("/discovery/options");
  const runs = useApi<{ items: Run[] }>("/discovery/runs?limit=15");
  const research = useApi<{ items: Discovery[] }>("/contacts/discoveries?limit=8");
  const people = useApi<{ capability_areas: Record<string, string> }>("/people?limit=1");
  const [purpose, setPurpose] = useState<Purpose>("opportunities");
  const [latest, setLatest] = useState<DiscoveryDetail | null>(null);
  const current = PURPOSES.find((p) => p.id === purpose)!;
  return (
    <>
      <PageHeader eyebrow="Discovery" title="Research the open market"
                  description="Who operates here, what can they do, who matters, what is changing and where could we create business — as well as finding formal tenders. Searches public information directly for the selected geography and capability areas: airline, airport and company sites, directories, public tender and procurement notices, newsrooms, trade publications, public reports and documents. Every page found is read itself; what it states, and what still needs confirmation, is recorded with its source. A search is never a complete view of a market." />
      <div className="panel" aria-label="Research purpose">
        <div className="field" id="purpose-label">What are you looking for?</div>
        <div className="segmented" role="group" aria-labelledby="purpose-label">
          {PURPOSES.map((p) => <button key={p.id} type="button" aria-pressed={purpose === p.id} onClick={() => { setPurpose(p.id); setLatest(null); }}>{p.label}</button>)}
        </div>
        <p className="small muted" style={{ marginTop: 8 }}>{current.hint} No tender or opportunity has to exist first.</p>
      </div>
      {(purpose === "companies" || purpose === "people") && (
        <div className="stack">
          <ResearchForm key={purpose} purpose={purpose} areas={people.data?.capability_areas ?? {}} onDone={(d) => { setLatest(d); research.reload(); }} />
          {latest && <ResearchResult d={latest} onContinue={async () => { const d = await api.post<DiscoveryDetail>(`/contacts/discoveries/${latest.id}/continue`); setLatest(d); research.reload(); }} />}
          <RecentResearch items={(research.data?.items ?? []).filter((d) => d.purpose === purpose)} onOpen={async (id) => setLatest(await api.get<DiscoveryDetail>(`/contacts/discoveries/${id}`))} />
          <p className="small muted">Results also appear in <Link href="/companies">Companies</Link> and <Link href="/relationships">Relationships</Link>.</p>
        </div>
      )}
      {(purpose === "opportunities" || purpose === "market") && <>
      {o.stale && <StaleBanner onRetry={o.reload} />}
      {o.status === "loading" && <Loading what="discovery options" />}
      {o.status === "error" && !o.data && <ErrorState error={o.error} onRetry={o.reload} />}
      {o.data && (
        <div className="stack">
          <SearchForm key={purpose} o={o.data} purpose={purpose} onSaved={o.reload} />
          <SavedSearches saved={o.data.saved} reload={() => { o.reload(); runs.reload(); }} />
          <Section title="Recent runs" actions={<Link className="btn" href="/sources">Manage sources</Link>}>
            {runs.data && runs.data.items.length === 0 && <Empty title="No searches run yet" />}
            {runs.data && runs.data.items.length > 0 && (
              <TableWrap label="Recent discovery runs">
                <table>
                  <thead><tr><th>Started</th><th>Search / source</th><th>Status</th><th>Outcome</th><th className="num">Matches</th><th className="num">Cost (USD)</th></tr></thead>
                  <tbody>{runs.data.items.map((r) => (
                    <tr key={r.id}>
                      <td><Link href={`/discovery/runs/${r.id}`}>{dateTime(r.created_at)}</Link><span className="muted small">{r.trigger}</span></td>
                      <td>{r.search_name ?? r.source_name ?? "Unsaved search"}
                        <span className="muted small">{Array.isArray(r.countries) ? r.countries.join(", ") : r.countries ?? ""}</span></td>
                      <td><Badge value={r.status} /></td>
                      <td>{r.outcome ? <Badge value={r.outcome} /> : "—"}</td>
                      <td className="num">{r.counts?.matched ?? "—"}</td>
                      <td className="num">{r.actual_cost_usd ?? "—"}<span className="muted small">est. {r.estimated_cost_usd ?? "n/a"}</span></td>
                    </tr>
                  ))}</tbody>
                </table>
              </TableWrap>
            )}
          </Section>
        </div>
      )}
      </>}
    </>
  );
}

function SearchForm({ o, purpose, onSaved }: { o: Options; purpose: "opportunities" | "market"; onSaved: () => void }) {
  const router = useRouter();
  const [brief, setBrief] = useState("");
  const [mode, setMode] = useState<GeoMode>("country");
  const [countries, setCountries] = useState<string[]>([]);
  const [region, setRegion] = useState("");
  const [modules, setModules] = useState<string[]>([]);
  const [organisation, setOrganisation] = useState("");
  const [airline, setAirline] = useState("");
  const [keywords, setKeywords] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [dateFilter, setDateFilter] = useState<"include_unknown" | "strict">("include_unknown");
  const [name, setName] = useState("");
  const a = useAction();

  const enabled = o.sources.filter((s) => s.enabled && s.type !== "web_search");
  const covering = enabled.filter((s) => mode === "worldwide" || s.global || (mode !== "region" && s.countries.some((c) => countries.includes(c))));
  const webOn = o.open_web.enabled && o.open_web.connected;
  const ready = mode === "worldwide" || (mode === "region" ? region !== "" : countries.length > 0);

  function body(save: boolean, runNow: boolean) {
    return { geo_mode: mode, countries: mode === "region" || mode === "worldwide" ? [] : countries, regions: mode === "region" ? [region] : [],
             modules, organisation: organisation || null, airline: airline || null, keywords: keywords || null, date_from: from || null,
             date_to: to || null, date_filter: dateFilter, name: name || null, save, run_now: runNow, purpose, brief: brief.trim() || null };
  }
  async function search(e: FormEvent) {
    e.preventDefault();
    const r = await a.run(() => api.post<{ run: { run_id: string } }>("/discovery/searches", body(Boolean(name), true)));
    if (r?.run) router.push(`/discovery/runs/${r.run.run_id}`);
  }
  async function saveOnly() {
    const r = await a.run(() => api.post("/discovery/searches", body(true, false)), "Search saved. Run or schedule it below.");
    if (r) onSaved();
  }
  return (
    <Section title={purpose === "market" ? "New market intelligence search" : "New opportunity search"}>
      {!o.open_web.connected && (
        <div className="notice" role="status" aria-label="Open-web search status">
          Open-web search is not configured on the server ({o.open_web.detail}). Only configured monitoring sources are searched until a search
          connector is set once, server-side (see <Link href="/settings">Settings</Link>, Service status). No tender-platform registration is needed.
        </div>
      )}
      {!o.ai.connected && (
        <div className="notice" role="status">
          AI extraction is not connected ({o.ai.detail}). Searches still retrieve and store documents; they wait in the
          <Link href="/review"> review queue</Link> for a reviewer to add claims.
        </div>
      )}
      {o.ai.connected && o.ai.kill_switch && (
        <div className="notice" role="status">The AI kill switch is on: documents will be retrieved but not extracted until it is lifted in Settings.</div>
      )}
      <form onSubmit={search} className="stack">
        <label className="field">Research brief (plain language, optional)
          <textarea className="input" rows={2} maxLength={600} value={brief} onChange={(e) => setBrief(e.target.value)}
                    placeholder={purpose === "market" ? "e.g. Find airline expansion announcements that could create representation opportunities" : "e.g. Identify providers and decision makers relevant to cargo booking technology"} />
        </label>
        <div>
          <div className="field" id="geo-mode-label">Geography</div>
          <div className="segmented" role="group" aria-labelledby="geo-mode-label">
            {GEO_MODES.map((g) => (
              <button key={g.id} type="button" aria-pressed={mode === g.id} onClick={() => { setMode(g.id); if (g.id === "country") setCountries(countries.slice(0, 1)); }}>
                {g.label}
              </button>
            ))}
          </div>
        </div>
        {(mode === "country" || mode === "countries") && (
          <CountryPicker value={countries} onChange={setCountries} max={mode === "country" ? 1 : 60} label={mode === "country" ? "Country" : "Countries"} />
        )}
        {mode === "region" && <RegionSelect value={region} onChange={setRegion} allowEmpty />}
        <fieldset className="plain">
          <legend className="field">Capability areas (none selected = all nine)</legend>
          <div className="check-grid">
            {MODULES.map((m) => (
              <label key={m}>
                <input type="checkbox" checked={modules.includes(m)}
                       onChange={(e) => setModules(e.target.checked ? [...modules, m] : modules.filter((x) => x !== m))} />
                {moduleLabel(m)}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="form-grid">
          <label className="field">Airline (optional)<input className="input" value={airline} onChange={(e) => setAirline(e.target.value)} placeholder="e.g. Example Air" /></label>
          <label className="field">Issuing organisation (optional)<input className="input" value={organisation} onChange={(e) => setOrganisation(e.target.value)} /></label>
          <label className="field">Keywords (optional, results must contain one)<input className="input" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="e.g. GSSA, appel d'offres" /></label>
          <label className="field">Published from<input className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
          <label className="field">Published to<input className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          {(from || to) && (
            <label className="field">Documents with no known publication date
              <select className="input" value={dateFilter} onChange={(e) => setDateFilter(e.target.value === "strict" ? "strict" : "include_unknown")}>
                <option value="include_unknown">Include them, marked &quot;date unknown&quot;</option>
                <option value="strict">Exclude them (listed on the run)</option>
              </select>
            </label>
          )}
          <label className="field">Name (to save this search)<input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. East Africa GSSA tenders" /></label>
        </div>
        <p className="muted small" role="status">
          {ready ? (webOn ? `Public web search for this geography and the selected capability areas${covering.length ? `, plus ${covering.length} configured monitoring source(s)` : ""}.${purpose === "market" ? " Market intelligence: procurement-portal search templates are not used; results are market signals, kept apart from opportunities and tenders." : ""}`
                          : `Open-web search is not configured. ${covering.length} configured monitoring source(s) cover this selection${covering.length === 0 ? ": nothing would be searched" : ""}.`)
                 : "Select the geography to search."}
          {o.ai.estimate_per_document_usd && ` Up to ${money(o.ai.estimate_per_document_usd, "USD")} AI cost per new document. Each run gets one approved ceiling (its upper-bound estimate, capped by the per-run limit); every call, retry and re-extraction for the run counts against it.`}
        </p>
        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={!ready || a.busy}>{a.busy ? "Starting…" : "Search now"}</button>
          <button className="btn" type="button" onClick={saveOnly} disabled={!ready || !name.trim() || a.busy}>Save search</button>
        </div>
        <ActionNote state={a} />
      </form>
    </Section>
  );
}

function SavedSearches({ saved, reload }: { saved: Saved[]; reload: () => void }) {
  const router = useRouter();
  const a = useAction();
  const [interval, setIntervalMin] = useState<Record<string, string>>({});
  if (saved.length === 0) return null;
  return (
    <Section title="Saved searches">
      <TableWrap label="Saved searches">
        <table>
          <thead><tr><th>Name</th><th>Scope</th><th>Last run</th><th>Schedule</th><th /></tr></thead>
          <tbody>{saved.map((s) => (
            <tr key={s.id}>
              <td>{s.name}{s.purpose === "market" && <span className="muted small">Market intelligence</span>}</td>
              <td>{s.geo_mode === "worldwide" ? "Worldwide" : [...s.countries, ...s.regions].join(", ")}
                <span className="muted small">{s.modules.length ? s.modules.map(moduleLabel).join(", ") : "All capability areas"}</span></td>
              <td>{s.last_run ? <Link href={`/discovery/runs/${s.last_run.id}`}><Badge value={s.last_run.outcome ?? s.last_run.status} /></Link> : "Never"}
                {(s.queued_links ?? 0) > 0 && <div className="small">{s.queued_links} link(s) queued for the next run</div>}</td>
              <td>{s.schedule ? (
                <>Every {s.schedule.interval_minutes} min <Badge value={s.schedule.enabled ? "ready" : "parked"} />
                  <span className="muted small">next {dateTime(s.schedule.next_run_at)}</span></>
              ) : (
                <span className="inline">
                  <select className="select" aria-label={`Schedule interval for ${s.name}`} value={interval[s.id] ?? "1440"}
                          onChange={(e) => setIntervalMin({ ...interval, [s.id]: e.target.value })} style={{ width: "auto" }}>
                    <option value="360">Every 6 hours</option><option value="1440">Daily</option><option value="10080">Weekly</option>
                  </select>
                  <button className="btn" type="button" disabled={a.busy}
                          onClick={() => a.run(() => api.post(`/discovery/searches/${s.id}/schedule`, { interval_minutes: Number(interval[s.id] ?? "1440"), timezone: "Asia/Dubai", enabled: true }), "Schedule created").then(reload)}>
                    Schedule
                  </button>
                </span>
              )}</td>
              <td className="actions">
                <button className="btn" type="button" disabled={a.busy}
                        onClick={async () => { const r = await a.run(() => api.post<{ run_id: string }>(`/discovery/searches/${s.id}/run`)); if (r) router.push(`/discovery/runs/${r.run_id}`); }}>
                  Run now
                </button>
              </td>
            </tr>
          ))}</tbody>
        </table>
      </TableWrap>
      <ActionNote state={a} />
    </Section>
  );
}
