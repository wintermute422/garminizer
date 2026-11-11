/**
 * Option builders so every chart follows the same mark specs: 2px lines, 10 % area wash,
 * bars ≤ 24px with 4px rounded data-ends, 2px surface gaps in stacks, recessive axes,
 * crosshair tooltips, one y-axis per chart (never dual axes).
 */
import { fmtDate } from "./format";
import { addDays } from "./range";
import { CHROME, MARK_RADIUS, type Mode, barEnd, wash } from "./tokens";

type Obj = Record<string, unknown>;

export const GRID = { left: 4, right: 12, top: 28, bottom: 4 };
export const GRID_WITH_LEGEND = { ...GRID, top: 40 };

export function legend(show = true): Obj {
  return { show, top: 0, left: 0, type: "scroll" };
}

export function timeXAxis(extra: Obj = {}): Obj {
  return { type: "time", ...extra };
}

export function categoryXAxis(data: (string | number)[], extra: Obj = {}): Obj {
  return { type: "category", data, axisTick: { show: false }, ...extra };
}

export function valueYAxis(name?: string, formatter?: (v: number) => string, extra: Obj = {}): Obj {
  return {
    type: "value",
    name,
    nameGap: 10,
    nameTextStyle: { align: "left" },
    splitNumber: 4,
    axisLabel: formatter ? { formatter } : {},
    ...extra,
  };
}

/** The fields of an ECharts tooltip parameter (one hovered point) that formatters read. */
export interface TipParam {
  value?: unknown;
  data?: unknown;
  axisValue?: number;
  dataIndex?: number;
  seriesIndex?: number;
  seriesId?: string;
  seriesName?: string;
  name?: string;
  color?: string;
}

/** Tooltip params as an array (axis triggers pass one per series, item triggers a single one). */
export function asParams<P = TipParam>(params: unknown): P[] {
  if (Array.isArray(params)) return params as P[];
  return params == null ? [] : [params as P];
}

/** Crosshair tooltip; the formatter always gets the hovered points as an array. */
export function axisTooltip<P = TipParam>(
  formatter?: (params: P[]) => string,
  extra: Obj = {},
): Obj {
  return {
    trigger: "axis",
    axisPointer: { type: "line" },
    confine: true,
    ...(formatter ? { formatter: (p: unknown) => formatter(asParams<P>(p)) } : {}),
    ...extra,
  };
}

export function itemTooltip<P = TipParam>(formatter?: (param: P) => string): Obj {
  return {
    trigger: "item",
    confine: true,
    ...(formatter ? { formatter: (p: unknown) => formatter(p as P) } : {}),
  };
}

export function line(
  name: string,
  data: unknown[],
  color: string,
  opts: { area?: boolean; smooth?: boolean; dashed?: boolean; width?: number; z?: number } = {},
): Obj {
  return {
    type: "line",
    name,
    data,
    showSymbol: false,
    symbol: "circle",
    symbolSize: 8,
    smooth: opts.smooth ?? false,
    connectNulls: false,
    z: opts.z,
    lineStyle: { width: opts.width ?? 2, color, type: opts.dashed ? "dashed" : "solid" },
    itemStyle: { color },
    emphasis: { focus: "none" },
    ...(opts.area ? { areaStyle: { color: wash(color, 0.12) } } : {}),
  };
}

export function bars(
  name: string,
  data: unknown[],
  color: string,
  mode: Mode,
  opts: { stack?: string; horizontal?: boolean; barMaxWidth?: number } = {},
): Obj {
  const radius = barEnd(opts.horizontal ? "right" : "up");
  return {
    type: "bar",
    name,
    data,
    stack: opts.stack,
    barMaxWidth: opts.barMaxWidth ?? 24,
    itemStyle: {
      color,
      borderRadius: opts.stack ? 0 : radius,
      borderColor: CHROME[mode].surface,
      borderWidth: opts.stack ? 1 : 0,
    },
    emphasis: { focus: "series" },
  };
}

function numericValue(d: unknown): number | null {
  const v = d && typeof d === "object" && "value" in d ? (d as { value: unknown }).value : d;
  const n = Array.isArray(v) ? v[v.length - 1] : v;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

/**
 * Round the visible top of every stacked column (the highest non-zero segment per category,
 * which is not always the last series) and keep hover from fading the rest of the stack.
 */
export function roundStackTops(series: Obj[], mode: Mode): Obj[] {
  const values = series.map((s) => ((s.data as unknown[]) ?? []).map(numericValue));
  const columns = values[0]?.length ?? 0;
  const top: number[] = [];
  for (let i = 0; i < columns; i++) {
    let k = values.length - 1;
    while (k >= 0 && !((values[k]?.[i] ?? 0) > 0)) k -= 1;
    top.push(k);
  }
  return series.map((s, k) => ({
    ...s,
    emphasis: { focus: "none" },
    data: ((s.data as unknown[]) ?? []).map((d, i) =>
      top[i] === k
        ? {
            value: d && typeof d === "object" && "value" in d ? (d as { value: unknown }).value : d,
            itemStyle: { borderRadius: barEnd("up"), borderColor: CHROME[mode].surface },
          }
        : d,
    ),
  }));
}

export function scatter(name: string, data: unknown[], color: string, size = 8): Obj {
  return {
    type: "scatter",
    name,
    data,
    symbolSize: size,
    itemStyle: { color, opacity: 0.85 },
  };
}

/** Thin dashed reference line (goal, average, threshold) with a label. */
export function refLine(value: number, label: string, mode: Mode, axis: "y" | "x" = "y"): Obj {
  return {
    silent: true,
    symbol: "none",
    lineStyle: { color: CHROME[mode].muted, type: [4, 4], width: 1 },
    label: { formatter: label, color: CHROME[mode].muted, fontSize: 11, position: "insideEndTop" },
    data: [{ [axis === "y" ? "yAxis" : "xAxis"]: value }],
  };
}

export function tooltipRow(color: string, label: string, value: string): string {
  return `<div style="display:flex;align-items:center;gap:8px;justify-content:space-between;min-width:160px"><span style="display:inline-flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:2px;background:${color};display:inline-block"></span>${label}</span><b style="font-variant-numeric:tabular-nums">${value}</b></div>`;
}

export function tooltipTitle(text: string): string {
  return `<div style="font-weight:600;margin-bottom:6px">${text}</div>`;
}

// ---------------------------------------------------------------- day-based time axes

export const DAY_MS = 86_400_000;

/** Chart x of an ISO day: its local noon (a day mark never lands on a DST-shifted midnight). */
export function dayX(day: string): number {
  return new Date(`${day}T12:00:00`).getTime();
}

/** [epochMillis, value] pairs from ISO days (noon local avoids DST edge cases). */
export function dayPoint(day: string, value: number | null | undefined): [number, number | null] {
  return [dayX(day), value ?? null];
}

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO day ("2026-10-31") of a chart x value made with `dayPoint` (local noon). */
export function dayOfPoint(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** x range of a time axis. */
export interface Extent {
  min: number;
  max: number;
}

/**
 * Time-axis extent of the days `start`…`end`. "half" (default) pads half a day around the
 * first and last noon marks so bars are not clipped; "midnight" runs from local midnight of
 * `start` to the midnight after `end` (charts whose marks span whole days).
 */
export function dayExtent(
  start: string,
  end: string,
  bounds: "half" | "midnight" = "half",
): Extent {
  if (bounds === "midnight")
    return {
      min: new Date(`${start}T00:00:00`).getTime(),
      max: new Date(`${addDays(end, 1)}T00:00:00`).getTime(),
    };
  return { min: dayX(start) - DAY_MS / 2, max: dayX(end) + DAY_MS / 2 };
}

/** Tooltip title of a day: weekday, day, month and year. */
export function dayTitle(day: string): string {
  return tooltipTitle(
    fmtDate(day, { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
  );
}

/**
 * Row under an axis tooltip of a one-row-per-day chart (`byX`: rows keyed by `dayX`): the
 * first hovered point whose [x, …] value is a known day, else the day under the axis pointer.
 */
export function rowAt<T>(params: unknown, byX: ReadonlyMap<number, T>): T | undefined {
  const arr = asParams(params);
  for (const p of arr) {
    const v = p.value;
    if (Array.isArray(v) && typeof v[0] === "number" && byX.has(v[0])) return byX.get(v[0]);
  }
  const x = arr[0]?.axisValue;
  return typeof x === "number" ? byX.get(dayX(dayOfPoint(x))) : undefined;
}

/**
 * Axis-tooltip formatter for a chart with one row per day: finds the hovered row (`rowAt`) and
 * renders it with its index, or shows nothing between days.
 */
export function dayTooltip<T>(
  rows: readonly T[],
  dayOf: (row: T) => string,
  render: (row: T, index: number) => string,
): (params: unknown) => string {
  const byX = new Map(rows.map((r, i) => [dayX(dayOf(r)), i]));
  return (params) => {
    const i = rowAt(params, byX);
    return i === undefined ? "" : render(rows[i]!, i);
  };
}

/** Monday of the ISO week that contains `day`. */
export function weekStart(day: string): string {
  const d = new Date(`${day}T12:00:00`);
  return addDays(day, -((d.getDay() + 6) % 7));
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

// ---------------------------------------------------------------- marks for daily series

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
  return wash(color, mode === "dark" ? 0.6 : 0.3);
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

/** Text label halo so reference labels stay legible where they cross data. */
export function halo(mode: Mode): Obj {
  return { backgroundColor: CHROME[mode].surface, padding: [1, 4], borderRadius: MARK_RADIUS };
}

/** Reference line whose label sits on a surface-coloured halo (legible over data). */
export function haloLine(value: number, label: string, mode: Mode, axis: "y" | "x" = "y"): Obj {
  const base = refLine(value, label, mode, axis);
  return { ...base, label: { ...(base.label as Obj), ...halo(mode) } };
}

// ---------------------------------------------------------------- round axis bounds

/** 1-2-2.5-3-5-10 × 10ⁿ: the smallest round step ≥ `raw` (raw > 0). */
export function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 3 ? 3 : f <= 5 ? 5 : 10) * p;
}

/**
 * Fixed axis bounds on a round step giving about `ticks` intervals, so labels never crowd.
 * `steps`: ascending candidates (the first ≥ the raw step wins, else the last) or a function of
 * the raw step. `floor` clamps the minimum; `even` extends the maximum to an even number of
 * steps (so the middle tick is round too).
 */
export function niceScale(
  lo: number,
  hi: number,
  opts: {
    steps: readonly number[] | ((raw: number) => number);
    ticks?: number;
    floor?: number;
    even?: boolean;
  },
): { min: number; max: number; interval: number } {
  const raw = (hi - lo) / (opts.ticks ?? 4);
  const { steps } = opts;
  const interval =
    typeof steps === "function"
      ? steps(raw)
      : (steps.find((s) => s >= raw) ?? steps[steps.length - 1]!);
  let min = Math.floor(lo / interval) * interval;
  if (opts.floor !== undefined) min = Math.max(opts.floor, min);
  let max = Math.ceil(hi / interval) * interval;
  if (opts.even && Math.round((max - min) / interval) % 2 === 1) max += interval;
  return { min, max, interval };
}

// ---------------------------------------------------------------- zoomable time axes

/** Extra height a zoomable chart gets for its slider row (the plot keeps its size). */
export const ZOOM_SLIDER_SPACE = 34;

/** Smallest window a day-based chart can be zoomed into. */
export const ZOOM_MIN_SPAN = 3 * DAY_MS;

/**
 * Make the first x-axis of `option` zoomable through a slider under the plot (drag the window
 * or its handles, brush on the track); `<Chart zoom>` adds ctrl+wheel / trackpad pinch. The
 * y-axis follows the visible data (`filterMode`). `slider: false` keeps the slider hidden: for
 * charts linked (`group`) to one that shows it, so the whole group zooms together.
 *
 * No `inside` dataZoom: its roam controller swallows every wheel and touch drag over the plot
 * (whatever `zoomOnMouseWheel` says), so the page could no longer scroll past a chart.
 */
export function withZoom(option: Obj, mode: Mode, slider = true): Obj {
  const grid = option.grid;
  const g = grid && !Array.isArray(grid) ? (grid as Obj) : null;
  const left = (g?.left as number | undefined) ?? GRID.left;
  const right = (g?.right as number | undefined) ?? GRID.right;
  const bottom = (g?.bottom as number | undefined) ?? GRID.bottom;
  const xAxis = Array.isArray(option.xAxis) ? (option.xAxis[0] as Obj) : (option.xAxis as Obj);
  const isTime = xAxis?.type === "time";
  const c = CHROME[mode];
  const zoom = {
    type: "slider",
    show: slider,
    xAxisIndex: 0,
    filterMode: "filter",
    ...(isTime ? { minValueSpan: ZOOM_MIN_SPAN } : {}),
  };
  if (!slider) return { ...option, dataZoom: [zoom] };
  return {
    ...option,
    // ECharts 6 lets axis labels hang below the grid down to `outerBounds`: lift both.
    ...(g
      ? {
          grid: {
            ...g,
            bottom: bottom + ZOOM_SLIDER_SPACE,
            outerBounds: {
              left: 0,
              right: 0,
              top: 0,
              ...(g.outerBounds as Obj),
              bottom: ZOOM_SLIDER_SPACE,
            },
          },
        }
      : {}),
    dataZoom: [
      {
        ...zoom,
        left: typeof left === "number" ? left + 8 : left,
        right: typeof right === "number" ? right + 8 : right,
        bottom: 6,
        height: 18,
        showDataShadow: false,
        borderColor: c.axis,
        backgroundColor: "transparent",
        fillerColor: c.zoom,
        handleSize: "110%",
        handleStyle: { color: c.surface, borderColor: c.muted },
        moveHandleSize: 5,
        moveHandleStyle: { color: c.axis, opacity: 1 },
        emphasis: {
          handleStyle: { borderColor: c.text2 },
          moveHandleStyle: { color: c.muted },
        },
        textStyle: { color: c.muted, fontSize: 11 },
        ...(isTime
          ? {
              labelFormatter: (v: number) =>
                new Date(v).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                  year: "2-digit",
                }),
            }
          : {}),
      },
    ],
  };
}

/** The visible window of a zoomable chart, as read back from `getOption().dataZoom`. */
export interface ZoomWindow {
  /** Percent of the full axis. */
  start: number;
  end: number;
  startValue?: number;
  endValue?: number;
}

/** True when the window shows less than the whole axis. */
export function isZoomed(w: ZoomWindow | undefined): boolean {
  return !!w && (w.start > 0.01 || w.end < 99.99);
}

/**
 * New window after a ctrl+wheel step at axis value `x`: `factor` < 1 zooms in, > 1 out; the
 * value under the pointer stays put. Clamped to the full axis and to `minSpan`.
 */
export function zoomAround(
  w: ZoomWindow,
  x: number,
  factor: number,
  minSpan = 0,
): { startValue: number; endValue: number } | null {
  if (w.startValue == null || w.endValue == null || w.end <= w.start) return null;
  const shown = w.endValue - w.startValue;
  const full = (shown * 100) / (w.end - w.start);
  const lo = w.startValue - (w.start / 100) * full;
  const hi = lo + full;
  const span = Math.min(full, Math.max(minSpan, shown * factor));
  const t = shown > 0 ? Math.min(1, Math.max(0, (x - w.startValue) / shown)) : 0.5;
  let start = x - t * span;
  start = Math.min(hi - span, Math.max(lo, start));
  return { startValue: start, endValue: start + span };
}

/**
 * Tick patch for a `dayAxis` x-axis after zooming: the calm weekly/monthly ticks of the visible
 * window (they were computed for the full range). Null when the axis is not a `dayAxis`.
 */
export function zoomedDayTicks(option: Obj, w: ZoomWindow): Obj | null {
  const xAxis = Array.isArray(option.xAxis) ? (option.xAxis[0] as Obj) : (option.xAxis as Obj);
  const label = xAxis?.axisLabel as Obj | undefined;
  if (xAxis?.type !== "time" || !Array.isArray(label?.customValues)) return null;
  if (w.startValue == null || w.endValue == null) return null;
  const a = dayAxis(w.startValue, w.endValue);
  return { xAxis: { axisTick: a.axisTick, axisLabel: a.axisLabel } };
}
