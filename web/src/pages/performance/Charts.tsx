/** Performance page cards: VO2max, endurance, race predictions, hill score, fitness age, efficiency. */
import { useNavigate } from "@tanstack/react-router";
import { clsx } from "clsx";
import { useMemo, useState } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, Delta, EmptyState, LegendItem, Segmented } from "@/components/ui";
import {
  axisTooltip,
  dayX,
  GRID,
  haloLine,
  itemTooltip,
  line,
  niceScale,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import {
  DASH,
  fmtDate,
  fmtDuration,
  fmtNumber,
  fmtPace,
  fmtPercent,
  fmtTimeDelta,
  smooth,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { sportColor } from "@/lib/sports";
import { CATEGORICAL, CHROME, DIVERGING, NEUTRAL, wash, barEnd } from "@/lib/tokens";
import {
  ENDURANCE_CLASSES,
  firstLast,
  RACES,
  sentenceCase,
  type RaceField,
  withGaps,
} from "./util";

type Series = Schemas["PerformanceSeries"];
type Efficiency = Schemas["PerformanceEfficiencyPoint"];

const longDay = (iso: string) =>
  fmtDate(iso, { weekday: "short", day: "numeric", month: "short", year: "numeric" });

function timeAxis(): Record<string, unknown> {
  return { type: "time", splitLine: { show: false }, axisLabel: { hideOverlap: true } };
}

/** Axis tooltip for time series: date of the hovered point + one row per series. */
function seriesTooltip(format: (v: number) => string) {
  return axisTooltip((p) => {
    const arr = p as { seriesName: string; color: string; value: [number, number] }[];
    const first = arr[0];
    if (!first) return "";
    const day = new Date(first.value[0]).toISOString().slice(0, 10);
    return (
      tooltipTitle(longDay(day)) +
      arr.map((a) => tooltipRow(a.color, a.seriesName, format(a.value[1]))).join("")
    );
  });
}

/** VO2max trend for running and cycling (sport colours). */
export function Vo2Card({ data }: { data: Series["vo2max"] }) {
  const mode = useMode();
  const lines = useMemo(
    () =>
      [
        {
          name: "Running",
          color: sportColor("run", mode),
          data: withGaps(
            data
              .filter((d) => d.running !== null)
              .map((d) => [dayX(d.day), d.running!] as [number, number]),
          ),
        },
        {
          name: "Cycling",
          color: sportColor("ride", mode),
          data: withGaps(
            data
              .filter((d) => d.cycling !== null)
              .map((d) => [dayX(d.day), d.cycling!] as [number, number]),
          ),
        },
      ].filter((l) => l.data.length > 0),
    [data, mode],
  );
  const option = useMemo<ChartOption>(
    () => ({
      grid: GRID,
      tooltip: seriesTooltip((v) => fmtNumber(v, 1)),
      xAxis: timeAxis(),
      yAxis: valueYAxis("ml/kg/min", (v) => fmtNumber(v), { scale: true, minInterval: 1 }),
      series: lines.map((l) => ({
        ...line(l.name, l.data, l.color),
        showSymbol: l.data.length < 40,
        symbolSize: 6,
      })),
    }),
    [lines],
  );
  return (
    <Card title="VO2max" subtitle="Garmin's estimate of your maximal oxygen uptake">
      {lines.length === 0 ? (
        <EmptyState title="No VO2max estimates in this period" />
      ) : (
        <>
          {lines.length > 1 && (
            <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
              {lines.map((l) => (
                <LegendItem key={l.name} shape="line" color={l.color} label={l.name} />
              ))}
            </div>
          )}
          <Chart
            option={option}
            zoom
            height={260}
            ariaLabel="VO2max for running and cycling over time"
          />
        </>
      )}
    </Card>
  );
}

/** Endurance score with Garmin's classification bands behind it. */
export function EnduranceCard({ data }: { data: Series["endurance"] }) {
  const mode = useMode();
  const points = useMemo(() => data.filter((d) => d.score !== null), [data]);
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const color = CATEGORICAL[mode][0]!;
    const scores = points.map((d) => d.score!);
    const step = 500;
    const lo = Math.floor((Math.min(...scores) - 200) / step) * step;
    const hi = Math.ceil((Math.max(...scores) + 200) / step) * step;
    const bands = ENDURANCE_CLASSES.map((k, i) => ({
      ...k,
      max: ENDURANCE_CLASSES[i + 1]?.min ?? Number.POSITIVE_INFINITY,
    }))
      .filter((b) => b.max > lo && b.min < hi)
      .map((b, i) => [
        {
          yAxis: Math.max(b.min, lo),
          name: sentenceCase(b.key),
          itemStyle: { color: wash(NEUTRAL[mode], i % 2 ? 0.05 : 0.14) },
        },
        { yAxis: Math.min(b.max, hi) },
      ]);
    return {
      grid: { ...GRID, right: 88 },
      tooltip: axisTooltip((p) => {
        const i = (p as { dataIndex: number }[])[0]?.dataIndex ?? -1;
        const d = points[i];
        if (!d) return "";
        return (
          tooltipTitle(longDay(d.day)) +
          tooltipRow(color, "Endurance score", fmtNumber(d.score)) +
          (d.classification
            ? `<div style="color:${c.muted};margin-top:4px">${sentenceCase(d.classification)}</div>`
            : "")
        );
      }),
      xAxis: timeAxis(),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v), { min: lo, max: hi, interval: step * 2 }),
      series: [
        {
          ...line(
            "Endurance score",
            points.map((d) => [dayX(d.day), d.score]),
            color,
          ),
          markArea: {
            silent: true,
            label: {
              show: true,
              // Outside the plot, in the right margin, so class names never sit on the line.
              position: "right",
              distance: 6,
              color: c.muted,
              fontSize: 11,
              width: 76,
              overflow: "break",
            },
            data: bands,
          },
        },
      ],
    };
  }, [points, mode]);
  return (
    <Card
      title="Endurance score"
      subtitle="Shaded bands: Garmin's endurance classes (reference thresholds)"
    >
      {points.length === 0 ? (
        <EmptyState title="No endurance score in this period" />
      ) : (
        <Chart
          option={option}
          zoom
          height={260}
          ariaLabel="Endurance score with classification bands"
        />
      )}
    </Card>
  );
}

/** Race predictions: four distances as tiles + the selected distance over time. */
export function RaceCard({
  data,
  latest,
  bests,
}: {
  data: Series["race_predictions"];
  latest: Series["latest"];
  bests: Map<number, number>;
}) {
  const mode = useMode();
  const units = useUnits();
  const [key, setKey] = useState("5k");
  const race = RACES.find((r) => r.key === key) ?? RACES[0]!;
  const color = sportColor("run", mode);
  const points = useMemo(() => data.filter((d) => d[race.field] !== null), [data, race.field]);
  const pr = bests.get(race.distance) ?? null;

  const option = useMemo<ChartOption>(() => {
    const values = points.map((d) => d[race.field]!);
    const all = pr !== null ? [...values, pr] : values;
    const axis = niceScale(
      Math.min(...all) - (Math.max(...all) - Math.min(...all)) * 0.05,
      Math.max(...all) + (Math.max(...all) - Math.min(...all)) * 0.05,
      { steps: [5, 10, 15, 20, 30, 60, 120, 300, 600, 900, 1800] },
    );
    return {
      grid: { ...GRID, top: 16, right: 16 },
      tooltip: axisTooltip((p) => {
        const i = (p as { dataIndex: number }[])[0]?.dataIndex ?? -1;
        const d = points[i];
        const s = d?.[race.field];
        if (!d || s === null || s === undefined) return "";
        return (
          tooltipTitle(longDay(d.day)) +
          tooltipRow(color, `${race.label} prediction`, fmtDuration(s)) +
          tooltipRow("transparent", "Pace", fmtPace(race.distance / s, units))
        );
      }),
      xAxis: timeAxis(),
      yAxis: valueYAxis(undefined, (v) => fmtDuration(v), {
        inverse: true,
        ...axis,
      }),
      series: [
        {
          ...line(
            `${race.label} prediction`,
            points.map((d) => [dayX(d.day), d[race.field]]),
            color,
          ),
          ...(pr !== null ? { markLine: haloLine(pr, `Your best ${fmtDuration(pr)}`, mode) } : {}),
        },
      ],
    };
  }, [points, race, pr, color, units, mode]);

  return (
    <Card
      className="lg:col-span-2"
      title="Race predictions"
      subtitle="Garmin's predicted finish times from your VO2max and training history; faster is up"
      actions={
        <Segmented
          size="sm"
          label="Race distance"
          value={key}
          onChange={setKey}
          options={RACES.map((r) => ({ value: r.key, label: r.label }))}
        />
      }
    >
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="grid grid-cols-2 gap-3 self-start lg:col-span-2">
          {RACES.map((r) => (
            <RaceTile
              key={r.key}
              label={r.label}
              field={r.field}
              distance={r.distance}
              data={data}
              latest={latest[r.field]}
              selected={r.key === key}
            />
          ))}
        </div>
        <div className="min-w-0 lg:col-span-3">
          {points.length === 0 ? (
            <EmptyState title={`No ${race.label} predictions in this period`} />
          ) : (
            <Chart
              option={option}
              zoom
              height={250}
              ariaLabel={`Predicted ${race.label} finish time over time`}
            />
          )}
        </div>
      </div>
    </Card>
  );
}

function RaceTile({
  label,
  field,
  distance,
  data,
  latest,
  selected,
}: {
  label: string;
  field: RaceField;
  distance: number;
  data: Series["race_predictions"];
  latest: number | null;
  selected: boolean;
}) {
  const units = useUnits();
  const change = firstLast(data, (d) => d[field]);
  return (
    <div
      className={clsx(
        "rounded-card border p-3",
        selected ? "border-accent bg-surface ring-1 ring-accent" : "border-line bg-surface-2",
      )}
    >
      <p className="text-xs font-medium text-ink-2">{label}</p>
      <p className="mt-1 text-xl leading-tight font-semibold text-ink">{fmtDuration(latest)}</p>
      <p className="text-xs text-ink-3">{latest ? fmtPace(distance / latest, units) : DASH}</p>
      {change && (
        <div className="mt-1.5">
          <Delta
            value={change.last - change.first}
            text={fmtTimeDelta(change.last - change.first)}
            direction="down-good"
          />
        </div>
      )}
    </div>
  );
}

/** Hill score with its endurance and strength components. */
export function HillCard({ data }: { data: Series["hill"] }) {
  const mode = useMode();
  const lines = useMemo(() => {
    const cat = CATEGORICAL[mode];
    const pick = (k: "score" | "endurance" | "strength") =>
      data.filter((d) => d[k] !== null).map((d) => [dayX(d.day), d[k]!]);
    return [
      { name: "Hill score", color: cat[0]!, data: pick("score"), area: true },
      { name: "Endurance", color: cat[1]!, data: pick("endurance"), area: false },
      { name: "Strength", color: cat[2]!, data: pick("strength"), area: false },
    ].filter((l) => l.data.length > 0);
  }, [data, mode]);
  const option = useMemo<ChartOption>(
    () => ({
      grid: GRID,
      tooltip: seriesTooltip((v) => fmtNumber(v)),
      xAxis: timeAxis(),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v), {
        min: (v: { min: number }) => Math.max(0, Math.floor((v.min - 3) / 10) * 10),
        max: (v: { max: number }) => Math.min(100, Math.ceil((v.max + 3) / 10) * 10),
      }),
      series: lines.map((l) => line(l.name, l.data, l.color, { area: l.area })),
    }),
    [lines],
  );
  return (
    <Card title="Hill score" subtitle="Climbing ability (1–100) from hill endurance and strength">
      {lines.length === 0 ? (
        <EmptyState title="No hill score in this period" />
      ) : (
        <>
          <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
            {lines.map((l) => (
              <LegendItem key={l.name} shape="line" color={l.color} label={l.name} />
            ))}
          </div>
          <Chart
            option={option}
            zoom
            height={240}
            ariaLabel="Hill score with endurance and strength components over time"
          />
        </>
      )}
    </Card>
  );
}

/** Fitness age against chronological age. */
export function FitnessAgeCard({ data, age }: { data: Series["fitness_age"]; age: number | null }) {
  const mode = useMode();
  const points = useMemo(() => data.filter((d) => d.value !== null), [data]);
  const option = useMemo<ChartOption>(() => {
    const color = CATEGORICAL[mode][0]!;
    const values = points.map((d) => d.value!);
    const all = age !== null ? [...values, age] : values;
    return {
      grid: { ...GRID, top: 16, right: 16 },
      tooltip: seriesTooltip((v) => `${fmtNumber(v, 1)} yrs`),
      xAxis: timeAxis(),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v), {
        ...niceScale(Math.min(...all) - 1, Math.max(...all) + 1, { steps: [1, 2, 5, 10] }),
      }),
      series: [
        {
          ...line(
            "Fitness age",
            points.map((d) => [dayX(d.day), d.value]),
            color,
            { area: false },
          ),
          ...(age !== null ? { markLine: haloLine(age, `Your age ${age}`, mode) } : {}),
        },
      ],
    };
  }, [points, age, mode]);
  return (
    <Card title="Fitness age" subtitle="The age your fitness corresponds to, against your real age">
      {points.length === 0 ? (
        <EmptyState title="No fitness age in this period" />
      ) : (
        <Chart
          option={option}
          zoom
          height={260}
          ariaLabel="Fitness age over time against real age"
        />
      )}
    </Card>
  );
}

const DECOUPLING_GUIDE = 5;
const BIN = 2.5;

function histogram(values: number[]) {
  const lo = Math.min(0, Math.max(-10, Math.floor(Math.min(...values) / BIN) * BIN));
  const hi = Math.max(10, Math.min(15, Math.ceil(Math.max(...values) / BIN) * BIN));
  const n = Math.round((hi - lo) / BIN);
  const counts = Array.from({ length: n }, () => 0);
  for (const v of values) {
    const x = Math.min(Math.max(v, lo), hi - 1e-9);
    counts[Math.floor((x - lo) / BIN)]! += 1;
  }
  return { lo, hi, counts };
}

/** Efficiency factor per run over time and the aerobic-decoupling distribution. */
export function EfficiencyCard({ data }: { data: Efficiency[] }) {
  const mode = useMode();
  const units = useUnits();
  const navigate = useNavigate();
  const decoupling = useMemo(
    () => data.map((d) => d.aerobic_decoupling_pct).filter((v): v is number => v !== null),
    [data],
  );
  const runs = Math.min(10, Math.max(3, Math.round(data.length / 8)));

  const efOption = useMemo<ChartOption>(() => {
    const color = sportColor("run", mode);
    const c = CHROME[mode];
    const mean = smooth(
      data.map((d) => d.efficiency_factor),
      runs,
    );
    return {
      grid: GRID,
      tooltip: itemTooltip((p) => {
        const it = p as { seriesIndex: number; dataIndex: number };
        const d = data[it.dataIndex];
        if (!d) return "";
        if (it.seriesIndex === 1)
          return (
            tooltipTitle(longDay(d.day)) +
            tooltipRow(color, `${runs}-run average`, fmtNumber(mean[it.dataIndex], 2))
          );
        return (
          tooltipTitle(d.name ?? "Run") +
          `<div style="color:${c.muted};margin:-2px 0 6px">${fmtDate(d.day)}</div>` +
          tooltipRow(NEUTRAL[mode], "Efficiency factor", fmtNumber(d.efficiency_factor, 2)) +
          tooltipRow("transparent", "Pace", fmtPace(d.avg_speed_mps, units)) +
          tooltipRow("transparent", "Avg heart rate", d.avg_hr ? `${d.avg_hr} bpm` : DASH) +
          (d.aerobic_decoupling_pct !== null
            ? tooltipRow("transparent", "Decoupling", fmtPercent(d.aerobic_decoupling_pct, 1))
            : "")
        );
      }),
      xAxis: timeAxis(),
      yAxis: valueYAxis(undefined, (v) => fmtNumber(v, 2), { scale: true }),
      series: [
        {
          type: "scatter",
          name: "Each run",
          symbolSize: 7,
          cursor: "pointer",
          itemStyle: { color: NEUTRAL[mode], opacity: 0.75 },
          data: data.map((d) => [dayX(d.day), d.efficiency_factor, d.activity_id]),
        },
        line(
          `${runs}-run average`,
          data.map((d, i) => [dayX(d.day), mean[i]]),
          color,
          { z: 3 },
        ),
      ],
    };
  }, [data, mode, units, runs]);

  const hist = useMemo(() => (decoupling.length ? histogram(decoupling) : null), [decoupling]);
  const histOption = useMemo<ChartOption>(() => {
    if (!hist) return {};
    const div = DIVERGING[mode];
    const centers = hist.counts.map((_, i) => hist.lo + (i + 0.5) * BIN);
    const label = (i: number) => {
      const a = hist.lo + i * BIN;
      const b = a + BIN;
      if (i === 0 && a <= -10) return `≤ ${fmtNumber(b, 1)} %`;
      if (i === hist.counts.length - 1 && b >= 15) return `≥ ${fmtNumber(a, 1)} %`;
      return `${fmtNumber(a, 1)} to ${fmtNumber(b, 1)} %`;
    };
    const split = (well: boolean) =>
      hist.counts.map((n, i) => {
        const end = hist.lo + (i + 1) * BIN;
        return [centers[i], end <= DECOUPLING_GUIDE === well ? n || null : null];
      });
    const series = (name: string, well: boolean, color: string) => ({
      type: "bar",
      name,
      stack: "runs",
      barWidth: "86%",
      data: split(well),
      itemStyle: { color, borderRadius: barEnd("up") },
    });
    return {
      grid: { ...GRID, right: 16 },
      tooltip: itemTooltip((p) => {
        const it = p as { dataIndex: number; color: string };
        const n = hist.counts[it.dataIndex] ?? 0;
        return tooltipRow(it.color, label(it.dataIndex), `${n} ${n === 1 ? "run" : "runs"}`);
      }),
      xAxis: {
        type: "value",
        min: hist.lo,
        max: hist.hi,
        interval: BIN * 2,
        splitLine: { show: false },
        axisLabel: { formatter: (v: number) => `${fmtNumber(v)} %`, hideOverlap: true },
      },
      yAxis: valueYAxis("runs", (v) => fmtNumber(v), { minInterval: 1 }),
      series: [
        {
          ...series(`Under ${DECOUPLING_GUIDE} %`, true, div.negative),
          markLine: haloLine(DECOUPLING_GUIDE, `${DECOUPLING_GUIDE} %`, mode, "x"),
        },
        series(`${DECOUPLING_GUIDE} % or more`, false, div.positive),
      ],
    };
  }, [hist, mode]);

  const well = decoupling.filter((v) => v < DECOUPLING_GUIDE).length;
  const color = sportColor("run", mode);
  return (
    <Card
      className="lg:col-span-2"
      title="Running efficiency"
      subtitle="Efficiency factor = speed per heartbeat (m/min per bpm); rising means more speed for the same effort"
    >
      {data.length === 0 ? (
        <EmptyState title="No runs with heart rate in this period" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="min-w-0 lg:col-span-3">
            <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
              <LegendItem color={NEUTRAL[mode]} label={`Each run · ${data.length}`} />
              <LegendItem shape="line" color={color} label={`${runs}-run average`} />
            </div>
            <Chart
              option={efOption}
              zoom
              height={260}
              ariaLabel="Efficiency factor per run with a rolling average"
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
          <div className="min-w-0 lg:col-span-2">
            <p className="mb-1 text-xs font-medium text-ink-2">Aerobic decoupling per run</p>
            {hist ? (
              <>
                <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1.5">
                  <LegendItem color={DIVERGING[mode].negative} label="Well paced (< 5 %)" />
                  <LegendItem color={DIVERGING[mode].positive} label="Drifting (≥ 5 %)" />
                </div>
                <Chart
                  option={histOption}
                  height={210}
                  ariaLabel="Distribution of aerobic decoupling across runs"
                />
                <p className="mt-2 text-xs text-ink-3">
                  <span className="font-medium text-ink-2">
                    {well} of {decoupling.length} runs (
                    {fmtPercent((well / decoupling.length) * 100)})
                  </span>{" "}
                  stayed under 5 %: heart rate held steady against pace, the mark of a well-paced
                  aerobic effort. More drift means the pace outran your aerobic base.
                </p>
              </>
            ) : (
              <EmptyState title="No decoupling data" />
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
