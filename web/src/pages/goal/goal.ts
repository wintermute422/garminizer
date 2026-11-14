/** Pure helpers of the weight-goal page: notes, checkpoint states, the target line, form errors. */
import type { Schemas } from "@/api/client";
import { DASH, fmtDistance, fmtDuration, fmtNumber, type UnitSystem } from "@/lib/format";
import { addDays } from "@/lib/range";
import { sportLabel } from "@/lib/sports";
import type { Status } from "@/lib/tokens";

type Activity = Schemas["GoalActivity"];
type Day = Schemas["GoalDay"];
type Checkpoint = Schemas["GoalCheckpoint"];
type LinePoint = Schemas["GoalLinePoint"];

export const WEEKDAYS = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

/** Trend at or below target + this (kg) counts as on plan (the backend's rule, for labels). */
export const ON_PLAN_TOLERANCE_KG = 0.2;

/** "Tempo Run 8.57 km · 41:50 · 152 bpm · 622 kcal" (parts without data are left out). */
export function activityNote(a: Activity, units: UnitSystem): string {
  const name = a.name?.trim() || sportLabel(a.sport_group);
  const head = a.distance_m ? `${name} ${fmtDistance(a.distance_m, units, 2)}` : name;
  const parts = [head];
  if (a.duration_s) parts.push(fmtDuration(a.duration_s));
  if (a.avg_hr) parts.push(`${Math.round(a.avg_hr)} bpm`);
  if (a.calories != null) parts.push(`${fmtNumber(a.calories)} kcal`);
  return parts.join(" · ");
}

/** Notes of one day: the meal names in one line, then one line per activity. */
export function dayNotes(d: Pick<Day, "meal_names" | "activities">, units: UnitSystem): string[] {
  const lines: string[] = [];
  if (d.meal_names.length) lines.push(d.meal_names.join(" · "));
  for (const a of d.activities) lines.push(activityNote(a, units));
  return lines;
}

export interface CheckpointState {
  status: Status | null;
  label: string;
  /** What the action button does, if the checkpoint can be changed by hand. */
  action: { accepted: boolean; label: string } | null;
}

/** Status pill + action of a checkpoint (accepting counts a past one as reached). */
export function checkpointState(c: Pick<Checkpoint, "status">): CheckpointState {
  switch (c.status) {
    case "reached":
      return { status: "good", label: "Reached", action: null };
    case "accepted":
      return {
        status: "good",
        label: "Counted as reached",
        action: { accepted: false, label: "Undo" },
      };
    case "missed":
      return {
        status: "warning",
        label: "Missed",
        action: { accepted: true, label: "Count as reached" },
      };
    case "no_weigh_in":
      return {
        status: null,
        label: "No weigh-in",
        action: { accepted: true, label: "Count as reached" },
      };
    default:
      return { status: null, label: "Upcoming", action: null };
  }
}

/**
 * Target on any day from the target line (pairs of segment start and end points, oldest
 * first). On an anchor day two segments meet; the later (stepped-down) one wins.
 */
export function targetAt(line: readonly LinePoint[], day: string): number | null {
  let found: number | null = null;
  for (let i = 0; i + 1 < line.length; i += 2) {
    const a = line[i]!;
    const b = line[i + 1]!;
    if (day < a.day || day > b.day) continue;
    const span = daysBetween(a.day, b.day);
    const t = span > 0 ? daysBetween(a.day, day) / span : 0;
    found = a.target_kg + (b.target_kg - a.target_kg) * t;
  }
  return found;
}

/** Whole days from `a` to `b` (ISO days). */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);
}

/** Later of two ISO days. */
export function maxDay(a: string, b: string): string {
  return a > b ? a : b;
}

/** Default end of a new goal: 12 weeks after the start. */
export function defaultEnd(start: string): string {
  return addDays(start, 84);
}

/** Planned kg per week as a loss ("−0.25 kg/week"). */
export function fmtRate(rate: number): string {
  const tenths = Math.abs(rate * 10 - Math.round(rate * 10)) < 1e-9;
  return `−${fmtNumber(rate, tenths ? 1 : 2)} kg/week`;
}

/** kg with one decimal, or the dash. */
export function kg(v: number | null | undefined, digits = 1): string {
  return v == null ? DASH : `${fmtNumber(v, digits)} kg`;
}

export interface FormErrors {
  /** Messages per settings field (`start_day`, `rate_kg_per_week`, …). */
  fields: Record<string, string>;
  /** Messages that belong to no single field. */
  general: string[];
}

const PREFIX = /^(Value error|Assertion failed), /;

/**
 * Errors of a failed request: FastAPI's 422 list (`detail: [{loc, msg}]`) by field, or a plain
 * `detail` string (HTTPException) as a general message.
 */
export function formErrors(error: unknown): FormErrors {
  const out: FormErrors = { fields: {}, general: [] };
  if (error == null) return out;
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    out.general.push(detail);
  } else if (Array.isArray(detail)) {
    for (const d of detail as { loc?: unknown[]; msg?: string }[]) {
      const msg = (d.msg ?? "Invalid value").replace(PREFIX, "");
      const loc = (d.loc ?? []).filter((x) => x !== "body");
      const field = typeof loc[0] === "string" ? loc[0] : null;
      if (field && !out.fields[field]) out.fields[field] = msg;
      else if (!field) out.general.push(msg);
    }
  } else if (error instanceof Error) {
    out.general.push(error.message);
  } else {
    out.general.push("Saving failed.");
  }
  return out;
}

/** Days of the log, newest first. */
export function newestFirst<T extends { day: string }>(days: readonly T[]): T[] {
  return [...days].sort((a, b) => (a.day < b.day ? 1 : a.day > b.day ? -1 : 0));
}
