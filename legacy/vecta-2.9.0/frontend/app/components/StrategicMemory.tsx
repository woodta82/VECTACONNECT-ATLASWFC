"use client";

import { useEffect, useState } from "react";
import { api, type WhatChanged } from "@/lib/api";

/**
 * Strategic Memory — "what changed" for one opportunity.
 *
 * Executives care about movement more than state. "Win probability 65" is
 * inert; "65, down from 77 because a competitor secured the local partner"
 * is a decision trigger.
 *
 * The panel is deliberately silent when nothing has moved. A component
 * that always renders something teaches you to stop reading it — so if
 * there is no change worth reporting, it says so in one line and stops.
 */
export default function StrategicMemory({
  opportunityId,
  compact = false,
}: {
  opportunityId: string;
  compact?: boolean;
}) {
  const [data, setData] = useState<WhatChanged | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .whatChanged(opportunityId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load history");
      });
    return () => {
      cancelled = true;
    };
  }, [opportunityId]);

  if (error) return <p className="sm-error">{error}</p>;
  if (!data || !data.available) return null;

  if (!data.has_changes && compact) {
    return <p className="sm-none">No change since your last review.</p>;
  }

  const focus = data.executive_focus;
  const previous = data.previous_recommendation;
  const impact = data.commercial_impact;

  return (
    <div className={`sm ${compact ? "sm-compact" : ""}`}>
      <p className="sm-summary">{data.summary}</p>

      {/* Previous vs current recommendation — the comparison an executive
          reaches for first when priorities appear to have shifted. */}
      {previous && (
        <div className="sm-recommendation">
          <div className="sm-rec-row">
            <span className="sm-label">Previously</span>
            <span className="sm-value">
              {previous.recommended.replace(/_/g, " ")}
              {!previous.agreed && (
                <span className="sm-override">
                  {" "}
                  — you decided {previous.decided.replace(/_/g, " ")}
                </span>
              )}
            </span>
            <span className="sm-when">
              {previous.decided_at
                ? new Date(previous.decided_at).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "short",
                  })
                : ""}
            </span>
          </div>
          {previous.focus_at_decision !== null && focus && (
            <p className="sm-impact">
              Executive Focus was {previous.focus_at_decision} at that decision, now{" "}
              {focus.current}
              {focus.delta !== null && focus.delta !== 0 && (
                <>
                  {" "}
                  ({focus.delta > 0 ? "+" : ""}
                  {focus.delta})
                </>
              )}
              .
              {focus.delta !== null &&
                Math.abs(focus.delta) >= 15 &&
                " The earlier recommendation may no longer hold."}
            </p>
          )}
        </div>
      )}

      {/* Expected commercial impact. A movement in points is abstract;
          the same movement in money is a decision input. */}
      {impact && (
        <p className={`sm-money sm-money-${impact.direction}`}>
          {impact.direction === "loss" ? "▼" : "▲"} {impact.currency}{" "}
          {Math.abs(impact.delta).toLocaleString()} expected value{" "}
          {impact.direction === "loss" ? "lost" : "gained"}
          {impact.is_estimate && <span className="sm-est"> (on an estimated value)</span>}
        </p>
      )}

      {/* Score movement — only dimensions that actually moved. */}
      {Object.entries(data.scores).some(([, v]) => v.delta) && (
        <table className="sm-table">
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col">Was</th>
              <th scope="col">Now</th>
              <th scope="col">Why</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.scores)
              .filter(([, v]) => v.delta)
              .map(([dimension, v]) => (
                <tr key={dimension}>
                  <td>{dimension.replace(/_/g, " ")}</td>
                  <td className="sm-num">{v.previous ?? "—"}</td>
                  <td className={`sm-num ${v.direction === "up" ? "sm-up" : "sm-down"}`}>
                    {/* Risk suppression must survive this layer too. */}
                    {v.suppressed ? "Not established" : v.current}
                    {v.delta !== null && (
                      <span className="sm-delta">
                        {" "}
                        {v.delta > 0 ? "▲" : "▼"}
                        {Math.abs(v.delta)}
                      </span>
                    )}
                  </td>
                  <td className="sm-reason">
                    {(v.change_reason ?? "").replace(/_/g, " ") || "—"}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      )}

      {data.qualification?.previous && (
        <p className="sm-qual">
          Qualification moved from {data.qualification.previous.replace(/_/g, " ")} to{" "}
          {data.qualification.current.replace(/_/g, " ")}.
        </p>
      )}

      {!compact && data.recent_events.length > 0 && (
        <ul className="sm-events">
          {data.recent_events.map((e, i) => (
            <li key={i} className={`sm-event sm-event-${e.materiality}`}>
              <span>{e.summary}</span>
              <span className="sm-when">
                {e.occurred_at
                  ? new Date(e.occurred_at).toLocaleDateString(undefined, {
                      day: "numeric",
                      month: "short",
                    })
                  : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
