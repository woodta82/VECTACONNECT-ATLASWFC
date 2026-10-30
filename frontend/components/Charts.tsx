"use client";

/* Supporting geographic and score visuals (from the Control panel of 29 Oct 2026; shared by the Dashboard since 30 Oct 2026). Existing tokens only. */

export type Bucket = { live: number; tenders_open: number; commercial: number; signals: number; with_relationships: number; avg_score: number | null; top_score: number | null };
export type RegionRow = Bucket & { region: string; share: number };
export type Decile = { range: string; count: number };

/** Fixed colour per region (never by rank), so a filter never repaints the regions that remain. */
const REGION_SLOT: Record<string, string> = { Africa: "1", Asia: "2", Europe: "3", Americas: "4", Oceania: "5" };
export const slot = (region: string) => REGION_SLOT[region] ?? "none";
export const pct = (x: number) => (x > 0 && x < 0.01 ? "<1%" : `${Math.round(x * 100)}%`);
export const avg = (v: number | null) => (v === null ? "not scored" : `avg ${v.toFixed(1)}`);

export function RegionDonut({ regions }: { regions: RegionRow[] }) {
  const total = regions.reduce((s, r) => s + r.live, 0);
  const R = 70, C = 2 * Math.PI * R, GAP = regions.length > 1 ? 3 : 0;
  let offset = 0;
  return (
    <div className="cp-donut-wrap">
      <svg viewBox="0 0 180 180" className="cp-donut" role="img" aria-label={regions.map((r) => `${r.region}: ${r.live}`).join(", ")}>
        <circle cx="90" cy="90" r={R} className="cp-donut-track" />
        {regions.map((r) => {
          const len = (r.live / total) * C;
          const seg = (
            <circle key={r.region} cx="90" cy="90" r={R} className={`cp-seg s-${slot(r.region)}`}
                    strokeDasharray={`${Math.max(len - GAP, 0.5)} ${C}`} strokeDashoffset={-offset} transform="rotate(-90 90 90)">
              <title>{`${r.region}: ${r.live} live (${pct(r.live / total)} of region entries), ${avg(r.avg_score)}`}</title>
            </circle>
          );
          offset += len;
          return seg;
        })}
        <text x="90" y="86" textAnchor="middle" className="cp-donut-num">{total}</text>
        <text x="90" y="106" textAnchor="middle" className="cp-donut-cap">region entries</text>
      </svg>
      <ul className="cp-legend">
        {regions.map((r) => (
          <li key={r.region}><span className={`cp-dot s-${slot(r.region)}`} aria-hidden="true" /><span>{r.region}</span>
            <span className="muted">{pct(r.live / total)} · {r.live} live · {avg(r.avg_score)}</span></li>
        ))}
      </ul>
    </div>
  );
}

export function ScoreHistogram({ deciles }: { deciles: Decile[] }) {
  const max = Math.max(1, ...deciles.map((d) => d.count));
  return (
    <div className="cp-hist" role="img" aria-label={deciles.map((d) => `${d.range}: ${d.count}`).join(", ")}>
      {deciles.map((d) => (
        <div key={d.range} className="cp-hcol" title={`Score ${d.range}: ${d.count} record(s)`}>
          <span className="cp-hval">{d.count || ""}</span>
          <span className="cp-hbar" style={{ height: `${(d.count / max) * 100}%` }} />
          <span className="cp-hlab">{d.range.split("–")[0]}</span>
        </div>
      ))}
    </div>
  );
}

