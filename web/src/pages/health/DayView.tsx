/** One day in detail: linked HR, stress, body battery and steps with sleep and activities marked. */
import { Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { SportIcon } from "@/components/SportIcon";
import { Card, EmptyState, ErrorState, LegendItem, Skeleton } from "@/components/ui";
import { Stepper } from "@/components/kit";
import { axisTooltip, bars, DAY_MS, line, smallTitle, tooltipRow, valueYAxis } from "@/lib/charts";
import { DASH, fmtDate, fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { sportColor, sportLabel } from "@/lib/sports";
import { CHROME, measureColors, NEUTRAL, wash, type Mode } from "@/lib/tokens";
import { HOUR_MS, fmtWallTime, wallClock, wallMidnight } from "@/lib/wallClock";

type Intraday = Schemas["WellnessIntraday"];
type Day = Schemas["WellnessDay"];

interface Panel {
  key: string;
  label: string;
  unit: string;
  color: string;
  kind: "line" | "area" | "bars";
  data: [number, number | null][];
  min?: number;
  max?: number;
}

/** Data-driven heart-rate axis on round tens with at least a 40 bpm span (never 0–200). */
function hrBounds(values: (number | null)[]): { min?: number; max?: number } {
  const v = values.filter((x): x is number => x !== null);
  if (!v.length) return {};
  let min = Math.floor((Math.min(...v) - 5) / 10) * 10;
  let max = Math.ceil((Math.max(...v) + 5) / 10) * 10;
  if (max - min < 40) {
    const pad = Math.ceil((40 - (max - min)) / 20) * 10;
    min -= pad;
    max += pad;
  }
  min = Math.max(0, min);
  // Three equal steps on round tens, so the top tick sits on the axis end.
  const step = Math.ceil((max - min) / 30) * 10;
  return { min, max: min + 3 * step };
}

function panels(d: Intraday, mode: Mode): Panel[] {
  const col = measureColors(mode);
  const wall = wallClock(d.time_zone);
  const pts = (arr: { ts: string; value: number | null }[]) =>
    arr.map((p) => [wall(p.ts), p.value] as [number, number | null]);
  const out: Panel[] = [];
  if (d.hr.some((p) => p.value != null))
    out.push({
      key: "hr",
      label: "Heart rate",
      unit: "bpm",
      color: col.hr,
      kind: "line",
      data: pts(d.hr),
      ...hrBounds(d.hr.map((p) => p.value)),
    });
  if (d.stress.some((p) => p.value != null))
    out.push({
      key: "stress",
      label: "Stress",
      unit: "0–100",
      color: col.stress,
      kind: "area",
      data: pts(d.stress),
      min: 0,
      max: 100,
    });
  if (d.body_battery.some((p) => p.value != null))
    out.push({
      key: "bb",
      label: "Body battery",
      unit: "0–100",
      color: col.bodyBattery,
      kind: "area",
      data: pts(d.body_battery),
      min: 0,
      max: 100,
    });
  if (d.steps.some((s) => s.steps > 0))
    out.push({
      key: "steps",
      label: "Steps",
      unit: "per 15 min",
      color: col.steps,
      kind: "bars",
      data: d.steps.map((s) => [(wall(s.start) + wall(s.end)) / 2, s.steps]),
      min: 0,
    });
  return out;
}

function panelOption(
  p: Panel,
  d: Intraday,
  mode: Mode,
  first: boolean,
  last: boolean,
): ChartOption {
  const c = CHROME[mode];
  const wall = wallClock(d.time_zone);
  const t0 = wallMidnight(d.day);
  const t1 = t0 + DAY_MS;
  const areas: unknown[] = [];
  if (d.sleep) {
    const s0 = Math.max(wall(d.sleep.start), t0);
    const s1 = Math.min(wall(d.sleep.end), t1);
    if (s1 > s0)
      areas.push([
        {
          xAxis: s0,
          name: "Sleep",
          itemStyle: { color: wash(NEUTRAL[mode], mode === "dark" ? 0.16 : 0.13) },
        },
        { xAxis: s1 },
      ]);
  }
  for (const a of d.activities) {
    const a0 = Math.max(wall(a.start), t0);
    const a1 = Math.min(wall(a.end), t1);
    if (a1 > a0)
      areas.push([
        {
          xAxis: a0,
          name: a.name ?? sportLabel(a.sport_group),
          label: { show: false },
          itemStyle: {
            color: wash(sportColor(a.sport_group, mode), mode === "dark" ? 0.22 : 0.16),
          },
        },
        { xAxis: a1 },
      ]);
  }
  const fmt = (v: number) => fmtNumber(v);
  const base =
    p.kind === "bars"
      ? { ...bars(p.label, p.data, p.color, mode, { barMaxWidth: 6 }), barCategoryGap: "20%" }
      : { ...line(p.label, p.data, p.color, { area: p.kind === "area" }), sampling: "lttb" };
  return {
    useUTC: true,
    title: smallTitle(`${p.label} (${p.unit})`, mode),
    // Top padding keeps the panel title clear of the first tick label.
    grid: { left: 40, right: 12, top: 32, bottom: last ? 24 : 6, outerBoundsMode: "none" },
    tooltip: axisTooltip<{ value: [number, number | null] }>((arr) => {
      const v = arr[0]?.value;
      if (!v) return "";
      return `<div style="color:${c.muted};margin-bottom:4px">${fmtWallTime(v[0])}</div>${tooltipRow(
        p.color,
        p.label,
        v[1] == null ? DASH : `${fmt(v[1])}${p.key === "hr" ? " bpm" : ""}`,
      )}`;
    }),
    xAxis: {
      type: "time",
      min: t0,
      max: t1,
      interval: 3 * HOUR_MS,
      axisLabel: { show: last, formatter: "{HH}:{mm}", hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: valueYAxis(undefined, fmt, {
      scale: p.min === undefined,
      min: p.min,
      max: p.max,
      ...(p.key === "hr" && p.min !== undefined && p.max !== undefined
        ? { interval: (p.max - p.min) / 3 }
        : {}),
      splitNumber: 2,
    }),
    series: [
      {
        ...base,
        markArea: areas.length
          ? {
              silent: true,
              label: {
                show: first,
                position: "insideTop",
                color: c.muted,
                fontSize: 11,
                overflow: "truncate",
              },
              data: areas,
            }
          : undefined,
      },
    ],
  };
}

export function DayView({
  day,
  summary,
  onPrev,
  onNext,
}: {
  day: string;
  summary: Day | undefined;
  onPrev: (() => void) | null;
  onNext: (() => void) | null;
}) {
  const mode = useMode();
  const q = api.useQuery(
    "get",
    "/api/wellness/intraday",
    { params: { query: { day } } },
    { placeholderData: (prev) => prev },
  );
  const list = useMemo(() => (q.data ? panels(q.data, mode) : []), [q.data, mode]);
  const options = useMemo(
    () =>
      q.data
        ? list.map((p, i) => panelOption(p, q.data!, mode, i === 0, i === list.length - 1))
        : [],
    [list, q.data, mode],
  );
  const wall = q.data ? wallClock(q.data.time_zone) : null;
  const facts = summary
    ? [
        summary.resting_hr != null ? `Resting HR ${summary.resting_hr} bpm` : null,
        summary.steps != null ? `${fmtNumber(summary.steps)} steps` : null,
        summary.avg_stress != null ? `stress avg ${summary.avg_stress}` : null,
        summary.body_battery_low != null && summary.body_battery_high != null
          ? `body battery ${summary.body_battery_low}–${summary.body_battery_high}`
          : null,
      ].filter(Boolean)
    : [];
  return (
    <Card
      id="day-timeline"
      title={`Day timeline · ${fmtDate(day, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}`}
      subtitle={facts.length ? facts.join(" · ") : "All-day measurements in local time"}
      actions={
        <Stepper
          label={fmtDate(day, { day: "numeric", month: "short" })}
          onPrev={onPrev}
          onNext={onNext}
          prevLabel="Previous day"
          nextLabel="Next day"
        />
      }
      className="lg:col-span-2"
    >
      {q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data ? (
        <Skeleton height={480} />
      ) : !list.length ? (
        <EmptyState title="No all-day data for this day">
          Heart rate, stress and body battery are recorded while you wear the watch.
        </EmptyState>
      ) : (
        <div style={{ opacity: q.isPlaceholderData ? 0.6 : 1 }}>
          <div className="flex flex-col gap-1">
            {list.map((p, i) => (
              <Chart
                key={p.key}
                option={options[i]!}
                height={i === list.length - 1 ? 140 : 120}
                group="health-day"
                ariaLabel={`${p.label} through the day`}
              />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            {q.data.sleep && (
              <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
                <LegendItem
                  color={wash(NEUTRAL[mode], 0.45)}
                  label={`Sleep ${wall ? `${fmtWallTime(wall(q.data.sleep.start))}–${fmtWallTime(wall(q.data.sleep.end))}` : ""}`}
                />
              </span>
            )}
            {q.data.activities.map((a) => (
              <Link
                key={a.activity_id}
                to="/activities/$activityId"
                params={{ activityId: String(a.activity_id) }}
                className="inline-flex items-center gap-1.5 rounded-control px-1.5 py-0.5 text-xs text-ink-2 hover:bg-hover hover:text-ink"
              >
                <SportIcon group={a.sport_group} size={13} colored />
                <span className="font-medium text-ink">{a.name ?? sportLabel(a.sport_group)}</span>
                {wall && (
                  <span className="tabular">
                    {fmtWallTime(wall(a.start))}–{fmtWallTime(wall(a.end))}
                  </span>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
