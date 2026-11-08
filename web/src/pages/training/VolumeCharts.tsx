/** Volume-side charts of the training page: volume by sport, HR-zone intensity, training effect. */
import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, LegendItem, QueryState, Segmented } from "@/components/ui";
import {
  axisTooltip,
  GRID,
  itemTooltip,
  refLine,
  roundStackTops,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import {
  distanceUnit,
  distanceValue,
  fmtDate,
  fmtHours,
  fmtNumber,
  fmtPercent,
  teLabel,
  type UnitSystem,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { bySlot, sportColor, sportLabel } from "@/lib/sports";
import { BLUE, CHROME, INTENSITY_BANDS, NEUTRAL, type Mode } from "@/lib/tokens";
import { halo, jitter, periodLabel, periodTitle } from "./util";

type Period = "week" | "month";
type VolumeMetric = "distance" | "time" | "load";
type Query = { start: string; end: string; sport?: string };

const PERIODS = [
  { value: "week", label: "Week" },
  { value: "month", label: "Month" },
] as const;

/** Weeks for ranges up to ~a year, months beyond (keeps columns readable). */
function defaultPeriod(q: Query): Period {
  const days =
    (new Date(`${q.end}T12:00:00`).getTime() - new Date(`${q.start}T12:00:00`).getTime()) /
    86_400_000;
  return days > 400 ? "month" : "week";
}

function volumeValue(
  r: Schemas["TrainingVolumePoint"],
  metric: VolumeMetric,
  units: UnitSystem,
): number {
  if (metric === "distance") return r.distance_m ? distanceValue(r.distance_m, units) : 0;
  if (metric === "time") return (r.moving_s ?? r.duration_s ?? 0) / 3600;
  return r.training_load ?? 0;
}

function volumeFormat(metric: VolumeMetric, units: UnitSystem): (v: number) => string {
  if (metric === "distance")
    return (v) => `${fmtNumber(v, v > 0 && v < 10 ? 1 : 0)} ${distanceUnit(units)}`;
  if (metric === "time") return (v) => fmtHours(v * 3600);
  return (v) => fmtNumber(v);
}

/** Weekly / monthly volume stacked by sport (fixed sport colours, slot order). */
export function VolumeCard({ query, ready }: { query: Query; ready: boolean }) {
  const mode = useMode();
  const units = useUnits();
  const [periodChoice, setPeriod] = useState<Period | null>(null);
  const [metric, setMetric] = useState<VolumeMetric>("distance");
  const period = periodChoice ?? defaultPeriod(query);
  const q = api.useQuery(
    "get",
    "/api/training/volume",
    { params: { query: { ...query, period } } },
    { enabled: ready, placeholderData: (prev) => prev },
  );

  const built = useMemo(() => {
    const rows = q.data ?? [];
    const periods = [...new Set(rows.map((r) => r.period_start))].sort();
    const col = new Map(periods.map((p, i) => [p, i]));
    const sports = [...new Set(rows.map((r) => r.sport_group))].sort(bySlot);
    const stacks = sports
      .map((s) => {
        const values = periods.map(() => 0);
        for (const r of rows)
          if (r.sport_group === s)
            values[col.get(r.period_start)!]! += volumeValue(r, metric, units);
        return { sport: s, values };
      })
      .filter((s) => s.values.some((v) => v > 0));
    const totals = periods.map((_, j) => stacks.reduce((sum, s) => sum + (s.values[j] ?? 0), 0));
    return { periods, stacks, totals };
  }, [q.data, metric, units]);

  const fmt = useMemo(() => volumeFormat(metric, units), [metric, units]);
  const total = built.totals.reduce((a, b) => a + b, 0);
  const avg = built.totals.length ? total / built.totals.length : 0;

  const option = useMemo<ChartOption>(() => {
    const { periods, stacks, totals } = built;
    const c = CHROME[mode];
    const avgLine = refLine(avg, `avg ${fmt(avg)}`, mode);
    const series = stacks.map((s, i) => ({
      type: "bar",
      name: sportLabel(s.sport),
      stack: "volume",
      barMaxWidth: 24,
      data: s.values.map((v) => v || null),
      itemStyle: {
        color: sportColor(s.sport, mode),
        borderColor: c.surface,
        borderWidth: periods.length > 60 ? 0 : 1,
        borderRadius: 0,
      },
      emphasis: { focus: "series" },
      ...(i === stacks.length - 1 && avg > 0
        ? {
            markLine: {
              ...avgLine,
              label: { ...(avgLine.label as object), position: "insideStartTop", ...halo(mode) },
            },
          }
        : {}),
    }));
    return {
      grid: GRID,
      tooltip: axisTooltip((p) => {
        const arr = p as { dataIndex: number }[];
        const j = arr[0]?.dataIndex ?? -1;
        const iso = periods[j];
        if (!iso) return "";
        const rowsHtml = stacks
          .filter((s) => (s.values[j] ?? 0) > 0)
          .map((s) => tooltipRow(sportColor(s.sport, mode), sportLabel(s.sport), fmt(s.values[j]!)))
          .join("");
        return (
          tooltipTitle(periodTitle(iso, period)) +
          rowsHtml +
          `<div style="border-top:1px solid ${c.grid};margin-top:6px;padding-top:6px">${tooltipRow("transparent", "Total", fmt(totals[j] ?? 0))}</div>`
        );
      }),
      xAxis: {
        type: "category",
        data: periods.map((p) => periodLabel(p, period)),
        axisTick: { show: false },
        axisLabel: { hideOverlap: true },
      },
      yAxis: valueYAxis(
        metric === "distance" ? distanceUnit(units) : metric === "time" ? "hours" : "load",
        (v) => fmtNumber(v),
      ),
      series: roundStackTops(series, mode),
    };
  }, [built, mode, period, metric, units, avg, fmt]);

  return (
    <Card
      title="Volume by sport"
      subtitle={
        q.data && total > 0
          ? `${fmt(total)} in total · ${fmt(avg)} per ${period} on average`
          : `Per ${period}, stacked by sport`
      }
      actions={
        <>
          <Segmented
            size="sm"
            label="Volume metric"
            value={metric}
            onChange={setMetric}
            options={[
              { value: "distance", label: "Distance" },
              { value: "time", label: "Time" },
              { value: "load", label: "Load" },
            ]}
          />
          <Segmented
            size="sm"
            label="Volume period"
            value={period}
            onChange={setPeriod}
            options={PERIODS}
          />
        </>
      }
    >
      <QueryState
        query={q}
        height={280}
        isEmpty={() => built.stacks.length === 0}
        empty={<EmptyState title="No activities in this period" />}
      >
        {() => (
          <>
            <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
              {built.stacks.map((s) => (
                <LegendItem
                  key={s.sport}
                  color={sportColor(s.sport, mode)}
                  label={sportLabel(s.sport)}
                />
              ))}
            </div>
            <Chart
              option={option}
              height={280}
              ariaLabel={`Training ${metric} per ${period}, stacked by sport`}
            />
          </>
        )}
      </QueryState>
    </Card>
  );
}

const ZONES = [1, 2, 3, 4, 5] as const;
const ZONE_NAMES = ["Warm-up", "Easy", "Aerobic", "Threshold", "Maximum"];
/** Stacks show three bands; five blue steps cannot be told apart in thin columns. */
const BANDS = [
  { label: "Easy", range: "Z1–2", zones: [1, 2] },
  { label: "Moderate", range: "Z3", zones: [3] },
  { label: "Hard", range: "Z4–5", zones: [4, 5] },
] as const;
type IntensityRow = Schemas["TrainingIntensityPoint"];

function zoneSeconds(r: IntensityRow, n: (typeof ZONES)[number]): number {
  return r[`zone_${n}_s` as `zone_${typeof n}_s`] ?? 0;
}

function bandSeconds(r: IntensityRow, b: (typeof BANDS)[number]): number {
  return b.zones.reduce((s, n) => s + zoneSeconds(r, n), 0);
}

/** Time in heart-rate zones per period, absolute hours or 100 % share. */
export function IntensityCard({ query, ready }: { query: Query; ready: boolean }) {
  const mode = useMode();
  const [periodChoice, setPeriod] = useState<Period | null>(null);
  const [scale, setScale] = useState<"time" | "share">("time");
  const period = periodChoice ?? defaultPeriod(query);
  const q = api.useQuery(
    "get",
    "/api/training/intensity",
    { params: { query: { ...query, period } } },
    { enabled: ready, placeholderData: (prev) => prev },
  );
  const rows = useMemo(() => (q.data ?? []).filter((r) => r.total_s > 0), [q.data]);
  const sums = useMemo(() => {
    const z = ZONES.map((n) =>
      rows.reduce((s, r) => s + (r[`zone_${n}_s` as `zone_${typeof n}_s`] ?? 0), 0),
    );
    const all = z.reduce((a, b) => a + b, 0) || 1;
    return z.map((v) => (v / all) * 100);
  }, [rows]);

  const option = useMemo<ChartOption>(() => {
    const share = scale === "share";
    const values = BANDS.map((b) =>
      rows.map((r) => {
        const s = bandSeconds(r, b);
        return share ? (s / r.total_s) * 100 : s / 3600;
      }),
    );
    const ramp = INTENSITY_BANDS[mode];
    const bandOf = (n: number) =>
      BANDS.findIndex((b) => (b.zones as readonly number[]).includes(n));
    const c = CHROME[mode];
    return {
      grid: GRID,
      tooltip: axisTooltip((p) => {
        const j = (p as { dataIndex: number }[])[0]?.dataIndex ?? -1;
        const r = rows[j];
        if (!r) return "";
        return (
          tooltipTitle(periodTitle(r.period_start, period)) +
          ZONES.map((n, i) => {
            const s = zoneSeconds(r, n);
            return tooltipRow(
              ramp[bandOf(n)]!,
              `Zone ${n} · ${ZONE_NAMES[i]}`,
              `${fmtHours(s)} · ${fmtPercent((s / r.total_s) * 100)}`,
            );
          })
            .reverse()
            .join("") +
          `<div style="border-top:1px solid ${c.grid};margin-top:6px;padding-top:6px">${tooltipRow("transparent", "Total", fmtHours(r.total_s))}</div>`
        );
      }),
      xAxis: {
        type: "category",
        data: rows.map((r) => periodLabel(r.period_start, period)),
        axisTick: { show: false },
        axisLabel: { hideOverlap: true },
      },
      yAxis: valueYAxis(share ? "%" : "hours", (v) => fmtNumber(v), share ? { max: 100 } : {}),
      series: roundStackTops(
        BANDS.map((b, i) => ({
          type: "bar",
          name: `${b.label} (${b.range})`,
          stack: "zones",
          barMaxWidth: 24,
          data: values[i]!.map((v) => v || null),
          itemStyle: {
            color: ramp[i],
            borderColor: c.surface,
            borderWidth: rows.length > 60 ? 0 : 1,
            borderRadius: 0,
          },
        })),
        mode,
      ),
    };
  }, [rows, scale, mode, period]);

  const easy = (sums[0] ?? 0) + (sums[1] ?? 0);
  const hard = (sums[3] ?? 0) + (sums[4] ?? 0);
  return (
    <Card
      title="Intensity distribution"
      subtitle={
        rows.length
          ? `${fmtPercent(easy)} easy (Z1–2) · ${fmtPercent(sums[2])} moderate (Z3) · ${fmtPercent(hard)} hard (Z4–5)`
          : `Time in heart-rate zones per ${period}`
      }
      actions={
        <>
          <Segmented
            size="sm"
            label="Intensity scale"
            value={scale}
            onChange={setScale}
            options={[
              { value: "time", label: "Hours" },
              { value: "share", label: "Share" },
            ]}
          />
          <Segmented
            size="sm"
            label="Intensity period"
            value={period}
            onChange={setPeriod}
            options={PERIODS}
          />
        </>
      }
    >
      <QueryState
        query={q}
        height={280}
        isEmpty={() => rows.length === 0}
        empty={<EmptyState title="No heart-rate zone data in this period" />}
      >
        {() => (
          <>
            <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
              {BANDS.map((b, i) => (
                <LegendItem
                  key={b.label}
                  color={INTENSITY_BANDS[mode][i]!}
                  label={`${b.label} (${b.range})`}
                />
              ))}
            </div>
            <Chart
              option={option}
              height={280}
              ariaLabel={`Time in heart-rate zones per ${period}${scale === "share" ? " as a share of the total" : ""}`}
            />
          </>
        )}
      </QueryState>
    </Card>
  );
}

const TE_TICKS = [0, 1, 2, 3, 4, 5];

/** Garmin's primary-benefit labels in increasing intensity (ordinal ramp order). */
const BENEFIT_ORDER = [
  "RECOVERY",
  "AEROBIC_BASE",
  "TEMPO",
  "LACTATE_THRESHOLD",
  "VO2MAX",
  "ANAEROBIC_CAPACITY",
  "SPRINT",
];
const BENEFIT_RAMP: Record<Mode, number[]> = {
  light: [250, 300, 350, 450, 500, 600, 650],
  // Dark steps start at the first blue that clears 3:1 on the card.
  dark: [500, 450, 400, 350, 300, 200, 100],
};

function benefitRank(label: string): number {
  const i = BENEFIT_ORDER.indexOf(label);
  return i < 0 ? BENEFIT_ORDER.length : i;
}

function benefitColor(label: string, mode: Mode): string {
  const i = BENEFIT_ORDER.indexOf(label);
  return i < 0 ? NEUTRAL[mode] : BLUE[BENEFIT_RAMP[mode][i]!]!;
}

/** Aerobic vs anaerobic training effect per activity, plus the primary-benefit mix. */
export function EffectsCard({ query, ready }: { query: Query; ready: boolean }) {
  const mode = useMode();
  const navigate = useNavigate();
  const q = api.useQuery(
    "get",
    "/api/training/effects",
    { params: { query } },
    { enabled: ready, placeholderData: (prev) => prev },
  );
  const acts = useMemo(
    () =>
      (q.data?.activities ?? []).filter((a) => a.aerobic_te !== null && a.anaerobic_te !== null),
    [q.data],
  );
  const labels = useMemo(
    () => [...(q.data?.labels ?? [])].sort((a, b) => benefitRank(a.label) - benefitRank(b.label)),
    [q.data],
  );

  const groups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of acts) counts.set(a.sport_group, (counts.get(a.sport_group) ?? 0) + 1);
    const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([s]) => s);
    // At most three sport colours on screen (all pairs must stay distinguishable): the three
    // most frequent coloured sports keep theirs; the rest, and neutral-coloured ones such as
    // walking, fold into a labelled grey "Other".
    const coloured = ranked.filter((s) => sportColor(s, mode) !== NEUTRAL[mode]);
    const shown = coloured.slice(0, 3).sort(bySlot);
    const rest = ranked.filter((s) => !shown.includes(s));
    const restNames = rest.map((s) => sportLabel(s).toLowerCase());
    return [
      ...(rest.length
        ? [
            {
              name:
                rest.length === 1
                  ? sportLabel(rest[0]!)
                  : `Other (${restNames.slice(0, 3).join(", ")}${rest.length > 3 ? ", …" : ""})`,
              color: NEUTRAL[mode],
              items: acts.filter((a) => rest.includes(a.sport_group)),
              z: 2,
            },
          ]
        : []),
      ...shown.map((s) => ({
        name: sportLabel(s),
        color: sportColor(s, mode),
        items: acts.filter((a) => a.sport_group === s),
        z: 3,
      })),
    ];
  }, [acts, mode]);

  const scatterOption = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const byId = new Map(acts.map((a) => [a.activity_id, a]));
    return {
      grid: { ...GRID, bottom: 4 },
      tooltip: itemTooltip((p) => {
        const v = (p as { value: [number, number, number]; color: string }).value;
        const a = byId.get(v[2]);
        if (!a) return "";
        return (
          tooltipTitle(a.name ?? sportLabel(a.sport_group)) +
          `<div style="color:${c.muted};margin:-2px 0 6px">${fmtDate(a.day)} · ${teLabel(a.training_effect_label)}</div>` +
          tooltipRow(sportColor(a.sport_group, mode), "Sport", sportLabel(a.sport_group)) +
          tooltipRow("transparent", "Aerobic TE", fmtNumber(a.aerobic_te, 1)) +
          tooltipRow("transparent", "Anaerobic TE", fmtNumber(a.anaerobic_te, 1)) +
          (a.training_load !== null
            ? tooltipRow("transparent", "Load", fmtNumber(a.training_load))
            : "")
        );
      }),
      // Half a step of room around 0–5 so dots on the scale ends are not cut by the plot edge.
      xAxis: {
        type: "value",
        min: -0.25,
        max: 5.25,
        name: "Aerobic training effect",
        nameLocation: "middle",
        nameGap: 26,
        splitLine: { show: true },
        axisLine: { show: false },
        axisTick: { show: false, customValues: TE_TICKS },
        axisLabel: { customValues: TE_TICKS },
      },
      yAxis: valueYAxis("Anaerobic", (v) => fmtNumber(v), {
        min: -0.25,
        max: 5.25,
        axisTick: { show: false, customValues: TE_TICKS },
        axisLabel: { customValues: TE_TICKS, formatter: (v: number) => fmtNumber(v) },
      }),
      series: groups.map((g) => ({
        type: "scatter",
        name: g.name,
        symbolSize: 9,
        cursor: "pointer",
        z: g.z,
        itemStyle: { color: g.color, opacity: 0.6, borderColor: c.surface, borderWidth: 0.5 },
        emphasis: { itemStyle: { opacity: 1 } },
        // Training effect comes in 0.1 steps, so many activities share a point: a small,
        // stable jitter (≤ 0.12) spreads them without moving a dot to another tenth.
        data: g.items.map((a) => [
          a.aerobic_te! + jitter(a.activity_id, 1, 0.12),
          Math.max(-0.2, a.anaerobic_te! + jitter(a.activity_id, 2, 0.12)),
          a.activity_id,
        ]),
      })),
    };
  }, [acts, groups, mode]);

  const benefitOption = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const total = labels.reduce((s, l) => s + l.activities, 0) || 1;
    return {
      grid: { left: 4, right: 52, top: 4, bottom: 4 },
      tooltip: itemTooltip((p) => {
        const l = labels[(p as { dataIndex: number }).dataIndex];
        if (!l) return "";
        return tooltipRow(
          benefitColor(l.label, mode),
          teLabel(l.label),
          `${l.activities} · ${fmtPercent((l.activities / total) * 100)}`,
        );
      }),
      xAxis: { type: "value", show: false },
      yAxis: {
        type: "category",
        inverse: true,
        data: labels.map((l) => teLabel(l.label)),
        axisLine: { show: false },
        axisLabel: { color: c.text2 },
      },
      series: [
        {
          type: "bar",
          name: "Activities",
          barMaxWidth: 16,
          data: labels.map((l) => ({
            value: l.activities,
            itemStyle: { color: benefitColor(l.label, mode), borderRadius: [0, 4, 4, 0] },
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
  }, [labels, mode]);

  return (
    <Card
      className="lg:col-span-2"
      title="Training effect"
      subtitle="Aerobic vs anaerobic effect of every activity (click a dot to open it) and Garmin's primary benefit"
    >
      <QueryState
        query={q}
        height={300}
        isEmpty={() => acts.length === 0}
        empty={<EmptyState title="No training-effect data in this period" />}
      >
        {() => (
          <div className="grid gap-5 lg:grid-cols-5">
            <div className="lg:col-span-3">
              <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
                {[...groups.filter((g) => g.z === 3), ...groups.filter((g) => g.z !== 3)].map(
                  (g) => (
                    <LegendItem
                      key={g.name}
                      color={g.color}
                      label={`${g.name} · ${g.items.length}`}
                    />
                  ),
                )}
              </div>
              <Chart
                option={scatterOption}
                height={300}
                ariaLabel="Aerobic versus anaerobic training effect per activity, coloured by sport"
                onEvents={{
                  click: (p) => {
                    const id = (p as { value?: number[] }).value?.[2];
                    if (id)
                      void navigate({
                        to: "/activities/$activityId",
                        params: { activityId: String(id) },
                      });
                  },
                }}
              />
            </div>
            {labels.length > 0 && (
              <div className="lg:col-span-2">
                <p className="mb-1 text-xs font-medium text-ink-2">Primary benefit · activities</p>
                <Chart
                  option={benefitOption}
                  height={Math.max(150, labels.length * 34 + 12)}
                  ariaLabel="Activities per primary training benefit"
                />
              </div>
            )}
          </div>
        )}
      </QueryState>
    </Card>
  );
}
