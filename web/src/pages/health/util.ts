/**
 * Helpers shared by the health, sleep and body pages (candidates for src/lib once a second
 * area needs them): period maths, weekly aggregation, athlete-time-zone wall clock for
 * intraday charts, floating range bars and per-measure colours.
 */
import { useSyncExternalStore } from "react";
import { addDays } from "@/lib/range";
import { CATEGORICAL, CHROME, MEASURE_COLORS, NEUTRAL, type Mode, type Status } from "@/lib/tokens";

type Obj = Record<string, unknown>;

export const HOUR_MS = 3_600_000;
export const DAY_MS = 24 * HOUR_MS;

const NARROW = "(max-width: 640px)";

/** Phone-width viewport: dense bars and heatmap cells drop their 1px surface gaps. */
export function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia?.(NARROW);
      mq?.addEventListener("change", cb);
      return () => mq?.removeEventListener("change", cb);
    },
    () => window.matchMedia?.(NARROW).matches ?? false,
    () => false,
  );
}

// ---------------------------------------------------------------- periods and statistics

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

/** Monday of the ISO week that contains `day`. */
export function weekStart(day: string): string {
  const d = new Date(`${day}T12:00:00`);
  return addDays(day, -((d.getDay() + 6) % 7));
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

// ---------------------------------------------------------------- athlete wall clock

const dtfCache = new Map<string, Intl.DateTimeFormat | null>();

function formatter(tz: string): Intl.DateTimeFormat | null {
  if (!dtfCache.has(tz)) {
    try {
      dtfCache.set(
        tz,
        new Intl.DateTimeFormat("en-US", {
          timeZone: tz,
          hourCycle: "h23",
          year: "numeric",
          month: "numeric",
          day: "numeric",
          hour: "numeric",
          minute: "numeric",
          second: "numeric",
        }),
      );
    } catch {
      dtfCache.set(tz, null);
    }
  }
  return dtfCache.get(tz) ?? null;
}

function offsetAt(tz: string, utcMs: number): number {
  const f = formatter(tz);
  if (!f) return 0;
  const parts = f.formatToParts(new Date(utcMs));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const asUtc = Date.UTC(
    get("year"),
    get("month") - 1,
    get("day"),
    get("hour") % 24,
    get("minute"),
    get("second"),
  );
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

/**
 * UTC instant → the athlete's local wall-clock time expressed as a UTC epoch. Charts that use
 * it set `useUTC: true`, so axes and tooltips show the athlete's local time whatever the
 * browser's time zone is.
 */
export function wallClock(tz: string | null | undefined): (iso: string) => number {
  const zone = tz || "UTC";
  const cache = new Map<number, number>();
  return (iso: string) => {
    const t = Date.parse(iso);
    const hour = Math.floor(t / HOUR_MS);
    let off = cache.get(hour);
    if (off === undefined) {
      off = offsetAt(zone, hour * HOUR_MS);
      cache.set(hour, off);
    }
    return t + off;
  };
}

/** Local midnight of an ISO day in the wall-clock frame (see `wallClock`). */
export function wallMidnight(day: string): number {
  const [y, m, d] = day.split("-").map(Number);
  return Date.UTC(y!, (m ?? 1) - 1, d ?? 1);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "07:42" of a wall-clock epoch. */
export function fmtWallTime(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** Date of a wall-clock epoch, e.g. "Sat 31 Oct". */
export function fmtWallDate(ms: number, opts?: Intl.DateTimeFormatOptions): string {
  return new Date(ms).toLocaleDateString(undefined, {
    ...(opts ?? { weekday: "short", day: "numeric", month: "short" }),
    timeZone: "UTC",
  });
}

/** ISO day ("2026-10-31") of a chart x value made with `dayPoint` (local noon). */
export function dayOfPoint(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Calm date ticks for a day-based time axis: Mondays (weekly / fortnightly), month starts or
 * quarter starts depending on the span, labelled "3 Aug", "Sep" or the year at January.
 * ECharts' own time ticks mix day and month levels ("29Sep 5 8") at these widths.
 */
export function dayAxis(min: number, max: number): Obj {
  const span = (max - min) / DAY_MS;
  const first = dayOfPoint(min + DAY_MS / 2);
  const last = dayOfPoint(max - DAY_MS / 2);
  const values: number[] = [];
  const noon = (iso: string) => new Date(`${iso}T12:00:00`).getTime();
  let fmt: (v: number) => string;
  if (span <= 120) {
    const every = span <= 35 ? 7 : 14;
    let d = weekStart(first);
    if (d < first) d = addDays(d, 7);
    for (; d <= last; d = addDays(d, every)) values.push(noon(d));
    fmt = (v) => new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  } else {
    const months = span <= 400 ? 1 : span <= 800 ? 3 : 12;
    const [y0, m0] = first.split("-").map(Number);
    let y = y0!;
    let m = m0! - 1;
    if (first.slice(8) !== "01") m += 1;
    while (m % months !== 0) m += 1;
    for (;;) {
      y += Math.floor(m / 12);
      m %= 12;
      const iso = `${y}-${pad(m + 1)}-01`;
      if (iso > last) break;
      values.push(noon(iso));
      m += months;
    }
    fmt = (v) => {
      const d = new Date(v);
      return d.getMonth() === 0
        ? String(d.getFullYear())
        : d.toLocaleDateString(undefined, { month: "short" });
    };
  }
  return {
    type: "time",
    min,
    max,
    splitLine: { show: false },
    axisTick: { show: false, customValues: values },
    axisLabel: { customValues: values, formatter: fmt, hideOverlap: true },
  };
}

// ---------------------------------------------------------------- colours

/** One fixed categorical slot per measure, the same on every health page. */
export function measureColors(mode: Mode) {
  const m = MEASURE_COLORS[mode];
  const c = CATEGORICAL[mode];
  return {
    hr: m.hr,
    hrv: m.hrv,
    stress: m.stress,
    bodyBattery: m.bodyBattery,
    steps: m.steps,
    spo2: m.spo2,
    respiration: m.respiration,
    sleep: m.sleep,
    readiness: m.fitness,
    weight: m.weight,
    // Not in the shared measure set (body page only): distinct slots on that page.
    fat: c[1]!,
    muscle: c[2]!,
    pressure: c[6]!,
    // Weekday / weekend nights: two categorical slots + fill style as the second encoding.
    weekday: c[0]!,
    weekend: c[1]!,
    neutral: NEUTRAL[mode],
  };
}

/**
 * Raw daily dots under a trend line: lighter than the line but still ≥ 3:1 against the card
 * (a plain 40 % opacity sinks into the dark surface).
 */
export function dotStyle(color: string, mode: Mode): Obj {
  return { color, opacity: mode === "dark" ? 0.85 : 0.75, borderWidth: 0 };
}

/**
 * A trend line with a surface-coloured casing underneath, so it reads above dense dots.
 * Returns [casing, line]; keep the casing out of the legend with `legend.data`.
 */
export function cased(lineSeries: Obj, mode: Mode): Obj[] {
  const ls = (lineSeries.lineStyle as Obj | undefined) ?? {};
  return [
    {
      type: "line",
      name: CASING,
      data: lineSeries.data,
      symbol: "none",
      silent: true,
      connectNulls: false,
      lineStyle: { color: CHROME[mode].surface, width: ((ls.width as number) ?? 2) + 3 },
      itemStyle: { color: CHROME[mode].surface },
      tooltip: { show: false },
      z: 3,
    },
    { ...lineSeries, z: 4 },
  ];
}

export const CASING = "casing";

/** Value rounded the way it is displayed (so "no change" never wears an arrow colour). */
export function shown(v: number | null, digits: number): number | null {
  if (v == null) return null;
  return Math.abs(v) < 0.5 * 10 ** -digits ? 0 : v;
}

/** Garmin state strings → reserved status colours (always shown with icon + label). */
export function hrvStatus(s: string | null | undefined): Status | null {
  switch (s) {
    case "BALANCED":
      return "good";
    case "UNBALANCED":
      return "warning";
    case "LOW":
      return "serious";
    case "POOR":
      return "critical";
    default:
      return null;
  }
}

export function readinessStatus(level: string | null | undefined): Status | null {
  switch (level) {
    case "PRIME":
    case "HIGH":
      return "good";
    case "MODERATE":
      return "warning";
    case "LOW":
      return "serious";
    case "POOR":
      return "critical";
    default:
      return null;
  }
}

export function sleepQualityStatus(q: string | null | undefined): Status | null {
  switch (q) {
    case "EXCELLENT":
    case "GOOD":
      return "good";
    case "FAIR":
      return "warning";
    case "POOR":
      return "critical";
    default:
      return null;
  }
}

export function pressureStatus(category: string | null | undefined): Status | null {
  const c = (category ?? "").toUpperCase();
  if (!c) return null;
  if (c.includes("NORMAL") || c === "LOW") return "good";
  if (c.includes("ELEVATED")) return "warning";
  if (c.includes("CRISIS") || c.includes("STAGE_2") || c.includes("STAGE2")) return "critical";
  if (c.includes("STAGE") || c.includes("HIGH") || c.includes("HYPERTENSION")) return "serious";
  return null;
}

// ---------------------------------------------------------------- chart pieces

interface RenderApi {
  value: (dim: number) => number;
  coord: (v: number[]) => number[];
  size: (v: number[]) => number[];
}

/**
 * Floating bars from `lo` to `hi` (data `[x, lo, hi, ...]`), rounded at both data-ends.
 * `band` is the x distance one bar may occupy (a day in ms, 1 on a category axis).
 * `outline` draws a wash fill with a solid edge — the secondary encoding for a second group.
 */
export function rangeBars(
  name: string,
  data: unknown[],
  color: string,
  mode: Mode,
  opts: {
    band: number;
    maxWidth?: number;
    outline?: boolean;
    horizontal?: boolean;
    labels?: (lo: number, hi: number) => [string, string];
    z?: number;
  },
): Obj {
  const fill = opts.outline ? outlineFill(color, mode) : color;
  return {
    type: "custom",
    name,
    data,
    z: opts.z ?? 2,
    encode: opts.horizontal ? { y: 0, x: [1, 2] } : { x: 0, y: [1, 2] },
    itemStyle: { color: fill, borderColor: color },
    renderItem: (_params: unknown, api: RenderApi) => {
      const x = api.value(0);
      const lo = api.value(1);
      const hi = api.value(2);
      const a = opts.horizontal ? api.coord([lo, x]) : api.coord([x, lo]);
      const b = opts.horizontal ? api.coord([hi, x]) : api.coord([x, hi]);
      const bandPx = opts.horizontal
        ? Math.abs(api.size([0, opts.band])[1] ?? 0)
        : Math.abs(api.size([opts.band, 0])[0] ?? 0);
      const w = Math.max(2, Math.min(opts.maxWidth ?? 14, bandPx * 0.62));
      const ax = a[0]!;
      const ay = a[1]!;
      const bx = b[0]!;
      const by = b[1]!;
      const shape = opts.horizontal
        ? { x: Math.min(ax, bx), y: ay - w / 2, width: Math.max(Math.abs(bx - ax), 2), height: w }
        : { x: ax - w / 2, y: Math.min(ay, by), width: w, height: Math.max(Math.abs(by - ay), 2) };
      const r = Math.min(w / 2, 4);
      const rect = {
        type: "rect",
        shape: { ...shape, r },
        style: {
          fill,
          stroke: opts.outline ? color : null,
          lineWidth: opts.outline ? 1.5 : 0,
        },
      };
      if (!opts.labels) return rect;
      const [loText, hiText] = opts.labels(lo, hi);
      const text = (t: string, px: number, py: number, align: string, vAlign: string) => ({
        type: "text",
        style: {
          text: t,
          x: px,
          y: py,
          align,
          verticalAlign: vAlign,
          fill: CHROME[mode].text2,
          fontSize: 11,
        },
      });
      // Each label sits beyond its own end of the bar (axes may be inverted).
      const [first, second] = opts.horizontal
        ? ax <= bx
          ? [loText, hiText]
          : [hiText, loText]
        : ay <= by
          ? [loText, hiText]
          : [hiText, loText];
      const children = opts.horizontal
        ? [
            rect,
            text(first, Math.min(ax, bx) - 6, ay, "right", "middle"),
            text(second, Math.max(ax, bx) + 6, ay, "left", "middle"),
          ]
        : [
            rect,
            text(first, ax, Math.min(ay, by) - 4, "center", "bottom"),
            text(second, ax, Math.max(ay, by) + 4, "center", "top"),
          ];
      return { type: "group", children };
    },
  };
}

/**
 * Fill of an outlined (secondary-encoded) mark: a strong enough wash that it reads as the hue on
 * the dark card instead of a muddy brown, while the solid edge keeps it distinct from solid fills.
 */
export function outlineFill(color: string, mode: Mode): string {
  return washHex(color, mode === "dark" ? 0.6 : 0.3);
}

/** rgba() wash of a hex colour (same as tokens.wash; kept here for custom series fills). */
export function washHex(hex: string, alpha: number): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/**
 * Stacked bar series whose top-most non-empty segment in each column gets the 4px rounded
 * data-end (roundStackTops only rounds the last series, which may be empty).
 */
export function roundVisibleTops(series: Obj[]): Obj[] {
  const values = series.map((s) => (s.data as unknown[]).map(valueOf));
  const n = values[0]?.length ?? 0;
  const topIdx: number[] = [];
  for (let i = 0; i < n; i++) {
    let top = -1;
    for (let k = values.length - 1; k >= 0; k--) {
      const v = values[k]![i];
      if (v !== null && v !== undefined && v > 0) {
        top = k;
        break;
      }
    }
    topIdx.push(top);
  }
  return series.map((s, k) => ({
    ...s,
    // Hovering one segment must not fade the rest of the stack.
    emphasis: { focus: "none" },
    data: (s.data as unknown[]).map((d, i) =>
      topIdx[i] === k
        ? {
            value: d,
            itemStyle: { borderRadius: [4, 4, 0, 0] },
          }
        : d,
    ),
  }));
}

function valueOf(d: unknown): number | null {
  if (Array.isArray(d)) {
    const v = d[1];
    return typeof v === "number" ? v : null;
  }
  return typeof d === "number" ? d : null;
}

/** Title row of a small-multiple chart ("Heart rate (bpm)") in secondary ink. */
export function smallTitle(text: string, mode: Mode): Obj {
  return {
    text,
    left: 0,
    top: 0,
    textStyle: { fontSize: 12, fontWeight: 500, color: CHROME[mode].text2 },
  };
}

/** Tooltip line without a swatch (for context values). */
export function tooltipMuted(label: string, value: string, mode: Mode): string {
  return `<div style="display:flex;justify-content:space-between;gap:12px;min-width:160px;color:${CHROME[mode].muted}"><span>${label}</span><span style="font-variant-numeric:tabular-nums">${value}</span></div>`;
}

/** Marker size that keeps long ranges from turning into a carpet of dots. */
export function dotSize(points: number, base = 6): number {
  return points > 240 ? base - 2 : points > 120 ? base - 1 : base;
}

const LINE_ICON = "path://M0,0H24V5H0Z";

/** Legend entries whose icon matches the mark: dots for raw readings, a dash for lines. */
export function legendItems(items: [string, "dot" | "line" | "area"][]): Obj[] {
  return items.map(([name, kind]) => ({
    name,
    icon: kind === "dot" ? "circle" : kind === "line" ? LINE_ICON : "roundRect",
  }));
}
