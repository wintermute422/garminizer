/** One night: hypnogram plus linked heart rate, SpO₂, respiration and body battery, and facts. */
import { useMemo } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, ErrorState, Skeleton, StatusPill } from "@/components/ui";
import { axisTooltip, line, tooltipRow } from "@/lib/charts";
import { DASH, fmtDate, fmtHours, fmtNumber, signed, titleCase } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { addDays } from "@/lib/range";
import { CHROME, SLEEP_STAGES, type Mode } from "@/lib/tokens";
import { FactRow, Stepper } from "../health/kit";
import {
  HOUR_MS,
  fmtWallTime,
  hrvStatus,
  measureColors,
  sleepQualityStatus,
  smallTitle,
  wallClock,
} from "../health/util";
import { asleep, STAGES } from "./options";

type Detail = Schemas["SleepDetail"];
type Night = Schemas["SleepNight"];
type StageKey = (typeof STAGES)[number]["key"];

const ROWS: StageKey[] = ["deep", "light", "rem", "awake"];
const GRID = { left: 44, right: 12, outerBoundsMode: "none" };

interface RenderApi {
  value: (dim: number) => number;
  coord: (v: number[]) => number[];
  size: (v: number[]) => number[];
}

function extentOf(d: Detail, wall: (iso: string) => number): [number, number] | null {
  const n = d.night;
  if (n.start_utc && n.end_utc) return [wall(n.start_utc), wall(n.end_utc)];
  if (d.stages.length) return [wall(d.stages[0]!.start), wall(d.stages[d.stages.length - 1]!.end)];
  return null;
}

function timeAxis(ext: [number, number], showLabels: boolean): Record<string, unknown> {
  const span = ext[1] - ext[0];
  return {
    type: "time",
    min: ext[0],
    max: ext[1],
    interval: span > 7 * HOUR_MS ? 2 * HOUR_MS : HOUR_MS,
    axisLabel: { show: showLabels, formatter: "{HH}:{mm}", hideOverlap: true },
    splitLine: { show: false },
  };
}

function hypnogramOption(
  d: Detail,
  wall: (iso: string) => number,
  ext: [number, number],
  mode: Mode,
): ChartOption {
  const colors = SLEEP_STAGES[mode];
  const stages = d.stages
    .filter((s) => (ROWS as string[]).includes(s.stage))
    .map((s) => ({
      t0: wall(s.start),
      t1: wall(s.end),
      row: ROWS.indexOf(s.stage as StageKey),
      stage: s.stage as StageKey,
    }));
  const steps: [number, number][] = stages.map((s) => [s.t0, s.row]);
  const lastStage = stages[stages.length - 1];
  if (lastStage) steps.push([lastStage.t1, lastStage.row]);
  const label = (k: StageKey) => STAGES.find((s) => s.key === k)!.label;
  return {
    useUTC: true,
    title: smallTitle("Sleep stages", mode),
    grid: { ...GRID, top: 32, bottom: 6 },
    tooltip: axisTooltip((p) => {
      const arr = (Array.isArray(p) ? p : [p]) as { axisValue?: number; value?: unknown }[];
      const v = arr[0]?.value;
      const x = Array.isArray(v) && typeof v[0] === "number" ? v[0] : arr[0]?.axisValue;
      if (typeof x !== "number") return "";
      const s = stages.find((st) => x >= st.t0 && x < st.t1) ?? stages.find((st) => st.t0 === x);
      if (!s) return "";
      return `<div style="color:${CHROME[mode].muted};margin-bottom:4px">${fmtWallTime(s.t0)}–${fmtWallTime(s.t1)}</div>${tooltipRow(
        colors[s.stage],
        label(s.stage),
        fmtHours((s.t1 - s.t0) / 1000),
      )}`;
    }),
    xAxis: timeAxis(ext, false),
    yAxis: {
      type: "category",
      data: ROWS.map(label),
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { show: true, lineStyle: { color: CHROME[mode].grid } },
    },
    series: [
      {
        type: "line",
        name: "Transitions",
        step: "end",
        data: steps,
        symbol: "none",
        lineStyle: { color: CHROME[mode].axis, width: 1 },
        itemStyle: { color: CHROME[mode].axis },
        z: 1,
      },
      {
        type: "custom",
        name: "Stages",
        data: stages.map((s) => [s.t0, s.t1, s.row]),
        encode: { x: [0, 1], y: 2 },
        z: 2,
        renderItem: (_params: unknown, api: RenderApi) => {
          const row = api.value(2);
          const a = api.coord([api.value(0), row]);
          const b = api.coord([api.value(1), row]);
          const h = Math.abs(api.size([0, 1])[1] ?? 0) * 0.62;
          const stage = ROWS[row] ?? "light";
          return {
            type: "rect",
            shape: {
              x: a[0]!,
              y: a[1]! - h / 2,
              width: Math.max(b[0]! - a[0]!, 1),
              height: h,
              r: 2,
            },
            style: { fill: colors[stage] },
          };
        },
      },
    ],
  };
}

/**
 * Samples that belong to the night: inside [bed, wake) and not during an activity (a run that
 * starts as the watch still scores sleep would otherwise spike HR at the right edge). The two
 * minutes before an activity are dropped too: a sample summarises the minutes after its stamp.
 */
function sleepSamples(
  points: Schemas["SleepPoint"][],
  night: Night,
  busy: [number, number][],
): Schemas["SleepPoint"][] {
  const t0 = night.start_utc ? Date.parse(night.start_utc) : -Infinity;
  const t1 = night.end_utc ? Date.parse(night.end_utc) : Infinity;
  return points.filter((p) => {
    const t = Date.parse(p.ts);
    return t >= t0 && t < t1 && !busy.some(([a, b]) => t >= a - 2 * 60_000 && t <= b);
  });
}

/** SpO₂ axis that never runs past 100 %: steps of 5 (or 10 for wide ranges) down from 100. */
function spo2Axis(points: Schemas["SleepPoint"][]): Record<string, unknown> {
  const v = points.map((p) => p.value).filter((x): x is number => x != null);
  const lo = v.length ? Math.min(...v) : 90;
  const span = 100 - Math.floor(lo) + 1;
  const interval = span <= 12 ? 5 : 10;
  return { min: 100 - interval * Math.ceil(span / interval), max: 100, interval };
}

interface Trace {
  key: string;
  label: string;
  unit: string;
  color: string;
  digits: number;
  points: Schemas["SleepPoint"][];
}

function traceOption(
  t: Trace,
  wall: (iso: string) => number,
  ext: [number, number],
  mode: Mode,
  last: boolean,
): ChartOption {
  const fmt = (v: number) => fmtNumber(v, t.digits);
  return {
    useUTC: true,
    title: smallTitle(`${t.label} (${t.unit})`, mode),
    // Top padding keeps the panel title clear of the first tick label.
    grid: { ...GRID, top: 32, bottom: last ? 24 : 6 },
    tooltip: axisTooltip((p) => {
      const arr = p as { value: [number, number | null] }[];
      const v = arr[0]?.value;
      if (!v) return "";
      return `<div style="color:${CHROME[mode].muted};margin-bottom:4px">${fmtWallTime(v[0])}</div>${tooltipRow(
        t.color,
        t.label,
        v[1] == null ? DASH : `${fmt(v[1])} ${t.unit}`,
      )}`;
    }),
    xAxis: timeAxis(ext, last),
    yAxis: {
      type: "value",
      scale: true,
      splitNumber: 2,
      axisLabel: { formatter: (v: number) => fmtNumber(v) },
      ...(t.key === "spo2" ? spo2Axis(t.points) : {}),
    },
    series: [
      {
        ...line(
          t.label,
          t.points.map((p) => [wall(p.ts), p.value]),
          t.color,
          { area: t.key === "bb" },
        ),
        connectNulls: true,
      },
    ],
  };
}

function StageBreakdown({ n, mode }: { n: Night; mode: Mode }) {
  const colors = SLEEP_STAGES[mode];
  const total = STAGES.reduce((s, st) => s + (n[st.field] ?? 0), 0);
  if (!total) return null;
  return (
    <div>
      <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full" aria-hidden>
        {STAGES.map((s) => {
          const v = n[s.field] ?? 0;
          return v > 0 ? (
            <span
              key={s.key}
              style={{ width: `${(v / total) * 100}%`, background: colors[s.key] }}
            />
          ) : null;
        })}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
        {STAGES.map((s) => {
          const v = n[s.field];
          return (
            <div key={s.key} className="flex items-baseline justify-between gap-2 text-sm">
              <dt className="inline-flex items-center gap-1.5 text-ink-2">
                <span
                  className="inline-block size-2.5 rounded-[3px]"
                  style={{ background: colors[s.key] }}
                  aria-hidden
                />
                {s.label}
              </dt>
              <dd className="font-medium text-ink tabular">
                {fmtHours(v)}
                <span className="ml-1 text-xs font-normal text-ink-3">
                  {v == null ? "" : `${fmtNumber((v / total) * 100)} %`}
                </span>
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

function feedbackText(f: string | null): string | null {
  if (!f) return null;
  const words = f.toLowerCase().split("_");
  const s = words.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function Facts({ n, wall }: { n: Night; wall: (iso: string) => number }) {
  const mode = useMode();
  const quality = n.score_quality;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-ink-2">Sleep score</p>
          <p className="mt-1 text-[40px] leading-none font-semibold text-ink">{n.score ?? DASH}</p>
        </div>
        {quality && <StatusPill status={sleepQualityStatus(quality)} label={titleCase(quality)} />}
      </div>
      {feedbackText(n.feedback) && <p className="text-xs text-ink-3">{feedbackText(n.feedback)}</p>}
      <StageBreakdown n={n} mode={mode} />
      <div className="divide-y divide-line border-t border-line">
        <FactRow
          label="In bed"
          value={
            n.start_utc && n.end_utc
              ? `${fmtWallTime(wall(n.start_utc))} → ${fmtWallTime(wall(n.end_utc))}`
              : DASH
          }
        />
        <FactRow
          label="Asleep"
          value={fmtHours(asleep(n))}
          sub={n.sleep_need_min ? `need ${fmtHours(n.sleep_need_min * 60)}` : undefined}
        />
        <FactRow
          label="Heart rate"
          value={n.avg_hr != null ? `${fmtNumber(n.avg_hr)} bpm` : DASH}
          sub={n.lowest_hr != null ? `lowest ${n.lowest_hr}` : undefined}
        />
        <FactRow
          label={
            <span className="inline-flex items-center gap-2">
              Overnight HRV
              {n.hrv_status && (
                <StatusPill status={hrvStatus(n.hrv_status)} label={titleCase(n.hrv_status)} />
              )}
            </span>
          }
          value={n.avg_overnight_hrv != null ? `${fmtNumber(n.avg_overnight_hrv)} ms` : DASH}
        />
        <FactRow
          label="Respiration"
          value={n.avg_respiration != null ? `${fmtNumber(n.avg_respiration, 1)} brpm` : DASH}
          sub={
            n.lowest_respiration != null && n.highest_respiration != null
              ? `${fmtNumber(n.lowest_respiration)}–${fmtNumber(n.highest_respiration)}`
              : undefined
          }
        />
        <FactRow
          label="Blood oxygen"
          value={n.avg_spo2 != null ? `${fmtNumber(n.avg_spo2, 1)} %` : DASH}
          sub={n.lowest_spo2 != null ? `lowest ${fmtNumber(n.lowest_spo2)} %` : undefined}
        />
        <FactRow
          label="Body battery"
          value={n.body_battery_change != null ? signed(n.body_battery_change) : DASH}
        />
        <FactRow
          label="Awakenings · restless moments"
          value={`${n.awake_count ?? DASH} · ${n.restless_moments ?? DASH}`}
        />
        <FactRow
          label="Stress while asleep"
          value={n.avg_stress != null ? fmtNumber(n.avg_stress) : DASH}
        />
      </div>
    </div>
  );
}

export function NightDetail({
  day,
  nights,
  onPick,
  timeZone,
}: {
  day: string;
  nights: Night[];
  onPick: (day: string) => void;
  timeZone: string | null | undefined;
}) {
  const mode = useMode();
  const q = api.useQuery(
    "get",
    "/api/sleep/{day}",
    { params: { path: { day } } },
    { placeholderData: (prev) => prev },
  );
  const wall = useMemo(() => wallClock(timeZone), [timeZone]);
  const idx = nights.findIndex((n) => n.day === day);
  const prev = idx > 0 ? nights[idx - 1]!.day : null;
  const next = idx >= 0 && idx < nights.length - 1 ? nights[idx + 1]!.day : null;
  const col = measureColors(mode);
  // Activities around this night (local days before and of waking), to mask their samples.
  const acts = api.useQuery("get", "/api/activities", {
    params: { query: { start: addDays(day, -1), end: day, limit: 20 } },
  });

  const charts = useMemo(() => {
    const d = q.data;
    if (!d) return null;
    const ext = extentOf(d, wall);
    if (!ext) return null;
    const busy: [number, number][] = (acts.data?.items ?? []).map((a) => {
      const t = Date.parse(a.start_time_utc);
      return [t, t + (a.duration_s ?? 0) * 1000];
    });
    const own = (points: Schemas["SleepPoint"][]) => sleepSamples(points, d.night, busy);
    const traces: Trace[] = [
      { key: "hr", label: "Heart rate", unit: "bpm", color: col.hr, digits: 0, points: own(d.hr) },
      {
        key: "spo2",
        label: "Blood oxygen",
        unit: "%",
        color: col.spo2,
        digits: 0,
        points: own(d.spo2),
      },
      {
        key: "resp",
        label: "Respiration",
        unit: "brpm",
        color: col.respiration,
        digits: 1,
        points: own(d.respiration),
      },
      {
        key: "bb",
        label: "Body battery",
        unit: "0–100",
        color: col.bodyBattery,
        digits: 0,
        points: own(d.body_battery),
      },
    ].filter((t) => t.points.some((p) => p.value != null));
    return {
      hypnogram: d.stages.length ? hypnogramOption(d, wall, ext, mode) : null,
      traces: traces.map((t, i) => ({
        t,
        option: traceOption(t, wall, ext, mode, i === traces.length - 1),
      })),
    };
  }, [q.data, acts.data, wall, mode, col.hr, col.spo2, col.respiration, col.bodyBattery]);

  return (
    <Card
      id="night-detail"
      title={fmtDate(day, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
      subtitle="Night ending on this morning · pick a night or click a bar above"
      className="lg:col-span-2"
      actions={
        <Stepper
          label=""
          onPrev={prev ? () => onPick(prev) : null}
          onNext={next ? () => onPick(next) : null}
          prevLabel="Previous night"
          nextLabel="Next night"
        >
          <label className="sr-only" htmlFor="night-select">
            Night
          </label>
          <select
            id="night-select"
            value={day}
            onChange={(e) => onPick(e.target.value)}
            className="rounded-lg border border-line bg-surface-2 px-2 py-1 text-sm text-ink"
          >
            {[...nights].reverse().map((n) => (
              <option key={n.day} value={n.day}>
                {fmtDate(n.day, {
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })}
                {n.score != null ? ` · ${n.score}` : ""}
              </option>
            ))}
          </select>
        </Stepper>
      }
    >
      {q.error ? (
        <ErrorState error={q.error} />
      ) : !q.data ? (
        <Skeleton height={520} />
      ) : (
        <div
          className="grid gap-6 lg:grid-cols-3"
          style={{ opacity: q.isPlaceholderData ? 0.6 : 1 }}
        >
          <div className="flex min-w-0 flex-col gap-1 lg:col-span-2">
            {charts?.hypnogram ? (
              <Chart
                option={charts.hypnogram}
                height={176}
                group="sleep-night"
                ariaLabel="Hypnogram: sleep stage over the night"
              />
            ) : (
              <EmptyState title="No sleep stages recorded for this night" />
            )}
            {charts?.traces.map(({ t, option }, i) => (
              <Chart
                key={t.key}
                option={option}
                height={i === charts.traces.length - 1 ? 136 : 112}
                group="sleep-night"
                ariaLabel={`${t.label} during the night`}
              />
            ))}
          </div>
          <Facts n={q.data.night} wall={wall} />
        </div>
      )}
    </Card>
  );
}
