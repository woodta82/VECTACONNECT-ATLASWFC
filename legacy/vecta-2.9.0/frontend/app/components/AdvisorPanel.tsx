"use client";

import { useEffect, useState } from "react";
import { api, type AdvisorClaim, type AdvisorResponse } from "@/lib/api";

/**
 * Executive AI Advisor panel.
 *
 * Renders the six-section response in fixed order. Two things make this
 * an adviser rather than a chat interface:
 *
 *  - there is no text input. Questions come from a known set, so the
 *    advisor is never asked something the data cannot support;
 *  - every claim shows its kind — verified, interpretation, assumption,
 *    recommendation — using the same vocabulary as the rest of ATLAS.
 *    An advisor that blurred those would undo the discipline the platform
 *    is built on.
 */

const SECTION_TITLES: Record<string, string> = {
  "1_recommendation": "Recommendation",
  "2_key_reasons": "Key reasons",
  "3_supporting_evidence": "Supporting evidence",
  "4_risks": "Risks",
  "5_assumptions": "Assumptions",
  "6_suggested_actions": "Suggested actions",
};

export default function AdvisorPanel({
  answer,
  onAnswer,
}: {
  answer: AdvisorResponse | null;
  onAnswer: (a: AdvisorResponse | null) => void;
}) {
  const [questions, setQuestions] = useState<
    { key: string; question: string; available: boolean }[]
  >([]);
  const [asking, setAsking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .advisorQuestions()
      .then(setQuestions)
      .catch(() => setQuestions([]));
  }, []);

  async function ask(key: string) {
    setAsking(key);
    setError(null);
    try {
      onAnswer(await api.advisorAsk(key));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The advisor could not answer");
    } finally {
      setAsking(null);
    }
  }

  return (
    <div className="adv">
      <div className="adv-questions">
        {questions.map((q) => (
          <button
            key={q.key}
            type="button"
            onClick={() => ask(q.key)}
            disabled={!q.available || asking !== null}
            className="adv-question"
            title={q.available ? undefined : "Not enough data to answer this yet"}
          >
            {asking === q.key ? "…" : q.question}
          </button>
        ))}
      </div>

      {error && (
        <p className="adv-error" role="alert">
          {error}
        </p>
      )}

      {answer && (
        <div className="adv-answer">
          <div className="adv-answer-head">
            <p className="adv-asked">{answer.question}</p>
            <button type="button" onClick={() => onAnswer(null)} className="adv-close">
              Close
            </button>
          </div>

          {!answer.answerable ? (
            <p className="adv-unanswerable">
              Cannot answer yet — {answer.unanswerable_reason}
            </p>
          ) : (
            <>
              {Object.entries(answer.sections).map(([key, value]) => {
                const claims: AdvisorClaim[] = Array.isArray(value) ? value : [value];
                const populated = claims.filter((c) => c && c.text);
                // An empty section is noise. Recommendation always renders
                // (its absence would be the story); the rest disappear when
                // they have nothing to say.
                if (populated.length === 0 && key !== "1_recommendation") return null;
                return (
                  <section key={key} className="adv-section">
                    <h4 className="adv-section-title">{SECTION_TITLES[key] ?? key}</h4>
                    {populated.length === 0 ? (
                      <p className="adv-none">None identified.</p>
                    ) : (
                      <ul className="adv-claims">
                        {populated.map((claim, i) => (
                          <li key={i} className="adv-claim">
                            <span className={`adv-kind adv-kind-${claim.kind}`}>
                              {claim.kind_label}
                            </span>
                            <span className="adv-text">{claim.text}</span>
                            {claim.source && (
                              <a
                                href={claim.source}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="adv-source"
                              >
                                source
                              </a>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </section>
                );
              })}
            </>
          )}

          <p className="adv-provenance">
            {answer.ai_calls_used} AI calls · computed from stored intelligence
            {answer.profile_version && <> · profile v{answer.profile_version}</>}
          </p>
        </div>
      )}
    </div>
  );
}
