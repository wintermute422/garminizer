/** Load-side charts of the training page: PMC (fitness/fatigue/form), ACWR, status, load focus. */
import {
  AlertTriangle,
  CircleAlert,
  CircleCheck,
  CircleMinus,
  OctagonAlert,
  type LucideIcon,
} from "lucide-react";
import { createElement, useMemo } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, LegendItem, QueryState, StatusPill } from "@/components/ui";
import {
  axisTooltip,
  GRID,
  itemTooltip,
  line,
  refLine,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import { fmtDate, fmtNumber, signed } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import {
  CATEGORICAL,
  CHROME,
  DIVERGING,
  MEASURE_COLORS,
  NEUTRAL,
  STATUS,
  wash,
  ZONE_RAMP,
  type Mode,
  type Status,
  barEnd,
} from "@/lib/tokens";
import { loadBalanceState, trainingState } from "@/lib/status";
import {
  acwrZone,
  dayExtent,
  dayMs,
  halo,
  statusIconSvg,
  statusKey,
  statusLabel,
  statusRank,
  statusSwatch,
} from "./util";

type LoadPoint = Schemas["TrainingLoadPoint"];
type StatusPoint = Schemas["TrainingStatusPoint"];
type Obj = Record<string, unknown>;
/** The slice of a query result the cards need (loading / error / data). */
export type Q<T> = { data?: T; isPending: boolean; error: unknown };
const NO_LOAD: LoadPoint[] = [];
const NO_STATUS: StatusPoint[] = [];

const PMC_GROUP = "training-pmc";
/** Fixed plot insets so the three linked PMC charts share one x scale pixel for pixel. */
const PMC_LEFT = 44;
const PMC_RIGHT = 16;

function subTitle(text: string, mode: Mode): Obj {
  return {
    text,
    left: 0,
    top: 0,
    textStyle: { fontSize: 12, fontWeight: 500, color: CHROME[mode].text2 },
  };
}

function timeAxis(extent: [number, number], showLabels: boolean): Obj {
  return {
    type: "time",
    min: extent[0],
    max: extent[1],
    splitLine: { show: false },
    axisLabel: { show: showLabels, hideOverlap: true },
  };
}

/** Axis bounds on a round step that yields about four intervals (fixed, so labels never crowd). */
function niceBounds(lo: number, hi: number): { min: number; max: number; interval: number } {
  const raw = (hi - lo) / 4;
  const interval = [5, 10, 20, 25, 30, 50, 100].find((s) => s >= raw) ?? Math.ceil(raw / 100) * 100;
  return {
    min: Math.floor(lo / interval) * interval,
    max: Math.ceil(hi / interval) * interval,
    interval,
  };
}

/** Reference line whose label sits on a surface-coloured halo (legible over data). */
function haloLine(value: number, label: string, mode: Mode, axis: "y" | "x" = "y"): Obj {
  const base = refLine(value, label, mode, axis);
  return { ...base, label: { ...(base.label as Obj), ...halo(mode) } };
}

const longDay = (iso: string) =>
  fmtDate(iso, { weekday: "short", day: "numeric", month: "short", year: "numeric" });

/** Fitness (CTL) and fatigue (ATL) lines, daily load bars and form (TSB), crosshair-linked. */
export function PmcCard({
  query,
  start,
  end,
  sportFiltered,
}: {
  query: Q<LoadPoint[]>;
  start: string;
  end: string;
  sportFiltered: boolean;
}) {
  const mode = useMode();
  const data = query.data ?? NO_LOAD;
  const options = useMemo(() => {
    const c = CHROME[mode];
    const m = MEASURE_COLORS[mode];
    const div = DIVERGING[mode];
    const loadColor = NEUTRAL[mode];
    const extent = dayExtent(start, end);
    const grid = (bottom: number) => ({
      left: PMC_LEFT,
      right: PMC_RIGHT,
      top: 26,
      bottom,
      outerBoundsMode: "none",
    });
    const passive = { trigger: "axis", showContent: false, axisPointer: { type: "line" } };

    const fitness: ChartOption = {
      grid: grid(6),
      title: subTitle("Fitness & fatigue", mode),
      tooltip: axisTooltip((p) => {
        const i = (p as { dataIndex: number }[])[0]?.dataIndex ?? -1;
        const d = data[i];
        if (!d) return "";
        return (
          tooltipTitle(longDay(d.day)) +
          tooltipRow(m.fitness, "Fitness (CTL)", fmtNumber(d.ctl, 1)) +
          tooltipRow(m.fatigue, "Fatigue (ATL)", fmtNumber(d.atl, 1)) +
          tooltipRow(d.tsb >= 0 ? div.negative : div.positive, "Form (TSB)", signed(d.tsb, 1)) +
          tooltipRow(
            loadColor,
            "Load",
            d.activities
              ? `${fmtNumber(d.load)} · ${d.activities} ${d.activities === 1 ? "activity" : "activities"}`
              : "rest day",
          )
        );
      }),
      xAxis: timeAxis(extent, false),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v), { scale: true }),
      series: [
        line(
          "Fitness",
          data.map((d) => [dayMs(d.day), d.ctl]),
          m.fitness,
          { area: true, z: 3 },
        ),
        line(
          "Fatigue",
          data.map((d) => [dayMs(d.day), d.atl]),
          m.fatigue,
        ),
      ],
    };
    const tsb = data.map((d) => d.tsb);
    const formAxis = niceBounds(Math.min(...tsb, -32), Math.max(...tsb, 12));

    const load: ChartOption = {
      grid: grid(2),
      title: subTitle("Daily load", mode),
      tooltip: passive,
      xAxis: timeAxis(extent, false),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v), { splitNumber: 2 }),
      series: [
        {
          type: "bar",
          name: "Daily load",
          data: data.map((d) => [dayMs(d.day), d.load]),
          barMaxWidth: 12,
          itemStyle: { color: loadColor, borderRadius: barEnd("up") },
        },
      ],
    };

    const form: ChartOption = {
      grid: grid(24),
      title: subTitle("Form", mode),
      tooltip: passive,
      xAxis: timeAxis(extent, true),
      yAxis: valueYAxis(undefined, (v) => signed(v), formAxis),
      series: [
        {
          type: "bar",
          name: "Form",
          barMaxWidth: 12,
          data: data.map((d) => ({
            value: [dayMs(d.day), d.tsb],
            itemStyle: {
              color: d.tsb >= 0 ? div.negative : div.positive,
              borderRadius: barEnd(d.tsb >= 0 ? "up" : "down"),
            },
          })),
          markArea: {
            silent: true,
            itemStyle: { color: wash(NEUTRAL[mode], 0.14) },
            data: [[{ yAxis: -30 }, { yAxis: -10 }]],
          },
          markLine: {
            silent: true,
            symbol: "none",
            label: { show: false },
            lineStyle: { color: c.muted, width: 1, type: "solid" },
            data: [{ yAxis: 0 }],
          },
        },
      ],
    };
    return { fitness, load, form };
  }, [data, start, end, mode]);

  const m = MEASURE_COLORS[mode];
  return (
    <Card
      className="lg:col-span-2"
      title="Fitness, fatigue & form"
      subtitle={`Fitness (CTL) and fatigue (ATL) are exponentially weighted load averages with 42- and 7-day time constants; form (TSB) is yesterday's fitness minus fatigue.${sportFiltered ? " Load always includes every sport." : ""}`}
    >
      <QueryState
        query={query}
        height={520}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="No training load in this period" />}
      >
        {() => (
          <>
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1.5">
              <LegendItem shape="line" color={m.fitness} label="Fitness (CTL)" />
              <LegendItem shape="line" color={m.fatigue} label="Fatigue (ATL)" />
              <LegendItem color={NEUTRAL[mode]} label="Daily load" />
              <LegendItem color={DIVERGING[mode].negative} label="Fresh (form > 0)" />
              <LegendItem color={DIVERGING[mode].positive} label="Tired (form < 0)" />
              <LegendItem color={wash(NEUTRAL[mode], 0.45)} label="Productive range (−10 to −30)" />
            </div>
            <div className="flex flex-col gap-1">
              <Chart
                option={options.fitness}
                height={230}
                group={PMC_GROUP}
                ariaLabel="Fitness (CTL) and fatigue (ATL) per day"
              />
              <Chart
                option={options.load}
                height={96}
                group={PMC_GROUP}
                ariaLabel="Daily training load"
              />
              <Chart
                option={options.form}
                height={170}
                group={PMC_GROUP}
                ariaLabel="Form (TSB) per day: positive is fresh, negative is tired"
              />
            </div>
          </>
        )}
      </QueryState>
    </Card>
  );
}

/** Garminizer's own rolling ACWR with the 0.8–1.3 sweet spot and the 1.5 danger line. */
export function AcwrCard({
  query,
  start,
  end,
}: {
  query: Q<LoadPoint[]>;
  start: string;
  end: string;
}) {
  const mode = useMode();
  const data = query.data ?? NO_LOAD;
  const points = useMemo(() => data.filter((d) => d.acwr !== null), [data]);
  const latest = points[points.length - 1];
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const color = CATEGORICAL[mode][0]!;
    return {
      grid: { ...GRID, top: 14, right: 16 },
      tooltip: axisTooltip((p) => {
        const i = (p as { dataIndex: number }[])[0]?.dataIndex ?? -1;
        const d = points[i];
        if (!d || d.acwr === null) return "";
        return (
          tooltipTitle(longDay(d.day)) +
          tooltipRow(color, "ACWR (rolling)", `${fmtNumber(d.acwr, 2)} · ${acwrZone(d.acwr).label}`)
        );
      }),
      xAxis: timeAxis(dayExtent(start, end), true),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v, 1), {
        min: (v: { min: number }) => Math.min(0.6, Math.floor(v.min * 10) / 10),
        max: (v: { max: number }) => Math.max(1.7, Math.ceil(v.max * 10) / 10),
      }),
      series: [
        {
          ...line(
            "ACWR",
            points.map((d) => [dayMs(d.day), d.acwr]),
            color,
          ),
          markArea: {
            silent: true,
            itemStyle: { color: wash(NEUTRAL[mode], 0.16) },
            label: {
              show: true,
              position: "insideTopLeft",
              color: c.muted,
              fontSize: 11,
              formatter: "Optimal 0.8–1.3",
              ...halo(mode),
            },
            data: [[{ yAxis: 0.8 }, { yAxis: 1.3 }]],
          },
          markLine: haloLine(1.5, "Injury risk > 1.5", mode),
        },
      ],
    };
  }, [points, start, end, mode]);
  return (
    <Card
      title="ACWR · 7/28-day rolling (Garminizer)"
      subtitle={`Garminizer's ratio of the last 7 days of load to the 28-day average${
        latest?.acwr != null ? ` (now ${fmtNumber(latest.acwr, 2)})` : ""
      }. Ramp up slowly to stay in the band.`}
    >
      <QueryState
        query={query}
        height={240}
        isEmpty={() => points.length === 0}
        empty={<EmptyState title="Not enough load history for a ratio" />}
      >
        {() => (
          <Chart
            option={option}
            height={240}
            ariaLabel="Garminizer's rolling 7 to 28 day workload ratio per day"
          />
        )}
      </QueryState>
    </Card>
  );
}

const STATUS_ICON: Record<Status | "neutral", LucideIcon> = {
  good: CircleCheck,
  neutral: CircleMinus,
  warning: AlertTriangle,
  serious: CircleAlert,
  critical: OctagonAlert,
};

function StatusIcon({ status }: { status: Status | null }) {
  return createElement(STATUS_ICON[status ?? "neutral"], {
    size: 13,
    color: status ? STATUS[status] : "var(--text-muted)",
    "aria-hidden": true,
  });
}

interface Segment {
  key: string;
  start: string;
  end: string;
  days: number;
}

/** Consecutive days with the same status → one segment. */
function segments(data: StatusPoint[]): Segment[] {
  const out: Segment[] = [];
  for (const d of data) {
    const key = statusKey(d.status);
    if (!key) continue;
    const last = out[out.length - 1];
    const prevDay = last ? new Date(`${last.end}T12:00:00`) : null;
    if (prevDay) prevDay.setDate(prevDay.getDate() + 1);
    const contiguous =
      last && prevDay && prevDay.getTime() === new Date(`${d.day}T12:00:00`).getTime();
    if (last && last.key === key && contiguous) {
      last.end = d.day;
      last.days += 1;
    } else {
      out.push({ key, start: d.day, end: d.day, days: 1 });
    }
  }
  return out;
}

/** Garmin's daily training status as a strip: one swatch colour per status, labelled legend. */
export function StatusCard({
  query,
  start,
  end,
}: {
  query: Q<StatusPoint[]>;
  start: string;
  end: string;
}) {
  const mode = useMode();
  const data = query.data ?? NO_STATUS;
  const segs = useMemo(() => segments(data), [data]);
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of segs) m.set(s.key, (m.get(s.key) ?? 0) + s.days);
    return [...m.entries()]
      .map(([key, days]) => ({ key, days }))
      .sort((a, b) => statusRank(a.key) - statusRank(b.key));
  }, [segs]);
  const total = counts.reduce((s, x) => s + x.days, 0) || 1;
  const latest = segs[segs.length - 1];
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const [x0, x1] = dayExtent(start, end);
    const keys = [...new Set(segs.map((s) => s.key))];
    return {
      grid: { left: 14, right: 14, top: 4, bottom: 22, outerBoundsMode: "none" },
      tooltip: itemTooltip((p) => {
        const s = segs[(p as { dataIndex: number }).dataIndex];
        if (!s) return "";
        const span =
          s.start === s.end ? fmtDate(s.start) : `${fmtDate(s.start)} – ${fmtDate(s.end)}`;
        return (
          `<div style="display:flex;align-items:center;gap:6px;font-weight:600;margin-bottom:4px"><span style="width:10px;height:10px;border-radius:3px;background:${statusSwatch(s.key, mode)};display:inline-block"></span>${statusIconSvg(trainingState(s.key).status, mode)}${statusLabel(s.key)}</div>` +
          `<div style="color:${c.muted}">${span} · ${s.days} ${s.days === 1 ? "day" : "days"}</div>`
        );
      }),
      xAxis: {
        type: "time",
        min: x0,
        max: x1,
        splitLine: { show: false },
        axisLine: { show: false },
        axisLabel: { hideOverlap: true },
      },
      yAxis: { type: "value", min: 0, max: 1, show: false },
      series: [
        {
          type: "custom",
          name: "Training status",
          encode: { x: [0, 1] },
          data: segs.map((s) => [
            new Date(`${s.start}T00:00:00`).getTime(),
            new Date(`${s.end}T00:00:00`).getTime() + 86_400_000,
            keys.indexOf(s.key),
          ]),
          renderItem: (
            _params: unknown,
            api: { value: (i: number) => number; coord: (v: number[]) => number[] },
          ) => {
            const a = api.coord([api.value(0), 1]);
            const b = api.coord([api.value(1), 0]);
            const key = keys[api.value(2)] ?? "";
            return {
              type: "rect",
              shape: {
                x: a[0]!,
                y: a[1]!,
                width: Math.max(b[0]! - a[0]! - 1.5, 1),
                height: b[1]! - a[1]!,
                r: 3,
              },
              style: { fill: statusSwatch(key, mode) },
            };
          },
        },
      ],
    };
  }, [segs, start, end, mode]);

  const now = latest ? trainingState(latest.key) : null;
  return (
    <Card
      className="lg:col-span-2"
      title="Garmin training status"
      subtitle="What your watch concluded each day from load, VO2max trend and recovery"
      actions={
        latest && now ? (
          <StatusPill status={now.status} label={`Now: ${statusLabel(latest.key)}`} />
        ) : undefined
      }
    >
      <QueryState
        query={query}
        height={90}
        isEmpty={() => segs.length === 0}
        empty={<EmptyState title="No training status reported in this period" />}
      >
        {() => (
          <>
            <Chart option={option} height={58} ariaLabel="Garmin training status per day" />
            <ul
              className="mt-3 flex flex-wrap gap-x-5 gap-y-2"
              aria-label="Days per training status"
            >
              {counts.map((s) => (
                <li key={s.key} className="inline-flex items-center gap-1.5 text-xs text-ink-2">
                  <span
                    aria-hidden
                    className="inline-block size-2.5 rounded-swatch"
                    style={{ background: statusSwatch(s.key, mode) }}
                  />
                  <StatusIcon status={trainingState(s.key).status} />
                  <span className="font-medium text-ink">{statusLabel(s.key)}</span>
                  <span className="tabular">
                    {s.days} d · {fmtNumber((s.days / total) * 100)} %
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </QueryState>
    </Card>
  );
}

const FOCUS = [
  { key: "low_aerobic", label: "Low aerobic", ramp: 1 },
  { key: "high_aerobic", label: "High aerobic", ramp: 3 },
  { key: "anaerobic", label: "Anaerobic", ramp: 4 },
] as const;

/** One bullet row, styled like the Overview's load focus: dashed outline = target range. */
function FocusRow({
  label,
  value,
  min,
  max,
  scale,
  color,
}: {
  label: string;
  value: number;
  min: number | null;
  max: number | null;
  scale: number;
  color: string;
}) {
  const pct = (v: number) => `${Math.min(v / scale, 1) * 100}%`;
  const verdict =
    min === null || max === null
      ? null
      : value < min
        ? "Below target"
        : value > max
          ? "Above target"
          : "In target";
  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-2 text-xs">
        <span className="font-medium text-ink-2">
          {label}
          {min !== null && max !== null && (
            <span className="ml-1.5 font-normal text-ink-3 tabular">
              target {fmtNumber(min)}–{fmtNumber(max)}
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          {verdict && (
            <span className="inline-flex items-center gap-1 text-ink-3">
              {verdict === "In target" && <CircleCheck size={13} color={STATUS.good} aria-hidden />}
              {verdict}
            </span>
          )}
          <span className="font-semibold text-ink tabular">{fmtNumber(value)}</span>
        </span>
      </div>
      <div aria-hidden className="relative h-3.5 rounded-bar bg-surface-2">
        {min !== null && max !== null && (
          <div
            className="absolute inset-y-0 rounded-bar border border-dashed border-ink-3/70 bg-surface-3/60"
            style={{ left: pct(min), width: `calc(${pct(max)} - ${pct(min)})` }}
          />
        )}
        <div
          className="absolute top-1/2 left-0 h-2 -translate-y-1/2 rounded-bar"
          style={{ width: pct(value), background: color }}
        />
      </div>
    </div>
  );
}

/** Latest 28-day load per intensity bucket against Garmin's target range. */
export function FocusCard({ query }: { query: Q<StatusPoint[]> }) {
  const mode = useMode();
  const data = query.data ?? NO_STATUS;
  const latest = useMemo(
    () => [...data].reverse().find((d) => d.load_low_aerobic !== null),
    [data],
  );
  const rows = latest
    ? FOCUS.map((f) => ({
        ...f,
        value: (latest[`load_${f.key}`] as number | null) ?? 0,
        min: latest[`target_${f.key}_min`] as number | null,
        max: latest[`target_${f.key}_max`] as number | null,
      }))
    : [];
  const scale = Math.max(1, ...rows.flatMap((r) => [r.value, r.max ?? 0])) * 1.08;
  const balance = loadBalanceState(latest?.load_balance_feedback);
  return (
    <Card
      title="Load focus"
      subtitle={
        latest
          ? `Last 4 weeks to ${fmtDate(latest.day)} · dashed = Garmin's target range`
          : "Last 4 weeks · dashed = Garmin's target range"
      }
      actions={
        latest?.load_balance_feedback ? (
          <StatusPill status={balance.status} label={balance.label} />
        ) : undefined
      }
    >
      <QueryState
        query={query}
        height={200}
        isEmpty={() => !latest}
        empty={<EmptyState title="No load focus reported in this period" />}
      >
        {() => (
          <div
            className="flex flex-col gap-5 pt-2"
            role="img"
            aria-label={rows
              .map(
                (r) =>
                  `${r.label} ${fmtNumber(r.value)}${r.min !== null && r.max !== null ? `, target ${fmtNumber(r.min)} to ${fmtNumber(r.max)}` : ""}`,
              )
              .join("; ")}
          >
            {rows.map((r) => (
              <FocusRow
                key={r.key}
                label={r.label}
                value={r.value}
                min={r.min}
                max={r.max}
                scale={scale}
                color={ZONE_RAMP[mode][r.ramp]!}
              />
            ))}
            <p className="text-xs text-ink-3">
              Low aerobic builds the base, high aerobic raises threshold and VO2max, anaerobic
              sharpens speed. Garmin sets the targets from your recent load.
            </p>
          </div>
        )}
      </QueryState>
    </Card>
  );
}
