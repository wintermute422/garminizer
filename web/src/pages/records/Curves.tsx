/** Records charts: mean-maximal curves and year-over-year cumulative totals. */
import { useMemo, useState } from "react";
import { api } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, LegendItem, QueryState, Segmented } from "@/components/ui";
import { axisTooltip, GRID, line, tooltipRow, tooltipTitle, valueYAxis } from "@/lib/charts";
import {
  distanceUnit,
  distanceValue,
  fmtDate,
  fmtHours,
  fmtNumber,
  fmtPercent,
  signed,
  type UnitSystem,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { sportLabel, usesPace } from "@/lib/sports";
import { CATEGORICAL, CHROME, type Mode } from "@/lib/tokens";
import {
  CURVE_TICKS,
  curveDisplay,
  doyDate,
  doyLabel,
  durText,
  durTick,
  MONTH_STARTS,
  monthOfDoy,
  type CurveMetric,
} from "./util";

const WINDOW_STYLE: Record<string, { slot: number | null; dashed: boolean }> = {
  all: { slot: null, dashed: true },
  "365d": { slot: 0, dashed: false },
  "90d": { slot: 1, dashed: false },
};

function windowColor(key: string, mode: Mode): string {
  const slot = WINDOW_STYLE[key]?.slot;
  return slot === null || slot === undefined ? CHROME[mode].muted : CATEGORICAL[mode][slot]!;
}

/** Best average pace/speed, power or heart rate held for each duration (log time axis). */
export function CurveCard({ sport }: { sport: string }) {
  const mode = useMode();
  const units = useUnits();
  const [metric, setMetric] = useState<CurveMetric>("speed");
  const q = api.useQuery(
    "get",
    "/api/records/curves",
    { params: { query: { sport, metric } } },
    { placeholderData: (prev) => prev },
  );
  const disp = useMemo(() => curveDisplay(metric, sport, units), [metric, sport, units]);
  const windows = useMemo(
    () =>
      (q.data?.windows ?? [])
        .map((w) => ({
          ...w,
          values: w.points.map((p) => ({ ...p, shown: disp.value(p.value) })),
        }))
        .filter((w) => w.values.some((p) => p.shown !== null)),
    [q.data, disp],
  );
  const durations = useMemo(
    () =>
      [...new Set(windows.flatMap((w) => w.points.map((p) => p.duration_s)))].sort((a, b) => a - b),
    [windows],
  );

  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const maxDur = durations[durations.length - 1] ?? 3600;
    const ticks = CURVE_TICKS.filter((t) => t <= maxDur).map((t) => Math.log10(t));
    return {
      grid: { ...GRID, right: 16 },
      tooltip: axisTooltip((p) => {
        const arr = p as { seriesIndex: number; dataIndex: number; color: string }[];
        const first = arr[0];
        if (!first) return "";
        const w0 = windows[first.seriesIndex];
        const pt0 = w0?.values[first.dataIndex];
        if (!pt0) return "";
        return (
          tooltipTitle(`Best ${durText(pt0.duration_s)}`) +
          arr
            .map((a) => {
              const w = windows[a.seriesIndex];
              const pt = w?.values[a.dataIndex];
              if (!w || !pt || pt.shown === null) return "";
              return (
                tooltipRow(
                  windowColor(w.key, mode),
                  w.label,
                  `${disp.format(pt.shown)} ${disp.unit}`,
                ) +
                `<div style="color:${c.muted};font-size:11px;margin:-2px 0 4px 14px">${fmtDate(pt.day)}</div>`
              );
            })
            .join("")
        );
      }),
      xAxis: {
        type: "value",
        min: 0,
        max: Math.log10(maxDur),
        splitLine: { show: true },
        axisTick: { show: false, customValues: ticks },
        axisLabel: { customValues: ticks, formatter: (v: number) => durTick(10 ** v) },
      },
      yAxis: valueYAxis(disp.unit, disp.format, {
        scale: true,
        inverse: disp.inverse,
        nameLocation: disp.inverse ? "start" : "end",
      }),
      series: windows.map((w) => {
        const style = WINDOW_STYLE[w.key] ?? { slot: null, dashed: false };
        return {
          ...line(
            w.label,
            w.values.map((p) => [Math.log10(p.duration_s), p.shown]),
            windowColor(w.key, mode),
            { dashed: style.dashed, z: style.dashed ? 1 : 3 },
          ),
          smooth: 0.2,
        };
      }),
    };
  }, [windows, durations, disp, mode]);

  const allTime = windows.find((w) => w.key === "all");
  const recent = windows.find((w) => w.key === "90d");
  const keyPoints = CURVE_TICKS.map((t) => {
    const best = allTime?.values.find((p) => p.duration_s === t);
    const now = recent?.values.find((p) => p.duration_s === t);
    return best && best.shown !== null
      ? { t, best: best.shown, now: now?.shown ?? null, day: best.day }
      : null;
  }).filter((k) => k !== null);

  const metricName =
    metric === "speed"
      ? usesPace(sport)
        ? "pace"
        : "speed"
      : metric === "power"
        ? "power"
        : "heart rate";
  return (
    <Card
      className="lg:col-span-2"
      title={`Best ${metricName} by duration · ${sportLabel(sport)}`}
      subtitle="Your best average held for every duration, all-time against the last 365 and 90 days"
      actions={
        <Segmented
          size="sm"
          label="Curve metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "speed", label: usesPace(sport) ? "Pace" : "Speed" },
            { value: "power", label: "Power" },
            { value: "hr", label: "Heart rate" },
          ]}
        />
      }
    >
      <QueryState
        query={q}
        height={300}
        isEmpty={() => windows.length === 0}
        empty={
          <EmptyState title={`No ${metricName} data for ${sportLabel(sport).toLowerCase()}`}>
            Best efforts are computed from activities with per-second data.
          </EmptyState>
        }
      >
        {() => (
          <>
            <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
              {windows.map((w) => (
                <LegendItem
                  key={w.key}
                  shape="line"
                  color={windowColor(w.key, mode)}
                  label={w.label}
                />
              ))}
            </div>
            <Chart
              option={option}
              height={300}
              ariaLabel={`Best ${metricName} for each duration, all time and recent windows`}
            />
            {keyPoints.length > 0 && (
              <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {keyPoints.map((k) => {
                  const ratio = k.now !== null && disp.ratio ? disp.ratio(k.now, k.best) : null;
                  return (
                    <div
                      key={k.t}
                      className="rounded-card border border-line bg-surface-2 px-3 py-2.5"
                    >
                      <dt className="text-xs text-ink-3">{durText(k.t)}</dt>
                      <dd className="mt-0.5 text-base font-semibold text-ink tabular">
                        {disp.format(k.best)}{" "}
                        <span className="text-xs font-normal text-ink-3">{disp.unit}</span>
                      </dd>
                      <dd className="text-xs text-ink-3 tabular">
                        {k.now === null
                          ? "none in 90 d"
                          : ratio !== null
                            ? `90 d: ${disp.format(k.now)} · ${fmtPercent(ratio * 100)}`
                            : `90 d: ${disp.format(k.now)}`}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            )}
          </>
        )}
      </QueryState>
    </Card>
  );
}

type CumulativeMetric = "distance" | "duration" | "elevation";

function cumulativeValue(metric: CumulativeMetric, units: UnitSystem): (v: number) => number {
  if (metric === "distance") return (v) => distanceValue(v, units);
  if (metric === "duration") return (v) => v / 3600;
  return (v) => (units === "metric" ? v : v * 3.28084);
}

function cumulativeFormat(metric: CumulativeMetric, units: UnitSystem): (v: number) => string {
  if (metric === "distance") return (v) => `${fmtNumber(v)} ${distanceUnit(units)}`;
  if (metric === "duration") return (v) => fmtHours(v * 3600);
  return (v) => `${fmtNumber(v)} ${units === "metric" ? "m" : "ft"}`;
}

/** Running total per day of year, one line per year; the current year leads. */
export function CumulativeCard({ sport }: { sport: string }) {
  const mode = useMode();
  const units = useUnits();
  const [metric, setMetric] = useState<CumulativeMetric>("distance");
  const q = api.useQuery(
    "get",
    "/api/records/cumulative",
    { params: { query: { sport, metric } } },
    { placeholderData: (prev) => prev },
  );
  const conv = useMemo(() => cumulativeValue(metric, units), [metric, units]);
  const fmt = useMemo(() => cumulativeFormat(metric, units), [metric, units]);
  const years = useMemo(
    () => [...(q.data?.years ?? [])].filter((y) => y.total > 0).sort((a, b) => a.year - b.year),
    [q.data],
  );
  const current = years[years.length - 1];

  const styleFor = useMemo(
    () => (year: number) => {
      const c = CHROME[mode];
      if (year === current?.year)
        return { color: CATEGORICAL[mode][0]!, width: 2.5, opacity: 1, text: c.text };
      const age = (current?.year ?? year) - year;
      return { color: c.muted, width: 1.5, opacity: age <= 1 ? 0.95 : 0.5, text: c.muted };
    },
    [mode, current],
  );

  const option = useMemo<ChartOption>(() => {
    return {
      grid: { ...GRID, right: 48 },
      tooltip: axisTooltip((p) => {
        const arr = p as { seriesIndex: number; value: [number, number] }[];
        const doy = arr[0]?.value[0];
        if (doy === undefined) return "";
        return (
          tooltipTitle(doyLabel(doy)) +
          [...arr]
            .reverse()
            .map((a) => {
              const y = years[a.seriesIndex];
              return y ? tooltipRow(styleFor(y.year).color, String(y.year), fmt(a.value[1])) : "";
            })
            .join("")
        );
      }),
      xAxis: {
        type: "value",
        min: 1,
        max: 366,
        splitLine: { show: false },
        axisTick: { show: false, customValues: MONTH_STARTS },
        axisLabel: {
          customValues: MONTH_STARTS,
          formatter: (v: number) => monthOfDoy(v),
          hideOverlap: true,
        },
      },
      yAxis: valueYAxis(
        metric === "distance"
          ? distanceUnit(units)
          : metric === "duration"
            ? "hours"
            : units === "metric"
              ? "m"
              : "ft",
        (v) => fmtNumber(v),
      ),
      series: years.map((y) => {
        const s = styleFor(y.year);
        return {
          ...line(
            String(y.year),
            y.points.map((pt) => [pt.day_of_year, conv(pt.value)]),
            s.color,
            { width: s.width, z: y.year === current?.year ? 5 : 2 },
          ),
          lineStyle: { width: s.width, color: s.color, opacity: s.opacity },
          endLabel: {
            show: true,
            formatter: "{a}",
            color: s.text,
            fontSize: 11,
            fontWeight: y.year === current?.year ? 600 : 400,
            distance: 6,
          },
          labelLayout: { moveOverlap: "shiftY" },
          emphasis: { focus: "series" },
          blur: { lineStyle: { opacity: 0.25 } },
        };
      }),
    };
  }, [years, conv, fmt, metric, units, styleFor, current]);

  // Current year vs last year at the same day of year.
  const lastPoint = current?.points[current.points.length - 1];
  const prev = years.find((y) => current && y.year === current.year - 1);
  const prevSame = lastPoint
    ? prev?.points.find((p) => p.day_of_year === lastPoint.day_of_year)
    : undefined;
  const pct =
    lastPoint && prevSame && prevSame.value > 0
      ? (lastPoint.value / prevSame.value - 1) * 100
      : null;

  return (
    <Card
      className="lg:col-span-2"
      title={`Year over year · ${sportLabel(sport)}`}
      subtitle={
        current && lastPoint
          ? `${current.year} so far: ${fmt(conv(lastPoint.value))} by ${doyDate(current.year, lastPoint.day_of_year)}${
              pct !== null && prev
                ? ` · ${signed(pct, 0, " %")} vs ${prev.year} at the same point`
                : ""
            }`
          : "Running total through each year"
      }
      actions={
        <Segmented
          size="sm"
          label="Cumulative metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "distance", label: "Distance" },
            { value: "duration", label: "Time" },
            { value: "elevation", label: "Elevation" },
          ]}
        />
      }
    >
      <QueryState
        query={q}
        height={300}
        isEmpty={() => years.length === 0}
        empty={<EmptyState title={`No ${sportLabel(sport).toLowerCase()} activities yet`} />}
      >
        {() => (
          <>
            <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
              {[...years].reverse().map((y) => (
                <LegendItem
                  key={y.year}
                  shape="line"
                  color={styleFor(y.year).color}
                  label={`${y.year} · ${fmt(conv(y.total))}${y.year === current?.year ? " so far" : ""}`}
                />
              ))}
            </div>
            <Chart
              option={option}
              height={300}
              ariaLabel={`Cumulative ${metric} per day of year, one line per year`}
            />
          </>
        )}
      </QueryState>
    </Card>
  );
}
