/** Training page helpers: day ↔ time-axis conversion, Garmin status mapping, load zones. */
import { useSyncExternalStore } from "react";
import { titleCase } from "@/lib/format";
import { addDays } from "@/lib/range";
import { NEUTRAL, STATUS, type Mode, type Status } from "@/lib/tokens";

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

export type StatusClass = "good" | "neutral" | "warning" | "serious";

const GARMIN_STATUS: Record<string, { label: string; cls: StatusClass }> = {
  PEAKING: { label: "Peaking", cls: "good" },
  PRODUCTIVE: { label: "Productive", cls: "good" },
  MAINTAINING: { label: "Maintaining", cls: "neutral" },
  RECOVERY: { label: "Recovery", cls: "neutral" },
  UNPRODUCTIVE: { label: "Unproductive", cls: "warning" },
  DETRAINING: { label: "Detraining", cls: "warning" },
  OVERREACHING: { label: "Overreaching", cls: "serious" },
  STRAINED: { label: "Strained", cls: "serious" },
};

/** Garmin status key without its phrase suffix ("PRODUCTIVE_3" → "PRODUCTIVE"). */
export function statusKey(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const key = raw.toUpperCase().replace(/_\d+$/, "");
  return key === "NO_STATUS" || key === "NONE" ? null : key;
}

export function statusInfo(key: string): { label: string; cls: StatusClass } {
  return GARMIN_STATUS[key] ?? { label: titleCase(key), cls: "neutral" };
}

/** Order statuses good → serious so legends read from best to worst. */
export const CLASS_ORDER: StatusClass[] = ["good", "neutral", "warning", "serious"];

export function classColor(cls: StatusClass, mode: Mode): string {
  return cls === "neutral" ? NEUTRAL[mode] : STATUS[cls];
}

/** StatusPill status for a class (neutral has no status colour). */
export function classStatus(cls: StatusClass): Status | null {
  return cls === "neutral" ? null : cls;
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

/**
 * For stacked columns: which series is the top non-empty segment of each column, so only that
 * segment gets the rounded data-end (`values[series][column]`).
 */
export function stackTops(values: number[][]): boolean[][] {
  const tops = values.map((row) => row.map(() => false));
  const columns = values[0]?.length ?? 0;
  for (let j = 0; j < columns; j++) {
    for (let i = values.length - 1; i >= 0; i--) {
      if ((values[i]?.[j] ?? 0) > 0) {
        tops[i]![j] = true;
        break;
      }
    }
  }
  return tops;
}

/** "3 Nov" for weeks, "Nov 25" for months. */
export function periodLabel(iso: string, period: "week" | "month"): string {
  const d = new Date(`${iso}T12:00:00`);
  return period === "week"
    ? d.toLocaleDateString(undefined, { day: "numeric", month: "short" })
    : d.toLocaleDateString(undefined, { month: "short", year: "2-digit" });
}

export function periodTitle(iso: string, period: "week" | "month"): string {
  const d = new Date(`${iso}T12:00:00`);
  return period === "week"
    ? `Week of ${d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}`
    : d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
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
