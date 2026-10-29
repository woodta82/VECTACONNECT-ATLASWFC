"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { countryName, useGeography } from "@/components/Geo";
import { Badge, Empty, ErrorState, Loading, PageHeader, StaleBanner, TableWrap } from "@/components/States";
import { ActionNote, Section } from "@/components/Ui";
import { api } from "@/lib/api";
import { dateTime, deadline, moduleLabel, type DeadlineInfo } from "@/lib/format";
import { useAction } from "@/lib/useAction";
import { useApi } from "@/lib/useApi";

type Match = {
  geography_basis: "scope" | "issuer_only" | "worldwide"; geography: { country: string; name: string; role: string }[];
  withdrawn?: boolean; withdrawn_reason?: string; withdrawn_at?: string; previous_geography?: { country: string; name: string; role: string }[];
  all_countries: { country: string; role: string; support: string }[]; capability_area: string; related_areas: string[];
  classification: string; published_at: string | null; deadline_utc: string | null; deadline_source_tz: string | null; deadline: DeadlineInfo | null;
  tender_status: string | null; qualification_status: string | null;
  confidence: { independent_families: number; best_authority: string | null; claims_supported: number }; date_note?: string;
  gaps: string[]; recommended_next_action: string; sources: string[];
};
type Issue = { url: string; reason: string; detail: string | null; country: string | null };
const ISSUE: Record<string, { label: string; material: boolean }> = {
  retrieval_failed: { label: "Retrieval failed", material: true },
  language_not_permitted: { label: "Language not permitted for this source", material: true },
  extraction_not_run: { label: "Not extracted", material: true },
  extraction_rejected: { label: "All proposed claims rejected", material: true },
  not_fetched_limit: { label: "Not fetched (per-run limit)", material: true },
  budget_run_cap: { label: "Not extracted (run budget ceiling reached)", material: true },
  source_disabled: { label: "Source disabled after planning; not searched", material: true },
  document_partially_read: { label: "Document only partly read (resumes next run)", material: true },
  search_not_configured: { label: "Open-web search not configured on the server", material: true },
  search_failed: { label: "Public web search failed", material: true },
  access_restricted: { label: "Registration, login or payment required: not read", material: false },
  listing_links_not_followed: { label: "Further links on a listing page not followed", material: false },
  date_unknown_excluded: { label: "Excluded: publication date unknown (strict date filter)", material: false },
  some_claims_rejected: { label: "Some proposed claims rejected to review", material: false },
};

type Detail = {
  run: { id: string; status: string; outcome: string | null; trigger: string; created_at: string; started_at: string | null; finished_at: string | null;
         error: string | null; estimated_cost_usd: string | null; actual_cost_usd: string | null; budget_cap_usd: string | null;
         budget_root_id: string | null;
         plan: { countries: string[] | "worldwide"; modules: string[] | "all"; sources: { id: string; name: string; authority: string }[];
                 coverage_gaps: string[]; coverage_note: string; ai_status: string; max_documents?: number; run_budget_cap_usd?: string | null;
                 open_web?: { planned: boolean; connected: boolean; reason: string | null; provider: string | null; queries: number; countries: number } };
         progress: { sources_total?: number; sources_done?: number; documents_seen?: number; documents_new?: number; current_source?: string | null };
         counts: { matched?: number; documents?: number; new_documents?: number; claims?: number; rejected_claims?: number; unextracted?: number;
                   failed_sources?: number; skipped_out_of_range?: number; skipped_language?: number; flags?: string[];
                   not_searched_countries?: string[]; documents_not_fetched?: number; date_unknown?: number;
                   issues?: Issue[]; issue_counts?: Record<string, number>;
                   web_searches?: { purpose: string; query: string; country: string | null; status: string; results: number; link: string; reason?: string }[];
                   restricted?: { url: string; title: string | null; restriction: string; label: string; country: string | null; corroboration: string | null }[];
                   restricted_count?: number;
                   coverage?: { planned: string[]; attempted: string[]; retrieved: string[]; extracted: string[]; not_attempted: string[] };
                   queue?: { pending: number; gave_up: number; resumed: number }; partially_read?: number } };
  search: { id: string; name: string | null; saved: boolean; keywords: string | null; airline: string | null; organisation: string | null } | null;
  sources: { source_id: string; name: string; authority: string; status: string; detail: string | null; documents: number; new_documents: number; failures: number }[];
  results: { signal_id: string; opportunity_id: string | null; is_new: boolean; title: string; classification: string; module: string;
             qualification_status: string | null; match: Match }[];
};

const OUTCOME: Record<string, { tone: string; title: string; text: string }> = {
  results: { tone: "good", title: "Results found", text: "Every planned search and source ran and every new document was read in full." },
  no_relevant_results: { tone: "none", title: "No relevant results", text: "The searches and sources ran successfully and nothing matched. This covers only what was searched, listed below; it is not a complete view of the market." },
  partial_coverage: { tone: "warn", title: "Partial coverage", text: "Some selected countries have no enabled source. Nothing was searched for them." },
  source_failure: { tone: "bad", title: "Source failure", text: "Every planned source failed. This is not an absence of opportunities." },
  incomplete: { tone: "warn", title: "Incomplete search", text: "Some sources failed, some documents could not be extracted, or the per-run limits were reached. Results may be missing." },
  no_sources: { tone: "none", title: "Nothing searched", text: "No enabled source covers this search. This is not an absence of opportunities: add or enable a source for these countries." },
  cancelled: { tone: "none", title: "Cancelled", text: "The run was cancelled before it finished." },
  search_not_configured: { tone: "bad", title: "Open-web search not configured", text: "No public web search was run because no search connector is configured on the server (Settings → Service status). This is not an absence of opportunities. The searches are listed below with links to open yourself." },
  search_failure: { tone: "bad", title: "Search failure", text: "Every public web search failed. This is not an absence of opportunities." },
  inaccessible_sources: { tone: "warn", title: "Some sources inaccessible", text: "Some results need registration, login or payment: they were labelled and not read; a public original was searched for." },
};

export default function RunPage() {
  const { id = "" } = useParams<{ id: string }>();
  const r = useApi<Detail>(id ? `/discovery/runs/${id}` : null);
  const live = r.data && ["queued", "running"].includes(r.data.run.status);
  useEffect(() => {
    if (!live) return;
    const t = window.setInterval(r.reload, 2000);
    return () => window.clearInterval(t);
  }, [live, r.reload]);
  return (
    <>
      {r.stale && <StaleBanner onRetry={r.reload} />}
      {r.status === "loading" && <Loading what="discovery run" />}
      {r.status === "error" && !r.data && <ErrorState error={r.error} onRetry={r.reload} />}
      {r.data && <Body d={r.data} reload={r.reload} />}
    </>
  );
}

function Body({ d, reload }: { d: Detail; reload: () => void }) {
  useGeography();   // loads country names for countryName()
  const router = useRouter();
  const a = useAction();
  const run = d.run;
  const p = run.progress ?? {};
  const pct = p.sources_total ? Math.round(((p.sources_done ?? 0) / p.sources_total) * 100) : run.status === "queued" ? 0 : 100;
  const countries = run.plan.countries === "worldwide" ? "Worldwide" : run.plan.countries.map((c) => `${countryName(c)} (${c})`).join(", ");
  const out = run.outcome ? OUTCOME[run.outcome] : null;
  const flags = run.counts?.flags ?? [];
  return (
    <div className="stack">
      <PageHeader eyebrow="Discovery run" title={d.search?.name ?? "Country search"}
                  description={`${countries} · ${run.plan.modules === "all" ? "All capability areas" : run.plan.modules.map(moduleLabel).join(", ")}${d.search?.keywords ? ` · keywords: ${d.search.keywords}` : ""}`}
                  actions={<>
                    <Link className="btn" href="/discovery">New search</Link>
                    {["queued", "running"].includes(run.status) && (
                      <button className="btn btn-danger" type="button" disabled={a.busy} onClick={() => a.run(() => api.post(`/discovery/runs/${run.id}/cancel`), "Cancelled").then(reload)}>Cancel</button>
                    )}
                    {["failed", "partial", "cancelled"].includes(run.status) && (
                      <button className="btn" type="button" disabled={a.busy}
                              onClick={async () => { const r = await a.run(() => api.post<{ run_id: string }>(`/discovery/runs/${run.id}/retry`)); if (r) router.push(`/discovery/runs/${r.run_id}`); }}>
                        Retry
                      </button>
                    )}
                    {run.finished_at && <a className="btn" href={`/api/discovery/runs/${run.id}/results.csv`}>Export CSV</a>}
                  </>} />
      <ActionNote state={a} />
      {["queued", "running"].includes(run.status) && (
        <section className="panel" aria-live="polite">
          <div className="inline"><Badge value={run.status} /> {p.current_source ? `Searching ${p.current_source}` : "Waiting for a worker"}</div>
          <div className="progress" style={{ marginTop: 10 }} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${pct}%` }} /></div>
          <p className="muted small">{p.sources_done ?? 0} of {p.sources_total ?? run.plan.sources.length} source(s) · {p.documents_seen ?? 0} document(s) read, {p.documents_new ?? 0} new</p>
        </section>
      )}
      {out && (
        <div className={`outcome outcome-${out.tone}`} role="status">
          <strong>{out.title}</strong>{out.text}
          {flags.some((f) => f !== run.outcome) && <div className="small">Also: {flags.filter((f) => f !== run.outcome).map((f) => OUTCOME[f]?.text ? `${OUTCOME[f].title}: ${OUTCOME[f].text}` : f).join(" ")}</div>}
          {run.counts?.not_searched_countries?.length ? <div className="small">Not reached this run (per-run limit): {run.counts.not_searched_countries.map(countryName).join(", ")}.</div> : null}
          {run.counts?.documents_not_fetched ? <div className="small">{run.counts.documents_not_fetched} linked document(s) not fetched this run (per-run limit).</div> : null}
          {run.error && <div className="small">Error: {run.error}</div>}
        </div>
      )}
      <div className="grid grid-4">
        <div className="stat"><div className="stat-label">Matches</div><div className="stat-value">{run.counts?.matched ?? "—"}</div>
          <div className="stat-note" data-testid="match-breakdown">{d.results.filter((x) => x.is_new).length} new this run · {d.results.filter((x) => x.classification === "qualified_opportunity").length} qualified · {d.results.filter((x) => x.classification === "freight_candidate").length} freight candidate(s) · {d.results.filter((x) => x.classification === "excluded").length} excluded (not freight, kept with reason) · {d.results.filter((x) => x.classification === "historical_record").length} historical record(s) (cancelled, awarded or closed; not actionable)</div></div>
        <div className="stat"><div className="stat-label">Documents</div><div className="stat-value">{run.counts?.documents ?? p.documents_seen ?? "—"}</div>
          <div className="stat-note">{run.counts?.new_documents ?? 0} new · {run.counts?.unextracted ?? 0} not extracted</div></div>
        <div className="stat"><div className="stat-label">Claims</div><div className="stat-value">{run.counts?.claims ?? "—"}</div>
          <div className="stat-note">{run.counts?.rejected_claims ?? 0} rejected to review</div></div>
        <div className="stat"><div className="stat-label">AI cost (USD)</div><div className="stat-value">{run.actual_cost_usd ?? "—"}</div>
          <div className="stat-note">estimate ≤ {run.estimated_cost_usd ?? "n/a"}{run.plan.max_documents != null ? ` for at most ${run.plan.max_documents} document(s)` : ""}
            {" · "}{run.budget_root_id ? "spends against the original run's ceiling" : `approved ceiling ${run.budget_cap_usd ?? "none"}`}</div></div>
      </div>
      <p className="muted small">{run.plan.coverage_note} AI extraction: {run.plan.ai_status}.
        {run.plan.coverage_gaps.length > 0 && ` No source covers: ${run.plan.coverage_gaps.map(countryName).join(", ")}.`}</p>

      <Section title={`Matches (${d.results.length}: ${d.results.filter((x) => x.classification === "excluded").length} excluded)`}>
        {d.results.length === 0 ? <Empty title={run.finished_at ? "No matching signals" : "No matches yet"}>
          {run.finished_at ? "Nothing retrieved in this run matched the geography and filters." : "Results appear as sources are processed."}</Empty> : (
          <TableWrap label="Matching signals">
            <table>
              <thead><tr><th>Signal</th><th>Why it matches</th><th>Deadline</th><th>Status</th><th>Evidence</th><th>Next action</th></tr></thead>
              <tbody>{d.results.map((x) => {
                const m = x.match;
                return (
                  <tr key={x.signal_id}>
                    <td>{x.opportunity_id ? <Link href={`/opportunities/${x.opportunity_id}`}>{x.title}</Link> : x.title}
                      <span className="small">{x.is_new ? <Badge value="new" /> : <span className="muted">seen before</span>} {moduleLabel(m.capability_area)}</span></td>
                    <td>{m.withdrawn ? <><Badge value="withdrawn" /><div className="why">Match withdrawn after a re-check: {m.withdrawn_reason}. Previously {(m.previous_geography ?? m.geography).map((g) => `${g.name}: ${g.role.replace("_", " ")}`).join("; ") || "—"}</div></> : <><Badge value={m.geography_basis} />
                      <div className="why">{m.geography.map((g) => `${g.name}: ${g.role.replace("_", " ")}`).join("; ")}</div></>}
                      <div className="why">Sources: {m.sources.join(", ")}{m.published_at ? ` · published ${dateTime(m.published_at)}` : " · publication date unknown"}</div>
                      {m.date_note && <div className="why"><Badge value="date unknown" /> {m.date_note}</div>}</td>
                    <td>{deadline(m.deadline_utc, m.deadline_source_tz, m.deadline)}</td>
                    <td><Badge value={x.classification} />{m.tender_status && <div className="small">Tender: <Badge value={m.tender_status} /></div>}
                      {x.qualification_status && <div className="small">Qualification: <Badge value={x.qualification_status} /></div>}</td>
                    <td className="small">{m.confidence.independent_families} independent famil{m.confidence.independent_families === 1 ? "y" : "ies"} · best source: {m.confidence.best_authority?.replace("_", " ") ?? "none"}
                      {m.gaps.length > 0 && <div className="why">Gaps: {m.gaps.join("; ")}</div>}</td>
                    <td className="small">{m.recommended_next_action}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </TableWrap>
        )}
      </Section>

      {run.counts?.queue && (run.counts.queue.pending > 0 || run.counts.queue.resumed > 0 || run.counts.queue.gave_up > 0) && (
        <Section title="Remaining work">
          <p className={run.counts.queue.pending > 0 ? "notice" : "muted small"} role="status">
            {run.counts.queue.resumed > 0 && `${run.counts.queue.resumed} link(s) queued by earlier runs were read first. `}
            {run.counts.queue.pending > 0
              ? `${run.counts.queue.pending} relevant link(s) are queued and not yet read; this search is not complete. The next run of this search reads them first.`
              : "No relevant links are waiting."}
            {run.counts.queue.gave_up > 0 && ` ${run.counts.queue.gave_up} link(s) were given up after repeated retrieval failures and are listed below.`}
          </p>
          {run.counts.queue.gave_up > 0 && (d.search || d.run.plan.sources.length === 1) && (
            <button className="btn" type="button" disabled={a.busy}
                    onClick={() => a.run(() => api.post<{ requeued: number }>(d.search ? `/discovery/searches/${d.search.id}/queue/retry`
                                                                                         : `/sources/${d.run.plan.sources[0]?.id}/queue/retry`),
                                         (x) => `${x.requeued} link(s) queued again for the next run`)}>
              Queue given-up links again
            </button>
          )}
        </Section>
      )}
      {(run.counts?.web_searches?.length ?? 0) > 0 && <WebSearches items={run.counts?.web_searches ?? []} restricted={run.counts?.restricted ?? []} />}
      {run.counts?.coverage && <Coverage c={run.counts.coverage} notSearched={run.counts.not_searched_countries ?? []} />}
      {(run.counts?.issues?.length ?? 0) > 0 && <Issues issues={run.counts?.issues ?? []} counts={run.counts?.issue_counts ?? {}} />}

      <Section title="Sources searched">
        {d.sources.length === 0 && run.plan.sources.length === 0 ? <Empty title="No source covered this search" /> : (
          <TableWrap label="Sources in this run">
            <table>
              <thead><tr><th>Source</th><th>Authority</th><th>Status</th><th className="num">Documents</th><th>Detail</th></tr></thead>
              <tbody>{run.plan.sources.map((s) => {
                const rs = d.sources.find((x) => x.source_id === s.id);
                return (
                  <tr key={s.id}>
                    <td><Link href={`/sources/${s.id}`}>{s.name}</Link></td><td>{s.authority.replace("_", " ")}</td>
                    <td><Badge value={rs?.status ?? (run.finished_at ? "skipped" : "pending")} /></td>
                    <td className="num">{rs ? `${rs.documents} (${rs.new_documents} new)` : "—"}</td>
                    <td className="small">{rs?.detail ?? ""}</td>
                  </tr>
                );
              })}</tbody>
            </table>
          </TableWrap>
        )}
      </Section>
      <p className="muted small">Started {dateTime(run.started_at ?? run.created_at)}{run.finished_at && ` · finished ${dateTime(run.finished_at)}`} · trigger: {run.trigger}</p>
    </div>
  );
}

function Coverage({ c, notSearched }: { c: NonNullable<NonNullable<Detail["run"]["counts"]>["coverage"]>; notSearched: string[] }) {
  const rows: [string, string[], string][] = [
    ["Planned", c.planned, "countries the selected sources cover for this search"],
    ["Attempted", c.attempted, "a query or page was requested"],
    ["Retrieved", c.retrieved, "the source answered"],
    ["Extracted", c.extracted, "at least one document was fully processed"],
  ];
  const remaining = Array.from(new Set([...c.not_attempted, ...notSearched])).sort();
  return (
    <Section title="Coverage">
      <TableWrap label="Coverage by stage">
        <table>
          <thead><tr><th>Stage</th><th className="num">Countries</th><th>Meaning</th></tr></thead>
          <tbody>{rows.map(([label, list, meaning]) => (
            <tr key={label}><td>{label}</td><td className="num">{list.length}</td><td className="small">{meaning}</td></tr>
          ))}</tbody>
        </table>
      </TableWrap>
      {remaining.length > 0 && (
        <p className="small"><strong>Not searched in this run:</strong> {remaining.map(countryName).join(", ")}.
          {notSearched.length > 0 && " The next run of this saved search continues from here."}</p>
      )}
    </Section>
  );
}

type WebSearch = NonNullable<NonNullable<Detail["run"]["counts"]>["web_searches"]>[number];
type Restricted = NonNullable<NonNullable<Detail["run"]["counts"]>["restricted"]>[number];
/** What the open web was asked, with what each search returned; and the results that could not be read because of a restriction. */
function WebSearches({ items, restricted }: { items: WebSearch[]; restricted: Restricted[] }) {
  const run = items.filter((w) => w.status === "run");
  const notRun = items.filter((w) => w.status === "not_run");
  const failed = items.filter((w) => w.status === "failed");
  return (
    <Section title="Public web searches">
      <p className="muted small">{run.length} run ({run.reduce((n, w) => n + w.results, 0)} result page(s)) · {notRun.length} not run · {failed.length} failed.
        Every result page is fetched and read itself; search snippets are never used as evidence.</p>
      <details className="small" open={notRun.length > 0 || failed.length > 0}>
        <summary>Searches ({items.length})</summary>
        <ul className="list-plain">{items.map((w, i) => (
          <li key={`${w.query}-${i}`}><Badge value={w.status === "run" ? "run" : w.status === "failed" ? "failed" : "not run"} /> {w.purpose}:{" "}
            <a href={w.link} target="_blank" rel="noreferrer noopener">{w.query}</a>
            <span className="muted"> · {w.status === "run" ? `${w.results} result(s)` : w.reason ?? ""}</span></li>))}</ul>
      </details>
      {restricted.length > 0 && (
        <details className="small" open>
          <summary>Restricted results ({restricted.length}): labelled, not read, never bypassed</summary>
          <ul className="list-plain">{restricted.map((r) => (
            <li key={r.url}><Badge value="restricted" /> <a href={r.url} target="_blank" rel="noreferrer noopener">{r.title ?? r.url}</a>
              <span className="muted"> · {r.label}{r.corroboration ? ` · public original or corroboration: ${r.corroboration}` : ""}</span></li>))}</ul>
        </details>
      )}
    </Section>
  );
}

function Issues({ issues, counts }: { issues: Issue[]; counts: Record<string, number> }) {
  const total = Object.values(counts).reduce((x, y) => x + y, 0);
  const material = Object.entries(counts).filter(([r]) => ISSUE[r]?.material !== false).reduce((x, [, n]) => x + n, 0);
  return (
    <Section title={material > 0 ? `Not fully processed (${material})` : `Notes on this run (${total})`}>
      <p className="muted small">{Object.entries(counts).map(([r, n]) => `${n} × ${ISSUE[r]?.label ?? r}`).join(" · ")}
        {issues.length < total ? ` · first ${issues.length} listed` : ""}.
        {material > 0 ? " Retry runs these again within the same budget ceiling." : " Nothing material was left unprocessed."}</p>
      <TableWrap label="Targets not fully processed">
        <table>
          <thead><tr><th>Reason</th><th>Target</th><th>Country</th><th>Detail</th></tr></thead>
          <tbody>{issues.map((i, n) => (
            <tr key={`${i.url}-${i.reason}-${n}`}>
              <td><Badge value={ISSUE[i.reason]?.material === false ? "info" : "incomplete"} /> {ISSUE[i.reason]?.label ?? i.reason}</td>
              <td className="small"><a href={i.url} rel="noopener noreferrer" target="_blank">{i.url}</a></td>
              <td>{i.country ? countryName(i.country) : "—"}</td>
              <td className="small">{i.detail ?? ""}</td>
            </tr>
          ))}</tbody>
        </table>
      </TableWrap>
    </Section>
  );
}
