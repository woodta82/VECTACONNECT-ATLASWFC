import type { Opportunity } from "./api";

/**
 * VECTA Alignment Score measures quality, not urgency — a 90-scoring
 * opportunity with a deadline six months out and one with a deadline next
 * week look identical by that score alone. This combines alignment score,
 * deadline proximity, and the deliverability sub-score (from the score
 * breakdown) into one number that answers "what should I actually look at
 * first" rather than just "what's good."
 *
 * Weights: 55% alignment score, 30% urgency, 15% deliverability. Urgency
 * is intentionally steep — something closing this week should outrank a
 * slightly-higher-scoring item with months of runway.
 */
export function computeActNowScore(o: Opportunity): number {
  const alignment = o.alignment_score;
  const deliverability = o.score_breakdown?.deliverability ?? 50;

  let urgency = 0;
  if (o.deadline) {
    const days = Math.ceil((new Date(o.deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
    if (days < 0) urgency = 100; // overdue — still worth surfacing, may need re-checking
    else if (days <= 7) urgency = 100;
    else if (days <= 14) urgency = 75;
    else if (days <= 30) urgency = 45;
    else if (days <= 90) urgency = 15;
    else urgency = 0;
  }

  const score = alignment * 0.55 + urgency * 0.3 + deliverability * 0.15;
  return Math.round(score);
}

export function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  return Math.ceil((new Date(dateStr).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}
