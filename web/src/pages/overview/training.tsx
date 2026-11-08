/** Training cards: status + load focus, fitness (CTL/ATL/TSB), VO2max + race predictions. */
import { clsx } from "clsx";
import { CircleCheck } from "lucide-react";
import { useMemo } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, Delta, EmptyState, Skeleton, StatusPill } from "@/components/ui";
import {
  axisTooltip,
  dayPoint,
  GRID_WITH_LEGEND,
  legend,
  line,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import { DASH, fmtDate, fmtDuration, fmtNumber, fmtPace, fmtShortDate, signed } from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { addDays, isoDay } from "@/lib/range";
import { CATEGORICAL, CHROME, STATUS, ZONE_RAMP, type Mode } from "@/lib/tokens";
import { acwrState, loadBalanceState, trainingState } from "./status";
import { BigValue, MiniStat } from "./widgets";

type Overview = Schemas["OverviewToday"];

function FocusRow({
  label,
  value,
  min,
  max,
  scale,
  color,
}: {
  label: string;
  value: number | null;
  min: number | null;
  max: number | null;
  scale: number;
  color: string;
}) {
  const pct = (v: number) => `${Math.min(v / scale, 1) * 100}%`;
  const inRange = value !== null && min !== null && max !== null && value >= min && value <= max;
  const verdict =
    value === null || min === null || max === null
      ? null
      : value < min
        ? "Below target"
        : value > max
          ? "Above target"
          : "In target";
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium text-ink-2">{label}</span>
        <span className="flex items-center gap-2">
          {verdict && (
            <span className="inline-flex items-center gap-1 text-ink-3">
              {inRange && <CircleCheck size={13} color={STATUS.good} aria-hidden />}
              {verdict}
            </span>
          )}
          <span className="font-semibold text-ink tabular">{fmtNumber(value)}</span>
        </span>
      </div>
      <div aria-hidden className="relative h-3.5 rounded-full bg-surface-2">
        {min !== null && max !== null && (
          <div
            className="absolute inset-y-0 rounded-full border border-dashed border-ink-3/70 bg-surface-3/60"
            style={{ left: pct(min), width: `calc(${pct(max)} - ${pct(min)})` }}
          />
        )}
        {value !== null && (
          <div
            className="absolute top-1/2 left-0 h-2 -translate-y-1/2 rounded-full"
            style={{ width: pct(value), background: color }}
          />
        )}
      </div>
    </div>
  );
}

export function TrainingStatusCard({
  t,
  day,
  className,
}: {
  t: Overview["training_status"];
  day: string;
  className?: string;
}) {
  const mode = useMode();
  const detail = api.useQuery("get", "/api/training/status", {
    params: { query: { start: day, end: day } },
  });
  const target = detail.data?.[0];
  const state = trainingState(t?.status);
  const acwr = acwrState(t?.acwr_status);
  const balance = loadBalanceState(target?.load_balance_feedback);
  const rows = t
    ? [
        {
          label: "Low aerobic",
          value: t.load_low_aerobic,
          min: target?.target_low_aerobic_min ?? null,
          max: target?.target_low_aerobic_max ?? null,
        },
        {
          label: "High aerobic",
          value: t.load_high_aerobic,
          min: target?.target_high_aerobic_min ?? null,
          max: target?.target_high_aerobic_max ?? null,
        },
        {
          label: "Anaerobic",
          value: t.load_anaerobic,
          min: target?.target_anaerobic_min ?? null,
          max: target?.target_anaerobic_max ?? null,
        },
      ]
    : [];
  const scale =
    Math.max(1, ...rows.flatMap((r) => [r.value ?? 0, r.max ?? 0]).filter(Number.isFinite)) * 1.08;
  // Low → high intensity on the ordinal blue ramp.
  const ramp = ZONE_RAMP[mode];
  const colors = [ramp[1]!, ramp[3]!, ramp[4]!];
  return (
    <Card
      title="Training status"
      subtitle="Garmin's view of your recent training"
      actions={t?.status ? <StatusPill status={state.status} label={state.label} /> : undefined}
      className={className}
    >
      {!t ? (
        <EmptyState title="No training status for this day" />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-3 gap-3">
            <MiniStat
              label="Acute : chronic"
              value={fmtNumber(t.acwr, 2)}
              sub={
                t.acwr_status ? (
                  <span className="inline-flex items-center gap-1">
                    {acwr.status === "good" && (
                      <CircleCheck size={12} color={STATUS.good} aria-hidden />
                    )}
                    {acwr.label}
                  </span>
                ) : undefined
              }
            />
            <MiniStat label="Acute load" value={fmtNumber(t.acute_load)} sub="7 days" />
            <MiniStat label="Chronic load" value={fmtNumber(t.chronic_load)} sub="28 days" />
          </div>
          <div className="border-t border-line pt-3">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h3 className="text-xs font-semibold text-ink">Load focus</h3>
                <p className="text-xs text-ink-3">Last 4 weeks · dashed = target range</p>
              </div>
              {target?.load_balance_feedback && (
                <StatusPill status={balance.status} label={balance.label} />
              )}
            </div>
            {detail.isPending ? (
              <Skeleton height={124} />
            ) : (
              <div className="flex flex-col gap-3">
                {rows.map((r, i) => (
                  <FocusRow key={r.label} {...r} scale={scale} color={colors[i]!} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

function fitnessOption(
  points: Schemas["TrainingLoadPoint"][],
  mode: Mode,
  ctlColor: string,
): ChartOption {
  const muted = CHROME[mode].muted;
  return {
    grid: { ...GRID_WITH_LEGEND, top: 30 },
    legend: legend(),
    tooltip: axisTooltip((p) => {
      const arr = p as { seriesName: string; color: string; value: [number, number] }[];
      const first = arr[0];
      if (!first) return "";
      return (
        tooltipTitle(fmtDate(isoDay(new Date(first.value[0])))) +
        arr.map((a) => tooltipRow(a.color, a.seriesName, fmtNumber(a.value[1], 1))).join("")
      );
    }),
    xAxis: {
      type: "time",
      axisLabel: {
        formatter: (v: number) => fmtShortDate(isoDay(new Date(v))),
        hideOverlap: true,
      },
      splitNumber: 3,
    },
    yAxis: valueYAxis(undefined, undefined, { scale: true, splitNumber: 3 }),
    series: [
      line(
        "Fitness (CTL)",
        points.map((p) => dayPoint(p.day, p.ctl)),
        ctlColor,
        { area: true },
      ),
      line(
        "Fatigue (ATL)",
        points.map((p) => dayPoint(p.day, p.atl)),
        muted,
        { width: 1.5 },
      ),
    ],
  };
}

export function FitnessCard({
  f,
  day,
  className,
}: {
  f: Overview["fitness"];
  day: string;
  className?: string;
}) {
  const mode = useMode();
  const load = api.useQuery("get", "/api/training/load", {
    params: { query: { start: addDays(day, -89), end: day } },
  });
  const option = useMemo(
    () =>
      load.data && load.data.length > 1
        ? fitnessOption(load.data, mode, CATEGORICAL[mode][0]!)
        : null,
    [load.data, mode],
  );
  const form = f.tsb;
  return (
    <Card
      title="Fitness & form"
      subtitle="Training stress balance, last 90 days"
      className={clsx("flex flex-col", className)}
      bodyClassName="flex flex-1 flex-col"
    >
      {f.ctl === null ? (
        <EmptyState title="No load history yet" />
      ) : (
        <div className="flex flex-1 flex-col gap-3">
          <div className="grid grid-cols-3 gap-3">
            <MiniStat
              label="Fitness"
              value={fmtNumber(f.ctl)}
              sub={
                <Delta
                  value={f.ctl_delta_28d}
                  text={`${signed(f.ctl_delta_28d, 1)} in 28d`}
                  direction="up-good"
                />
              }
            />
            <MiniStat label="Fatigue" value={fmtNumber(f.atl)} sub="7-day load" />
            <MiniStat
              label="Form"
              value={signed(form, 0)}
              sub={
                form === null
                  ? undefined
                  : form > 5
                    ? "Fresh"
                    : form < -20
                      ? "Heavy fatigue"
                      : form < -5
                        ? "Building"
                        : "Neutral"
              }
            />
          </div>
          {load.isPending ? (
            <Skeleton height={212} />
          ) : option ? (
            <Chart
              option={option}
              height="100%"
              className="min-h-[200px] flex-1"
              ariaLabel="Fitness and fatigue over 90 days"
            />
          ) : null}
        </div>
      )}
    </Card>
  );
}

const RACES = [
  { key: "time_5k_s", label: "5K", m: 5000 },
  { key: "time_10k_s", label: "10K", m: 10000 },
  { key: "time_half_s", label: "Half marathon", m: 21097.5 },
  { key: "time_marathon_s", label: "Marathon", m: 42195 },
] as const;

export function PerformanceCard({
  v,
  races,
  className,
}: {
  v: Overview["vo2max"];
  races: Overview["race_predictions"];
  className?: string;
}) {
  const units = useUnits();
  return (
    <Card title="Running performance" className={className}>
      <div className="flex flex-col gap-4">
        <div>
          <p className="text-xs text-ink-3">VO2 max</p>
          <BigValue value={v.running !== null ? fmtNumber(v.running, 1) : DASH} unit="ml/kg/min">
            <Delta
              value={v.delta_30d}
              text={`${signed(v.delta_30d, 1)} in 30 days`}
              direction="up-good"
            />
          </BigValue>
        </div>
        <div className="border-t border-line pt-3">
          <h3 className="mb-2 text-xs font-semibold text-ink">Race predictions</h3>
          {!races ? (
            <EmptyState title="No race predictions yet" />
          ) : (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              {RACES.map((r) => {
                const s = races[r.key];
                return (
                  <div key={r.key} className="min-w-0">
                    <dt className="truncate text-xs text-ink-3">{r.label}</dt>
                    <dd className="mt-0.5 text-lg leading-tight font-semibold text-ink tabular">
                      {fmtDuration(s)}
                    </dd>
                    <dd className="text-xs text-ink-3 tabular">
                      {s ? fmtPace(r.m / s, units) : DASH}
                    </dd>
                  </div>
                );
              })}
            </dl>
          )}
        </div>
      </div>
    </Card>
  );
}
