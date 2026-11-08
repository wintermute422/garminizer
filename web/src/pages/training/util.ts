/** Training page helpers: day ↔ time-axis conversion, Garmin status swatches, load zones. */
import { titleCase } from "@/lib/format";
import { addDays } from "@/lib/range";
import {
  CATEGORICAL,
  CHROME,
  NEUTRAL,
  STATUS,
  ZONE_RAMP,
  type Mode,
  type Status,
} from "@/lib/tokens";

/** Local midnight of an ISO day (time-axis bounds). */
export function dayStartMs(day: string): number {
  return new Date(`${day}T00:00:00`).getTime();
}

/** Local noon of an ISO day (where a day's mark sits on a time axis). */
export function dayMs(day: string): number {
  return new Date(`${day}T12:00:00`).getTime();
}

/** Time-axis extent covering whole days `start`…`end`, shared by linked charts. */
export function dayExtent(start: string, end: string): [number, number] {
  return [dayStartMs(start), dayStartMs(addDays(end, 1))];
}

/** Garmin status key without its phrase suffix ("PRODUCTIVE_3" → "PRODUCTIVE"). */
export function statusKey(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = raw.toUpperCase().replace(/_\d+$/, "");
  return key === "NO_STATUS" || key === "NONE" ? null : key;
}

/** Garmin training statuses, best → worst (legend order). */
export const STATUS_ORDER = [
  "PEAKING",
  "PRODUCTIVE",
  "MAINTAINING",
  "RECOVERY",
  "UNPRODUCTIVE",
  "DETRAINING",
  "OVERREACHING",
  "STRAINED",
];

/**
 * Each status owns one categorical slot (fixed, never by rank) so the strip can be decoded;
 * the frequent neighbours (maintaining ↔ productive / unproductive / recovery) get the most
 * distinct hues. Detraining is neutral grey.
 */
const STATUS_SLOT: Record<string, number | null> = {
  PEAKING: 6,
  PRODUCTIVE: 2,
  MAINTAINING: 0,
  RECOVERY: 4,
  UNPRODUCTIVE: 3,
  DETRAINING: null,
  OVERREACHING: 1,
  STRAINED: 7,
};

export function statusSwatch(key: string, mode: Mode): string {
  const slot = STATUS_SLOT[key];
  return slot === null || slot === undefined ? NEUTRAL[mode] : CATEGORICAL[mode][slot]!;
}

export function statusRank(key: string): number {
  const i = STATUS_ORDER.indexOf(key);
  return i < 0 ? STATUS_ORDER.length : i;
}

export function statusLabel(key: string): string {
  return titleCase(key);
}

const ICON_PATHS: Record<Status | "neutral", string> = {
  good: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  neutral: '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/>',
  warning:
    '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  serious:
    '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
  critical:
    '<path d="M2.586 16.726A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2h6.624a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586z"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
};

/** The StatusPill icon as inline SVG for ECharts tooltips (status = null → neutral). */
export function statusIconSvg(status: Status | null, mode: Mode): string {
  const color = status ? STATUS[status] : CHROME[mode].muted;
  return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px">${ICON_PATHS[status ?? "neutral"]}</svg>`;
}

/** ACWR zones (Gabbett): < 0.8 under-loading, 0.8–1.3 optimal, > 1.5 high injury risk. */
export function acwrZone(v: number): { label: string; status: Status } {
  if (v < 0.8) return { label: "Low", status: "warning" };
  if (v <= 1.3) return { label: "Optimal", status: "good" };
  if (v <= 1.5) return { label: "High", status: "serious" };
  return { label: "Very high", status: "critical" };
}

/** Form (TSB) zones as commonly used with the performance management chart. */
export function formZone(tsb: number): string {
  if (tsb > 25) return "Transition";
  if (tsb > 5) return "Fresh";
  if (tsb >= -10) return "Neutral";
  if (tsb >= -30) return "Productive";
  return "Overload risk";
}

/** HR-zone ramp (shared; every step clears 3:1 against the card). */
export function zoneRamp(mode: Mode): readonly string[] {
  return ZONE_RAMP[mode];
}

/** "Oct 27" for weeks, "Nov 2025" for months. */
export function periodLabel(iso: string, period: "week" | "month"): string {
  const d = new Date(`${iso}T12:00:00`);
  return period === "week"
    ? d.toLocaleDateString(undefined, { day: "numeric", month: "short" })
    : d.toLocaleDateString(undefined, { month: "short", year: "numeric" });
}

export function periodTitle(iso: string, period: "week" | "month"): string {
  const d = new Date(`${iso}T12:00:00`);
  return period === "week"
    ? `Week of ${d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`
    : d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

/** Deterministic offset in [−amp, amp] from an id (stable jitter for overplotted dots). */
export function jitter(id: number, salt: number, amp: number): number {
  const x = Math.sin((id % 100_003) * 12.9898 + salt * 78.233) * 43758.5453;
  return (x - Math.floor(x) - 0.5) * 2 * amp;
}

/** Text label halo so reference labels stay legible where they cross data. */
export function halo(mode: Mode): Record<string, unknown> {
  return { backgroundColor: CHROME[mode].surface, padding: [1, 4], borderRadius: 3 };
}
