/**
 * Calendar data helpers. `/api/calendar` has no sport filter, so with a sport selected the
 * per-day totals are rebuilt from that sport's activities (paged through `/api/activities`)
 * and the streaks are recomputed with the same rules as the backend.
 */
import { fetchClient, type Schemas } from "@/api/client";
import { addDays } from "@/lib/range";

export type DayTotals = Schemas["CalendarDay"];

const PAGE = 1000;

/** Per-day totals of one sport's activities in [start, end]. */
export async function fetchSportDays(
  start: string,
  end: string,
  sport: string,
): Promise<DayTotals[]> {
  const byDay = new Map<string, DayTotals>();
  for (let offset = 0; ; offset += PAGE) {
    const { data, error } = await fetchClient.GET("/api/activities", {
      params: {
        query: { start, end, sport, sort: "start_time", order: "asc", limit: PAGE, offset },
      },
    });
    if (error || !data) throw error ?? new Error("Could not load activities");
    for (const a of data.items) {
      const day = a.start_time_local.slice(0, 10);
      const t = byDay.get(day) ?? {
        day,
        activities: 0,
        duration_s: 0,
        distance_m: 0,
        training_load: 0,
        sport_groups: [a.sport_group],
      };
      t.activities += 1;
      t.duration_s += a.duration_s ?? 0;
      t.distance_m += a.distance_m ?? 0;
      t.training_load += a.training_load ?? 0;
      byDay.set(day, t);
    }
    if (offset + data.items.length >= data.total || data.items.length === 0) break;
  }
  return [...byDay.values()].sort((a, b) => (a.day < b.day ? -1 : 1));
}

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
