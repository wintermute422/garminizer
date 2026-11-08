/** ECharts options for the daily health charts (one measure per chart, one y-axis each). */
import type { Schemas } from "@/api/client";
import type { ChartOption } from "@/components/Chart";
import {
  axisTooltip,
  bars,
  dayPoint,
  GRID_WITH_LEGEND,
  legend,
  line,
  scatter,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import {
  DASH,
  fmtCompact,
  fmtDate,
  fmtDistance,
  fmtHours,
  fmtNumber,
  smooth,
  titleCase,
} from "@/lib/format";
import type { UnitSystem } from "@/lib/format";
import { CHROME, STATUS, STRESS_LEVELS, wash, type Mode } from "@/lib/tokens";
import {
  cased,
  DAY_MS,
  dotSize,
  dotStyle,
  legendItems,
  dayAxis,
  measureColors,
  rangeBars,
  readinessStatus,
  roundVisibleTops,
  tooltipMuted,
  weekly,
} from "./util";

type Day = Schemas["WellnessDay"];
type Readiness = Schemas["WellnessReadiness"];
type Obj = Record<string, unknown>;
interface AxisParam {
  value?: unknown;
  axisValue?: number;
}

export interface Extent {
  min: number;
  max: number;
}

/** x extent of a day range with half a day of padding (bars at noon are not clipped). */
export function dayExtent(start: string, end: string): Extent {
  return { min: dayPoint(start, 0)[0] - DAY_MS / 2, max: dayPoint(end, 0)[0] + DAY_MS / 2 };
}

function dateTitle(day: string): string {
  return tooltipTitle(
    fmtDate(day, { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
  );
}

/** Look up the hovered row from axis-tooltip params (x of the first array-valued point). */
function rowAt<T>(params: unknown, byTime: Map<number, T>): T | undefined {
  const arr = (Array.isArray(params) ? params : [params]) as AxisParam[];
  for (const p of arr) {
    const v = p.value;
    if (Array.isArray(v) && typeof v[0] === "number") {
      const hit = byTime.get(v[0]);
      if (hit) return hit;
    }
  }
  const x = arr[0]?.axisValue;
  return typeof x === "number" ? byTime.get(x) : undefined;
}

function indexByDay<T extends { day: string }>(rows: readonly T[]): Map<number, T> {
  return new Map(rows.map((r) => [dayPoint(r.day, 0)[0], r]));
}

function timeAxis(ext: Extent, extra: Obj = {}): Obj {
  return { ...dayAxis(ext.min, ext.max), ...extra };
}

function endLabel(mode: Mode, fmt: (v: number) => string): Obj {
  return {
    show: true,
    color: CHROME[mode].text2,
    fontSize: 11,
    distance: 6,
    formatter: (p: { value: [number, number | null] }) =>
      p.value[1] == null ? "" : fmt(p.value[1]),
  };
}

const n0 = (v: number) => fmtNumber(v);
const n1 = (v: number) => fmtNumber(v, 1);

// ---------------------------------------------------------------- resting HR

export function restingHrOption(rows: Day[], mode: Mode, ext: Extent): ChartOption {
  const col = measureColors(mode);
  const byTime = indexByDay(rows);
  const mean7 = smooth(
    rows.map((r) => r.resting_hr),
    7,
  );
  const daily = rows.filter((r) => r.resting_hr != null).map((r) => dayPoint(r.day, r.resting_hr));
  return {
    grid: { ...GRID_WITH_LEGEND, right: 34 },
    legend: {
      ...legend(),
      data: legendItems([
        ["Daily", "dot"],
        ["7-day mean", "line"],
      ]),
    },
    tooltip: axisTooltip((p) => {
      const r = rowAt(p, byTime);
      if (!r) return "";
      const i = rows.indexOf(r);
      return (
        dateTitle(r.day) +
        tooltipRow(col.hr, "Resting HR", r.resting_hr == null ? DASH : `${r.resting_hr} bpm`) +
        tooltipRow(col.hr, "7-day mean", mean7[i] == null ? DASH : `${n1(mean7[i]!)} bpm`) +
        tooltipMuted("Min · max HR", `${r.min_hr ?? DASH} · ${r.max_hr ?? DASH} bpm`, mode)
      );
    }),
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, undefined, { scale: true, minInterval: 1 }),
    series: [
      {
        ...scatter("Daily", daily, col.hr, dotSize(rows.length)),
        itemStyle: dotStyle(col.hr, mode),
      },
      ...cased(
        {
          ...line(
            "7-day mean",
            rows.map((r, i) => [dayPoint(r.day, 0)[0], mean7[i]]),
            col.hr,
          ),
          endLabel: endLabel(mode, n0),
        },
        mode,
      ),
    ],
  };
}

// ---------------------------------------------------------------- HRV

export function hrvOption(rows: Day[], mode: Mode, ext: Extent): ChartOption {
  const col = measureColors(mode);
  const byTime = indexByDay(rows);
  const t = rows.map((r) => dayPoint(r.day, 0)[0]);
  const band = rows.map((r) =>
    r.hrv_baseline_balanced_low_ms != null && r.hrv_baseline_balanced_upper_ms != null
      ? ([r.hrv_baseline_balanced_low_ms, r.hrv_baseline_balanced_upper_ms] as [number, number])
      : null,
  );
  const bandSeries = (name: string, values: (number | null)[], area: boolean): Obj => ({
    type: "line",
    name,
    stack: "baseline",
    data: values.map((v, i) => [t[i], v]),
    symbol: "none",
    silent: true,
    connectNulls: false,
    lineStyle: { opacity: 0, width: 0 },
    itemStyle: { color: wash(col.hrv, mode === "dark" ? 0.5 : 0.35) },
    areaStyle: area ? { color: wash(col.hrv, mode === "dark" ? 0.2 : 0.13) } : { opacity: 0 },
    tooltip: { show: false },
    z: 1,
  });
  return {
    grid: { ...GRID_WITH_LEGEND, right: 34 },
    legend: {
      ...legend(),
      data: legendItems([
        ["Nightly", "dot"],
        ["Weekly average", "line"],
        ["Balanced range", "area"],
      ]),
    },
    tooltip: axisTooltip((p) => {
      const r = rowAt(p, byTime);
      if (!r) return "";
      const low = r.hrv_baseline_balanced_low_ms;
      const up = r.hrv_baseline_balanced_upper_ms;
      return (
        dateTitle(r.day) +
        tooltipRow(
          col.hrv,
          "Last night",
          r.hrv_last_night_avg_ms == null ? DASH : `${n0(r.hrv_last_night_avg_ms)} ms`,
        ) +
        tooltipRow(
          col.hrv,
          "Weekly average",
          r.hrv_weekly_avg_ms == null ? DASH : `${n0(r.hrv_weekly_avg_ms)} ms`,
        ) +
        tooltipRow(
          wash(col.hrv, 0.35),
          "Balanced range",
          low == null || up == null ? DASH : `${n0(low)}–${n0(up)} ms`,
        ) +
        tooltipMuted("Status", r.hrv_status ? titleCase(r.hrv_status) : DASH, mode)
      );
    }),
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, undefined, { scale: true, minInterval: 1 }),
    series: [
      bandSeries(
        "Baseline low",
        band.map((b) => (b ? b[0] : null)),
        false,
      ),
      bandSeries(
        "Balanced range",
        band.map((b) => (b ? b[1] - b[0] : null)),
        true,
      ),
      {
        ...scatter(
          "Nightly",
          rows
            .filter((r) => r.hrv_last_night_avg_ms != null)
            .map((r) => dayPoint(r.day, r.hrv_last_night_avg_ms)),
          col.hrv,
          dotSize(rows.length),
        ),
        itemStyle: dotStyle(col.hrv, mode),
        z: 2,
      },
      ...cased(
        {
          ...line(
            "Weekly average",
            rows.map((r) => dayPoint(r.day, r.hrv_weekly_avg_ms)),
            col.hrv,
          ),
          endLabel: endLabel(mode, n0),
        },
        mode,
      ),
    ],
  };
}

// ---------------------------------------------------------------- readiness

const READINESS_GROUPS: { label: string; levels: string[]; status: keyof typeof STATUS }[] = [
  { label: "Prime / high", levels: ["PRIME", "HIGH"], status: "good" },
  { label: "Moderate", levels: ["MODERATE"], status: "warning" },
  { label: "Low", levels: ["LOW"], status: "serious" },
  { label: "Poor", levels: ["POOR"], status: "critical" },
];

export function readinessOption(rows: Readiness[], mode: Mode, ext: Extent): ChartOption {
  const byTime = indexByDay(rows);
  const groups = READINESS_GROUPS.filter((g) =>
    rows.some((r) => r.level && g.levels.includes(r.level)),
  );
  const factor = (label: string, v: number | null) =>
    tooltipMuted(label, v == null ? DASH : `${v}`, mode);
  return {
    grid: GRID_WITH_LEGEND,
    legend: { ...legend(), data: legendItems(groups.map((g) => [g.label, "dot"])) },
    tooltip: axisTooltip((p) => {
      const r = rowAt(p, byTime);
      if (!r) return "";
      const st = readinessStatus(r.level);
      return (
        dateTitle(r.day) +
        tooltipRow(
          st ? STATUS[st] : CHROME[mode].muted,
          r.level ? titleCase(r.level) : "Score",
          r.score == null ? DASH : `${r.score}`,
        ) +
        factor("Sleep score", r.sleep_score_factor) +
        factor("Recovery", r.recovery_factor) +
        factor("HRV", r.hrv_factor) +
        factor("Acute load", r.acwr_factor) +
        factor("Stress history", r.stress_history_factor) +
        factor("Sleep history", r.sleep_history_factor) +
        tooltipMuted(
          "Recovery time",
          r.recovery_time_min ? fmtHours(r.recovery_time_min * 60) : "none",
          mode,
        )
      );
    }),
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, undefined, { min: 0, max: 100, interval: 25 }),
    series: [
      {
        ...line(
          "Score",
          rows.map((r) => dayPoint(r.day, r.score)),
          CHROME[mode].axis,
          { width: 1.5 },
        ),
        z: 1,
      },
      ...groups.map((g) => ({
        ...scatter(
          g.label,
          rows
            .filter((r) => r.level && g.levels.includes(r.level) && r.score != null)
            .map((r) => dayPoint(r.day, r.score)),
          STATUS[g.status],
          dotSize(rows.length, 7),
        ),
        itemStyle: {
          color: STATUS[g.status],
          opacity: 1,
          borderColor: CHROME[mode].surface,
          borderWidth: 1.5,
        },
        z: 3,
      })),
    ],
  };
}

// ---------------------------------------------------------------- stress

export function weekCentre(week: string): number {
  return dayPoint(week, 0)[0] + 3 * DAY_MS;
}

/** Extent covering both the day range and the weekly bars (the two stress charts align). */
export function weeklyExtent(rows: Day[], ext: Extent): Extent {
  const weeks = weekly(
    rows,
    (r) => r.day,
    () => 0,
  );
  if (!weeks.length) return ext;
  return {
    min: Math.min(ext.min, weekCentre(weeks[0]!.week) - 3.5 * DAY_MS),
    max: Math.max(ext.max, weekCentre(weeks[weeks.length - 1]!.week) + 3.5 * DAY_MS),
  };
}

export function stressDailyOption(rows: Day[], mode: Mode, ext: Extent): ChartOption {
  const col = measureColors(mode);
  const byTime = indexByDay(rows);
  const mean7 = smooth(
    rows.map((r) => r.avg_stress),
    7,
  );
  return {
    grid: { ...GRID_WITH_LEGEND, right: 34 },
    legend: {
      ...legend(),
      data: legendItems([
        ["Daily average", "dot"],
        ["7-day mean", "line"],
      ]),
    },
    tooltip: axisTooltip((p) => {
      const r = rowAt(p, byTime);
      if (!r) return "";
      const i = rows.indexOf(r);
      return (
        dateTitle(r.day) +
        tooltipRow(col.stress, "Daily average", r.avg_stress == null ? DASH : `${r.avg_stress}`) +
        tooltipRow(col.stress, "7-day mean", mean7[i] == null ? DASH : n1(mean7[i]!)) +
        tooltipMuted("Peak", r.max_stress == null ? DASH : `${r.max_stress}`, mode)
      );
    }),
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, undefined, { scale: true, minInterval: 5 }),
    series: [
      {
        ...scatter(
          "Daily average",
          rows.filter((r) => r.avg_stress != null).map((r) => dayPoint(r.day, r.avg_stress)),
          col.stress,
          dotSize(rows.length),
        ),
        itemStyle: dotStyle(col.stress, mode),
      },
      ...cased(
        {
          ...line(
            "7-day mean",
            rows.map((r, i) => [dayPoint(r.day, 0)[0], mean7[i]]),
            col.stress,
          ),
          endLabel: endLabel(mode, n0),
        },
        mode,
      ),
    ],
  };
}

const STRESS_CLASSES = [
  { key: "stress_rest_s", label: "Rest" },
  { key: "stress_low_s", label: "Low" },
  { key: "stress_medium_s", label: "Medium" },
  { key: "stress_high_s", label: "High" },
] as const;

export function stressWeeklyOption(rows: Day[], mode: Mode, ext: Extent): ChartOption {
  const colors = STRESS_LEVELS[mode];
  const perClass = STRESS_CLASSES.map((c) =>
    weekly(
      rows,
      (r) => r.day,
      (r) => (r[c.key] == null ? null : r[c.key]! / 3600),
    ),
  );
  const weeks = perClass[0]!.map((w) => w.week);
  const byTime = new Map(weeks.map((w, i) => [weekCentre(w), i]));
  const series = STRESS_CLASSES.map((c, k) =>
    bars(
      c.label,
      perClass[k]!.map((w) => [weekCentre(w.week), w.value]),
      colors[k]!,
      mode,
      { stack: "stress", barMaxWidth: 22 },
    ),
  );
  return {
    grid: GRID_WITH_LEGEND,
    legend: legend(),
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      confine: true,
      formatter: (p: unknown) => {
        const arr = p as AxisParam[];
        const v = arr[0]?.value;
        const i = Array.isArray(v) ? byTime.get(v[0] as number) : undefined;
        if (i === undefined) return "";
        const head = tooltipTitle(
          `Week of ${fmtDate(weeks[i]!, { day: "numeric", month: "short", year: "numeric" })}`,
        );
        return (
          head +
          STRESS_CLASSES.map((c, k) => {
            const h = perClass[k]![i]!.value;
            return tooltipRow(colors[k]!, c.label, h == null ? DASH : `${fmtHours(h * 3600)}/day`);
          }).join("")
        );
      },
    },
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, (v) => `${fmtNumber(v)} h`, { minInterval: 1 }),
    series: roundVisibleTops(series),
  };
}

// ---------------------------------------------------------------- body battery

export function bodyBatteryOption(rows: Day[], mode: Mode, ext: Extent): ChartOption {
  const col = measureColors(mode);
  const byTime = indexByDay(rows);
  const ranged = rows.filter((r) => r.body_battery_low != null && r.body_battery_high != null);
  return {
    grid: GRID_WITH_LEGEND,
    legend: legend(),
    tooltip: axisTooltip((p) => {
      const r = rowAt(p, byTime);
      if (!r) return "";
      return (
        dateTitle(r.day) +
        tooltipRow(
          col.bodyBattery,
          "Range",
          `${r.body_battery_low ?? DASH}–${r.body_battery_high ?? DASH}`,
        ) +
        tooltipRow(CHROME[mode].text, "At wake", `${r.body_battery_at_wake ?? DASH}`) +
        tooltipMuted(
          "Charged · drained",
          `+${r.body_battery_charged ?? DASH} · −${r.body_battery_drained ?? DASH}`,
          mode,
        )
      );
    }),
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, undefined, { min: 0, max: 100, interval: 25 }),
    series: [
      rangeBars(
        "Daily range",
        ranged.map((r) => [dayPoint(r.day, 0)[0], r.body_battery_low, r.body_battery_high]),
        col.bodyBattery,
        mode,
        { band: DAY_MS, maxWidth: 12 },
      ),
      {
        ...scatter(
          "At wake",
          rows
            .filter((r) => r.body_battery_at_wake != null)
            .map((r) => dayPoint(r.day, r.body_battery_at_wake)),
          CHROME[mode].text,
          dotSize(rows.length),
        ),
        itemStyle: {
          color: CHROME[mode].text,
          opacity: 1,
          borderColor: CHROME[mode].surface,
          borderWidth: 1.5,
        },
        z: 4,
      },
    ],
  };
}

// ---------------------------------------------------------------- steps

export function stepsOption(rows: Day[], mode: Mode, ext: Extent, units: UnitSystem): ChartOption {
  const col = measureColors(mode);
  const byTime = indexByDay(rows);
  return {
    grid: GRID_WITH_LEGEND,
    legend: legend(),
    tooltip: {
      ...axisTooltip((p) => {
        const r = rowAt(p, byTime);
        if (!r) return "";
        const pct = r.steps != null && r.step_goal ? (r.steps / r.step_goal) * 100 : null;
        return (
          dateTitle(r.day) +
          tooltipRow(col.steps, "Steps", fmtNumber(r.steps)) +
          tooltipRow(CHROME[mode].muted, "Goal", fmtNumber(r.step_goal)) +
          tooltipMuted("Of goal", pct == null ? DASH : `${fmtNumber(pct)} %`, mode) +
          tooltipMuted("Distance", fmtDistance(r.distance_m, units), mode)
        );
      }),
      axisPointer: { type: "shadow" },
    },
    xAxis: timeAxis(ext),
    yAxis: valueYAxis(undefined, (v) => fmtCompact(v)),
    series: [
      bars(
        "Steps",
        rows.map((r) => dayPoint(r.day, r.steps)),
        col.steps,
        mode,
        { barMaxWidth: 14 },
      ),
      {
        type: "line",
        name: "Goal",
        step: "middle",
        data: rows.map((r) => dayPoint(r.day, r.step_goal)),
        symbol: "none",
        silent: true,
        lineStyle: { color: CHROME[mode].text2, width: 1.5, type: [4, 3] },
        itemStyle: { color: CHROME[mode].text2 },
        z: 3,
      },
    ],
  };
}
