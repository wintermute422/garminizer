/**
 * Calendar heatmap (ECharts `calendar` + heatmap series) in two layouts that always show the
 * whole range — nothing is cropped or hidden behind a scroll:
 * - "strip" (wide containers): one continuous strip of Monday-first weeks from the range start
 *   to the range end, wrapped every 53 weeks like lines of text;
 * - "months" (phones): one small month grid per month (weekdays as columns), 3–4 per row.
 * In-range days without activity are faint "rest" cells. Magnitude uses a 4-step blue ramp
 * whose every step clears 3:1 against the card in both themes. Shared by the calendar and
 * year-in-review pages — a candidate for src/lib/charts.
 */
import { useCallback, useState } from "react";
import type { ChartOption } from "@/components/Chart";
import { fmtMonth } from "@/lib/format";
import { addDays } from "@/lib/range";
import { BLUE, CHROME, type Mode } from "@/lib/tokens";

/** Low → high; each step ≥ 3:1 against the card surface (light 3.5–11.6, dark 3.2–13.2). */
export const HEAT_RAMP: Record<Mode, readonly string[]> = {
  light: [BLUE[400]!, BLUE[500]!, BLUE[600]!, BLUE[700]!],
  dark: [BLUE[500]!, BLUE[350]!, BLUE[200]!, BLUE[100]!],
};

export interface HeatBin {
  /** Exclusive lower edge. */
  min: number;
  /** Inclusive upper edge (null = open-ended). */
  max: number | null;
  color: string;
  label: string;
}

/** Up to 4 bins cut at the (rounded) quartiles of the positive values. */
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
  const ramp = HEAT_RAMP[mode];
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

const STRIP_LEFT = 34; // weekday labels
const STRIP_TOP = 20; // month labels above each row
const STRIP_ROW_GAP = 28;
const STRIP_WEEKS = 53;
const MIN_CELL = 11;
const MAX_CELL = 22;
const MONTH_GAP = 14;
const MONTH_TITLE = 18;

function monday(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return addDays(iso, -((d.getDay() + 6) % 7));
}

function weeksBetween(a: string, b: string): number {
  return Math.round(
    (new Date(`${b}T12:00:00`).getTime() - new Date(`${a}T12:00:00`).getTime()) / (7 * 86_400_000),
  );
}

interface Block {
  /** Calendar range (inclusive ISO days). */
  from: string;
  to: string;
  /** Data range inside this block (in-range days only). */
  dataFrom: string;
  dataTo: string;
  left: number;
  top: number;
  orient: "horizontal" | "vertical";
}

interface Layout {
  kind: "strip" | "months";
  cell: number;
  height: number;
  blocks: Block[];
  titles: { text: string; left: number; top: number; size: number; strong?: boolean }[];
}

function stripLayout(width: number, start: string, end: string): Layout | null {
  const first = monday(start);
  const weeks = weeksBetween(first, monday(end)) + 1;
  const perRow = Math.min(weeks, STRIP_WEEKS);
  const cell = Math.min(MAX_CELL, Math.floor((width - STRIP_LEFT - 4) / perRow));
  if (cell < MIN_CELL) return null;
  const rows = Math.ceil(weeks / STRIP_WEEKS);
  const rowH = cell * 7 + STRIP_ROW_GAP;
  const blocks: Block[] = [];
  const titles: Layout["titles"] = [];
  for (let r = 0; r < rows; r++) {
    const rowStart = addDays(first, r * STRIP_WEEKS * 7);
    const rowEnd = addDays(rowStart, STRIP_WEEKS * 7 - 1);
    const from = r === 0 ? start : rowStart;
    const to = rowEnd < end ? rowEnd : end;
    const top = STRIP_TOP + r * rowH;
    blocks.push({
      from,
      to,
      dataFrom: from,
      dataTo: to,
      left: STRIP_LEFT,
      top,
      orient: "horizontal",
    });
    for (const wd of [0, 2, 4])
      titles.push({
        text: ["Mon", "", "Wed", "", "Fri"][wd]!,
        left: 2,
        top: top + wd * cell + (cell - 12) / 2,
        size: 10,
      });
  }
  return {
    kind: "strip",
    cell,
    height: STRIP_TOP + rows * rowH - STRIP_ROW_GAP + 4,
    blocks,
    titles,
  };
}

function monthsLayout(width: number, start: string, end: string): Layout {
  const cols = width >= 480 ? 4 : 3;
  const cell = Math.max(8, Math.min(18, Math.floor((width - (cols - 1) * MONTH_GAP) / (cols * 7))));
  const blockW = cell * 7;
  const blockH = MONTH_TITLE + cell * 6 + MONTH_GAP;
  const blocks: Block[] = [];
  const titles: Layout["titles"] = [];
  let i = 0;
  for (let m = `${start.slice(0, 7)}-01`; m <= end; m = addMonth(m), i++) {
    const last = addDays(addMonth(m), -1);
    const col = i % cols;
    const row = Math.floor(i / cols);
    const left = col * (blockW + MONTH_GAP);
    const top = row * blockH;
    blocks.push({
      from: m,
      to: last,
      dataFrom: m < start ? start : m,
      dataTo: last > end ? end : last,
      left,
      top: top + MONTH_TITLE,
      orient: "vertical",
    });
    titles.push({ text: fmtMonth(m), left, top, size: 11, strong: true });
  }
  return {
    kind: "months",
    cell,
    height: Math.ceil(i / cols) * blockH - MONTH_GAP + 2,
    blocks,
    titles,
  };
}

function addMonth(firstOfMonth: string): string {
  const y = Number(firstOfMonth.slice(0, 4));
  const m = Number(firstOfMonth.slice(5, 7));
  return m === 12 ? `${y + 1}-01-01` : `${y}-${String(m + 1).padStart(2, "0")}-01`;
}

/** Strip when a full row of weeks fits at ≥ 11 px cells, else month grids. */
export function heatmapLayout(width: number, start: string, end: string): Layout {
  return stripLayout(width, start, end) ?? monthsLayout(width, start, end);
}

export function calendarHeatmapOption({
  layout,
  values,
  bins,
  mode,
  tooltip,
  label,
}: {
  layout: Layout;
  /** Metric per active day (ISO day → value). */
  values: Map<string, number>;
  bins: HeatBin[];
  mode: Mode;
  tooltip: (day: string) => string;
  label: string;
}): ChartOption {
  const c = CHROME[mode];
  const { cell } = layout;
  const item = {
    borderColor: c.surface,
    borderWidth: cell >= 14 ? 2 : 1.5,
    borderRadius: Math.max(2, Math.round(cell / 5)),
  };
  // One heatmap series per block; every in-range day is a cell (rest days carry 0).
  const series = layout.blocks.map((b, i) => {
    const data: [string, number][] = [];
    for (let d = b.dataFrom; d <= b.dataTo; d = addDays(d, 1)) data.push([d, values.get(d) ?? 0]);
    return {
      type: "heatmap",
      name: `${label} ${b.from}`,
      coordinateSystem: "calendar",
      calendarIndex: i,
      data,
      itemStyle: item,
      emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1.5 } },
    };
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
    // Weekday labels (strip) and month titles (month grids) as positioned titles.
    title: layout.titles.map((t) => ({
      text: t.text,
      left: t.left,
      top: t.top,
      padding: 0,
      textStyle: {
        fontSize: t.size,
        fontWeight: t.strong ? 600 : 400,
        color: t.strong ? c.text2 : c.muted,
        lineHeight: t.size + 2,
      },
    })),
    calendar: layout.blocks.map((b, i) => ({
      orient: b.orient,
      range: [b.from, b.to],
      left: b.left,
      top: b.top,
      cellSize: [cell, cell],
      splitLine: { show: false },
      itemStyle: { color: "transparent", borderWidth: 0 },
      yearLabel: { show: false },
      dayLabel: { show: false, firstDay: 1 },
      monthLabel:
        layout.kind === "strip"
          ? {
              color: c.muted,
              fontSize: 11,
              margin: 6,
              align: "left",
              // Month names; the year joins January and the first month of the strip.
              formatter: (p: { yyyy: string; MM: string; nameMap: string }) =>
                i === 0 && `${p.yyyy}-${p.MM}` === b.from.slice(0, 7)
                  ? `${p.nameMap} ${p.yyyy}`
                  : p.MM === "01"
                    ? `${p.nameMap} ${p.yyyy}`
                    : p.nameMap,
            }
          : { show: false },
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
