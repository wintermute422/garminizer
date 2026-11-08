/** Recovery cards: readiness, sleep, body battery, HRV, resting HR, stress, daily goals. */
import { clsx } from "clsx";
import { CircleCheck, Moon, Sunrise } from "lucide-react";
import { useMemo } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, Delta, EmptyState, LegendItem, StatusPill } from "@/components/ui";
import { axisTooltip, GRID, line, tooltipRow, tooltipTitle, valueYAxis } from "@/lib/charts";
import { DASH, fmtHours, fmtNumber, signed } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CATEGORICAL, CHROME, SLEEP_STAGES, STATUS, wash, type Mode } from "@/lib/tokens";
import { hrvState, readinessState, sleepState, stressLabel } from "./status";
import { fmtClock, fmtHourOfDay, hoursIntoDay } from "./time";
import { BandBullet, BigValue, Meter, MiniStat } from "./widgets";

type Overview = Schemas["OverviewToday"];

function ringOption(score: number, mode: Mode): ChartOption {
  const c = CHROME[mode];
  const accent = CATEGORICAL[mode][0]!;
  return {
    series: [
      {
        type: "gauge",
        startAngle: 90,
        endAngle: -270,
        min: 0,
        max: 100,
        radius: "94%",
        silent: true,
        pointer: { show: false },
        progress: { show: true, roundCap: true, width: 12, itemStyle: { color: accent } },
        axisLine: {
          roundCap: true,
          lineStyle: { width: 12, color: [[1, wash(accent, mode === "dark" ? 0.2 : 0.16)]] },
        },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: { show: false },
        detail: {
          offsetCenter: [0, 0],
          valueAnimation: false,
          formatter: "{v|{value}}\n{s|of 100}",
          rich: {
            v: { fontSize: 34, fontWeight: 600, color: c.text, lineHeight: 38 },
            s: { fontSize: 11, color: c.muted, lineHeight: 14 },
          },
        },
        data: [{ value: score }],
      },
    ],
  };
}

function FactorRow({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
        <span className="text-ink-2">{label}</span>
        <span className="font-medium text-ink tabular">
          {value === null ? DASH : `${fmtNumber(value)} %`}
        </span>
      </div>
      <Meter value={value ?? 0} max={100} size="sm" />
    </div>
  );
}

export function ReadinessCard({ r, className }: { r: Overview["readiness"]; className?: string }) {
  const mode = useMode();
  const option = useMemo(() => (r?.score != null ? ringOption(r.score, mode) : null), [r, mode]);
  const state = readinessState(r?.level);
  const factors: { label: string; value: number | null }[] = r
    ? [
        { label: "Sleep", value: r.sleep_score_factor },
        { label: "HRV", value: r.hrv_factor },
        { label: "Acute load", value: r.acwr_factor },
      ]
    : [];
  const weakest = factors
    .filter((f): f is { label: string; value: number } => f.value !== null)
    .sort((a, b) => a.value - b.value)[0];
  return (
    <Card
      title="Training readiness"
      subtitle="Are you ready for a hard session?"
      actions={r?.level ? <StatusPill status={state.status} label={state.label} /> : undefined}
      className={clsx("flex flex-col", className)}
      bodyClassName="flex flex-1 flex-col justify-center"
    >
      {!r || !option ? (
        <EmptyState title="No readiness score for this day" />
      ) : (
        <div className="flex items-center gap-5">
          <div className="w-[152px] shrink-0">
            <Chart
              option={option}
              height={152}
              ariaLabel={`Training readiness ${r.score} of 100, ${state.label}`}
            />
          </div>
          <div className="flex min-w-0 flex-1 flex-col gap-2.5">
            {factors.map((f) => (
              <FactorRow key={f.label} label={f.label} value={f.value} />
            ))}
            <p className="text-xs text-ink-3">
              {r.recovery_time_min
                ? `Recovery time ${fmtHours(r.recovery_time_min * 60)}`
                : "Fully recovered"}
              {weakest && weakest.value < 60 ? ` · held back by ${weakest.label}` : ""}
            </p>
          </div>
        </div>
      )}
    </Card>
  );
}

const STAGES = [
  { key: "deep", label: "Deep" },
  { key: "light", label: "Light" },
  { key: "rem", label: "REM" },
  { key: "awake", label: "Awake" },
] as const;

export function SleepCard({
  s,
  tz,
  className,
}: {
  s: Overview["sleep"];
  tz: string | undefined;
  className?: string;
}) {
  const mode = useMode();
  const state = sleepState(s?.quality);
  const secs = s
    ? { deep: s.deep_s ?? 0, light: s.light_s ?? 0, rem: s.rem_s ?? 0, awake: s.awake_s ?? 0 }
    : null;
  const total = secs ? secs.deep + secs.light + secs.rem + secs.awake : 0;
  const asleep = secs ? secs.deep + secs.light + secs.rem : 0;
  return (
    <Card
      title="Last night's sleep"
      subtitle="Score, stages and timing"
      actions={s?.quality ? <StatusPill status={state.status} label={state.label} /> : undefined}
      className={className}
    >
      {!s || !secs ? (
        <EmptyState title="No sleep recorded for this night" />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-xs text-ink-3">Sleep score</p>
              <BigValue value={s.score ?? DASH} unit="/ 100" />
            </div>
            <div className="text-right">
              <p className="text-xs text-ink-3">Time asleep</p>
              <p className="text-[22px] leading-tight font-semibold text-ink">
                {fmtHours(s.duration_s ?? asleep)}
              </p>
            </div>
          </div>
          {total > 0 && (
            <>
              <div
                className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full"
                role="img"
                aria-label={`Sleep stages: ${STAGES.map((st) => `${st.label} ${fmtHours(secs[st.key])}`).join(", ")}`}
              >
                {STAGES.filter((st) => secs[st.key] > 0).map((st) => (
                  <span
                    key={st.key}
                    className="h-full first:rounded-l-full last:rounded-r-full"
                    style={{
                      width: `${(secs[st.key] / total) * 100}%`,
                      background: SLEEP_STAGES[mode][st.key],
                    }}
                  />
                ))}
              </div>
              <ul className="grid grid-cols-2 gap-x-4 gap-y-2">
                {STAGES.map((st) => (
                  <li key={st.key} className="flex items-baseline justify-between gap-2 text-xs">
                    <LegendItem color={SLEEP_STAGES[mode][st.key]} label={st.label} />
                    <span className="text-ink tabular">
                      {fmtHours(secs[st.key])}
                      {st.key !== "awake" && asleep > 0 && (
                        <span className="ml-1 text-ink-3">
                          {fmtNumber((secs[st.key] / asleep) * 100)} %
                        </span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {s.start_utc && s.end_utc && (
            <div className="grid grid-cols-3 gap-3 border-t border-line pt-3">
              <MiniStat
                label={
                  <span className="inline-flex items-center gap-1">
                    <Moon size={12} aria-hidden /> Asleep
                  </span>
                }
                value={fmtClock(s.start_utc, tz)}
              />
              <MiniStat
                label={
                  <span className="inline-flex items-center gap-1">
                    <Sunrise size={12} aria-hidden /> Awake
                  </span>
                }
                value={fmtClock(s.end_utc, tz)}
              />
              <MiniStat
                label="In bed"
                value={fmtHours((Date.parse(s.end_utc) - Date.parse(s.start_utc)) / 1000)}
              />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function batteryOption(
  points: [number, number][],
  sleep: [number, number] | null,
  mode: Mode,
): ChartOption {
  const c = CHROME[mode];
  const accent = CATEGORICAL[mode][0]!;
  return {
    grid: { ...GRID, top: 12, bottom: 4, left: 4, right: 8 },
    tooltip: axisTooltip((p) => {
      const first = (p as { value: [number, number] }[])[0];
      if (!first) return "";
      return (
        tooltipTitle(fmtHourOfDay(first.value[0])) +
        tooltipRow(accent, "Body battery", fmtNumber(first.value[1]))
      );
    }),
    xAxis: {
      type: "value",
      min: 0,
      max: 24,
      interval: 6,
      axisLabel: { formatter: (v: number) => fmtHourOfDay(v) },
      splitLine: { show: false },
    },
    yAxis: valueYAxis(undefined, undefined, { min: 0, max: 100, interval: 25 }),
    series: [
      {
        ...line("Body battery", points, accent, { area: true }),
        ...(sleep
          ? {
              markArea: {
                silent: true,
                itemStyle: { color: wash(SLEEP_STAGES[mode].rem, mode === "dark" ? 0.16 : 0.1) },
                label: {
                  show: true,
                  position: "insideTop",
                  color: c.muted,
                  fontSize: 11,
                  formatter: "Asleep",
                },
                data: [[{ xAxis: sleep[0] }, { xAxis: sleep[1] }]],
              },
            }
          : {}),
      },
    ],
  };
}

export function BodyBatteryCard({
  b,
  sleep,
  day,
  tz,
  className,
}: {
  b: Overview["body_battery"];
  sleep: Overview["sleep"];
  day: string;
  tz: string | undefined;
  className?: string;
}) {
  const mode = useMode();
  const points = useMemo(
    () =>
      b.series.map(
        (p) => [Math.round(hoursIntoDay(p.ts, day, tz) * 100) / 100, p.value] as [number, number],
      ),
    [b.series, day, tz],
  );
  const asleep = useMemo((): [number, number] | null => {
    if (!sleep?.start_utc || !sleep.end_utc) return null;
    const s = Math.max(0, hoursIntoDay(sleep.start_utc, day, tz));
    const e = Math.min(24, hoursIntoDay(sleep.end_utc, day, tz));
    return e > s ? [s, e] : null;
  }, [sleep, day, tz]);
  const option = useMemo(() => batteryOption(points, asleep, mode), [points, asleep, mode]);
  let charged = 0;
  let drained = 0;
  for (let i = 1; i < b.series.length; i++) {
    const d = b.series[i]!.value - b.series[i - 1]!.value;
    if (d > 0) charged += d;
    else drained -= d;
  }
  return (
    <Card
      title="Body battery"
      subtitle={
        b.series.length > 1 ? `Charged +${charged} · drained −${drained} today` : "Energy reserve"
      }
      className={className}
    >
      <div className="grid grid-cols-4 gap-3">
        <MiniStat label="At wake" value={b.at_wake ?? DASH} />
        <MiniStat label="High" value={b.high ?? DASH} />
        <MiniStat label="Low" value={b.low ?? DASH} />
        <MiniStat label="Latest" value={b.latest ?? DASH} />
      </div>
      {points.length > 1 ? (
        <Chart
          option={option}
          height={150}
          className="mt-3"
          ariaLabel={`Body battery through the day, from ${b.series[0]!.value} to ${b.latest ?? DASH}`}
        />
      ) : (
        <div className="mt-3">
          <EmptyState title="No body battery samples for this day" />
        </div>
      )}
    </Card>
  );
}

export function HrvCard({ h, className }: { h: Overview["hrv"]; className?: string }) {
  const state = hrvState(h?.status);
  const vals = [
    h?.last_night_avg_ms,
    h?.weekly_avg_ms,
    h?.baseline_balanced_low_ms,
    h?.baseline_balanced_upper_ms,
  ].filter((v): v is number => v !== null && v !== undefined);
  const lo = vals.length ? Math.min(...vals) : 0;
  const hi = vals.length ? Math.max(...vals) : 1;
  const pad = Math.max((hi - lo) * 0.35, 4);
  return (
    <Card
      title="Heart-rate variability"
      actions={h?.status ? <StatusPill status={state.status} label={state.label} /> : undefined}
      className={className}
    >
      {!h || h.last_night_avg_ms === null ? (
        <EmptyState title="No HRV reading for this night" />
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-xs text-ink-3">Last night average</p>
            <BigValue value={fmtNumber(h.last_night_avg_ms)} unit="ms" />
          </div>
          <BandBullet
            min={lo - pad}
            max={hi + pad}
            bandLow={h.baseline_balanced_low_ms}
            bandHigh={h.baseline_balanced_upper_ms}
            value={h.last_night_avg_ms}
            secondary={h.weekly_avg_ms}
          />
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-3">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-full bg-accent" aria-hidden /> Last night
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-0.5 rounded-full bg-ink-2" aria-hidden /> 7-day avg{" "}
              <span className="text-ink-2 tabular">{fmtNumber(h.weekly_avg_ms)} ms</span>
            </span>
            {h.baseline_balanced_low_ms !== null && h.baseline_balanced_upper_ms !== null && (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-3 rounded-full bg-accent-soft ring-1 ring-accent/40" />
                Baseline{" "}
                <span className="text-ink-2 tabular">
                  {fmtNumber(h.baseline_balanced_low_ms)}–{fmtNumber(h.baseline_balanced_upper_ms)}{" "}
                  ms
                </span>
              </span>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

export function RestingHrCard({ r, className }: { r: Overview["resting_hr"]; className?: string }) {
  const diff = r.value !== null && r.avg_30d !== null ? r.value - r.avg_30d : null;
  return (
    <Card title="Resting heart rate" className={className}>
      {r.value === null ? (
        <EmptyState title="No resting heart rate for this day" />
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-xs text-ink-3">Today</p>
            <BigValue value={r.value} unit="bpm">
              <Delta value={diff} text={`${signed(diff, 1)} vs 30d`} direction="down-good" />
            </BigValue>
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-line pt-3">
            <MiniStat label="7-day avg" value={fmtNumber(r.avg_7d, 1)} unit="bpm" />
            <MiniStat label="30-day avg" value={fmtNumber(r.avg_30d, 1)} unit="bpm" />
          </div>
        </div>
      )}
    </Card>
  );
}

export function StressCard({ s, className }: { s: Overview["stress"]; className?: string }) {
  return (
    <Card title="Stress" subtitle="Garmin stress level, 0–100" className={className}>
      {s.avg === null ? (
        <EmptyState title="No stress data for this day" />
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-xs text-ink-3">Daily average</p>
            <BigValue value={s.avg}>
              <span className="text-sm text-ink-2">{stressLabel(s.avg)}</span>
            </BigValue>
          </div>
          <div className="relative pt-1">
            <Meter value={s.avg} max={100} />
            {[25, 50, 75].map((p) => (
              <span
                key={p}
                aria-hidden
                className="absolute top-1 h-2 w-0.5 -translate-x-1/2 bg-surface"
                style={{ left: `${p}%` }}
              />
            ))}
            {s.max !== null && (
              <span
                aria-hidden
                className="absolute top-0 h-4 w-0.5 -translate-x-1/2 rounded-full bg-ink-2"
                style={{ left: `${Math.min(s.max, 100)}%` }}
              />
            )}
            <div className="mt-1.5 grid grid-cols-4 text-center text-[11px] text-ink-3" aria-hidden>
              <span>Rest</span>
              <span>Low</span>
              <span>Medium</span>
              <span>High</span>
            </div>
          </div>
          <p className="text-xs text-ink-3">
            Peak <span className="text-ink-2 tabular">{s.max ?? DASH}</span> ·{" "}
            {stressLabel(s.max).toLowerCase()} at its highest
          </p>
        </div>
      )}
    </Card>
  );
}

function GoalRow({
  label,
  value,
  goal,
  unit,
  note,
}: {
  label: string;
  value: number | null;
  goal: number | null;
  unit?: string;
  note?: string;
}) {
  const met = value !== null && goal !== null && goal > 0 && value >= goal;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs text-ink-3">{label}</p>
        {met && (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-2">
            <CircleCheck size={13} color={STATUS.good} aria-hidden /> Goal met
          </span>
        )}
      </div>
      <p className="mt-1 flex items-baseline gap-1">
        <span className="text-xl leading-none font-semibold text-ink">{fmtNumber(value)}</span>
        <span className="text-xs text-ink-3">
          / {fmtNumber(goal)}
          {unit ? ` ${unit}` : ""}
        </span>
        {value !== null && goal ? (
          <span className="ml-auto text-xs text-ink-2 tabular">
            {fmtNumber((value / goal) * 100)} %
          </span>
        ) : null}
      </p>
      <Meter value={value ?? 0} max={goal ?? 0} className="mt-2" />
      {note && <p className="mt-1.5 text-xs text-ink-3">{note}</p>}
    </div>
  );
}

export function GoalsCard({
  steps,
  im,
  className,
}: {
  steps: Overview["steps"];
  im: Overview["intensity_minutes"];
  className?: string;
}) {
  return (
    <Card title="Goals" className={className}>
      <div className="flex flex-col gap-4">
        <GoalRow
          label="Steps today"
          value={steps.value}
          goal={steps.goal}
          note={steps.avg_7d !== null ? `7-day avg ${fmtNumber(steps.avg_7d)}` : undefined}
        />
        <GoalRow
          label="Intensity minutes this week"
          value={im.week_total}
          goal={im.goal}
          unit="min"
        />
      </div>
    </Card>
  );
}
