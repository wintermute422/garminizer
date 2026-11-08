/** Calendar data helpers (streak rules mirror the backend's). */
import type { Schemas } from "@/api/client";
import { addDays } from "@/lib/range";

export type DayTotals = Schemas["CalendarDay"];

/** Current (ending at `end`, or the day before when `end` is still empty) and longest run. */
export function dayStreaks(
  days: string[],
  end: string,
): { current: number; longest: number; longestStart: string | null } {
  const set = new Set(days);
  const sorted = [...set].sort();
  if (!sorted.length) return { current: 0, longest: 0, longestStart: null };
  let longest = 1;
  let longestStart = sorted[0]!;
  let run = 1;
  let runStart = sorted[0]!;
  for (let i = 1; i < sorted.length; i++) {
    if (addDays(sorted[i - 1]!, 1) === sorted[i]) run += 1;
    else {
      run = 1;
      runStart = sorted[i]!;
    }
    if (run > longest) {
      longest = run;
      longestStart = runStart;
    }
  }
  let ref = set.has(end) ? end : addDays(end, -1);
  let current = 0;
  while (set.has(ref)) {
    current += 1;
    ref = addDays(ref, -1);
  }
  return { current, longest, longestStart };
}

function monday(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return addDays(iso, -((d.getDay() + 6) % 7));
}

/** Consecutive ISO weeks with an activity, ending with the week of `end` (or the one before). */
export function weeksInRow(days: string[], end: string): number {
  const weeks = new Set(days.map(monday));
  let ref = monday(end);
  if (!weeks.has(ref)) ref = addDays(ref, -7);
  let n = 0;
  while (weeks.has(ref)) {
    n += 1;
    ref = addDays(ref, -7);
  }
  return n;
}

export interface MonthTotals {
  key: string; // "2026-03"
  activeDays: number;
  activities: number;
  duration_s: number;
  distance_m: number;
  daysInRange: number;
}

/** One bucket per calendar month touched by [start, end]. */
export function monthTotals(days: DayTotals[], start: string, end: string): MonthTotals[] {
  const out = new Map<string, MonthTotals>();
  for (let d = start; d <= end; d = addDays(d, 1)) {
    const key = d.slice(0, 7);
    const m = out.get(key) ?? {
      key,
      activeDays: 0,
      activities: 0,
      duration_s: 0,
      distance_m: 0,
      daysInRange: 0,
    };
    m.daysInRange += 1;
    out.set(key, m);
  }
  for (const day of days) {
    const m = out.get(day.day.slice(0, 7));
    if (!m) continue;
    m.activeDays += 1;
    m.activities += day.activities;
    m.duration_s += day.duration_s;
    m.distance_m += day.distance_m;
  }
  return [...out.values()];
}

export function daysBetween(start: string, end: string): number {
  return (
    Math.round(
      (new Date(`${end}T12:00:00`).getTime() - new Date(`${start}T12:00:00`).getTime()) /
        86_400_000,
    ) + 1
  );
}
