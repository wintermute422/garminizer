/** ECharts options for the sleep page (stages, score, schedule, weekday/weekend, distribution). */
import type { Schemas } from "@/api/client";
import type { ChartOption } from "@/components/Chart";
import {
  axisTooltip,
  bars,
  dayPoint,
  GRID_WITH_LEGEND,
  itemTooltip,
  legend,
  line,
  scatter,
  tooltipRow,
  tooltipTitle,
} from "@/lib/charts";
import { DASH, fmtClockFromNoon, fmtDate, fmtHours, fmtNumber, smooth } from "@/lib/format";
import { CHROME, SLEEP_STAGES, ZONE_RAMP, type Mode } from "@/lib/tokens";
import {
  DAY_MS,
  dotSize,
  dayAxis,
  dayOfPoint,
  measureColors,
  rangeBars,
  roundVisibleTops,
  smallTitle,
  tooltipMuted,
  washHex,
} from "../health/util";

type Night = Schemas["SleepNight"];
type Stats = Schemas["SleepStats"];
type Obj = Record<string, unknown>;

export const STAGES = [
  { key: "deep", label: "Deep", field: "deep_s" },
  { key: "light", label: "Light", field: "light_s" },
  { key: "rem", label: "REM", field: "rem_s" },
  { key: "awake", label: "Awake", field: "awake_s" },
] as const;

export interface Extent {
  min: number;
  max: number;
}

export function nightExtent(start: string, end: string): Extent {
  return { min: dayPoint(start, 0)[0] - DAY_MS / 2, max: dayPoint(end, 0)[0] + DAY_MS / 2 };
}

/** Weekend = nights that end on Saturday or Sunday (same rule as /api/sleep/stats). */
export function isWeekend(day: string): boolean {
  const d = new Date(`${day}T12:00:00`).getDay();
  return d === 0 || d === 6;
}

export function nightTitle(day: string): string {
  return `Night to ${fmtDate(day, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}`;
}

function byTime(rows: readonly Night[]): Map<number, Night> {
  return new Map(rows.map((r) => [dayPoint(r.day, 0)[0], r]));
}

function rowAt(params: unknown, map: Map<number, Night>): Night | undefined {
  const arr = (Array.isArray(params) ? params : [params]) as { value?: unknown }[];
  for (const p of arr) {
    const v = p.value;
    if (Array.isArray(v) && typeof v[0] === "number") {
      const hit = map.get(v[0]);
      if (hit) return hit;
    }
  }
  return undefined;
}

export function asleep(n: Night): number | null {
  const parts = [n.deep_s, n.light_s, n.rem_s];
  return parts.every((v) => v == null) ? null : parts.reduce<number>((s, v) => s + (v ?? 0), 0);
}

function selection(selected: string | null, mode: Mode): Obj | undefined {
  if (!selected) return undefined;
  const t = dayPoint(selected, 0)[0];
  return {
    silent: true,
    itemStyle: { color: mode === "dark" ? "rgba(255,255,255,0.07)" : "rgba(11,11,11,0.06)" },
    data: [[{ xAxis: t - DAY_MS / 2 }, { xAxis: t + DAY_MS / 2 }]],
  };
}

// ---------------------------------------------------------------- stages per night

export function stagesOption(
  rows: Night[],
  mode: Mode,
  ext: Extent,
  selected: string | null,
  dense: boolean,
): ChartOption {
  const colors = SLEEP_STAGES[mode];
  const map = byTime(rows);
  const series = STAGES.map((s) =>
    bars(
      s.label,
      rows.map((r) => dayPoint(r.day, r[s.field] == null ? null : r[s.field]! / 3600)),
      colors[s.key],
      mode,
      { stack: "stages", barMaxWidth: 16 },
    ),
  );
  // Thin columns (phones, long ranges) lose their colour to the 1px surface gap: drop it.
  const gapless = dense
    ? series.map((x) => ({ ...x, itemStyle: { ...(x.itemStyle as Obj), borderWidth: 0 } }))
    : series;
  const rounded = roundVisibleTops(gapless);
  rounded[0] = { ...rounded[0], markArea: selection(selected, mode) };
  return {
    grid: GRID_WITH_LEGEND,
    legend: legend(),
    tooltip: {
      ...axisTooltip((p) => {
        const r = rowAt(p, map);
        if (!r) return "";
        const total = (asleep(r) ?? 0) + (r.awake_s ?? 0) || 1;
        return (
          tooltipTitle(nightTitle(r.day)) +
          STAGES.map((s) => {
            const v = r[s.field];
            return tooltipRow(
              colors[s.key],
              s.label,
              v == null ? DASH : `${fmtHours(v)} · ${fmtNumber((v / total) * 100)} %`,
            );
          })
            .reverse()
            .join("") +
          tooltipMuted("Asleep", fmtHours(asleep(r)), mode) +
          tooltipMuted(
            "Sleep need",
            r.sleep_need_min ? fmtHours(r.sleep_need_min * 60) : DASH,
            mode,
          ) +
          tooltipMuted("Score", r.score == null ? DASH : `${r.score}`, mode)
        );
      }),
      axisPointer: { type: "shadow" },
    },
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: {
      type: "value",
      splitNumber: 4,
      minInterval: 1,
      axisLabel: { formatter: (v: number) => `${fmtNumber(v)} h` },
    },
    series: [
      ...rounded,
      {
        type: "line",
        name: "Sleep need",
        step: "middle",
        data: rows.map((r) => dayPoint(r.day, r.sleep_need_min ? r.sleep_need_min / 60 : null)),
        symbol: "none",
        silent: true,
        lineStyle: { color: CHROME[mode].text2, width: 1.5, type: [4, 3] },
        itemStyle: { color: CHROME[mode].text2 },
        z: 4,
      },
    ],
  };
}

// ---------------------------------------------------------------- score

const QUALITY_LINES = [
  { value: 90, label: "Excellent" },
  { value: 80, label: "Good" },
  { value: 60, label: "Fair" },
];

export function scoreOption(rows: Night[], mode: Mode, ext: Extent): ChartOption {
  const col = measureColors(mode);
  const map = byTime(rows);
  const mean7 = smooth(
    rows.map((r) => r.score),
    7,
  );
  const scores = rows.map((r) => r.score).filter((v): v is number => v != null);
  const lo = Math.min(...scores, 60);
  return {
    grid: { ...GRID_WITH_LEGEND, right: 64 },
    legend: legend(),
    tooltip: axisTooltip((p) => {
      const r = rowAt(p, map);
      if (!r) return "";
      const i = rows.indexOf(r);
      return (
        tooltipTitle(nightTitle(r.day)) +
        tooltipRow(col.score, "Score", r.score == null ? DASH : `${r.score}`) +
        tooltipRow(col.score, "7-night mean", mean7[i] == null ? DASH : fmtNumber(mean7[i], 1)) +
        tooltipMuted("Quality", r.score_quality ? titleWord(r.score_quality) : DASH, mode) +
        tooltipMuted(
          "Duration · deep · REM",
          `${r.score_duration ?? DASH} · ${r.score_deep ?? DASH} · ${r.score_rem ?? DASH}`,
          mode,
        ) +
        tooltipMuted(
          "Awakenings · stress",
          `${r.score_awakenings ?? DASH} · ${r.score_stress ?? DASH}`,
          mode,
        )
      );
    }),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: {
      type: "value",
      min: Math.max(0, Math.floor((lo - 5) / 10) * 10),
      max: 100,
      interval: 10,
    },
    series: [
      {
        ...scatter(
          "Nightly",
          rows.filter((r) => r.score != null).map((r) => dayPoint(r.day, r.score)),
          col.score,
          dotSize(rows.length),
        ),
        itemStyle: { color: col.score, opacity: 0.45, borderWidth: 0 },
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: CHROME[mode].muted, type: [4, 4], width: 1 },
          label: { position: "end", color: CHROME[mode].muted, fontSize: 11, formatter: "{b}" },
          data: QUALITY_LINES.map((q) => ({ yAxis: q.value, name: q.label })),
        },
      },
      line(
        "7-night mean",
        rows.map((r, i) => [dayPoint(r.day, 0)[0], mean7[i]]),
        col.score,
      ),
    ],
  };
}

function titleWord(s: string): string {
  return s.charAt(0) + s.slice(1).toLowerCase();
}

// ---------------------------------------------------------------- bed & wake times

/** Clock-axis bounds on whole hours, the span a multiple of `step` minutes (even ticks). */
function clockBounds(values: number[], step = 60): { min: number; max: number } {
  const min = Math.floor((Math.min(...values) - 15) / 60) * 60;
  const raw = Math.max(...values) + 15 - min;
  return { min, max: min + Math.ceil(raw / step) * step };
}

export function scheduleOption(rows: Night[], mode: Mode, ext: Extent): ChartOption {
  const col = measureColors(mode);
  const map = byTime(rows);
  const timed = rows.filter((r) => r.bedtime_min != null && r.waketime_min != null);
  const point = (r: Night) => [dayPoint(r.day, 0)[0], r.bedtime_min, r.waketime_min];
  const all = timed.flatMap((r) => [r.bedtime_min!, r.waketime_min!]);
  const step = Math.max(...all) - Math.min(...all) > 13 * 60 ? 180 : 120;
  const b = clockBounds(all, step);
  const avgBed = mean(timed.map((r) => r.bedtime_min!));
  const avgWake = mean(timed.map((r) => r.waketime_min!));
  const refs = [
    avgBed != null && { yAxis: avgBed, name: `avg ${fmtClockFromNoon(avgBed)}` },
    avgWake != null && { yAxis: avgWake, name: `avg ${fmtClockFromNoon(avgWake)}` },
  ].filter(Boolean);
  return {
    grid: { ...GRID_WITH_LEGEND, right: 72 },
    legend: legend(),
    tooltip: axisTooltip((p) => {
      const arr = (Array.isArray(p) ? p : [p]) as { axisValue?: number }[];
      const x = arr[0]?.axisValue;
      const r =
        rowAt(p, map) ??
        (typeof x === "number" ? map.get(dayPoint(dayOfPoint(x), 0)[0]) : undefined);
      if (!r) return "";
      const inBed =
        r.bedtime_min != null && r.waketime_min != null
          ? fmtHours((r.waketime_min - r.bedtime_min) * 60)
          : DASH;
      return (
        tooltipTitle(nightTitle(r.day)) +
        tooltipRow(
          isWeekend(r.day) ? col.weekend : col.weekday,
          isWeekend(r.day) ? "Weekend night" : "Weekday night",
          `${fmtClockFromNoon(r.bedtime_min)} → ${fmtClockFromNoon(r.waketime_min)}`,
        ) +
        tooltipMuted("In bed", inBed, mode) +
        tooltipMuted("Asleep", fmtHours(asleep(r)), mode)
      );
    }),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: {
      type: "value",
      inverse: true,
      min: b.min,
      max: b.max,
      interval: step,
      axisLabel: { formatter: (v: number) => fmtClockFromNoon(v) },
    },
    series: [
      {
        ...rangeBars(
          "Weekday nights",
          timed.filter((r) => !isWeekend(r.day)).map(point),
          col.weekday,
          mode,
          { band: DAY_MS, maxWidth: 10 },
        ),
        markLine: refs.length
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: CHROME[mode].text2, type: [4, 4], width: 1 },
              label: { position: "end", color: CHROME[mode].muted, fontSize: 11, formatter: "{b}" },
              data: refs,
            }
          : undefined,
      },
      rangeBars(
        "Weekend nights",
        timed.filter((r) => isWeekend(r.day)).map(point),
        col.weekend,
        mode,
        { band: DAY_MS, maxWidth: 10, outline: true },
      ),
    ],
  };
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((s, v) => s + v, 0) / values.length : null;
}

// ---------------------------------------------------------------- weekday vs weekend

function miniBase(title: string, mode: Mode): Obj {
  return {
    title: smallTitle(title, mode),
    grid: { left: 4, right: 4, top: 44, bottom: 4 },
    xAxis: {
      type: "category",
      data: ["Weekday", "Weekend"],
      axisTick: { show: false },
      // The card's legend names the two groups (labels collide in a phone-width third).
      axisLabel: { show: false },
    },
  };
}

function groupItems(values: (number | null)[], mode: Mode): Obj[] {
  const col = measureColors(mode);
  return values.map((v, i) => ({
    value: v,
    itemStyle:
      i === 0
        ? { color: col.weekday, borderRadius: [4, 4, 0, 0] }
        : {
            color: washHex(col.weekend, 0.28),
            borderColor: col.weekend,
            borderWidth: 1.5,
            borderRadius: [4, 4, 0, 0],
          },
  }));
}

export function weekdayDurationOption(stats: Stats, mode: Mode): ChartOption {
  const hours = [stats.weekday.avg_duration_s, stats.weekend.avg_duration_s].map((v) =>
    v == null ? null : v / 3600,
  );
  return {
    ...miniBase("Asleep", mode),
    tooltip: itemTooltip((p) => {
      const it = p as { name: string; value: number };
      return `${it.name} nights<br/><b>${fmtHours(it.value * 3600)}</b> asleep on average`;
    }),
    yAxis: { type: "value", show: false, min: 0 },
    series: [
      {
        type: "bar",
        name: "Asleep",
        barMaxWidth: 28,
        data: groupItems(hours, mode),
        label: {
          show: true,
          position: "top",
          color: CHROME[mode].text,
          fontSize: 12,
          fontWeight: 600,
          formatter: (p: { value: number }) => fmtHours(p.value * 3600),
        },
      },
    ],
  };
}

export function weekdayScoreOption(stats: Stats, mode: Mode): ChartOption {
  const vals = [stats.weekday.avg_score, stats.weekend.avg_score];
  const present = vals.filter((v): v is number => v != null);
  return {
    ...miniBase("Score", mode),
    tooltip: itemTooltip((p) => {
      const it = p as { name: string; value: number };
      return `${it.name} nights<br/>average score <b>${fmtNumber(it.value, 1)}</b>`;
    }),
    yAxis: {
      type: "value",
      show: false,
      min: Math.max(0, Math.floor((Math.min(...present) - 15) / 10) * 10),
      max: 100,
    },
    series: [
      {
        type: "bar",
        name: "Score",
        barMaxWidth: 28,
        data: groupItems(vals, mode),
        label: {
          show: true,
          position: "top",
          color: CHROME[mode].text,
          fontSize: 12,
          fontWeight: 600,
          formatter: (p: { value: number }) => fmtNumber(p.value),
        },
      },
    ],
  };
}

export function weekdayScheduleOption(stats: Stats, mode: Mode): ChartOption {
  const col = measureColors(mode);
  const groups = [stats.weekday, stats.weekend];
  const vals = groups.flatMap((g) => [g.avg_bedtime_min, g.avg_waketime_min]);
  const present = vals.filter((v): v is number => v != null);
  const b = clockBounds(present);
  const point = (i: number) => [i, groups[i]!.avg_bedtime_min, groups[i]!.avg_waketime_min];
  const labels = (lo: number, hi: number): [string, string] => [
    fmtClockFromNoon(lo),
    fmtClockFromNoon(hi),
  ];
  return {
    ...miniBase("Bed → wake", mode),
    grid: { left: 4, right: 4, top: 44, bottom: 4 },
    tooltip: itemTooltip((p) => {
      const it = p as { value: [number, number, number] };
      const [i, lo, hi] = it.value;
      return `${i === 0 ? "Weekday" : "Weekend"} nights<br/><b>${fmtClockFromNoon(lo)} → ${fmtClockFromNoon(hi)}</b> on average`;
    }),
    yAxis: { type: "value", show: false, inverse: true, min: b.min - 50, max: b.max + 50 },
    series: [
      rangeBars(
        "Weekday",
        groups[0]!.avg_bedtime_min == null ? [] : [point(0)],
        col.weekday,
        mode,
        {
          band: 1,
          maxWidth: 28,
          labels,
        },
      ),
      rangeBars(
        "Weekend",
        groups[1]!.avg_bedtime_min == null ? [] : [point(1)],
        col.weekend,
        mode,
        {
          band: 1,
          maxWidth: 28,
          outline: true,
          labels,
        },
      ),
    ],
  };
}

// ---------------------------------------------------------------- distribution

const QUALITY = [
  { key: "POOR", label: "Poor", min: 0, ramp: 0 },
  { key: "FAIR", label: "Fair", min: 60, ramp: 1 },
  { key: "GOOD", label: "Good", min: 80, ramp: 3 },
  { key: "EXCELLENT", label: "Excellent", min: 90, ramp: 4 },
] as const;

function qualityOf(score: number): (typeof QUALITY)[number] {
  return [...QUALITY].reverse().find((q) => score >= q.min) ?? QUALITY[0];
}

export function distributionOption(rows: Night[], stats: Stats, mode: Mode): ChartOption {
  const scores = rows.map((r) => r.score).filter((v): v is number => v != null);
  const lo = Math.floor(Math.min(...scores) / 5) * 5;
  const hi = Math.floor(Math.max(...scores) / 5) * 5;
  const bins: number[] = [];
  for (let b = lo; b <= hi; b += 5) bins.push(b);
  const counts = bins.map((b) => scores.filter((s) => s >= b && s < b + 5).length);
  const present = QUALITY.filter((q) => bins.some((b) => qualityOf(b).key === q.key));
  const nights = new Map(stats.score_distribution.map((d) => [d.quality, d.nights]));
  const ramp = ZONE_RAMP[mode];
  const total = scores.length || 1;
  return {
    grid: GRID_WITH_LEGEND,
    legend: legend(),
    tooltip: itemTooltip((p) => {
      const it = p as { dataIndex: number; seriesName: string };
      const b = bins[it.dataIndex]!;
      const n = counts[it.dataIndex]!;
      return (
        tooltipTitle(`Score ${b}–${b + 4}`) +
        tooltipRow(
          ramp[qualityOf(b).ramp]!,
          qualityOf(b).label,
          `${n} night${n === 1 ? "" : "s"} · ${fmtNumber((n / total) * 100)} %`,
        )
      );
    }),
    xAxis: {
      type: "category",
      data: bins.map((b) => `${b}–${b + 4}`),
      axisTick: { show: false },
    },
    yAxis: { type: "value", minInterval: 1, splitNumber: 4 },
    series: present.map((q) => ({
      ...bars(
        `${q.label} · ${nights.get(q.key) ?? 0}`,
        bins.map((b, i) => (qualityOf(b).key === q.key ? counts[i] : null)),
        ramp[q.ramp]!,
        mode,
        { barMaxWidth: 36 },
      ),
      stack: "quality",
      itemStyle: { color: ramp[q.ramp]!, borderRadius: [4, 4, 0, 0] },
    })),
  };
}
