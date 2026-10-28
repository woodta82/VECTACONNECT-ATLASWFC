"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  api,
  REGION_LABELS,
  STAGE_LABELS,
  STAGE_ORDER,
  VERTICAL_LABELS,
  VERTICAL_POSITIONING,
  type Contact,
  type Opportunity,
  type OpportunityActivity,
  type Stage,
} from "@/lib/api";
import PageHeader from "../../components/PageHeader";
import ScoreBadge from "../../components/ScoreBadge";
import { useToast } from "../../components/ToastProvider";

const DIMENSION_LABELS: Record<string, string> = {
  vertical_fit: "Vertical fit (30%)",
  commercial_value: "Commercial value (25%)",
  regional_relevance: "Regional relevance (20%)",
  deliverability: "Deliverability (15%)",
  loop_value: "Loop value (10%)",
};

export default function OpportunityDetail() {
  const { id } = useParams<{ id: string }>();
  const { showUndo } = useToast();
  const [opp, setOpp] = useState<Opportunity | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [activity, setActivity] = useState<OpportunityActivity[]>([]);
  const [similar, setSimilar] = useState<Opportunity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingStage, setPendingStage] = useState<Stage | null>(null);
  const [reasonInput, setReasonInput] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);

  function load() {
    api
      .opportunity(id)
      .then((o) => {
        setOpp(o);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load opportunity"));
    api.contacts({ opportunityId: id }).then(setContacts).catch(() => {});
    api.opportunityActivity(id).then(setActivity).catch(() => {});
    api.similarOpportunities(id).then(setSimilar).catch(() => {});
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (error) {
    return (
      <div className="panel p-5" style={{ borderColor: "var(--danger)" }} role="alert">
        <p className="text-sm font-semibold mb-1" style={{ color: "var(--danger)" }}>
          Couldn&apos;t load this opportunity
        </p>
        <p className="text-sm text-muted mb-3">{error}</p>
        <button onClick={load} className="btn btn-secondary text-xs">
          Try again
        </button>
      </div>
    );
  }
  if (!opp) return <p className="text-sm text-muted">Loading…</p>;

  async function changeStage(stage: Stage) {
    if ((stage === "won" || stage === "lost") && stage !== opp?.stage) {
      setPendingStage(stage);
      setReasonInput("");
      return;
    }
    const previousStage = opp?.stage;
    await api.updateStage(id, stage);
    load();
    if (previousStage && previousStage !== stage) {
      showUndo(`Moved to ${STAGE_LABELS[stage]}`, async () => {
        await api.updateStage(id, previousStage);
        load();
      });
    }
  }

  async function confirmPendingStage() {
    if (!pendingStage) return;
    const previousStage = opp?.stage;
    await api.updateStage(id, pendingStage, reasonInput.trim() || undefined);
    const movedTo = pendingStage;
    setPendingStage(null);
    setReasonInput("");
    load();
    if (previousStage) {
      showUndo(`Moved to ${STAGE_LABELS[movedTo]}`, async () => {
        await api.updateStage(id, previousStage);
        load();
      });
    }
  }

  async function discoverContacts() {
    if (!opp?.organisation_name) return;
    setDiscovering(true);
    setDiscoverError(null);
    try {
      await api.discoverContacts({
        organisation_name: opp.organisation_name,
        region: opp.region ?? undefined,
        vertical: opp.vertical ?? undefined,
        opportunity_id: opp.id,
      });
      load();
    } catch (e) {
      setDiscoverError(e instanceof Error ? e.message : "Contact discovery failed");
    } finally {
      setDiscovering(false);
    }
  }

  const meta = [
    opp.vertical ? `${VERTICAL_LABELS[opp.vertical]} — ${VERTICAL_POSITIONING[opp.vertical]}` : "Unclassified",
    opp.region ? REGION_LABELS[opp.region] : null,
    opp.market,
    opp.deadline ? `deadline ${opp.deadline}` : null,
  ].filter(Boolean);

  return (
    <div>
      <PageHeader
        eyebrow={opp.vertical ? VERTICAL_LABELS[opp.vertical] : "Opportunity"}
        title={opp.title}
        back={{ label: "Back to pipeline", href: "/opportunities" }}
        actions={<ScoreBadge score={opp.alignment_score} />}
      />
      <p className="text-xs text-muted -mt-4 mb-6">
        {meta.join(" · ")}
        {opp.organisation_name && opp.organisation_id ? (
          <>
            {" · "}
            <Link href={`/organisations/${opp.organisation_id}`} className="text-accent hover:underline">
              {opp.organisation_name}
            </Link>
          </>
        ) : null}
      </p>
      {opp.outcome_reason && (opp.stage === "won" || opp.stage === "lost") && (
        <p className="text-xs mb-6 -mt-4" style={{ color: opp.stage === "won" ? "var(--success)" : "var(--danger)" }}>
          {opp.stage === "won" ? "Won" : "Lost"} — {opp.outcome_reason}
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 space-y-5">
          <section className="panel p-5">
            <h2 className="text-sm font-semibold text-main mb-2.5">Summary</h2>
            <p className="text-sm leading-relaxed text-muted">{opp.summary}</p>
            {opp.value_estimate != null && (
              <p className="text-sm text-main mt-3">
                Estimated value: <span className="text-accent font-semibold">${Math.round(opp.value_estimate).toLocaleString()}</span>
              </p>
            )}
          </section>

          <section className="panel p-5">
            <h2 className="text-sm font-semibold text-main mb-3">VECTA Alignment Score breakdown</h2>
            <div className="space-y-3">
              {Object.entries(opp.score_breakdown).map(([key, value]) => (
                <div key={key}>
                  <div className="flex justify-between text-xs text-muted mb-1">
                    <span>{DIMENSION_LABELS[key] ?? key}</span>
                    <span>{value}/100</span>
                  </div>
                  <div
                    className="h-1.5 rounded-full"
                    style={{ background: "var(--panel-raised)" }}
                    role="progressbar"
                    aria-valuenow={value as number}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={DIMENSION_LABELS[key] ?? key}
                  >
                    <div className="h-1.5 rounded-full" style={{ width: `${value}%`, background: "var(--accent)" }} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel p-5">
            <h2 className="text-sm font-semibold text-main mb-2.5">Sources</h2>
            {opp.source_urls.length === 0 ? (
              <p className="text-sm text-muted">No sources recorded.</p>
            ) : (
              <ul className="space-y-1.5">
                {opp.source_urls.map((url) => (
                  <li key={url}>
                    <a href={url} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline break-all">
                      {url}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="panel p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-main">Linked contacts</h2>
              <button onClick={discoverContacts} disabled={discovering || !opp.organisation_name} className="btn btn-secondary text-xs">
                {discovering ? "Searching…" : "Discover contacts"}
              </button>
            </div>
            {discoverError && (
              <p className="text-xs mb-3" style={{ color: "var(--danger)" }}>
                {discoverError}
              </p>
            )}
            {contacts.length === 0 ? (
              <p className="text-sm text-muted">
                No contacts identified yet.{" "}
                {opp.organisation_name
                  ? "Tap \"Discover contacts\" to search — this is a manual action and will use API credit."
                  : "No organisation is linked to this opportunity yet, so there's nothing to search against."}
              </p>
            ) : (
              <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
                {contacts.map((c) => (
                  <li key={c.id}>
                    <Link
                      href={`/relationships/${c.id}`}
                      className="flex items-center justify-between py-2.5 first:pt-0 last:pb-0 hover:text-accent"
                    >
                      <div>
                        <p className="text-sm text-main font-medium">{c.name}</p>
                        <p className="text-xs text-muted">{c.role ?? "Role unknown"}</p>
                      </div>
                      <span className="text-xs text-accent">{c.relevance_score}/100</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {similar.length > 0 && (
            <section className="panel p-5">
              <h2 className="text-sm font-semibold text-main mb-1">Similar opportunities</h2>
              <p className="text-xs text-muted mb-3">
                Same organisation, or same vertical and region — check these aren&apos;t the same relationship
                counted twice in pipeline value.
              </p>
              <ul className="divide-y" style={{ borderColor: "var(--border)" }}>
                {similar.map((s) => (
                  <li key={s.id}>
                    <Link
                      href={`/opportunities/${s.id}`}
                      className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0 hover:text-accent"
                    >
                      <div className="min-w-0">
                        <p className="text-sm text-main font-medium truncate">{s.title}</p>
                        <p className="text-xs text-muted">
                          {s.organisation_name ?? (s.vertical ? VERTICAL_LABELS[s.vertical] : "—")}
                        </p>
                      </div>
                      <ScoreBadge score={s.alignment_score} size="sm" />
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className="panel p-5 h-fit">
          <h2 className="text-sm font-semibold text-main mb-3" id="stage-heading">Stage</h2>
          <div className="space-y-1.5" role="group" aria-labelledby="stage-heading">
            {STAGE_ORDER.map((s) => (
              <button
                key={s}
                onClick={() => changeStage(s)}
                aria-pressed={opp.stage === s}
                className="w-full text-left rounded-lg px-3 py-2 text-sm font-medium transition-colors"
                style={{
                  background: opp.stage === s ? "var(--accent)" : "transparent",
                  color: opp.stage === s ? "#fff" : "var(--text)",
                  border: `1px solid ${opp.stage === s ? "var(--accent)" : "var(--border-strong)"}`,
                }}
              >
                {STAGE_LABELS[s]}
              </button>
            ))}
          </div>

          {pendingStage && (
            <div className="mt-4 pt-4 border-t" style={{ borderColor: "var(--border)" }}>
              <label htmlFor="outcome-reason" className="field-label">
                Why {pendingStage === "won" ? "won" : "lost"}? (optional)
              </label>
              <input
                id="outcome-reason"
                value={reasonInput}
                onChange={(e) => setReasonInput(e.target.value)}
                placeholder={pendingStage === "won" ? "e.g. strong relationship, best value" : "e.g. budget, competitor, timing"}
                className="input w-full mt-1 mb-2"
                onKeyDown={(e) => e.key === "Enter" && confirmPendingStage()}
              />
              <div className="flex gap-2">
                <button onClick={confirmPendingStage} className="btn btn-primary text-xs flex-1">
                  Confirm {STAGE_LABELS[pendingStage]}
                </button>
                <button onClick={() => setPendingStage(null)} className="btn btn-secondary text-xs">
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="mt-5 pt-4 border-t" style={{ borderColor: "var(--border)" }}>
            <h2 className="text-sm font-semibold text-main mb-3">Activity</h2>
            {activity.length === 0 ? (
              <p className="text-xs text-muted">No activity recorded yet.</p>
            ) : (
              <ul className="space-y-3">
                {activity.map((a) => (
                  <li key={a.id} className="text-xs">
                    <p className="text-main">{a.detail}</p>
                    <p className="text-muted mt-0.5">{new Date(a.created_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
