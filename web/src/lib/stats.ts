/** Small statistics over daily series: period maths, means, quantiles, weekly and trailing aggregates. */
import { DAY_MS, weekStart } from "./charts";
import { addDays } from "./range";

/** Number of days in [start, end] (ISO days, inclusive). */
export function spanDays(start: string, end: string): number {
  const a = new Date(`${start}T12:00:00`).getTime();
  const b = new Date(`${end}T12:00:00`).getTime();
  return Math.round((b - a) / DAY_MS) + 1;
}

/** The period of the same length that ends the day before `start`. */
export function previousPeriod(q: { start: string; end: string }): { start: string; end: string } {
  const n = spanDays(q.start, q.end);
  return { start: addDays(q.start, -n), end: addDays(q.start, -1) };
}

function present(values: readonly (number | null | undefined)[]): number[] {
  return values.filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v));
}

export function mean(values: readonly (number | null | undefined)[]): number | null {
  const p = present(values);
  return p.length ? p.reduce((s, v) => s + v, 0) / p.length : null;
}

export function stdev(values: readonly (number | null | undefined)[]): number | null {
  const p = present(values);
  if (p.length < 2) return null;
  const m = p.reduce((s, v) => s + v, 0) / p.length;
  return Math.sqrt(p.reduce((s, v) => s + (v - m) ** 2, 0) / (p.length - 1));
}

export function minOf(values: readonly (number | null | undefined)[]): number | null {
  const p = present(values);
  return p.length ? Math.min(...p) : null;
}

export function maxOf(values: readonly (number | null | undefined)[]): number | null {
  const p = present(values);
  return p.length ? Math.max(...p) : null;
}

export function quantile(values: readonly (number | null | undefined)[], q: number): number | null {
  const s = present(values).sort((a, b) => a - b);
  if (!s.length) return null;
  return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))]!;
}

/** Difference of two optional numbers (null when either is missing). */
export function diff(a: number | null | undefined, b: number | null | undefined): number | null {
  return a == null || b == null ? null : a - b;
}

/** Aggregate rows per ISO week (mean of the non-null values by default). */
export function weekly<T>(
  rows: readonly T[],
  day: (r: T) => string,
  value: (r: T) => number | null | undefined,
  agg: (values: (number | null | undefined)[]) => number | null = mean,
): { week: string; value: number | null }[] {
  const groups = new Map<string, (number | null | undefined)[]>();
  for (const r of rows) {
    const k = weekStart(day(r));
    const g = groups.get(k);
    if (g) g.push(value(r));
    else groups.set(k, [value(r)]);
  }
  return [...groups.entries()].map(([week, vs]) => ({ week, value: agg(vs) }));
}

/** Trailing mean over the previous `days` calendar days (irregular samples, e.g. weigh-ins). */
export function trailingByTime(
  points: readonly { t: number; v: number | null }[],
  days: number,
): (number | null)[] {
  const out: (number | null)[] = [];
  let lo = 0;
  let sum = 0;
  let n = 0;
  for (let hi = 0; hi < points.length; hi++) {
    const cur = points[hi]!;
    if (cur.v !== null) {
      sum += cur.v;
      n += 1;
    }
    while (points[lo]!.t <= cur.t - days * DAY_MS) {
      const old = points[lo]!.v;
      if (old !== null) {
        sum -= old;
        n -= 1;
      }
      lo += 1;
    }
    out.push(n ? sum / n : null);
  }
  return out;
}
