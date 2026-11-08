/** Hour-of-day × day heatmap (sequential ramp); clicking a day opens its intraday timeline. */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/api/client";
import { Chart, type ChartInstance, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, ErrorState, Segmented, Skeleton } from "@/components/ui";
import { tooltipRow, tooltipTitle } from "@/lib/charts";
import { fmtCompact, fmtDate, fmtNumber, fmtShortDate } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CHROME, SEQUENTIAL, type Mode } from "@/lib/tokens";
import { quantile, useNarrow } from "./util";

export type HeatMetric = "hr" | "stress" | "body_battery" | "steps";

const METRICS: { value: HeatMetric; label: string; unit: string; fmt: (v: number) => string }[] = [
  { value: "hr", label: "Heart rate", unit: "bpm", fmt: (v) => fmtNumber(v) },
  { value: "stress", label: "Stress", unit: "", fmt: (v) => fmtNumber(v) },
  { value: "body_battery", label: "Body battery", unit: "", fmt: (v) => fmtNumber(v) },
  { value: "steps", label: "Steps", unit: "steps", fmt: (v) => fmtNumber(v) },
];

const pad = (h: number) => String(h).padStart(2, "0");

function heatOption(
  data: { days: string[]; values: (number | null)[][] },
  metric: (typeof METRICS)[number],
  selected: string | null,
  mode: Mode,
  narrow: boolean,
): ChartOption {
  const c = CHROME[mode];
  const cells: { value: [number, number, number]; day: string }[] = [];
  data.values.forEach((row, i) =>
    row.forEach((v, h) => {
      if (v !== null) cells.push({ value: [i, h, v], day: data.days[i]! });
    }),
  );
  const all = cells.map((x) => x.value[2]);
  const lo = metric.value === "steps" ? 0 : (quantile(all, 0.02) ?? 0);
  const hi = Math.max(quantile(all, metric.value === "steps" ? 0.97 : 0.98) ?? 1, lo + 1);
  const sel = selected ? data.days.indexOf(selected) : -1;
  const dense = data.days.length > (narrow ? 40 : 120);
  const short = (v: number) => (metric.value === "steps" ? fmtCompact(v) : fmtNumber(v));
  return {
    grid: { left: 4, right: 8, top: 34, bottom: 4 },
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (p: unknown) => {
        const it = p as { data?: { value: [number, number, number]; day: string } };
        if (!it.data) return "";
        const [, h, v] = it.data.value;
        return (
          tooltipTitle(fmtDate(it.data.day, { weekday: "short", day: "numeric", month: "short" })) +
          `<div style="color:${c.muted};margin:-2px 0 6px">${pad(h)}:00–${pad((h + 1) % 24)}:00 local time</div>` +
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
    visualMap: {
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
      text: [short(hi), short(lo)],
      textGap: 6,
      textStyle: { color: c.muted, fontSize: 11 },
      inRange: { color: [...SEQUENTIAL[mode]] },
    },
    series: [
      {
        type: "heatmap",
        name: metric.label,
        data: cells,
        progressive: 0,
        itemStyle: { borderColor: c.surface, borderWidth: dense ? 0 : 1 },
        emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1 } },
        markArea:
          sel >= 0
            ? {
                silent: true,
                itemStyle: { color: "transparent", borderColor: c.text, borderWidth: 1.5 },
                data: [[{ xAxis: sel }, { xAxis: sel }]],
              }
            : undefined,
      },
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
  const narrow = useNarrow();
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
        </div>
      )}
    </Card>
  );
}
