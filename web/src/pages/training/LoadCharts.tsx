/** Load-side charts of the training page: PMC (fitness/fatigue/form), ACWR, status, load focus. */
import { AlertTriangle, CircleAlert, CircleCheck, CircleMinus } from "lucide-react";
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
import { fmtDate, fmtNumber, fmtShortDate, signed, titleCase } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CATEGORICAL, CHROME, DIVERGING, NEUTRAL, wash, ZONE_RAMP, type Mode } from "@/lib/tokens";
import {
  acwrZone,
  CLASS_ORDER,
  classColor,
  classStatus,
  dayExtent,
  dayMs,
  statusInfo,
  statusKey,
  type StatusClass,
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
    const cat = CATEGORICAL[mode];
    const div = DIVERGING[mode];
    const loadColor = ZONE_RAMP[mode][0]!;
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
          tooltipRow(cat[0]!, "Fitness (CTL)", fmtNumber(d.ctl, 1)) +
          tooltipRow(cat[1]!, "Fatigue (ATL)", fmtNumber(d.atl, 1)) +
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
        {
          ...line(
            "Fitness",
            data.map((d) => [dayMs(d.day), d.ctl]),
            cat[0]!,
            { area: true, z: 3 },
          ),
        },
        line(
          "Fatigue",
          data.map((d) => [dayMs(d.day), d.atl]),
          cat[1]!,
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
          itemStyle: { color: loadColor, borderRadius: [2, 2, 0, 0] },
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
              borderRadius: d.tsb >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2],
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

  const cat = CATEGORICAL[mode];
  return (
    <Card
      className="lg:col-span-2"
      title="Fitness, fatigue & form"
      subtitle={`Fitness is your 42-day load average, fatigue the 7-day one; form is yesterday's fitness minus fatigue.${sportFiltered ? " Load always includes every sport." : ""}`}
    >
      <QueryState
        query={query}
        height={500}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="No training load in this period" />}
      >
        {() => (
          <>
            <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1.5">
              <LegendItem shape="line" color={cat[0]!} label="Fitness (CTL)" />
              <LegendItem shape="line" color={cat[1]!} label="Fatigue (ATL)" />
              <LegendItem color={ZONE_RAMP[mode][0]!} label="Daily load" />
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

/** Acute:chronic workload ratio with the 0.8–1.3 sweet spot and the 1.5 danger line. */
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
          tooltipRow(color, "ACWR", `${fmtNumber(d.acwr, 2)} · ${acwrZone(d.acwr).label}`)
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
            },
            data: [[{ yAxis: 0.8 }, { yAxis: 1.3 }]],
          },
          markLine: refLine(1.5, "Injury risk > 1.5", mode),
        },
      ],
    };
  }, [points, start, end, mode]);
  const zone = latest?.acwr != null ? acwrZone(latest.acwr) : null;
  return (
    <Card
      title="Acute : chronic workload ratio"
      subtitle="Last 7 days of load vs the 28-day average. Ramp up slowly to stay in the band."
      actions={
        zone && latest?.acwr != null ? (
          <StatusPill status={zone.status} label={`${fmtNumber(latest.acwr, 2)} · ${zone.label}`} />
        ) : undefined
      }
    >
      <QueryState
        query={query}
        height={240}
        isEmpty={() => points.length === 0}
        empty={<EmptyState title="Not enough load history for a ratio" />}
      >
        {() => (
          <Chart option={option} height={240} ariaLabel="Acute to chronic workload ratio per day" />
        )}
      </QueryState>
    </Card>
  );
}

const CLASS_ICON = {
  good: CircleCheck,
  neutral: CircleMinus,
  warning: AlertTriangle,
  serious: CircleAlert,
} as const;

function StatusIcon({ cls, mode }: { cls: StatusClass; mode: Mode }) {
  return createElement(CLASS_ICON[cls], {
    size: 14,
    color: classColor(cls, mode),
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

/** Garmin's daily training status as a thin categorical band with a labelled legend. */
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
      .map(([key, days]) => ({ key, days, ...statusInfo(key) }))
      .sort((a, b) => CLASS_ORDER.indexOf(a.cls) - CLASS_ORDER.indexOf(b.cls) || b.days - a.days);
  }, [segs]);
  const total = counts.reduce((s, x) => s + x.days, 0) || 1;
  const latest = segs[segs.length - 1];
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const [x0, x1] = dayExtent(start, end);
    return {
      grid: { left: 14, right: 14, top: 4, bottom: 22, outerBoundsMode: "none" },
      tooltip: itemTooltip((p) => {
        const s = segs[(p as { dataIndex: number }).dataIndex];
        if (!s) return "";
        const info = statusInfo(s.key);
        const span =
          s.start === s.end
            ? fmtShortDate(s.start)
            : `${fmtShortDate(s.start)} – ${fmtDate(s.end)}`;
        return (
          tooltipTitle(info.label) +
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
            CLASS_ORDER.indexOf(statusInfo(s.key).cls),
          ]),
          renderItem: (
            _params: unknown,
            api: { value: (i: number) => number; coord: (v: number[]) => number[] },
          ) => {
            const a = api.coord([api.value(0), 1]);
            const b = api.coord([api.value(1), 0]);
            const cls = CLASS_ORDER[api.value(2)] ?? "neutral";
            return {
              type: "rect",
              shape: {
                x: a[0]!,
                y: a[1]!,
                width: Math.max(b[0]! - a[0]! - 1.5, 1),
                height: b[1]! - a[1]!,
                r: 3,
              },
              style: { fill: classColor(cls, mode) },
            };
          },
        },
      ],
    };
  }, [segs, start, end, mode]);

  const latestInfo = latest ? statusInfo(latest.key) : null;
  return (
    <Card
      className="lg:col-span-2"
      title="Garmin training status"
      subtitle="What your watch concluded each day from load, VO2max trend and recovery"
      actions={
        latestInfo ? (
          <StatusPill status={classStatus(latestInfo.cls)} label={`Now: ${latestInfo.label}`} />
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
                  <StatusIcon cls={s.cls} mode={mode} />
                  <span className="font-medium text-ink">{s.label}</span>
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
  { key: "low_aerobic", label: "Low aerobic", ramp: 0 },
  { key: "high_aerobic", label: "High aerobic", ramp: 2 },
  { key: "anaerobic", label: "Anaerobic", ramp: 4 },
] as const;

function sentence(key: string): string {
  const t = titleCase(key).toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Latest 28-day load per intensity bucket against Garmin's target range (bullet chart). */
export function FocusCard({ query }: { query: Q<StatusPoint[]> }) {
  const mode = useMode();
  const data = query.data ?? NO_STATUS;
  const latest = useMemo(
    () => [...data].reverse().find((d) => d.load_low_aerobic !== null),
    [data],
  );
  const rows = useMemo(
    () =>
      latest
        ? FOCUS.map((f) => ({
            ...f,
            value: (latest[`load_${f.key}`] as number | null) ?? 0,
            lo: latest[`target_${f.key}_min`] as number | null,
            hi: latest[`target_${f.key}_max`] as number | null,
          }))
        : [],
    [latest],
  );
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const max = Math.max(...rows.map((r) => Math.max(r.value, r.hi ?? 0)), 1);
    const verdict = (r: (typeof rows)[number]) =>
      r.lo === null || r.hi === null
        ? ""
        : r.value < r.lo
          ? "below target"
          : r.value > r.hi
            ? "above target"
            : "in target";
    return {
      grid: { left: 4, right: 44, top: 4, bottom: 4 },
      tooltip: itemTooltip((p) => {
        const r = rows[(p as { dataIndex: number }).dataIndex];
        if (!r) return "";
        return (
          tooltipTitle(r.label) +
          tooltipRow(ZONE_RAMP[mode][r.ramp]!, "Last 28 days", fmtNumber(r.value)) +
          (r.lo !== null && r.hi !== null
            ? tooltipRow(
                wash(NEUTRAL[mode], 0.5),
                "Target",
                `${fmtNumber(r.lo)}–${fmtNumber(r.hi)}`,
              ) + `<div style="color:${c.muted};margin-top:4px">${sentence(verdict(r))}</div>`
            : "")
        );
      }),
      xAxis: { type: "value", max: Math.ceil(max * 1.12), splitNumber: 4, show: false },
      yAxis: {
        type: "category",
        inverse: true,
        data: rows.map((r) => r.label),
        axisLine: { show: false },
        axisLabel: {
          formatter: (_v: string, i: number) => {
            const r = rows[i];
            if (!r) return "";
            const target =
              r.lo !== null && r.hi !== null ? `target ${fmtNumber(r.lo)}–${fmtNumber(r.hi)}` : "";
            return `{name|${r.label}}\n{target|${target}}`;
          },
          rich: {
            name: { color: c.text2, fontSize: 12, lineHeight: 17, align: "right" },
            target: { color: c.muted, fontSize: 11, lineHeight: 15, align: "right" },
          },
        },
      },
      series: [
        {
          type: "custom",
          name: "Target range",
          silent: true,
          encode: { y: 0, x: [1, 2] },
          data: rows.map((r, i) => [i, r.lo ?? 0, r.hi ?? 0]),
          renderItem: (
            _params: unknown,
            api: {
              value: (i: number) => number;
              coord: (v: number[]) => number[];
              size: (v: number[]) => number[];
            },
          ) => {
            const a = api.coord([api.value(1), api.value(0)]);
            const b = api.coord([api.value(2), api.value(0)]);
            const h = Math.min((api.size([0, 1])[1] ?? 40) * 0.62, 30);
            return {
              type: "rect",
              shape: { x: a[0]!, y: a[1]! - h / 2, width: b[0]! - a[0]!, height: h, r: 6 },
              style: { fill: wash(NEUTRAL[mode], 0.2), stroke: c.axis, lineWidth: 1 },
            };
          },
          z: 1,
        },
        {
          type: "bar",
          name: "Last 28 days",
          barWidth: 10,
          z: 2,
          data: rows.map((r) => ({
            value: r.value,
            itemStyle: { color: ZONE_RAMP[mode][r.ramp], borderRadius: [0, 4, 4, 0] },
          })),
          label: {
            show: true,
            position: "right",
            color: c.text2,
            fontSize: 11,
            formatter: (p: { value: number }) => fmtNumber(p.value),
          },
        },
      ],
    };
  }, [rows, mode]);

  const feedback = latest?.load_balance_feedback ?? null;
  const balanced = feedback?.toUpperCase().includes("BALANCED") ?? false;
  return (
    <Card
      title="Load focus"
      subtitle={
        latest
          ? `28-day load by intensity on ${fmtDate(latest.day)}, against Garmin's target range`
          : "28-day load by intensity against Garmin's target range"
      }
      actions={
        feedback ? (
          <StatusPill status={balanced ? "good" : "warning"} label={sentence(feedback)} />
        ) : undefined
      }
    >
      <QueryState
        query={query}
        height={236}
        isEmpty={() => !latest}
        empty={<EmptyState title="No load focus reported in this period" />}
      >
        {() => (
          <>
            <Chart
              option={option}
              height={236}
              ariaLabel="Low aerobic, high aerobic and anaerobic load of the last 28 days against their target ranges"
            />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5">
              {FOCUS.map((f) => (
                <LegendItem key={f.key} color={ZONE_RAMP[mode][f.ramp]!} label={f.label} />
              ))}
              <LegendItem color={wash(NEUTRAL[mode], 0.45)} label="Target range" />
            </div>
          </>
        )}
      </QueryState>
    </Card>
  );
}
