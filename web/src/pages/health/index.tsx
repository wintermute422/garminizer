import {
  Activity,
  BatteryMedium,
  Droplets,
  Footprints,
  Gauge,
  HeartPulse,
  Waves,
  Wind,
} from "lucide-react";
import { keepPreviousData } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  StatusPill,
  type DeltaDirection,
} from "@/components/ui";
import { DASH, fmtDate, fmtHours, fmtNumber, fmtShortDate, titleCase } from "@/lib/format";
import { STRESS_LEVELS } from "@/lib/tokens";
import { useMode, useUnits } from "@/lib/preferences";
import { addDays, useRange } from "@/lib/range";
import { DayView } from "./DayView";
import { HourHeatmap } from "./Heatmap";
import { Change, MetricTile, Spark, TileSkeletons } from "./kit";
import {
  bodyBatteryOption,
  dayExtent,
  hrvOption,
  readinessOption,
  restingHrOption,
  stepsOption,
  stressDailyOption,
  stressWeeklyOption,
  weeklyExtent,
} from "./options";
import {
  diff,
  hrvStatus,
  mean,
  measureColors,
  minOf,
  previousPeriod,
  readinessStatus,
  spanDays,
  weekly,
} from "./util";

type Day = Schemas["WellnessDay"];

const TILE_GRID = "grid grid-cols-2 gap-3 md:grid-cols-4";

interface TileSpec {
  key: string;
  label: string;
  icon: ReactNode;
  unit?: string;
  digits: number;
  deltaDigits: number;
  direction: DeltaDirection;
  color: string;
  get: (d: Day) => number | null | undefined;
  /** State metrics show the latest value with that day's badge (and the period average). */
  latestBadge?: (row: Day) => ReactNode;
  sub?: (rows: Day[]) => ReactNode;
}

function Tiles({ rows, prev, days }: { rows: Day[]; prev: Day[]; days: number }) {
  const mode = useMode();
  const col = measureColors(mode);
  const specs: TileSpec[] = [
    {
      key: "rhr",
      label: "Resting HR",
      icon: <HeartPulse size={14} />,
      unit: "bpm",
      digits: 0,
      deltaDigits: 1,
      direction: "down-good",
      color: col.hr,
      get: (d) => d.resting_hr,
      sub: (r) => {
        const lo = minOf(r.map((d) => d.resting_hr));
        return lo == null ? null : `low ${lo}`;
      },
    },
    {
      key: "hrv",
      label: "HRV · last night",
      icon: <Activity size={14} />,
      unit: "ms",
      digits: 0,
      deltaDigits: 1,
      direction: "up-good",
      color: col.hrv,
      get: (d) => d.hrv_last_night_avg_ms,
      latestBadge: (d) =>
        d.hrv_status ? (
          <StatusPill status={hrvStatus(d.hrv_status)} label={titleCase(d.hrv_status)} />
        ) : null,
    },
    {
      key: "ready",
      label: "Training readiness",
      icon: <Gauge size={14} />,
      unit: "/ 100",
      digits: 0,
      deltaDigits: 1,
      direction: "up-good",
      color: col.readiness,
      get: (d) => d.readiness_score,
      latestBadge: (d) =>
        d.readiness_level ? (
          <StatusPill
            status={readinessStatus(d.readiness_level)}
            label={titleCase(d.readiness_level)}
          />
        ) : null,
    },
    {
      key: "bb",
      label: "Body battery at wake",
      icon: <BatteryMedium size={14} />,
      unit: "/ 100",
      digits: 0,
      deltaDigits: 1,
      direction: "up-good",
      color: col.bodyBattery,
      get: (d) => d.body_battery_at_wake,
    },
    {
      key: "stress",
      label: "Average stress",
      icon: <Waves size={14} />,
      unit: "/ 100",
      digits: 0,
      deltaDigits: 1,
      direction: "down-good",
      color: col.stress,
      get: (d) => d.avg_stress,
    },
    {
      key: "steps",
      label: "Steps per day",
      icon: <Footprints size={14} />,
      digits: 0,
      deltaDigits: 0,
      direction: "up-good",
      color: col.steps,
      get: (d) => d.steps,
      sub: (r) => {
        const withGoal = r.filter((d) => d.steps != null && d.step_goal);
        if (!withGoal.length) return null;
        const met = withGoal.filter((d) => d.steps! >= d.step_goal!).length;
        return `goal met ${fmtNumber((met / withGoal.length) * 100)} %`;
      },
    },
    {
      key: "spo2",
      label: "Blood oxygen",
      icon: <Droplets size={14} />,
      unit: "% SpO₂",
      digits: 1,
      deltaDigits: 1,
      direction: "neutral",
      color: col.spo2,
      get: (d) => d.avg_spo2,
      sub: (r) => {
        const lo = minOf(r.map((d) => d.lowest_spo2));
        return lo == null ? null : `lowest ${fmtNumber(lo)} %`;
      },
    },
    {
      key: "resp",
      label: "Respiration",
      icon: <Wind size={14} />,
      unit: "brpm",
      digits: 1,
      deltaDigits: 1,
      direction: "neutral",
      color: col.respiration,
      get: (d) => d.avg_waking_respiration,
      sub: () => "while awake",
    },
  ];
  return (
    <div className={TILE_GRID}>
      {specs.map((s) => {
        const cur = mean(rows.map(s.get));
        const before = mean(prev.map(s.get));
        const weeks = weekly(rows, (r) => r.day, s.get);
        const unitSuffix =
          s.unit && !s.unit.startsWith("/") && !s.unit.startsWith("%") ? s.unit : "";
        const spark = (
          <Spark
            values={weeks.map((w) => w.value)}
            color={s.color}
            label={`${s.label}, weekly averages`}
          />
        );
        if (s.latestBadge) {
          // The badge describes the number shown: both come from the latest day.
          const row = [...rows].reverse().find((r) => s.get(r) != null);
          return (
            <MetricTile
              key={s.key}
              label={s.label}
              icon={s.icon}
              value={row ? fmtNumber(s.get(row), s.digits) : DASH}
              unit={s.unit}
              delta={row ? s.latestBadge(row) : null}
              sub={
                row ? (
                  <span>
                    {fmtShortDate(row.day)} · {days}-day avg {fmtNumber(cur, s.digits)}
                  </span>
                ) : null
              }
              spark={spark}
            />
          );
        }
        return (
          <MetricTile
            key={s.key}
            label={s.label}
            icon={s.icon}
            value={fmtNumber(cur, s.digits)}
            unit={s.unit}
            delta={
              <Change
                value={diff(cur, before)}
                digits={s.deltaDigits}
                unit={unitSuffix}
                direction={s.direction}
                title={`Change vs the previous ${days} days`}
              />
            }
            sub={s.sub && <span>{s.sub(rows)}</span>}
            spark={spark}
          />
        );
      })}
    </div>
  );
}

function ChartCard({
  title,
  subtitle,
  actions,
  className,
  option,
  height = 240,
  ariaLabel,
  empty,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
  option: ChartOption | null;
  height?: number;
  ariaLabel: string;
  empty: string;
  children?: ReactNode;
}) {
  return (
    <Card title={title} subtitle={subtitle} actions={actions} className={className}>
      {option ? (
        <Chart option={option} height={height} ariaLabel={ariaLabel} />
      ) : (
        <EmptyState title={empty} />
      )}
      {children}
    </Card>
  );
}

function has(rows: Day[], get: (d: Day) => unknown): boolean {
  return rows.some((r) => get(r) !== null && get(r) !== undefined);
}

const STRESS_KEYS = ["rest", "low", "medium", "high"] as const;

export default function HealthPage() {
  const range = useRange("90d");
  const mode = useMode();
  const units = useUnits();
  const prevQuery = previousPeriod(range.query);
  const days = spanDays(range.query.start, range.query.end);
  const opts = { enabled: range.ready, placeholderData: keepPreviousData };
  const daily = api.useQuery(
    "get",
    "/api/wellness/daily",
    { params: { query: range.query } },
    opts,
  );
  const prevDaily = api.useQuery(
    "get",
    "/api/wellness/daily",
    { params: { query: prevQuery } },
    opts,
  );
  const readiness = api.useQuery(
    "get",
    "/api/wellness/readiness",
    { params: { query: range.query } },
    opts,
  );
  const meta = api.useQuery("get", "/api/meta");
  const [picked, setPicked] = useState<string | null>(null);

  const rows = useMemo(() => daily.data ?? [], [daily.data]);
  // Average time per stress level; the thin "high" slivers in the stack need it in text.
  const stressAvg = useMemo(
    () =>
      STRESS_KEYS.map((k) => {
        const v = rows.map((r) => r[`stress_${k}_s`]).filter((x): x is number => x != null);
        return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
      }),
    [rows],
  );
  const ext = useMemo(
    () => dayExtent(range.query.start, range.query.end),
    [range.query.start, range.query.end],
  );
  const charts = useMemo(() => {
    const wext = weeklyExtent(rows, ext);
    return {
      rhr: has(rows, (r) => r.resting_hr) ? restingHrOption(rows, mode, ext) : null,
      hrv: has(rows, (r) => r.hrv_last_night_avg_ms) ? hrvOption(rows, mode, ext) : null,
      stressDaily: has(rows, (r) => r.avg_stress) ? stressDailyOption(rows, mode, wext) : null,
      stressWeekly: has(rows, (r) => r.stress_rest_s) ? stressWeeklyOption(rows, mode, wext) : null,
      bb: has(rows, (r) => r.body_battery_high) ? bodyBatteryOption(rows, mode, ext) : null,
      steps: has(rows, (r) => r.steps) ? stepsOption(rows, mode, ext, units) : null,
    };
  }, [rows, mode, ext, units]);
  const readinessRows = readiness.data ?? [];
  const readinessChart = useMemo(
    () =>
      readiness.data && readiness.data.some((r) => r.score != null)
        ? readinessOption(readiness.data, mode, ext)
        : null,
    [readiness.data, mode, ext],
  );

  const lastDay = rows.length ? rows[rows.length - 1]!.day : null;
  const inRange = (d: string | null) =>
    d !== null && d >= range.query.start && d <= range.query.end;
  const day = inRange(picked) ? picked : lastDay;
  const step = (n: number) => {
    if (!day) return null;
    const next = addDays(day, n);
    return inRange(next) ? () => setPicked(next) : null;
  };
  const summary = rows.find((r) => r.day === day);
  const latestReady = [...readinessRows].reverse().find((r) => r.level);
  const stepsGoalDays = rows.filter((r) => r.steps != null && r.step_goal);
  const goalMet = stepsGoalDays.filter((r) => r.steps! >= r.step_goal!).length;
  const latestHrv = [...rows].reverse().find((r) => r.hrv_status);

  const onSelectDay = (d: string) => {
    setPicked(d);
    document.getElementById("day-timeline")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <PageHeader
        title="Health & recovery"
        description={`${fmtDate(range.start)} – ${fmtDate(range.end)} · averages for the period; arrows compare with the previous ${days} days.`}
      />
      <div className="flex flex-col gap-5">
        {daily.error ? (
          <ErrorState error={daily.error} />
        ) : !daily.data ? (
          <TileSkeletons n={8} className={TILE_GRID} />
        ) : rows.length === 0 ? (
          <EmptyState title="No daily health data in this period">
            Wear your watch day and night and sync it with Garmin Connect; resting heart rate, HRV,
            stress and body battery appear here after the next Garminizer sync.
          </EmptyState>
        ) : (
          <Tiles rows={rows} prev={prevDaily.data ?? []} days={days} />
        )}

        {daily.data && rows.length > 0 && (
          <div className="grid gap-5 lg:grid-cols-2">
            <ChartCard
              title="Resting heart rate"
              subtitle="Daily value and 7-day mean · lower usually means better recovery"
              option={charts.rhr}
              ariaLabel="Resting heart rate per day with 7-day mean"
              empty="No resting heart rate in this period"
            />
            <ChartCard
              title="Heart-rate variability"
              subtitle="Nightly average, weekly average and your balanced baseline"
              actions={
                latestHrv?.hrv_status ? (
                  <StatusPill
                    status={hrvStatus(latestHrv.hrv_status)}
                    label={titleCase(latestHrv.hrv_status)}
                  />
                ) : undefined
              }
              option={charts.hrv}
              ariaLabel="Nightly HRV with weekly average and balanced baseline range"
              empty="No HRV readings in this period"
            />
            <Card
              title="Training readiness"
              subtitle="Daily score from sleep, recovery, HRV, load and stress history"
              actions={
                latestReady?.level ? (
                  <StatusPill
                    status={readinessStatus(latestReady.level)}
                    label={`${titleCase(latestReady.level)}${latestReady.score != null ? ` · ${latestReady.score}` : ""}`}
                  />
                ) : undefined
              }
            >
              {readiness.error ? (
                <ErrorState error={readiness.error} />
              ) : !readiness.data ? (
                <Skeleton height={240} />
              ) : readinessChart ? (
                <Chart
                  option={readinessChart}
                  height={240}
                  ariaLabel="Training readiness score per day, coloured by level"
                />
              ) : (
                <EmptyState title="No training readiness in this period">
                  Training readiness needs a compatible watch worn overnight.
                </EmptyState>
              )}
            </Card>
            <ChartCard
              title="Body battery"
              subtitle="Daily low → high range and the level you woke up with"
              option={charts.bb}
              ariaLabel="Body battery daily range with value at wake"
              empty="No body battery in this period"
            />
            <Card
              title="Stress"
              subtitle="Daily average, and how each day splits into rest, low, medium and high stress (weekly average)"
              className="lg:col-span-2"
            >
              {charts.stressDaily || charts.stressWeekly ? (
                <div className="grid gap-x-6 gap-y-4 lg:grid-cols-2">
                  {charts.stressDaily && (
                    <Chart
                      option={charts.stressDaily}
                      height={220}
                      ariaLabel="Average stress per day"
                    />
                  )}
                  {charts.stressWeekly && (
                    <div>
                      <Chart
                        option={charts.stressWeekly}
                        height={220}
                        ariaLabel="Weekly average hours per day in rest, low, medium and high stress"
                      />
                      <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-2">
                        <span className="text-ink-3">Average day:</span>
                        {STRESS_KEYS.map((k, i) => (
                          <span key={k} className="inline-flex items-center gap-1.5 tabular">
                            <span
                              className="inline-block size-2.5 rounded-swatch"
                              style={{ background: STRESS_LEVELS[mode][i] }}
                              aria-hidden
                            />
                            {titleCase(k)} {fmtHours(stressAvg[i])}
                          </span>
                        ))}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState title="No stress data in this period" />
              )}
            </Card>
            <ChartCard
              title="Steps"
              subtitle={
                stepsGoalDays.length
                  ? `Goal met on ${goalMet} of ${stepsGoalDays.length} days`
                  : "Daily steps"
              }
              className="lg:col-span-2"
              option={charts.steps}
              height={220}
              ariaLabel="Steps per day with daily step goal"
              empty="No steps in this period"
            />
            <HourHeatmap
              query={range.query}
              enabled={range.ready}
              selected={day}
              onSelect={onSelectDay}
              timeZone={meta.data?.athlete?.time_zone ?? "local"}
            />
            {day && <DayView day={day} summary={summary} onPrev={step(-1)} onNext={step(1)} />}
          </div>
        )}
      </div>
    </>
  );
}
