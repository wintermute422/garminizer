/**
 * Calendar: consistency over time — streak tiles, a multi-year calendar heatmap (training load,
 * duration or distance per day), a weekday × hour punchcard and monthly totals. Honours the
 * global range and sport filter.
 */
import { useQuery } from "@tanstack/react-query";
import { useSearch } from "@tanstack/react-router";
import { CalendarCheck2, CalendarDays, Flame, Trophy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import {
  Card,
  EmptyState,
  ErrorState,
  LegendItem,
  PageHeader,
  ScrollArea,
  Segmented,
  Skeleton,
  StatTile,
} from "@/components/ui";
import {
  axisTooltip,
  bars,
  categoryXAxis,
  GRID,
  itemTooltip,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import {
  distanceUnit,
  distanceValue,
  fmtDate,
  fmtDistance,
  fmtHours,
  fmtNumber,
  fmtPercent,
  type UnitSystem,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { addDays, type GlobalSearch, useRange } from "@/lib/range";
import { sportColor, sportLabel } from "@/lib/sports";
import { CATEGORICAL, CHROME, type Mode } from "@/lib/tokens";
import {
  type DayTotals,
  daysBetween,
  dayStreaks,
  fetchSportDays,
  monthTotals,
  weeksInRow,
} from "./data";
import {
  calendarHeatmapOption,
  cellSize,
  heatmapHeight,
  heatmapWidth,
  type HeatBin,
  quantileBins,
  restColor,
  useElementWidth,
  yearsBetween,
} from "./heatmap";

type Metric = "load" | "duration" | "distance";
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function metricValue(d: DayTotals, metric: Metric, units: UnitSystem): number {
  if (metric === "load") return d.training_load;
  if (metric === "duration") return d.duration_s;
  return distanceValue(d.distance_m, units);
}

function roundTo(v: number, step: number): number {
  return Math.max(step, Math.round(v / step) * step);
}

const METRICS: Record<
  Metric,
  { label: string; nice: (v: number) => number; fmt: (v: number, units: UnitSystem) => string }
> = {
  load: {
    label: "Training load",
    nice: (v) => roundTo(v, v < 50 ? 5 : v < 200 ? 10 : 25),
    fmt: (v) => fmtNumber(v),
  },
  duration: {
    label: "Duration",
    nice: (v) => roundTo(v, v < 3600 ? 300 : 900),
    fmt: (v) => fmtHours(v),
  },
  distance: {
    label: "Distance",
    nice: (v) => roundTo(v, v < 10 ? 1 : 5),
    fmt: (v, units) => `${fmtNumber(v)} ${distanceUnit(units)}`,
  },
};

function tipLine(label: string, value: string): string {
  return `<div style="display:flex;justify-content:space-between;gap:16px;min-width:180px"><span>${label}</span><b style="font-variant-numeric:tabular-nums">${value}</b></div>`;
}

function dayTooltip(
  day: string,
  d: DayTotals | undefined,
  inRange: boolean,
  units: UnitSystem,
  mode: Mode,
): string {
  const title = tooltipTitle(
    fmtDate(day, { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
  );
  if (!d) return title + (inRange ? `<div style="color:${CHROME[mode].muted}">Rest day</div>` : "");
  const sports = d.sport_groups
    .map(
      (g) =>
        `<span style="display:inline-flex;align-items:center;gap:5px;margin-right:10px"><span style="width:8px;height:8px;border-radius:2px;background:${sportColor(g, mode)};display:inline-block"></span>${sportLabel(g)}</span>`,
    )
    .join("");
  return (
    title +
    `<div style="margin-bottom:6px">${sports}</div>` +
    tipLine("Activities", fmtNumber(d.activities)) +
    tipLine("Duration", fmtHours(d.duration_s)) +
    (d.distance_m > 0 ? tipLine("Distance", fmtDistance(d.distance_m, units)) : "") +
    tipLine("Training load", fmtNumber(d.training_load))
  );
}

function HeatLegend({ bins, mode }: { bins: HeatBin[]; mode: Mode }) {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      <LegendItem color={restColor(mode)} label="Rest day" />
      {bins.map((b) => (
        <LegendItem key={b.label} color={b.color} label={b.label} />
      ))}
    </div>
  );
}

function HeatmapCard({
  days,
  start,
  end,
  sport,
}: {
  days: DayTotals[];
  start: string;
  end: string;
  sport: string | null;
}) {
  const mode = useMode();
  const units = useUnits();
  const [metric, setMetric] = useState<Metric>("load");
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const m = METRICS[metric];
  const byDay = useMemo(() => new Map(days.map((d) => [d.day, d])), [days]);
  const values = useMemo(
    () => new Map(days.map((d) => [d.day, metricValue(d, metric, units)])),
    [days, metric, units],
  );
  const bins = useMemo(
    () => quantileBins([...values.values()], mode, m.nice, (v) => m.fmt(v, units)),
    [values, mode, m, units],
  );
  const cell = cellSize(width);
  const years = yearsBetween(start, end).length;
  const option = useMemo(
    () =>
      width > 0
        ? calendarHeatmapOption({
            start,
            end,
            values,
            bins,
            cell,
            mode,
            label: m.label,
            tooltip: (day) =>
              dayTooltip(day, byDay.get(day), day >= start && day <= end, units, mode),
          })
        : null,
    [width, start, end, values, bins, cell, mode, m.label, byDay, units],
  );
  const inner = heatmapWidth(cell, start, end);
  const scrolls = width > 0 && inner > width;
  const chart = option ? (
    <Chart
      option={option}
      height={heatmapHeight(years, cell)}
      ariaLabel={`Calendar heatmap of daily ${m.label.toLowerCase()}${sport ? ` (${sportLabel(sport)})` : ""}, ${fmtDate(start)} to ${fmtDate(end)}`}
    />
  ) : null;
  const hasMetric = bins.length > 0;
  return (
    <Card
      title="Activity calendar"
      subtitle={`Daily ${m.label.toLowerCase()}${sport ? ` · ${sportLabel(sport)} only` : ""} · ${mode === "dark" ? "brighter" : "darker"} = more`}
      actions={
        <Segmented
          size="sm"
          label="Calendar metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "load", label: "Load" },
            { value: "duration", label: "Duration" },
            { value: "distance", label: "Distance" },
          ]}
        />
      }
    >
      <div ref={measure} className="w-full">
        {!hasMetric ? (
          <EmptyState title={`No ${m.label.toLowerCase()} recorded in this period`} />
        ) : scrolls ? (
          <ScrollArea label="Activity calendar, scroll sideways" className="overflow-x-auto pb-1">
            <div
              style={{ width: inner }}
              ref={(node) => {
                // Start at the most recent weeks.
                if (node?.parentElement) node.parentElement.scrollLeft = node.scrollWidth;
              }}
            >
              {chart}
            </div>
          </ScrollArea>
        ) : (
          chart
        )}
      </div>
      {hasMetric && <HeatLegend bins={bins} mode={mode} />}
    </Card>
  );
}

function StreakTiles({
  days,
  start,
  end,
  api: fromApi,
}: {
  days: DayTotals[];
  start: string;
  end: string;
  api: { current: number; longest: number; longestStart: string | null; weeks: number } | null;
}) {
  const list = days.map((d) => d.day);
  const local = dayStreaks(list, end);
  const s = fromApi ?? { ...local, weeks: weeksInRow(list, end) };
  const total = daysBetween(start, end);
  const activities = days.reduce((n, d) => n + d.activities, 0);
  const icon = (I: typeof Flame) => <I size={15} className="text-ink-3" aria-hidden />;
  const plural = (n: number, w: string) => (n === 1 ? w : `${w}s`);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        icon={icon(Flame)}
        label="Current streak"
        value={fmtNumber(s.current)}
        unit={plural(s.current, "day")}
        sub={
          s.current > 0
            ? `active through ${fmtDate(list.includes(end) ? end : addDays(end, -1), { day: "numeric", month: "short" })}`
            : "no activity on the last two days"
        }
      />
      <StatTile
        icon={icon(Trophy)}
        label="Longest streak"
        value={fmtNumber(s.longest)}
        unit={plural(s.longest, "day")}
        sub={s.longestStart ? `from ${fmtDate(s.longestStart)}` : undefined}
      />
      <StatTile
        icon={icon(CalendarCheck2)}
        label="Weeks in a row"
        value={fmtNumber(s.weeks)}
        unit={plural(s.weeks, "week")}
        sub="with at least one activity"
      />
      <StatTile
        icon={icon(CalendarDays)}
        label="Active days"
        value={fmtNumber(days.length)}
        unit={`/ ${fmtNumber(total)}`}
        sub={`${fmtPercent((days.length / Math.max(total, 1)) * 100)} · ${fmtNumber(activities)} activities`}
      />
    </div>
  );
}

function punchcardOption(
  cells: { weekday: number; hour: number; activities: number; duration_s: number }[],
  maxSize: number,
  color: string,
  mode: Mode,
): ChartOption {
  const c = CHROME[mode];
  const max = Math.max(1, ...cells.map((x) => x.activities));
  return {
    grid: { left: 4, right: 8, top: 8, bottom: 4 },
    tooltip: itemTooltip((p) => {
      const v = (p as { value: [number, number, number, number] }).value;
      return (
        tooltipTitle(
          `${WEEKDAYS[v[1]]} · ${String(v[0]).padStart(2, "0")}:00–${String((v[0] + 1) % 24).padStart(2, "0")}:00`,
        ) +
        tooltipRow(color, "Activities", fmtNumber(v[2])) +
        tooltipRow(color, "Total time", fmtHours(v[3]))
      );
    }),
    xAxis: {
      type: "category",
      data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0")),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { interval: 2, color: c.muted },
      splitLine: { show: false },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: WEEKDAYS.map((d) => d.slice(0, 3)),
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { show: true, lineStyle: { color: c.grid } },
    },
    series: [
      {
        type: "scatter",
        name: "Activities",
        data: cells.map((x) => [x.hour, x.weekday, x.activities, x.duration_s]),
        symbolSize: (v: number[]) => 4 + Math.sqrt((v[2] ?? 0) / max) * (maxSize - 4),
        itemStyle: { color, opacity: 0.9, borderColor: c.surface, borderWidth: 1.5 },
        emphasis: { scale: 1.15, itemStyle: { opacity: 1 } },
      },
    ],
  };
}

function PunchcardCard({
  start,
  end,
  sport,
}: {
  start: string;
  end: string;
  sport: string | null;
}) {
  const mode = useMode();
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const q = api.useQuery("get", "/api/calendar/punchcard", {
    params: { query: { start, end, ...(sport ? { sport } : {}) } },
  });
  const cells = useMemo(() => q.data ?? [], [q.data]);
  const color = sport ? sportColor(sport, mode) : CATEGORICAL[mode][0]!;
  const maxSize = Math.max(8, Math.min(22, ((width || 500) - 40) / 24 - 2));
  const option = useMemo(
    () => punchcardOption(cells, maxSize, color, mode),
    [cells, maxSize, color, mode],
  );
  const peak = cells.reduce<(typeof cells)[number] | null>(
    (best, x) => (!best || x.activities > best.activities ? x : best),
    null,
  );
  const total = cells.reduce((n, x) => n + x.activities, 0);
  const byDay = WEEKDAYS.map((_, i) =>
    cells.filter((x) => x.weekday === i).reduce((n, x) => n + x.activities, 0),
  );
  const busiest = byDay.indexOf(Math.max(...byDay));
  const evening = cells.filter((x) => x.hour >= 17).reduce((n, x) => n + x.activities, 0);
  return (
    <Card
      title="When you train"
      subtitle="Start times by weekday and hour · bubble size = activities"
    >
      <div ref={measure}>
        {q.isPending ? (
          <Skeleton height={250} />
        ) : q.error ? (
          <ErrorState error={q.error} />
        ) : !cells.length ? (
          <EmptyState title="No activities in this period" />
        ) : (
          <>
            <Chart
              option={option}
              height={250}
              ariaLabel="Punchcard of activity start times by weekday and hour"
            />
            {peak && (
              <p className="mt-3 text-xs text-ink-3">
                Most common slot{" "}
                <span className="font-medium text-ink-2">
                  {WEEKDAYS[peak.weekday]}s at {String(peak.hour).padStart(2, "0")}:00
                </span>{" "}
                · busiest day <span className="font-medium text-ink-2">{WEEKDAYS[busiest]}</span> ·{" "}
                <span className="font-medium text-ink-2">
                  {fmtPercent((evening / total) * 100)}
                </span>{" "}
                start after 17:00
              </p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

type MonthMetric = "days" | "duration";

function monthlyOption(
  months: ReturnType<typeof monthTotals>,
  metric: MonthMetric,
  color: string,
  mode: Mode,
): ChartOption {
  const label = (key: string, i: number) => {
    const d = new Date(`${key}-15T12:00:00`);
    const mon = d.toLocaleDateString(undefined, { month: "short" });
    return i === 0 || d.getMonth() === 0 ? `${mon}\n${d.getFullYear()}` : mon;
  };
  const values = months.map((m) => (metric === "days" ? m.activeDays : m.duration_s / 3600));
  return {
    grid: { ...GRID, top: 28 },
    tooltip: axisTooltip(
      (p) => {
        const i = (p as { dataIndex: number }[])[0]?.dataIndex ?? 0;
        const m = months[i]!;
        const d = new Date(`${m.key}-15T12:00:00`);
        return (
          tooltipTitle(d.toLocaleDateString(undefined, { month: "long", year: "numeric" })) +
          tooltipRow(color, "Active days", `${m.activeDays} / ${m.daysInRange}`) +
          tooltipRow(color, "Activities", fmtNumber(m.activities)) +
          tooltipRow(color, "Moving time", fmtHours(m.duration_s))
        );
      },
      { axisPointer: { type: "shadow" } },
    ),
    xAxis: categoryXAxis(
      months.map((m, i) => label(m.key, i)),
      { axisLabel: { interval: months.length > 15 ? 1 : 0, lineHeight: 14 } },
    ),
    yAxis: valueYAxis(metric === "days" ? "days" : "hours", (v) => fmtNumber(v), {
      minInterval: 1,
    }),
    series: [bars(metric === "days" ? "Active days" : "Moving time", values, color, mode)],
  };
}

function MonthlyCard({
  days,
  start,
  end,
  sport,
}: {
  days: DayTotals[];
  start: string;
  end: string;
  sport: string | null;
}) {
  const mode = useMode();
  const [metric, setMetric] = useState<MonthMetric>("days");
  const months = useMemo(() => monthTotals(days, start, end), [days, start, end]);
  const color = sport ? sportColor(sport, mode) : CATEGORICAL[mode][0]!;
  const option = useMemo(
    () => monthlyOption(months, metric, color, mode),
    [months, metric, color, mode],
  );
  const best = months.reduce<(typeof months)[number] | null>(
    (b, m) =>
      !b || (metric === "days" ? m.activeDays > b.activeDays : m.duration_s > b.duration_s) ? m : b,
    null,
  );
  return (
    <Card
      title="Monthly totals"
      subtitle={
        best && (best.activeDays > 0 || best.duration_s > 0)
          ? `Best month ${new Date(`${best.key}-15T12:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" })} · ${metric === "days" ? `${best.activeDays} active days` : fmtHours(best.duration_s)}`
          : "Per calendar month"
      }
      actions={
        <Segmented
          size="sm"
          label="Monthly metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "days", label: "Active days" },
            { value: "duration", label: "Time" },
          ]}
        />
      }
    >
      {days.length === 0 ? (
        <EmptyState title="No activities in this period" />
      ) : (
        <Chart
          option={option}
          height={274}
          ariaLabel={`${metric === "days" ? "Active days" : "Moving time"} per month`}
        />
      )}
    </Card>
  );
}

export default function CalendarPage() {
  const range = useRange("365d");
  const search = useSearch({ strict: false }) as GlobalSearch;
  // Without an explicit range the calendar opens on a full year (and the filter bar shows it).
  useEffect(() => {
    if (range.ready && !search.preset && !search.start) range.setPreset("365d");
  }, [range.ready, search.preset, search.start]); // eslint-disable-line react-hooks/exhaustive-deps

  const { start, end } = range.query;
  const sport = range.sport;
  const cal = api.useQuery(
    "get",
    "/api/calendar",
    { params: { query: { start, end } } },
    { enabled: range.ready && !sport },
  );
  const sportDays = useQuery({
    queryKey: ["calendar-sport-days", start, end, sport],
    queryFn: () => fetchSportDays(start, end, sport!),
    enabled: range.ready && !!sport,
  });
  const days = sport ? sportDays.data : cal.data?.days;
  const error = sport ? sportDays.error : cal.error;
  const streaks =
    !sport && cal.data
      ? {
          current: cal.data.streak.current,
          longest: cal.data.streak.longest,
          longestStart: cal.data.streak.longest_start,
          weeks: cal.data.active_weeks_in_row,
        }
      : null;

  return (
    <>
      <PageHeader
        title="Calendar"
        description={`Consistency over time · ${fmtDate(start)} – ${fmtDate(end)}${sport ? ` · ${sportLabel(sport)}` : ""}`}
      />
      {error ? (
        <ErrorState error={error} />
      ) : !days ? (
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} height={104} />
            ))}
          </div>
          <Skeleton height={380} />
          <div className="grid gap-5 lg:grid-cols-2">
            <Skeleton height={340} />
            <Skeleton height={340} />
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <StreakTiles days={days} start={start} end={end} api={streaks} />
          <HeatmapCard days={days} start={start} end={end} sport={sport} />
          <div className="grid gap-5 lg:grid-cols-2">
            <PunchcardCard start={start} end={end} sport={sport} />
            <MonthlyCard days={days} start={start} end={end} sport={sport} />
          </div>
        </div>
      )}
    </>
  );
}
