/** Performance page helpers: race distances, endurance classes, deltas over a series. */
import { useSyncExternalStore } from "react";
import { fmtDuration, titleCase } from "@/lib/format";

export function dayMs(day: string): number {
  return new Date(`${day}T12:00:00`).getTime();
}

export type RaceField = "time_5k_s" | "time_10k_s" | "time_half_s" | "time_marathon_s";

export const RACES: { key: string; label: string; field: RaceField; distance: number }[] = [
  { key: "5k", label: "5K", field: "time_5k_s", distance: 5000 },
  { key: "10k", label: "10K", field: "time_10k_s", distance: 10000 },
  { key: "half", label: "Half marathon", field: "time_half_s", distance: 21097.5 },
  { key: "marathon", label: "Marathon", field: "time_marathon_s", distance: 42195 },
];

/**
 * Garmin endurance-score classes with reference lower bounds. Garmin scales them by age and
 * sex and the API does not return the thresholds, so the bands are a guide; the tooltip shows
 * the class Garmin actually reported for the day.
 */
export const ENDURANCE_CLASSES: { key: string; min: number }[] = [
  { key: "UNTRAINED", min: 0 },
  { key: "RECREATIONAL", min: 3000 },
  { key: "INTERMEDIATE", min: 4500 },
  { key: "TRAINED", min: 5500 },
  { key: "WELL_TRAINED", min: 6500 },
  { key: "EXPERT", min: 7500 },
  { key: "SUPERIOR", min: 8500 },
  { key: "ELITE", min: 9500 },
];

export function sentenceCase(key: string | null | undefined): string {
  const t = titleCase(key).toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** First and last non-null value of a series (change over the range). */
export function firstLast<T>(
  rows: T[],
  get: (r: T) => number | null | undefined,
): { first: number; last: number; firstRow: T } | null {
  let firstRow: T | undefined;
  let first: number | null = null;
  let last: number | null = null;
  for (const r of rows) {
    const v = get(r);
    if (v === null || v === undefined) continue;
    if (first === null) {
      first = v;
      firstRow = r;
    }
    last = v;
  }
  return first === null || last === null || firstRow === undefined
    ? null
    : { first, last, firstRow };
}

/** Axis bounds aligned to a round step giving about `ticks` intervals (labels never crowd). */
export function niceAxis(
  lo: number,
  hi: number,
  steps: number[],
  ticks = 4,
): { min: number; max: number; interval: number } {
  const raw = Math.max(hi - lo, 1e-9) / ticks;
  const interval = steps.find((s) => s >= raw) ?? steps[steps.length - 1]!;
  return {
    min: Math.floor(lo / interval) * interval,
    max: Math.ceil(hi / interval) * interval,
    interval,
  };
}

/** [ms, value] points with a null inserted where consecutive points are > `days` apart. */
export function withGaps(points: [number, number][], days = 14): [number, number | null][] {
  const out: [number, number | null][] = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i]!;
    const prev = points[i - 1];
    if (prev && p[0] - prev[0] > days * 86_400_000) out.push([(prev[0] + p[0]) / 2, null]);
    out.push(p);
  }
  return out;
}

/** "−0:18" / "+1:02" for a change in seconds. */
export function signedDuration(s: number): string {
  if (Math.abs(s) < 0.5) return "±0:00";
  return `${s > 0 ? "+" : "−"}${fmtDuration(Math.abs(s))}`;
}

/** Whole years between an ISO birth date and an ISO day. */
export function ageOn(birth: string, day: string): number {
  const b = new Date(`${birth}T12:00:00`);
  const d = new Date(`${day}T12:00:00`);
  let age = d.getFullYear() - b.getFullYear();
  if (d.getMonth() < b.getMonth() || (d.getMonth() === b.getMonth() && d.getDate() < b.getDate()))
    age -= 1;
  return age;
}

const WIDE = "(min-width: 640px)";

function subscribeWide(onChange: () => void): () => void {
  const mq = window.matchMedia?.(WIDE);
  mq?.addEventListener("change", onChange);
  return () => mq?.removeEventListener("change", onChange);
}

/** True from the `sm` breakpoint up (stat-tile sparklines only fit there). */
export function useWide(): boolean {
  return useSyncExternalStore(
    subscribeWide,
    () => window.matchMedia?.(WIDE).matches ?? true,
    () => true,
  );
}
