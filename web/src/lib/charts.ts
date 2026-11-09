/**
 * Option builders so every chart follows the same mark specs: 2px lines, 10 % area wash,
 * bars ≤ 24px with 4px rounded data-ends, 2px surface gaps in stacks, recessive axes,
 * crosshair tooltips, one y-axis per chart (never dual axes).
 */
import { addDays } from "./range";
import { CHROME, type Mode, barEnd, wash } from "./tokens";

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

export function axisTooltip(formatter?: (params: unknown) => string, extra: Obj = {}): Obj {
  return {
    trigger: "axis",
    axisPointer: { type: "line" },
    confine: true,
    ...(formatter ? { formatter } : {}),
    ...extra,
  };
}

export function itemTooltip(formatter?: (params: unknown) => string): Obj {
  return { trigger: "item", confine: true, ...(formatter ? { formatter } : {}) };
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

/** [epochMillis, value] pairs from ISO days (noon local avoids DST edge cases). */
export function dayPoint(day: string, value: number | null | undefined): [number, number | null] {
  return [new Date(`${day}T12:00:00`).getTime(), value ?? null];
}

export const DAY_MS = 86_400_000;

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO day ("2026-10-31") of a chart x value made with `dayPoint` (local noon). */
export function dayOfPoint(ms: number): string {
  const d = new Date(ms);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
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
