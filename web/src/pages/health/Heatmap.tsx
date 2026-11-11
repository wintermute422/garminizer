/** Hour-of-day × day heatmap (sequential ramp); clicking a day opens its intraday timeline. */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import { Chart, type ChartInstance, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, ErrorState, Segmented, Skeleton } from "@/components/ui";
import { tooltipRow, tooltipTitle } from "@/lib/charts";
import { fmtCompact, fmtDate, fmtNumber, fmtShortDate } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CHROME, SEQUENTIAL, type Mode } from "@/lib/tokens";
import { quantile } from "@/lib/stats";
import { NARROW, useMediaQuery } from "@/lib/useMediaQuery";

export type HeatMetric = "hr" | "stress" | "body_battery" | "steps";

const METRICS: {
  value: HeatMetric;
  label: string;
  unit: string;
  scale: string;
  fmt: (v: number) => string;
}[] = [
  { value: "hr", label: "Heart rate", unit: "bpm", scale: "bpm", fmt: (v) => fmtNumber(v) },
  { value: "stress", label: "Stress", unit: "", scale: "stress", fmt: (v) => fmtNumber(v) },
  {
    value: "body_battery",
    label: "Body battery",
    unit: "",
    scale: "body battery",
    fmt: (v) => fmtNumber(v),
  },
  { value: "steps", label: "Steps", unit: "steps", scale: "steps / h", fmt: (v) => fmtNumber(v) },
];

const pad = (h: number) => String(h).padStart(2, "0");

interface RenderApi {
  value: (dim: number) => number;
  coord: (v: number[]) => number[];
  size: (v: number[]) => number[];
}

function heatOption(
  data: { days: string[]; values: (number | null)[][] },
  metric: (typeof METRICS)[number],
  selected: string | null,
  mode: Mode,
  narrow: boolean,
): ChartOption {
  const c = CHROME[mode];
  const cells: { value: [number, number, number]; day: string }[] = [];
  const gaps: { value: [number, number, number]; day: string }[] = [];
  data.values.forEach((row, i) =>
    row.forEach((v, h) => {
      if (v !== null) cells.push({ value: [i, h, v], day: data.days[i]! });
      else gaps.push({ value: [i, h, 0], day: data.days[i]! });
    }),
  );
  const all = cells.map((x) => x.value[2]);
  const lo = metric.value === "steps" ? 0 : (quantile(all, 0.02) ?? 0);
  const hi = Math.max(quantile(all, metric.value === "steps" ? 0.97 : 0.98) ?? 1, lo + 1);
  const sel = selected ? data.days.indexOf(selected) : -1;
  const gapFill = CHROME[mode].wash;
  const dense = data.days.length > (narrow ? 40 : 120);
  const short = (v: number) => (metric.value === "steps" ? fmtCompact(v) : fmtNumber(v));
  return {
    grid: { left: 4, right: 8, top: 34, bottom: 4 },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (p: unknown) => {
        const it = p as {
          seriesIndex?: number;
          data?: { value: [number, number, number]; day: string };
        };
        if (!it.data) return "";
        const [, h, v] = it.data.value;
        const head =
          tooltipTitle(fmtDate(it.data.day, { weekday: "short", day: "numeric", month: "short" })) +
          `<div style="color:${c.muted};margin:-2px 0 6px">${pad(h)}:00–${pad((h + 1) % 24)}:00 local time</div>`;
        if (it.seriesIndex === 0)
          return `${head}<div style="color:${c.muted}">No measurement</div>`;
        return (
          head +
          tooltipRow(
            SEQUENTIAL[mode][3]!,
            metric.value === "steps" ? "Steps" : `Average ${metric.label.toLowerCase()}`,
            `${metric.fmt(v)}${metric.unit && metric.value !== "steps" ? ` ${metric.unit}` : ""}`,
          )
        );
      },
    },
    xAxis: {
      type: "category",
      data: data.days,
      axisLine: { show: false },
      axisLabel: { formatter: (d: string) => fmtShortDate(d), hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: "category",
      data: Array.from({ length: 24 }, (_, h) => `${pad(h)}:00`),
      inverse: true,
      axisLine: { show: false },
      axisLabel: { interval: 5 },
      splitLine: { show: false },
    },
    visualMap: [
      {
        type: "continuous",
        dimension: 2,
        min: lo,
        max: hi,
        calculable: false,
        orient: "horizontal",
        right: 0,
        top: 0,
        itemWidth: 10,
        itemHeight: 120,
        text: [`${short(hi)} ${metric.scale}`, short(lo)],
        seriesIndex: 1,
        textGap: 6,
        textStyle: { color: c.muted, fontSize: 11 },
        inRange: { color: [...SEQUENTIAL[mode]] },
      },
      {
        // Heatmap series need a visualMap; the no-measurement cells get one flat fill.
        type: "continuous",
        show: false,
        seriesIndex: 0,
        dimension: 2,
        min: 0,
        max: 1,
        inRange: { color: [gapFill, gapFill] },
      },
    ],
    series: [
      {
        // Hours without any sample: outlined so they never read as the lowest bin.
        type: "heatmap",
        name: "No measurement",
        data: gaps,
        progressive: 0,
        itemStyle: {
          color: gapFill,
          borderColor: mode === "dark" ? c.muted : c.axis,
          borderWidth: 1,
        },
        emphasis: { disabled: true },
      },
      {
        type: "heatmap",
        name: metric.label,
        data: cells,
        progressive: 0,
        itemStyle: { borderColor: c.surface, borderWidth: dense ? 0 : 1 },
        emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1 } },
      },
      // Outline of the selected day's column (a category markArea collapses to zero width).
      ...(sel >= 0
        ? [
            {
              type: "custom",
              name: "Selected day",
              silent: true,
              z: 10,
              data: [[sel, 0]],
              encode: { x: 0, y: 1 },
              renderItem: (_p: unknown, api: RenderApi) => {
                const top = api.coord([api.value(0), 0]);
                const bottom = api.coord([api.value(0), 23]);
                const w = Math.abs(api.size([1, 0])[0] ?? 0);
                const rh = Math.abs(api.size([0, 1])[1] ?? 0);
                const y0 = Math.min(top[1]!, bottom[1]!) - rh / 2;
                return {
                  type: "rect",
                  shape: {
                    x: top[0]! - w / 2,
                    y: y0,
                    width: Math.max(w, 2),
                    height: Math.abs(bottom[1]! - top[1]!) + rh,
                    r: 2,
                  },
                  style: { fill: "transparent", stroke: c.text, lineWidth: 1.5 },
                };
              },
            },
          ]
        : []),
    ],
  };
}

export function HourHeatmap({
  query,
  enabled,
  selected,
  onSelect,
  timeZone,
}: {
  query: { start: string; end: string };
  enabled: boolean;
  selected: string | null;
  onSelect: (day: string) => void;
  timeZone: string;
}) {
  const mode = useMode();
  const narrow = useMediaQuery(NARROW);
  const [metric, setMetric] = useState<HeatMetric>("hr");
  const spec = METRICS.find((m) => m.value === metric)!;
  const q = api.useQuery(
    "get",
    "/api/wellness/heatmap",
    { params: { query: { ...query, metric } } },
    { enabled, placeholderData: (prev) => prev },
  );
  const option = useMemo(
    () => (q.data ? heatOption(q.data, spec, selected, mode, narrow) : null),
    [q.data, spec, selected, mode, narrow],
  );
  // Click anywhere in a day's column (empty hours too) selects that day.
  const days = useRef<string[]>([]);
  const select = useRef(onSelect);
  useEffect(() => {
    days.current = q.data?.days ?? [];
    select.current = onSelect;
  });
  const onReady = (chart: ChartInstance) => {
    chart.getZr().on("click", (e: { offsetX: number; offsetY: number }) => {
      if (!chart.containPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])) return;
      const idx = chart.convertFromPixel({ xAxisIndex: 0 }, e.offsetX) as unknown as number;
      const day = days.current[Math.round(idx)];
      if (day) select.current(day);
    });
  };
  const hasData = q.data && q.data.values.some((row) => row.some((v) => v !== null));
  return (
    <Card
      title="Daily rhythm"
      subtitle={`Hour of day (${timeZone} time) · click a day to open its timeline`}
      actions={
        <Segmented
          size="sm"
          label="Heatmap metric"
          value={metric}
          onChange={setMetric}
          options={METRICS.map((m) => ({ value: m.value, label: m.label }))}
        />
      }
      className="lg:col-span-2"
    >
      {q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data ? (
        <Skeleton height={330} />
      ) : !hasData || !option ? (
        <EmptyState title={`No all-day ${spec.label.toLowerCase()} data in this period`} />
      ) : (
        <div style={{ opacity: q.isPlaceholderData ? 0.6 : 1 }}>
          <Chart
            option={option}
            height={330}
            ariaLabel={`${spec.label} by hour of day for each day in the period`}
            onReady={onReady}
          />
          <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-3">
            <span
              className="inline-block size-2.5 rounded-swatch border"
              style={{ borderColor: mode === "dark" ? CHROME.dark.muted : CHROME.light.axis }}
              aria-hidden
            />
            Outlined hours: no measurement
          </p>
        </div>
      )}
    </Card>
  );
}
