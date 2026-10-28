/** The configured reporting time zone (from the session; Asia/Dubai until loaded).
 * Every displayed time uses it unless a source time zone is shown alongside. */
let reportingTz = "Asia/Dubai";
export function setReportingTz(tz: string | null | undefined): void {
  if (tz) reportingTz = tz;
}
export function getReportingTz(): string {
  return reportingTz;
}

export function dateTime(iso: string | null | undefined, tz: string = reportingTz): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "short",
  }).format(d);
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "2-digit", month: "short", year: "numeric" }).format(d);
}

/** Deadlines show the reporting time zone AND the source time zone. */
/** A deadline as the source stated it (backend domain/deadlines.py). Only "instant" has an exact time. */
export type DeadlineInfo = {
  precision: "date" | "local_time" | "instant"; day: string; local_time: string | null; zone: string | null;
  exact_utc: string | null; earliest_utc: string | null; latest_utc: string | null;
  assumed_zone: string | null; assumed_utc: string | null; notes: string[];
};

function dayLabel(isoDay: string): string {
  const [y = 1970, m = 1, d = 1] = isoDay.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

/** Deadline text that never adds precision the source did not state. */
export function deadline(iso: string | null | undefined, sourceTz: string | null | undefined, info?: DeadlineInfo | null): string {
  if (info && info.precision === "date") return `${dayLabel(info.day)} (date only; time not stated)`;
  if (info && info.precision === "local_time") return `${dayLabel(info.day)}, ${info.local_time} (time zone not stated)`;
  if (!iso) return info?.exact_utc ? deadline(info.exact_utc, info.zone) : "Unknown";
  const local = dateTime(iso);
  if (!sourceTz || sourceTz === reportingTz) return local;
  let source: string;
  try {
    source = dateTime(iso, sourceTz);
  } catch {
    source = sourceTz; // a UTC offset label such as UTC+03:00 is not an IANA zone
  }
  return `${local} (source: ${source})`;
}

/** The labelled bounds and assumptions behind a deadline that is not an exact instant. */
export function deadlineNotes(info: DeadlineInfo | null | undefined): string[] {
  if (!info) return [];
  const out: string[] = [];
  if (info.precision !== "instant" && info.earliest_utc && info.latest_utc) {
    out.push(`Internal planning cutoff (earliest it could fall anywhere): ${dateTime(info.earliest_utc)}. ` +
             `Not treated as expired until ${dateTime(info.latest_utc)}.`);
  }
  if (info.assumed_zone && info.assumed_utc) out.push(`If ${info.assumed_zone} is meant (an assumption, not stated by the source): ${dateTime(info.assumed_utc)}.`);
  return out.concat(info.notes.filter((n) => !/not stated in the source$/.test(n)));
}

/** Numbers arrive as strings (Decimal) to avoid float rounding. Unknown stays unknown. */
export function num(v: string | number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || v === "") return "Unknown";
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function money(v: string | number | null | undefined, currency: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "Unqualified";
  if (!currency) return `${num(v, 2)} (currency unknown)`;
  return `${currency} ${num(v, 2)}`;
}

export function pct(ratio: string | number | null | undefined): string {
  if (ratio === null || ratio === undefined || ratio === "") return "Not available";
  const n = Number(ratio);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "Not available";
}

/** Labels whose plain-English form must not be shortened (status and freight-scope states shown across lists, details and briefings). */
const SPECIAL_LABEL: Record<string, string> = {
  announced: "Announced — current status unverified",
  not_freight: "Not freight",
  freight_candidate: "Freight candidate (review)",
  historical_record: "Historical record (not actionable)",
  tender_context: "Supporting information",
};

export function label(s: string | null | undefined): string {
  if (!s) return "—";
  if (SPECIAL_LABEL[s]) return SPECIAL_LABEL[s];
  return s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Days from now until an ISO instant (negative when passed); null when unknown. */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.floor((t - Date.now()) / 86_400_000);
}

export const MODULE_LABEL: Record<string, string> = {
  airline_representation: "Airline representation", account_growth: "Account growth", forwarder_sales: "Forwarder sales",
  capacity_lanes: "Capacity and trade lanes", service_operations: "Service and operations", trucking_gateways: "Trucking and gateways",
  outsourcing_training: "Outsourcing and training", technology_solutions: "Technology and solutions", network_development: "Network development",
};
export function moduleLabel(m: string | null | undefined): string {
  return m ? MODULE_LABEL[m] ?? label(m) : "—";
}

const ISO_IN_TEXT = /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})\b/g;

/** Server-written notes may embed UTC ISO timestamps; show them in the reporting time zone like every other time. */
export function humanText(s: string | null | undefined): string {
  return (s ?? "").replace(ISO_IN_TEXT, (m) => dateTime(m));
}
