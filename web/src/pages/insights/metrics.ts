/** Display helpers for the daily insight metrics (labels, units, conversions, wording). */
import type { Schemas } from "@/api/client";
import {
  fmtCompact,
  fmtHours,
  fmtNumber,
  signed,
  titleCase,
  weightValue,
  type UnitSystem,
} from "@/lib/format";
import { CHROME, DIVERGING, type Mode } from "@/lib/tokens";

type Metric = Schemas["InsightMetric"];

export interface MetricView {
  key: string;
  label: string;
  /** Display unit, "" for unitless scores and loads. */
  unit: string;
  /** API value (SI) → display number (axes, bars). */
  value: (v: number) => number;
  /** API value (SI) → text with unit. */
  text: (v: number) => string;
  /** Display-unit step used in "+1 … goes with …" sentences. */
  step: number;
  /** A signed change in display units as words: "+1 point of sleep score", "+1,000 steps". */
  amount: (d: number) => string;
  digits: number;
}

const STEP: Record<string, number> = { steps: 1000, active_kcal: 100, load: 10 };

export function metricView(
  key: string,
  metrics: Metric[] | undefined,
  units: UnitSystem,
): MetricView {
  const m = metrics?.find((x) => x.key === key);
  const label = m?.label ?? titleCase(key);
  const kind = m?.unit ?? "";
  const of = phrase(label);
  const num = (d: number) => signed(d, Math.abs(d) >= 10 || Number.isInteger(d) ? 0 : 1);
  const base = { key, label, step: STEP[key] ?? 1 };
  const plain = (digits: number, unit: string): MetricView => ({
    ...base,
    unit,
    value: (v) => v,
    text: (v) => `${fmtNumber(v, digits)}${unit ? ` ${unit}` : ""}`,
    amount: (d) =>
      kind === "score"
        ? `${num(d)} ${Math.abs(d) === 1 ? "point" : "points"} of ${of}`
        : kind === "load"
          ? `${num(d)} ${of}`
          : `${num(d)} ${unit} of ${of}`,
    digits,
  });
  switch (kind) {
    case "s":
      return {
        ...plain(1, "h"),
        value: (v) => v / 3600,
        text: (v) => fmtHours(v),
        amount: (d) =>
          Math.abs(d) < 1
            ? `${d < 0 ? "−" : "+"}${fmtNumber(Math.abs(d) * 60)} min of ${of}`
            : `${num(d)} h of ${of}`,
      };
    case "kg": {
      const u = units === "metric" ? "kg" : "lb";
      return {
        ...plain(1, u),
        value: (v) => weightValue(v, units),
        text: (v) => `${fmtNumber(weightValue(v, units), 1)} ${u}`,
      };
    }
    case "steps":
      return {
        ...plain(0, "steps"),
        text: (v) => `${fmtCompact(v)} steps`,
        amount: (d) => `${num(d)} steps`,
      };
    case "score":
    case "load":
      return plain(0, "");
    case "ml/kg/min":
      return plain(1, kind);
    default:
      return plain(0, kind);
  }
}

export function axisName(m: MetricView): string {
  return m.unit ? `${m.label} (${m.unit})` : m.label;
}

export type Strength = "strong" | "moderate" | "weak" | "none";

/** Same thresholds as the backend's card wording (|r| ≥ 0.5 strong, ≥ 0.3 moderate). */
export function strength(r: number): Strength {
  const a = Math.abs(r);
  return a >= 0.5 ? "strong" : a >= 0.3 ? "moderate" : a >= 0.1 ? "weak" : "none";
}

export function linkText(r: number): string {
  const s = strength(r);
  if (s === "none") return "No meaningful link";
  return `${s[0]!.toUpperCase()}${s.slice(1)} ${r > 0 ? "positive" : "negative"} link`;
}

export function lagText(lag: number): string {
  return lag === 0 ? "the same day" : lag === 1 ? "the next day" : `${lag} days later`;
}

/** r with a proper minus and without the leading zero: ".68", "−.44". */
export function fmtR(r: number, digits = 2): string {
  const s = Math.abs(r).toFixed(digits).replace(/^0/, "");
  return r < 0 ? `−${s}` : s;
}

function rgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Colour of r on the diverging ramp (linear RGB, as ECharts' visualMap interpolates). */
export function divergingColor(r: number, mode: Mode): string {
  const d = DIVERGING[mode];
  const a = rgb(d.mid);
  const b = rgb(r >= 0 ? d.positive : d.negative);
  const t = Math.min(Math.abs(r), 1);
  const c = a.map((v, i) => Math.round(v + (b[i]! - v) * t));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  }) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Whichever ink token (dark or light) has more contrast on the given fill. */
export function inkOn(fill: string): string {
  const l = luminance(fill);
  const dark = CHROME.light.text;
  const light = CHROME.dark.text;
  const cDark = (l + 0.05) / (luminance(dark) + 0.05);
  const cLight = (luminance(light) + 0.05) / (l + 0.05);
  return cDark >= cLight ? dark : light;
}

/** Label for use mid-sentence: "Sleep score" → "sleep score", but "VO2max", "HRV" and
 *  "Body Battery" keep their capitals. */
export function phrase(label: string): string {
  if (label.startsWith("Body Battery")) return label;
  const second = label.charAt(1);
  if (second && second === second.toUpperCase() && second !== second.toLowerCase()) return label;
  if (/^\w\d/.test(label)) return label;
  return label.charAt(0).toLowerCase() + label.slice(1);
}
