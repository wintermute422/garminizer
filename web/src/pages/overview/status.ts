/** Garmin state keys → status colour (or neutral) + readable label. */
import { titleCase } from "@/lib/format";
import type { Status } from "@/lib/tokens";

export interface StateInfo {
  status: Status | null;
  label: string;
}

function lookup(map: Record<string, Status | null>, key: string | null | undefined): StateInfo {
  if (!key) return { status: null, label: "No status" };
  return { status: map[key] ?? null, label: titleCase(key) };
}

const READINESS: Record<string, Status | null> = {
  PRIME: "good",
  HIGH: "good",
  MODERATE: null,
  LOW: "warning",
  POOR: "critical",
};

const HRV: Record<string, Status | null> = {
  BALANCED: "good",
  UNBALANCED: "warning",
  LOW: "serious",
  POOR: "critical",
};

const TRAINING: Record<string, Status | null> = {
  PEAKING: "good",
  PRODUCTIVE: "good",
  MAINTAINING: null,
  RECOVERY: null,
  UNPRODUCTIVE: "warning",
  DETRAINING: "serious",
  OVERREACHING: "critical",
  STRAINED: "critical",
};

const ACWR: Record<string, Status | null> = {
  LOW: null,
  OPTIMAL: "good",
  HIGH: "warning",
  VERY_HIGH: "critical",
};

const SLEEP: Record<string, Status | null> = {
  EXCELLENT: "good",
  GOOD: "good",
  FAIR: null,
  POOR: "serious",
};

export const readinessState = (k: string | null | undefined) => lookup(READINESS, k);
export const hrvState = (k: string | null | undefined) => lookup(HRV, k);
export const trainingState = (k: string | null | undefined) => lookup(TRAINING, k);
export const acwrState = (k: string | null | undefined) => lookup(ACWR, k);
export const sleepState = (k: string | null | undefined) => lookup(SLEEP, k);

export function loadBalanceState(k: string | null | undefined): StateInfo {
  if (!k) return { status: null, label: "No feedback" };
  if (k === "BALANCED") return { status: "good", label: "Balanced" };
  return { status: "warning", label: titleCase(k) };
}

/** Garmin's stress bands for a 0–100 stress level. */
export function stressLabel(v: number | null | undefined): string {
  if (v === null || v === undefined) return "No data";
  if (v <= 25) return "Resting";
  if (v <= 50) return "Low";
  if (v <= 75) return "Medium";
  return "High";
}
