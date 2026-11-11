/** Records page helpers: duration ticks, day-of-year months, pace/speed values, Garmin PR types. */
import { niceScale } from "@/lib/charts";
import {
  distanceUnit,
  fmtDuration,
  fmtNumber,
  paceSeconds,
  speedUnit,
  speedValue,
  titleCase,
  type UnitSystem,
} from "@/lib/format";
import { usesPace } from "@/lib/sports";

/** Mean-max x-axis ticks (seconds): 5 s, 1 min, 5 min, 20 min, 1 h. */
export const CURVE_TICKS = [5, 60, 300, 1200, 3600];

/** Short duration label for axis ticks: 5s, 1m, 20m, 1h, 2.5h. */
export function durTick(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${fmtNumber(s / 3600, s % 3600 ? 1 : 0)}h`;
}

/** Readable duration: "5 s", "1 min", "1 h 30 min". */
export function durText(s: number): string {
  if (s < 60) return `${Math.round(s)} s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m ? `${h} h ${m} min` : `${h} h`;
}

/** Day-of-year (non-leap) of each month start, for the cumulative x-axis. */
export const MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];

export function monthOfDoy(doy: number): string {
  return new Date(2001, 0, doy).toLocaleDateString(undefined, { month: "short" });
}

/** "Oct 31, 2026" for a day of a given year. */
export function doyDate(year: number, doy: number): string {
  return new Date(year, 0, doy).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function doyLabel(doy: number): string {
  return new Date(2001, 0, doy).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export type CurveMetric = "speed" | "power" | "hr";

/** How a curve metric is shown for a sport: pace (inverted axis), speed, power or HR. */
export function curveDisplay(
  metric: CurveMetric,
  sport: string,
  units: UnitSystem,
): {
  value: (raw: number) => number | null;
  format: (v: number) => string;
  unit: string;
  inverse: boolean;
  /** Ratio of a value to the best (1 = as good as the best), null when not meaningful. */
  ratio: ((v: number, best: number) => number) | null;
} {
  if (metric === "power")
    return {
      value: (v) => v,
      format: (v) => fmtNumber(v),
      unit: "W",
      inverse: false,
      ratio: (v, b) => v / b,
    };
  if (metric === "hr")
    return {
      value: (v) => v,
      format: (v) => fmtNumber(v),
      unit: "bpm",
      inverse: false,
      ratio: null,
    };
  if (usesPace(sport)) {
    const swim = sport === "swim";
    const per = swim ? (units === "metric" ? 100 : 91.44) : null;
    return {
      value: (v) => (v < 0.3 ? null : per ? per / v : paceSeconds(v, units)),
      format: (v) => fmtDuration(v),
      unit: swim ? (units === "metric" ? "/100 m" : "/100 yd") : `/${distanceUnit(units)}`,
      inverse: true,
      ratio: (v, b) => b / v,
    };
  }
  return {
    value: (v) => speedValue(v, units),
    format: (v) => fmtNumber(v, 1),
    unit: speedUnit(units),
    inverse: false,
    ratio: (v, b) => v / b,
  };
}

export type PrKind = "time" | "distance" | "elevation" | "power" | "steps" | "days" | "number";

const DISTANCE_TOKENS: Record<string, [number, string]> = {
  "400m": [400, "400 m"],
  "1k": [1000, "1 km"],
  "1km": [1000, "1 km"],
  mile: [1609.344, "1 mile"],
  "1mile": [1609.344, "1 mile"],
  "5k": [5000, "5 km"],
  "10k": [10000, "10 km"],
  "15k": [15000, "15 km"],
  half_marathon: [21097.5, "Half marathon"],
  marathon: [42195, "Marathon"],
  "40k": [40000, "40 km"],
};

const SPORT_WORDS: Record<string, string> = {
  run: "run",
  running: "run",
  ride: "ride",
  bike: "ride",
  cycling: "ride",
  swim: "swim",
  swimming: "swim",
  walk: "walk",
  walking: "walk",
};

/** Interpret a Garmin personal-record type key (e.g. run_5k, longest_ride, most_steps_day). */
export function prInfo(typeKey: string): {
  label: string;
  kind: PrKind;
  sport: string | null;
  distance: number | null;
} {
  const k = typeKey.toLowerCase();
  const longest = k.match(/^longest_([a-z]+)$/);
  if (longest) {
    const sport = SPORT_WORDS[longest[1]!] ?? null;
    return { label: `Longest ${sport ?? longest[1]}`, kind: "distance", sport, distance: null };
  }
  const sentence = (s: string) => {
    const t = titleCase(s).toLowerCase();
    return t.charAt(0).toUpperCase() + t.slice(1);
  };
  if (k.includes("steps"))
    return {
      label: sentence(k.replace(/_(day|week|month)$/, "_in_a_$1")),
      kind: "steps",
      sport: "walk",
      distance: null,
    };
  if (/ascent|climb|elevation/.test(k))
    return { label: sentence(k), kind: "elevation", sport: null, distance: null };
  if (k.includes("power"))
    return { label: sentence(k), kind: "power", sport: "ride", distance: null };
  if (k.includes("streak"))
    return { label: sentence(k), kind: "days", sport: null, distance: null };
  const timed = k.match(/^([a-z]+)_(.+)$/);
  if (timed && SPORT_WORDS[timed[1]!]) {
    const sport = SPORT_WORDS[timed[1]!]!;
    const token = DISTANCE_TOKENS[timed[2]!];
    const parsed = timed[2]!.match(/^(\d+(?:\.\d+)?)(m|k|km|y|yd|mi)$/);
    const distance = token
      ? token[0]
      : parsed
        ? Number(parsed[1]) *
          (
            { m: 1, k: 1000, km: 1000, y: 0.9144, yd: 0.9144, mi: 1609.344 } as Record<
              string,
              number
            >
          )[parsed[2]!]!
        : null;
    const name = token?.[1] ?? (parsed ? `${parsed[1]} ${parsed[2]}` : titleCase(timed[2]));
    return { label: name, kind: "time", sport, distance };
  }
  return { label: sentence(k), kind: "number", sport: null, distance: null };
}

const DURATION_STEPS = [1, 2, 5, 10, 15, 20, 30, 60, 120, 180, 240, 300, 600, 900, 1800, 3600];

/** Duration-axis bounds on a round step (s) giving about four intervals; never degenerate. */
export function niceDuration(
  lo: number,
  hi: number,
): { min: number; max: number; interval: number } {
  if (hi - lo < lo * 0.02) {
    lo -= lo * 0.02;
    hi += hi * 0.02;
  }
  return niceScale(lo, hi, { steps: DURATION_STEPS, floor: 0 });
}
