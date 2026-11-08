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

export type CallTone = "go" | "steady" | "easy";

export interface TodaysCall {
  tone: CallTone;
  status: Status;
  headline: string;
  reasons: string[];
}

interface CallInput {
  readiness: {
    score: number | null;
    level: string | null;
    recovery_time_min: number | null;
  } | null;
  hrv: { status: string | null } | null;
  sleep: { duration_s: number | null; score: number | null } | null;
  tsb: number | null;
  acwrStatus: string | null;
  batteryAtWake: number | null;
}

function hours(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
}

const signedInt = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(Math.round(v))}`;

/**
 * A rule-based, deliberately simple call for the day from Garmin readiness, HRV, sleep,
 * recovery time, acute:chronic load and form. Red flags win over amber ones; green needs
 * good readiness and no flags. Returns null when there is too little data to say anything.
 */
export function todaysCall(x: CallInput): TodaysCall | null {
  const score = x.readiness?.score ?? null;
  const hrv = x.hrv?.status ?? null;
  const sleepS = x.sleep?.duration_s ?? null;
  const recovery = x.readiness?.recovery_time_min ?? null;
  if (score === null && hrv === null && sleepS === null) return null;

  const red: string[] = [];
  const amber: string[] = [];
  if (score !== null && score < 40) red.push(`readiness ${score}`);
  else if (score !== null && score < 70) amber.push(`readiness ${score}`);
  if (hrv === "LOW" || hrv === "POOR") red.push(`HRV ${hrv.toLowerCase()}`);
  else if (hrv === "UNBALANCED") amber.push("HRV unbalanced");
  if (sleepS !== null && sleepS < 6 * 3600) red.push(`sleep ${hours(sleepS)}`);
  else if (sleepS !== null && sleepS < 7 * 3600) amber.push(`sleep ${hours(sleepS)}`);
  if (recovery !== null && recovery > 24 * 60)
    red.push(`${Math.round(recovery / 60)}h recovery left`);
  else if (recovery !== null && recovery > 6 * 60)
    amber.push(`${Math.round(recovery / 60)}h recovery left`);
  if (x.acwrStatus === "VERY_HIGH") red.push("acute load very high");
  else if (x.acwrStatus === "HIGH") amber.push("acute load high");
  if (x.batteryAtWake !== null && x.batteryAtWake < 25)
    red.push(`body battery ${x.batteryAtWake} at wake`);
  if (x.tsb !== null && x.tsb < -20) amber.push(`form ${signedInt(x.tsb)}`);

  if (red.length)
    return {
      tone: "easy",
      status: "serious",
      headline: "Take it easy today",
      reasons: [...red, ...amber].slice(0, 3),
    };
  if (amber.length || score === null)
    return {
      tone: "steady",
      status: "warning",
      headline: "Keep it steady — easy aerobic work rather than intervals",
      reasons: amber.length ? amber.slice(0, 3) : ["no readiness score for today"],
    };
  const good: string[] = [
    `readiness ${score}${x.readiness?.level ? ` (${x.readiness.level.toLowerCase()})` : ""}`,
  ];
  if (hrv === "BALANCED") good.push("HRV balanced");
  if (x.tsb !== null && x.tsb >= -5) good.push(`form ${signedInt(x.tsb)}`);
  else if (sleepS !== null) good.push(`slept ${hours(sleepS)}`);
  return { tone: "go", status: "good", headline: "Green light for a hard session", reasons: good };
}
