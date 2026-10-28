"use client";

import { useEffect, useState } from "react";
import { api, type Phase2Blocker, type Phase2Qualification } from "@/lib/api";

/**
 * Qualification workflow — the owner's route through the gate.
 *
 * Before this existed the gate was a dead end: the backend blocked
 * progression correctly, but nothing in the UI could answer a checklist
 * item, so every opportunity sat at "verification required" permanently.
 *
 * Two things make it a decision tool rather than a form:
 *  - answers re-evaluate the gate immediately, so the consequence of an
 *    answer is visible at the moment it is given;
 *  - "next actions" state exactly what is blocking progression, so a
 *    blocked opportunity always comes with a route forward.
 */

type NextAction = {
  type: string;
  action: string;
  detail: string;
  item_key: string | null;
};

type QualificationResponse = {
  qualification: Phase2Qualification;
  next_actions: NextAction[];
  can_enter_pipeline: boolean;
  pipeline_block_reason: string | null;
};

const ANSWERS = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
  { value: "unknown", label: "Unknown" },
  { value: "not_applicable", label: "N/A" },
] as const;

export default function QualificationWorkflow({ opportunityId }: { opportunityId: string }) {
  const [data, setData] = useState<QualificationResponse | null>(null);
  const [draft, setDraft] = useState<Record<string, { answer: string; explanation: string }>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showOverride, setShowOverride] = useState(false);
  const [overrideState, setOverrideState] = useState("qualified");
  const [overrideReason, setOverrideReason] = useState("");

  async function load() {
    setError(null);
    try {
      const res = await api.qualification(opportunityId);
      setData(res);
      const next: Record<string, { answer: string; explanation: string }> = {};
      res.qualification.checklist.forEach((i) => {
        next[i.item_key] = { answer: i.answer, explanation: i.explanation ?? "" };
      });
      setDraft(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load qualification");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opportunityId]);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const res = await api.answerQualification(opportunityId, draft);
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save qualification");
    } finally {
      setSaving(false);
    }
  }

  async function submitOverride() {
    if (!overrideReason.trim()) {
      setError("An override requires a reason.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.overrideQualification(opportunityId, overrideState, overrideReason.trim());
      setShowOverride(false);
      setOverrideReason("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Override failed");
    } finally {
      setSaving(false);
    }
  }

  if (!data) {
    return <p className="state-loading">{error ?? "Loading qualification…"}</p>;
  }

  const q = data.qualification;
  const absolute = q.blockers.filter((b) => b.failure_type === "absolute_disqualifier");
  const remediable = q.blockers.filter((b) => b.failure_type === "remediable_blocker");
  const unresolved = q.blockers.filter((b) => b.failure_type === "unresolved_mandatory_question");
  const nonMaterial = q.blockers.filter((b) => b.failure_type === "non_material_concern");

  const dirty = q.checklist.some(
    (i) =>
      draft[i.item_key] &&
      (draft[i.item_key].answer !== i.answer ||
        draft[i.item_key].explanation !== (i.explanation ?? ""))
  );

  return (
    <div className="p2-qual">
      <div className="p2-qual-head">
        <div>
          <span className="p2-qual-state-label">Qualification state</span>
          <span className={`p2-badge p2-badge-${stateTone(q.state)} p2-qual-state`}>
            {q.state_label}
          </span>
        </div>
        <div className="p2-qual-pipeline">
          {data.can_enter_pipeline ? (
            <span className="p2-badge p2-badge-qualified">Can enter active pipeline</span>
          ) : (
            <span className="p2-badge p2-badge-disqualified">Blocked from active pipeline</span>
          )}
        </div>
      </div>

      {!data.can_enter_pipeline && data.pipeline_block_reason && (
        <div className="p2-restriction" role="note">
          <strong>Why it is blocked:</strong> {data.pipeline_block_reason}
        </div>
      )}

      {data.next_actions.length > 0 && (
        <section className="p2-qual-actions">
          <h4>What is needed to progress</h4>
          <ul className="p2-list">
            {data.next_actions.map((a, i) => (
              <li key={i} className="p2-list-item">
                <span>
                  {a.action}
                  <span className="p2-note"> — {a.detail}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {q.blockers.length > 0 && (
        <section className="p2-qual-blockers">
          <BlockerGroup
            title="Absolute disqualifiers"
            help="Permanent bars. These cannot be remediated."
            blockers={absolute}
            tone="disqualified"
          />
          <BlockerGroup
            title="Remediable blockers"
            help="Real obstacles VECTA could resolve — the opportunity stays Conditionally Qualified while these are open."
            blockers={remediable}
            tone="conditional"
          />
          <BlockerGroup
            title="Unresolved mandatory questions"
            help="Must be answered either way before the opportunity can qualify."
            blockers={unresolved}
            tone="review"
          />
          <BlockerGroup
            title="Non-material concerns"
            help="Open points that do not prevent qualification."
            blockers={nonMaterial}
            tone="neutral"
          />
        </section>
      )}

      <section className="p2-qual-checklist">
        <h4>Qualification checklist</h4>
        <table className="p2-table">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Answer</th>
              <th scope="col">Explanation / review note</th>
            </tr>
          </thead>
          <tbody>
            {q.checklist.map((item) => (
              <tr key={item.item_key}>
                <td>
                  {item.item_label}
                  {item.is_mandatory && <span className="p2-mandatory"> (mandatory)</span>}
                </td>
                <td>
                  <div className="p2-answer-group" role="group" aria-label={item.item_label}>
                    {ANSWERS.map((a) => (
                      <button
                        key={a.value}
                        type="button"
                        onClick={() =>
                          setDraft((d) => ({
                            ...d,
                            [item.item_key]: {
                              answer: a.value,
                              explanation: d[item.item_key]?.explanation ?? "",
                            },
                          }))
                        }
                        className={`p2-answer-btn ${
                          draft[item.item_key]?.answer === a.value ? "p2-answer-btn-active" : ""
                        }`}
                        aria-pressed={draft[item.item_key]?.answer === a.value}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                </td>
                <td>
                  <input
                    type="text"
                    value={draft[item.item_key]?.explanation ?? ""}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        [item.item_key]: {
                          answer: d[item.item_key]?.answer ?? "unknown",
                          explanation: e.target.value,
                        },
                      }))
                    }
                    placeholder="Why? (optional)"
                    className="p2-qual-input"
                    aria-label={`Explanation for ${item.item_label}`}
                  />
                  {item.source === "manual" && <span className="p2-note"> Reviewed</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="p2-qual-footer">
          <button onClick={save} disabled={saving || !dirty} className="btn btn-primary">
            {saving ? "Saving…" : dirty ? "Save and re-evaluate" : "No changes"}
          </button>
          <button
            onClick={() => setShowOverride((v) => !v)}
            className="btn btn-secondary"
            type="button"
          >
            Override state
          </button>
        </div>
      </section>

      {showOverride && (
        <section className="p2-qual-override">
          <h4>Manual override</h4>
          <p className="p2-note">
            The computed assessment is preserved and remains auditable — an override records a
            documented disagreement, it does not erase what the gate concluded.
          </p>
          <div className="p2-qual-override-row">
            <select
              value={overrideState}
              onChange={(e) => setOverrideState(e.target.value)}
              className="input"
              aria-label="New qualification state"
            >
              <option value="not_assessed">Not assessed</option>
              <option value="verification_required">Verification required</option>
              <option value="conditionally_qualified">Conditionally qualified</option>
              <option value="qualified">Qualified</option>
              <option value="disqualified">Disqualified</option>
            </select>
            <input
              type="text"
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              placeholder="Reason (required)"
              className="input"
              aria-label="Override reason"
            />
            <button onClick={submitOverride} disabled={saving} className="btn btn-primary">
              Apply override
            </button>
          </div>
        </section>
      )}

      {error && (
        <p className="p2-qual-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function BlockerGroup({
  title,
  help,
  blockers,
  tone,
}: {
  title: string;
  help: string;
  blockers: Phase2Blocker[];
  tone: string;
}) {
  if (blockers.length === 0) return null;
  return (
    <div className="p2-blocker-group">
      <h5>
        {title} <span className="p2-badge p2-badge-neutral">{blockers.length}</span>
      </h5>
      <p className="p2-note">{help}</p>
      <ul className="p2-list">
        {blockers.map((b, i) => (
          <li key={i} className="p2-list-item">
            <span>{b.message}</span>
            <span className={`p2-badge p2-badge-${tone}`}>{b.failure_type_label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function stateTone(state: string): string {
  if (state === "qualified") return "qualified";
  if (state === "disqualified") return "disqualified";
  if (state === "conditionally_qualified") return "conditional";
  if (state === "verification_required") return "review";
  return "neutral";
}
