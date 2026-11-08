/**
 * Calendar heatmap (ECharts `calendar` + heatmap series): one row per year, each row clipped to
 * the days inside the range but positioned on a Monday-first full-year week grid, so months
 * line up across years. In-range days without activity are faint "rest" cells. Magnitude uses
 * the sequential blue ramp in up to 4 quantile bins (GitHub style). Shared by the calendar and
 * year-in-review pages — a candidate for src/lib/charts.
 */
import { useCallback, useState } from "react";
import type { ChartOption } from "@/components/Chart";
import { addDays } from "@/lib/range";
import { CHROME, SEQUENTIAL, type Mode } from "@/lib/tokens";

export interface HeatBin {
  /** Exclusive lower edge. */
  min: number;
  /** Inclusive upper edge (null = open-ended). */
  max: number | null;
  color: string;
  label: string;
}

/**
 * Up to 4 bins cut at the (rounded) quartiles of the positive values. The ramp skips its
 * lightest step so even the lowest bin stands clear of the rest-day colour in both themes.
 */
export function quantileBins(
  values: number[],
  mode: Mode,
  nice: (v: number) => number,
  fmt: (v: number) => string,
): HeatBin[] {
  const pos = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (!pos.length) return [];
  const q = (p: number) => pos[Math.min(pos.length - 1, Math.round(p * (pos.length - 1)))]!;
  const cuts = [...new Set([q(0.25), q(0.5), q(0.75)].map(nice))]
    .filter((c) => c > 0 && c < pos[pos.length - 1]!)
    .sort((a, b) => a - b);
  const edges = [0, ...cuts];
  const ramp = SEQUENTIAL[mode].slice(1);
  return edges.map((lo, i) => {
    const hi = edges[i + 1] ?? null;
    const step =
      edges.length === 1
        ? ramp.length - 1
        : Math.round((i * (ramp.length - 1)) / (edges.length - 1));
    return {
      min: lo,
      max: hi,
      color: ramp[step]!,
      label:
        hi === null
          ? i === 0
            ? "Active"
            : `over ${fmt(lo)}`
          : i === 0
            ? `up to ${fmt(hi)}`
            : `${fmt(lo)}–${fmt(hi)}`,
    };
  });
}

/** Colour of a day in the range without activity. */
export function restColor(mode: Mode): string {
  return CHROME[mode].grid;
}

const LEFT = 42; // weekday labels (the year label sits in the month-label line)
const TOP = 20; // month labels of the first row
const ROW_GAP = 30;
const WEEKS = 54;

/** Square cell size that fits a full year into `width`, never below `min` (then it scrolls). */
export function cellSize(width: number, min = 11, max = 22): number {
  return Math.max(min, Math.min(max, Math.floor((width - LEFT - 4) / WEEKS)));
}

/** Width of the widest row: rows end at 31 December or at `end`, whichever comes first. */
export function heatmapWidth(cell: number, start: string, end: string): number {
  const cols = yearsBetween(start, end).map((y) =>
    weekColumn(`${y}-12-31` < end ? `${y}-12-31` : end),
  );
  return LEFT + (Math.max(0, ...cols) + 1) * cell + 4;
}

export function heatmapHeight(years: number, cell: number): number {
  return TOP + years * (cell * 7 + ROW_GAP) - ROW_GAP + 4;
}

export function yearsBetween(start: string, end: string): number[] {
  const out: number[] = [];
  for (let y = Number(start.slice(0, 4)); y <= Number(end.slice(0, 4)); y++) out.push(y);
  return out;
}

/** Monday-first week column of `iso` within its year (0 = the week holding 1 January). */
function weekColumn(iso: string): number {
  const d = new Date(`${iso}T12:00:00`);
  const jan1 = new Date(d.getFullYear(), 0, 1, 12);
  const doy = Math.round((d.getTime() - jan1.getTime()) / 86_400_000);
  return Math.floor((doy + ((jan1.getDay() + 6) % 7)) / 7);
}

export function calendarHeatmapOption({
  start,
  end,
  values,
  bins,
  cell,
  mode,
  tooltip,
  label,
}: {
  start: string;
  end: string;
  /** Metric per active day (ISO day → value). */
  values: Map<string, number>;
  bins: HeatBin[];
  cell: number;
  mode: Mode;
  tooltip: (day: string) => string;
  label: string;
}): ChartOption {
  const c = CHROME[mode];
  const rows = yearsBetween(start, end).map((y, i) => ({
    year: y,
    from: `${y}-01-01` > start ? `${y}-01-01` : start,
    to: `${y}-12-31` < end ? `${y}-12-31` : end,
    top: TOP + i * (cell * 7 + ROW_GAP),
  }));
  const item = {
    borderColor: c.surface,
    borderWidth: cell >= 14 ? 2 : 1.5,
    borderRadius: Math.max(2, Math.round(cell / 5)),
  };
  // One heatmap series per year row; every in-range day is a cell (rest days carry 0).
  const series = rows.map((r, i) => {
    const data: [string, number][] = [];
    for (let d = r.from; d <= r.to; d = addDays(d, 1)) data.push([d, values.get(d) ?? 0]);
    return {
      type: "heatmap",
      name: `${r.year} ${label}`,
      coordinateSystem: "calendar",
      calendarIndex: i,
      data,
      itemStyle: item,
      emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1.5 } },
    };
  });
  const text = (t: string, left: number, top: number, size: number, strong = false) => ({
    text: t,
    left,
    top,
    padding: 0,
    textStyle: {
      fontSize: size,
      fontWeight: strong ? 600 : 400,
      color: strong ? c.text2 : c.muted,
      lineHeight: size + 2,
    },
  });
  return {
    // Heatmaps take their colours from a visualMap: rest days + the quantile bins.
    visualMap: {
      type: "piecewise",
      show: false,
      dimension: 1,
      seriesIndex: series.map((_, i) => i),
      pieces: [
        { value: 0, color: restColor(mode) },
        ...bins.map((b) =>
          b.max === null
            ? { gt: b.min, color: b.color }
            : { gt: b.min, lte: b.max, color: b.color },
        ),
      ],
    },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (p: unknown) => tooltip((p as { value: [string, number] }).value[0]),
    },
    // Year + weekday labels as titles: they stay at the row start even for clipped rows.
    title: rows.flatMap((r) => [
      text(String(r.year), 0, r.top - 17, 11, true),
      ...[0, 2, 4].map((wd) =>
        text(["Mon", "", "Wed", "", "Fri"][wd]!, 6, r.top + wd * cell + (cell - 12) / 2, 10),
      ),
    ]),
    calendar: rows.map((r) => ({
      orient: "horizontal",
      range: [r.from, r.to],
      left: LEFT + weekColumn(r.from) * cell,
      top: r.top,
      cellSize: [cell, cell],
      splitLine: { show: false },
      itemStyle: { color: "transparent", borderWidth: 0 },
      yearLabel: { show: false },
      dayLabel: { show: false, firstDay: 1 },
      monthLabel: { color: c.muted, fontSize: 11, margin: 6, align: "left" },
    })),
    series,
  };
}

/** Content width of an element, kept up to date with a ResizeObserver. */
export function useElementWidth<T extends HTMLElement>(): [(node: T | null) => void, number] {
  const [width, setWidth] = useState(0);
  const ref = useCallback((node: T | null) => {
    if (!node) return;
    setWidth(Math.floor(node.getBoundingClientRect().width));
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.floor(w));
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}
