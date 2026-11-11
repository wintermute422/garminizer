import { keepPreviousData } from "@tanstack/react-query";
import { Dumbbell, Percent, Ruler, Scale } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  ShowAllButton,
  StatusPill,
} from "@/components/ui";
import { Change, MetricTile, Spark, TileSkeletons } from "@/components/kit";
import {
  axisTooltip,
  cased,
  DAY_MS,
  dayAxis,
  dayExtent,
  dayOfPoint,
  dayPoint,
  dayTitle,
  dotSize,
  dotStyle,
  GRID_WITH_LEGEND,
  legend,
  legendItems,
  line,
  rangeBars,
  scatter,
  tooltipMuted,
  tooltipRow,
  type Extent,
} from "@/lib/charts";
import {
  DASH,
  fmtDate,
  fmtNumber,
  fmtShortDate,
  titleCase,
  weightValue,
  type UnitSystem,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { useRange } from "@/lib/range";
import { trailingByTime, weekly } from "@/lib/stats";
import { pressureStatus } from "@/lib/status";
import { CHROME, measureColors, type Mode } from "@/lib/tokens";
import { fmtWallDate, fmtWallTime, wallClock } from "@/lib/wallClock";

type Body = Schemas["BodyOverview"];
type WeighIn = Schemas["BodyWeighIn"];
type Pressure = Schemas["BodyBloodPressure"];
type Obj = Record<string, unknown>;

const TILE_GRID = "grid grid-cols-2 gap-3 md:grid-cols-4";

/** A measurement placed on its local day (athlete time zone), plus its wall-clock instant. */
interface Placed<T> {
  item: T;
  day: string;
  wall: number;
  x: number;
}

function place<T extends { measured_at: string }>(
  items: readonly T[],
  wall: (iso: string) => number,
): Placed<T>[] {
  return items.map((item) => {
    const w = wall(item.measured_at);
    const day = new Date(w).toISOString().slice(0, 10);
    return { item, day, wall: w, x: dayPoint(day, 0)[0] };
  });
}

/** Weigh-in dots + a trend line for one body measure (one y-axis). */
function measureOption(opts: {
  name: string;
  points: Placed<WeighIn>[];
  value: (w: WeighIn) => number | null;
  trend: [number, number | null][];
  color: string;
  fmt: (v: number) => string;
  ext: Extent;
  mode: Mode;
}): ChartOption {
  const { points, value, color, fmt, mode } = opts;
  const byX = new Map<number, Placed<WeighIn>[]>();
  for (const p of points) byX.set(p.x, [...(byX.get(p.x) ?? []), p]);
  const trendAt = new Map(opts.trend.map(([x, v]) => [x, v]));
  return {
    grid: { ...GRID_WITH_LEGEND, right: 40 },
    legend: {
      ...legend(),
      data: legendItems([
        ["Weigh-ins", "dot"],
        ["7-day trend", "line"],
      ]),
    },
    tooltip: axisTooltip((arr) => {
      const v = arr.find((a) => Array.isArray(a.value))?.value as [number, number] | undefined;
      if (!v) return "";
      const here = byX.get(v[0]) ?? [];
      const t = trendAt.get(v[0]);
      return (
        dayTitle(here[0]?.day ?? dayOfPoint(v[0])) +
        here
          .map((p) => {
            const val = value(p.item);
            return tooltipRow(
              color,
              `Weigh-in ${fmtWallTime(p.wall)}`,
              val == null ? DASH : fmt(val),
            );
          })
          .join("") +
        (t == null ? "" : tooltipMuted("7-day trend", fmt(t), mode))
      );
    }),
    xAxis: dayAxis(opts.ext.min, opts.ext.max),
    yAxis: {
      type: "value",
      scale: true,
      splitNumber: 4,
      axisLabel: { formatter: (v: number) => fmtNumber(v, Number.isInteger(v) ? 0 : 1) },
    },
    series: [
      {
        ...scatter(
          "Weigh-ins",
          points.filter((p) => value(p.item) != null).map((p) => [p.x, value(p.item)]),
          color,
          dotSize(points.length),
        ),
        itemStyle: dotStyle(color, mode),
      },
      ...cased(
        {
          ...line("7-day trend", opts.trend, color),
          endLabel: {
            show: true,
            color: CHROME[mode].text2,
            fontSize: 11,
            distance: 6,
            formatter: (p: { value: [number, number | null] }) =>
              p.value[1] == null ? "" : fmtNumber(p.value[1], 1),
          },
        },
        mode,
      ),
    ],
  };
}

function pressureOption(readings: Placed<Pressure>[], ext: Extent, mode: Mode): ChartOption {
  const col = measureColors(mode);
  const byX = new Map<number, Placed<Pressure>[]>();
  for (const p of readings) byX.set(p.x, [...(byX.get(p.x) ?? []), p]);
  const span = (ext.max - ext.min) / DAY_MS;
  const ref = (value: number, label: string): Obj => ({
    yAxis: value,
    name: label,
  });
  return {
    grid: { ...GRID_WITH_LEGEND, right: 64 },
    legend: legend(),
    tooltip: {
      trigger: "item",
      confine: true,
      formatter: (p: unknown) => {
        const it = p as { value?: [number, number, number] };
        const here = it.value ? (byX.get(it.value[0]) ?? []) : [];
        if (!here.length) return "";
        return (
          dayTitle(here[0]!.day) +
          here
            .map(
              (r) =>
                tooltipRow(
                  col.pressure,
                  fmtWallTime(r.wall),
                  `${r.item.systolic}/${r.item.diastolic} mmHg`,
                ) +
                tooltipMuted(
                  "Pulse · category",
                  `${r.item.pulse ?? DASH} bpm · ${r.item.category ? titleCase(r.item.category) : DASH}`,
                  mode,
                ),
            )
            .join("")
        );
      },
    },
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: { type: "value", scale: true, splitNumber: 4 },
    series: [
      {
        ...rangeBars(
          "Diastolic → systolic",
          readings.map((r) => [r.x, r.item.diastolic, r.item.systolic]),
          col.pressure,
          mode,
          { band: Math.max(1, Math.min(7, span / 45)) * DAY_MS, maxWidth: 10 },
        ),
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: CHROME[mode].muted, type: [4, 4], width: 1 },
          label: { position: "end", color: CHROME[mode].muted, fontSize: 11, formatter: "{b}" },
          data: [ref(120, "120 sys"), ref(80, "80 dia")],
        },
      },
    ],
  };
}

function bmiNote(bmi: number | null | undefined): string | null {
  if (bmi == null) return null;
  if (bmi < 18.5) return "below 18.5";
  if (bmi < 25) return "within 18.5–24.9";
  if (bmi < 30) return "25–29.9";
  return "30 or above";
}

/** Trailing 7-day mean of a weigh-in field, one value per weigh-in. */
function trendOf(points: Placed<WeighIn>[], value: (w: WeighIn) => number | null) {
  const vals = trailingByTime(
    points.map((p) => ({ t: p.x, v: value(p.item) })),
    7,
  );
  const byDay = new Map<number, number | null>();
  points.forEach((p, i) => byDay.set(p.x, vals[i] ?? null));
  return [...byDay.entries()];
}

/** Change of a trend series over ~30 days (closest point 23–37 days before the last). */
function change30(trend: [number, number | null][]): number | null {
  const pts = trend.filter((p): p is [number, number] => p[1] != null);
  const last = pts[pts.length - 1];
  if (!last) return null;
  const target = last[0] - 30 * DAY_MS;
  const near = pts
    .filter((p) => Math.abs(p[0] - target) <= 7 * DAY_MS)
    .sort((a, b) => Math.abs(a[0] - target) - Math.abs(b[0] - target))[0];
  return near ? last[1] - near[1] : null;
}

/** Last non-null point of a trend series. */
function lastOf(trend: [number, number | null][]): { x: number; v: number } | null {
  for (let i = trend.length - 1; i >= 0; i--) {
    const [x, v] = trend[i]!;
    if (v != null) return { x, v };
  }
  return null;
}

/**
 * Tiles show the same number the charts end on: the 7-day trend at the last weigh-in of the
 * period (labelled with its date), plus the change over ~30 days of that trend.
 */
function Tiles({
  data,
  points,
  units,
  mode,
}: {
  data: Body;
  points: Placed<WeighIn>[];
  units: UnitSystem;
  mode: Mode;
}) {
  const col = measureColors(mode);
  const latest = data.latest;
  const unit = units === "metric" ? "kg" : "lb";
  const wv = (kg: number) => weightValue(kg, units);
  const weightTrend: [number, number | null][] = data.trend.map((t) => [
    dayPoint(t.day, 0)[0],
    t.weight_kg,
  ]);
  const fatTrend: [number, number | null][] = data.trend.map((t) => [
    dayPoint(t.day, 0)[0],
    t.body_fat_pct,
  ]);
  const bmiTrend = trendOf(points, (w) => w.bmi);
  const muscleTrend = trendOf(points, (w) => w.muscle_mass_kg);
  const w = lastOf(weightTrend);
  const fat = lastOf(fatTrend);
  const bmi = lastOf(bmiTrend);
  const muscle = lastOf(muscleTrend);
  const wk = (trend: [number, number | null][], f: (v: number) => number = (v) => v) =>
    weekly(
      trend,
      ([x]) => dayOfPoint(x),
      ([, v]) => (v == null ? null : f(v)),
    ).map((x) => x.value);
  // Without weigh-ins in the period, fall back to the last weigh-in before it.
  const label = (p: { x: number } | null) =>
    p ? (
      <span className="basis-full">7-day trend · {fmtShortDate(dayOfPoint(p.x))}</span>
    ) : latest ? (
      <span className="basis-full">last weigh-in · {fmtShortDate(latest.measured_at)}</span>
    ) : null;
  const change = (d: number | null, digits: number, u: string) =>
    d == null ? null : (
      <>
        <Change
          value={d}
          digits={digits}
          unit={u}
          direction="neutral"
          title="Change of the 7-day trend over about 30 days"
        />
        <span>in 30 days</span>
      </>
    );
  return (
    <div className={TILE_GRID}>
      <MetricTile
        label="Weight"
        icon={<Scale size={14} />}
        value={w ? fmtNumber(wv(w.v), 1) : latest ? fmtNumber(wv(latest.weight_kg), 1) : DASH}
        unit={unit}
        delta={label(w)}
        sub={change(data.change_30d_kg == null ? null : wv(data.change_30d_kg), 1, unit)}
        spark={
          <Spark values={wk(weightTrend, wv)} color={col.weight} label="Weight trend, weekly" />
        }
      />
      <MetricTile
        label="BMI"
        icon={<Ruler size={14} />}
        value={fmtNumber(bmi?.v ?? latest?.bmi, 1)}
        delta={label(bmi)}
        sub={bmiNote(bmi?.v ?? latest?.bmi)}
        spark={<Spark values={wk(bmiTrend)} color={col.weight} label="BMI trend, weekly" />}
      />
      <MetricTile
        label="Body fat"
        icon={<Percent size={14} />}
        value={fmtNumber(fat?.v ?? latest?.body_fat_pct, 1)}
        unit="%"
        delta={label(fat)}
        sub={change(change30(fatTrend), 1, "pp")}
        spark={<Spark values={wk(fatTrend)} color={col.fat} label="Body fat trend, weekly" />}
      />
      <MetricTile
        label="Muscle mass"
        icon={<Dumbbell size={14} />}
        value={
          muscle
            ? fmtNumber(wv(muscle.v), 1)
            : latest?.muscle_mass_kg != null
              ? fmtNumber(wv(latest.muscle_mass_kg), 1)
              : DASH
        }
        unit={unit}
        delta={label(muscle)}
        sub={change(change30(muscleTrend) == null ? null : wv(change30(muscleTrend)!), 1, unit)}
        spark={
          <Spark
            values={wk(muscleTrend, wv)}
            color={col.muscle}
            label="Muscle mass trend, weekly"
          />
        }
      />
    </div>
  );
}

function HowToRecord({ kind }: { kind: "weight" | "pressure" }) {
  return kind === "weight" ? (
    <>
      Step on a Garmin Index smart scale, or log a weigh-in by hand in the Garmin Connect app
      (Health Stats → Weight → add). Garminizer imports it on the next sync; body-fat and muscle
      readings need a body-composition scale.
    </>
  ) : (
    <>
      Measure with a Garmin Index BPM monitor, or add a reading by hand in the Garmin Connect app
      (Health Stats → Blood Pressure → add). Readings appear here after the next sync.
    </>
  );
}

const PRESSURE_ROWS = 6;

function PressureTable({ readings }: { readings: Placed<Pressure>[] }) {
  const [all, setAll] = useState(false);
  const newest = [...readings].reverse();
  return (
    <>
      <table className="w-full text-sm tabular">
        <thead className="text-xs text-ink-3">
          <tr>
            <th scope="col" className="py-1.5 pr-3 text-left font-medium">
              Date
            </th>
            <th scope="col" className="py-1.5 pr-3 text-right font-medium">
              Reading
            </th>
            <th scope="col" className="py-1.5 text-right font-medium">
              Category
            </th>
          </tr>
        </thead>
        <tbody>
          {(all ? newest : newest.slice(0, PRESSURE_ROWS)).map((r) => (
            <tr key={r.item.measured_at} className="border-t border-line">
              <td className="py-2 pr-3 whitespace-nowrap">
                <span className="block text-ink">
                  {fmtWallDate(r.wall, { day: "numeric", month: "short", year: "numeric" })}
                </span>
                <span className="block text-xs text-ink-3">{fmtWallTime(r.wall)}</span>
              </td>
              <td className="py-2 pr-3 text-right whitespace-nowrap">
                <span className="block text-ink">
                  <span className="font-semibold">
                    {r.item.systolic}/{r.item.diastolic}
                  </span>
                  <span className="ml-1 text-xs text-ink-3">mmHg</span>
                </span>
                <span className="block text-xs text-ink-3">
                  {r.item.pulse != null ? `pulse ${r.item.pulse} bpm` : DASH}
                </span>
              </td>
              <td className="py-2 text-right">
                {r.item.category ? (
                  <StatusPill
                    status={pressureStatus(r.item.category)}
                    label={titleCase(r.item.category)}
                  />
                ) : (
                  DASH
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {newest.length > PRESSURE_ROWS && (
        <ShowAllButton
          total={newest.length}
          noun="readings"
          expanded={all}
          onToggle={() => setAll((v) => !v)}
        />
      )}
    </>
  );
}

export default function BodyPage() {
  const range = useRange("365d");
  const mode = useMode();
  const units = useUnits();
  const meta = api.useQuery("get", "/api/meta");
  const q = api.useQuery(
    "get",
    "/api/body",
    { params: { query: range.query } },
    { enabled: range.ready, placeholderData: keepPreviousData },
  );
  const tz = meta.data?.athlete?.time_zone;
  const ext = useMemo(
    () => dayExtent(range.query.start, range.query.end),
    [range.query.start, range.query.end],
  );
  const built = useMemo(() => {
    if (!q.data) return null;
    const wall = wallClock(tz);
    const points = place(q.data.weigh_ins, wall);
    const readings = place(q.data.blood_pressure, wall);
    const col = measureColors(mode);
    const unit = units === "metric" ? "kg" : "lb";
    const kg = (v: number | null) => (v == null ? null : weightValue(v, units));
    const weightTrend: [number, number | null][] = q.data.trend.map((t) => [
      dayPoint(t.day, 0)[0],
      kg(t.weight_kg),
    ]);
    const fatTrend: [number, number | null][] = q.data.trend.map((t) => [
      dayPoint(t.day, 0)[0],
      t.body_fat_pct,
    ]);
    const has = (f: (w: WeighIn) => number | null) => points.some((p) => f(p.item) != null);
    return {
      points,
      readings,
      weight: points.length
        ? measureOption({
            name: "Weight",
            points,
            value: (w) => kg(w.weight_kg),
            trend: weightTrend,
            color: col.weight,
            fmt: (v) => `${fmtNumber(v, 1)} ${unit}`,
            ext,
            mode,
          })
        : null,
      fat: has((w) => w.body_fat_pct)
        ? measureOption({
            name: "Body fat",
            points,
            value: (w) => w.body_fat_pct,
            trend: fatTrend,
            color: col.fat,
            fmt: (v) => `${fmtNumber(v, 1)} %`,
            ext,
            mode,
          })
        : null,
      muscle: has((w) => w.muscle_mass_kg)
        ? measureOption({
            name: "Muscle mass",
            points,
            value: (w) => kg(w.muscle_mass_kg),
            trend: trendOf(points, (w) => kg(w.muscle_mass_kg)),
            color: col.muscle,
            fmt: (v) => `${fmtNumber(v, 1)} ${unit}`,
            ext,
            mode,
          })
        : null,
      pressure: readings.length ? pressureOption(readings, ext, mode) : null,
    };
  }, [q.data, tz, mode, units, ext]);

  const unit = units === "metric" ? "kg" : "lb";
  return (
    <>
      <PageHeader
        title="Body"
        description={`${fmtDate(range.start)} – ${fmtDate(range.end)} · weight, body composition and blood pressure from your scale and monitor.`}
      />
      <div className="flex flex-col gap-5">
        {q.error ? (
          <ErrorState error={q.error} />
        ) : !q.data || !built ? (
          <TileSkeletons n={4} className={TILE_GRID} />
        ) : (
          <>
            {q.data.latest ? (
              <Tiles data={q.data} points={built.points} units={units} mode={mode} />
            ) : null}
            <div className="grid gap-5 lg:grid-cols-2">
              <Card
                title="Weight"
                subtitle={`Every weigh-in and the 7-day trend (${unit})`}
                className="lg:col-span-2"
              >
                {built.weight ? (
                  <Chart
                    option={built.weight}
                    height={280}
                    ariaLabel="Weigh-ins with 7-day weight trend"
                  />
                ) : (
                  <EmptyState title="No weigh-ins in this period">
                    <HowToRecord kind="weight" />
                  </EmptyState>
                )}
              </Card>
              {built.weight && (
                <>
                  <Card title="Body fat" subtitle="Per weigh-in and 7-day trend (%)">
                    {built.fat ? (
                      <Chart
                        option={built.fat}
                        height={220}
                        ariaLabel="Body fat percentage per weigh-in with 7-day trend"
                      />
                    ) : (
                      <EmptyState title="No body-fat readings in this period">
                        Body fat needs a body-composition scale such as the Garmin Index S2.
                      </EmptyState>
                    )}
                  </Card>
                  <Card title="Muscle mass" subtitle={`Per weigh-in and 7-day trend (${unit})`}>
                    {built.muscle ? (
                      <Chart
                        option={built.muscle}
                        height={220}
                        ariaLabel="Muscle mass per weigh-in with 7-day trend"
                      />
                    ) : (
                      <EmptyState title="No muscle-mass readings in this period">
                        Muscle mass needs a body-composition scale such as the Garmin Index S2.
                      </EmptyState>
                    )}
                  </Card>
                </>
              )}
              {built.pressure ? (
                <>
                  <Card
                    title="Blood pressure"
                    subtitle="Each bar spans diastolic to systolic (mmHg), with 120/80 for reference"
                  >
                    <Chart
                      option={built.pressure}
                      height={296}
                      ariaLabel="Blood pressure readings, diastolic to systolic"
                    />
                  </Card>
                  <Card
                    title="Blood pressure readings"
                    subtitle={`${built.readings.length} readings, newest first`}
                  >
                    <PressureTable readings={built.readings} />
                  </Card>
                </>
              ) : (
                <Card title="Blood pressure" className="lg:col-span-2">
                  <EmptyState title="No blood pressure readings in this period">
                    <HowToRecord kind="pressure" />
                  </EmptyState>
                </Card>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
