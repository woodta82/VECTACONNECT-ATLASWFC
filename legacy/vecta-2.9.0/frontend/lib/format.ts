/**
 * Compact number formatting for large monetary values — "$22.8B" instead
 * of "$22,768,137,000". Used anywhere a value needs to fit in a fixed-width
 * box (stat cards, heatmap cells): a full-precision figure at a large font
 * size will overflow its container once pipeline value crosses into the
 * billions, which is exactly what happened on the Control Panel stat cards.
 * Exact figures are still available in Reports and the underlying tables —
 * this is specifically for space-constrained summary displays.
 */
export function formatCompactNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return Math.round(value).toString();
}

export function formatCompactCurrency(value: number, symbol = "$"): string {
  return `${symbol}${formatCompactNumber(value)}`;
}
