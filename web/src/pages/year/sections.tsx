/** Year-in-review sections (page-local components). */
import { Link } from "@tanstack/react-router";
import {
  BedDouble,
  Flame,
  Footprints,
  Gauge,
  HeartPulse,
  Mountain,
  Route,
  Timer,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { createElement, useMemo, useState, type ReactNode } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { SportBadge, SportIcon } from "@/components/SportIcon";
import { Card, Delta, EmptyState, ScrollArea, Segmented } from "@/components/ui";
import {
  axisTooltip,
  bars,
  categoryXAxis,
  GRID_WITH_LEGEND,
  legend,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import {
  DASH,
  distanceUnit,
  distanceValue,
  fmtDelta,
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  fmtHours,
  fmtNumber,
  fmtPace,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { sportColor, sportLabel } from "@/lib/sports";
import { CATEGORICAL, CHROME, NEUTRAL, type Mode } from "@/lib/tokens";
import {
  calendarHeatmapOption,
  heatmapLayout,
  quantileBins,
  restColor,
  useElementWidth,
} from "@/lib/heatmap";

type Review = Schemas["YearReview"];
type Summary = Schemas["ActivitySummary"];

const MONTHS = Array.from({ length: 12 }, (_, i) =>
  new Date(2000, i, 15).toLocaleDateString(undefined, { month: "short" }),
);

function monthName(m: number): string {
  return new Date(2000, m - 1, 15).toLocaleDateString(undefined, { month: "long" });
}

/* ---------------------------------------------------------------- hero */

function HeroFigure({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-3">{label}</dt>
      <dd className="mt-1 text-[22px] leading-tight font-semibold text-ink">{value}</dd>
      {sub && <dd className="text-xs text-ink-3">{sub}</dd>}
    </div>
  );
}

const round0 = (v: number | null) => (v === null ? null : Math.round(v));

const EARTH_KM = 40_075;
const EVEREST_M = 8_849;

export function Hero({
  r,
  start,
  end,
  compare,
}: {
  r: Review;
  /** First and last day with data inside the year. */
  start: string;
  end: string;
  compare: { label: string; distance_m: number; duration_s: number; activities: number } | null;
}) {
  const units = useUnits();
  const t = r.totals;
  const dist = fmtDistance(t.distance_m, units, 0).split(" ")[0];
  const pct = (a: number, b: number) => (b > 0 ? ((a - b) / b) * 100 : null);
  const dDist = compare ? pct(t.distance_m, compare.distance_m) : null;
  const dTime = compare ? pct(t.moving_s || t.duration_s, compare.duration_s) : null;
  const dActs = compare ? pct(t.activities, compare.activities) : null;
  const partialEnd = end < `${r.year}-12-31`;
  const lateStart = start > `${r.year}-01-01`;
  const period =
    lateStart && partialEnd
      ? ` · ${fmtDate(start, { day: "numeric", month: "short" })} – ${fmtDate(end)}`
      : lateStart
        ? ` · since ${fmtDate(start)}`
        : partialEnd
          ? ` so far · through ${fmtDate(end)}`
          : " in total";
  const covered =
    Math.round(
      (new Date(`${end}T12:00:00`).getTime() - new Date(`${start}T12:00:00`).getTime()) /
        86_400_000,
    ) + 1;
  const facts: string[] = [];
  if (t.distance_m > 0)
    facts.push(
      `${fmtNumber((t.distance_m / 1000 / EARTH_KM) * 100, 1)} % of the way around the Earth`,
    );
  if (t.elevation_gain_m > EVEREST_M / 2)
    facts.push(`${fmtNumber(t.elevation_gain_m / EVEREST_M, 1)} × the height of Everest`);
  return (
    <section
      className="rounded-2xl border border-line bg-surface p-5 shadow-card sm:p-7"
      style={{
        // A faint accent tint (kept light enough that muted text still clears 4.5:1).
        background:
          "linear-gradient(135deg, color-mix(in srgb, var(--accent) 7%, var(--surface-1)) 0%, var(--surface-1) 65%)",
      }}
    >
      <h2 className="sr-only">Year totals</h2>
      <div className="grid items-center gap-6 lg:grid-cols-[1.15fr_1fr] lg:gap-10">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-2">
            {r.year}
            {period}
          </p>
          <p className="mt-2 flex flex-wrap items-baseline gap-x-3">
            <span className="text-[56px] leading-none font-semibold tracking-tight text-ink sm:text-[76px]">
              {dist}
            </span>
            <span className="text-2xl font-medium text-ink-3">{distanceUnit(units)}</span>
          </p>
          <p className="mt-3 max-w-lg text-sm text-ink-2">
            {fmtNumber(t.activities)} activities on {fmtNumber(t.active_days)} days and{" "}
            {fmtNumber((t.moving_s || t.duration_s) / 3600)} hours on the move
            {facts.length ? ` — ${facts.join(" and ")}.` : "."}
          </p>
          {compare && (
            <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-3">
              <span>{compare.label}</span>
              <Delta value={round0(dDist)} text={`${fmtDelta(dDist, 0, "%")} distance`} />
              <Delta value={round0(dTime)} text={`${fmtDelta(dTime, 0, "%")} time`} />
              <Delta value={round0(dActs)} text={`${fmtDelta(dActs, 0, "%")} activities`} />
            </p>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3">
          <HeroFigure label="Moving time" value={fmtHours(t.moving_s || t.duration_s)} />
          <HeroFigure label="Elevation gain" value={fmtElevation(t.elevation_gain_m, units)} />
          <HeroFigure label="Activities" value={fmtNumber(t.activities)} />
          <HeroFigure
            label="Active days"
            value={fmtNumber(t.active_days)}
            sub={`${fmtNumber((t.active_days / Math.max(covered, 1)) * 100)} % of days`}
          />
          <HeroFigure
            label={`Longest streak in ${r.year}`}
            value={`${fmtNumber(r.longest_streak)} ${r.longest_streak === 1 ? "day" : "days"}`}
          />
          <HeroFigure
            label="New map tiles"
            value={fmtNumber(r.new_tiles)}
            sub={
              r.new_tiles > 0 ? (
                <Link to="/map" className="underline underline-offset-2 hover:text-ink">
                  explore the map
                </Link>
              ) : (
                "first visits this year"
              )
            }
          />
        </dl>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- highlights */

const HIGHLIGHTS: {
  key: keyof Review["highlights"];
  label: string;
  icon: LucideIcon;
  value: (a: Summary, units: ReturnType<typeof useUnits>) => string;
  unit?: string;
}[] = [
  {
    key: "longest_distance",
    label: "Longest distance",
    icon: Route,
    value: (a, u) => fmtDistance(a.distance_m, u),
  },
  {
    key: "longest_duration",
    label: "Longest duration",
    icon: Timer,
    value: (a) => fmtHours(a.duration_s),
  },
  {
    key: "most_elevation",
    label: "Most climbing",
    icon: Mountain,
    value: (a, u) => fmtElevation(a.elevation_gain_m, u),
  },
  {
    key: "hardest_load",
    label: "Hardest session",
    icon: Flame,
    value: (a) => fmtNumber(a.training_load),
    unit: "training load",
  },
];

export function Highlights({ r }: { r: Review }) {
  const units = useUnits();
  const items = HIGHLIGHTS.map((h) => ({ ...h, a: r.highlights[h.key] })).filter(
    (h): h is typeof h & { a: Summary } => h.a !== null,
  );
  if (!items.length) return null;
  return (
    <section aria-labelledby="highlights-title">
      <h2 id="highlights-title" className="mb-3 text-sm font-semibold text-ink">
        Highlights
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {items.map((h) => (
          <Link
            key={h.key}
            to="/activities/$activityId"
            params={{ activityId: String(h.a.activity_id) }}
            className="group flex min-w-0 flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-card transition-colors hover:border-line-strong hover:bg-surface-2"
          >
            <span className="flex items-center gap-2 text-xs font-medium text-ink-2">
              {createElement(h.icon, { size: 15, "aria-hidden": true, className: "text-ink-3" })}
              {h.label}
            </span>
            <span className="flex items-baseline gap-1.5">
              <span className="text-[26px] leading-none font-semibold text-ink">
                {h.value(h.a, units)}
              </span>
              {h.unit && <span className="text-sm text-ink-3">{h.unit}</span>}
            </span>
            <span className="flex min-w-0 items-start gap-2 text-xs text-ink-3">
              <span className="mt-px shrink-0">
                <SportIcon group={h.a.sport_group} size={14} colored />
              </span>
              <span className="min-w-0">
                <span className="font-medium text-ink-2 group-hover:text-ink">
                  {h.a.name ?? sportLabel(h.a.sport_group)}
                </span>{" "}
                · {fmtDate(h.a.start_time_local, { day: "numeric", month: "short" })}
              </span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- by sport */

type SportMetric = "time" | "distance" | "count";

export function BySport({ r }: { r: Review }) {
  const mode = useMode();
  const units = useUnits();
  const [metric, setMetric] = useState<SportMetric>("time");
  const value = (s: Review["by_sport"][number]) =>
    metric === "time" ? s.duration_s : metric === "distance" ? s.distance_m : s.activities;
  const rows = r.by_sport.filter((s) => value(s) > 0).sort((a, b) => value(b) - value(a));
  const total = rows.reduce((n, s) => n + value(s), 0);
  const max = Math.max(1, ...rows.map(value));
  const fmt = (v: number) =>
    metric === "time"
      ? fmtHours(v)
      : metric === "distance"
        ? fmtDistance(v, units, 0)
        : `${fmtNumber(v)} ×`;
  return (
    <Card
      title="By sport"
      subtitle="Share of your year"
      actions={
        <Segmented
          size="sm"
          label="Sport breakdown metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "time", label: "Time" },
            { value: "distance", label: "Distance" },
            { value: "count", label: "Activities" },
          ]}
        />
      }
    >
      {!rows.length ? (
        <EmptyState title="No activities this year" />
      ) : (
        <ul className="flex flex-col gap-3.5">
          {rows.map((s) => (
            <li key={s.sport_group} className="flex items-center gap-3">
              <SportBadge group={s.sport_group} size={34} />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="truncate font-medium text-ink">{sportLabel(s.sport_group)}</span>
                  <span className="shrink-0 text-ink tabular">
                    {fmt(value(s))}
                    <span className="ml-1.5 text-xs text-ink-3">
                      {fmtNumber((value(s) / total) * 100)} %
                    </span>
                  </span>
                </div>
                <div aria-hidden className="mt-1.5 h-2 rounded-full bg-surface-2">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${(value(s) / max) * 100}%`,
                      minWidth: 6,
                      background: sportColor(s.sport_group, mode),
                    }}
                  />
                </div>
                <p className="mt-1 truncate text-xs text-ink-3">
                  {fmtNumber(s.activities)} {s.activities === 1 ? "activity" : "activities"} ·{" "}
                  {fmtHours(s.duration_s)}
                  {s.distance_m > 0 ? ` · ${fmtDistance(s.distance_m, units, 0)}` : ""}
                  {s.elevation_gain_m > 0 ? ` · ${fmtElevation(s.elevation_gain_m, units)} up` : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* ---------------------------------------------------------------- monthly */

type MonthMetric = "distance" | "time";

function monthlyOption(
  r: Review,
  prev: Review | null,
  metric: MonthMetric,
  units: ReturnType<typeof useUnits>,
  mode: Mode,
): ChartOption {
  const c = CHROME[mode];
  const accent = CATEGORICAL[mode][0]!;
  const conv = (m: Review["monthly"][number]) =>
    metric === "distance" ? distanceValue(m.distance_m, units) : m.duration_s / 3600;
  const cur = r.monthly.map(conv);
  const best = cur.indexOf(Math.max(...cur));
  const unit = metric === "distance" ? distanceUnit(units) : "h";
  const fmt = (v: number) => (metric === "distance" ? fmtNumber(v) : fmtHours(v * 3600));
  const series = [
    {
      ...bars(
        String(r.year),
        cur.map((v, i) =>
          i === best && v > 0
            ? {
                value: v,
                label: {
                  show: true,
                  position: "top",
                  color: c.text2,
                  fontSize: 11,
                  formatter: "Best",
                },
              }
            : v,
        ),
        accent,
        mode,
        { barMaxWidth: 18 },
      ),
      z: 3,
    },
  ];
  if (prev)
    series.push({
      ...bars(String(prev.year), prev.monthly.map(conv), NEUTRAL[mode], mode, { barMaxWidth: 18 }),
      z: 2,
    });
  return {
    grid: GRID_WITH_LEGEND,
    legend: { ...legend(prev !== null), left: "auto", right: 0 },
    tooltip: axisTooltip(
      (p) => {
        const arr = p as { seriesName: string; color: string; value: number; dataIndex: number }[];
        const i = arr[0]?.dataIndex ?? 0;
        return (
          tooltipTitle(monthName(i + 1)) +
          arr
            .map((a) =>
              tooltipRow(
                a.color,
                a.seriesName,
                `${fmt(Number(a.value))} ${metric === "distance" ? unit : ""}`,
              ),
            )
            .join("")
        );
      },
      { axisPointer: { type: "shadow" } },
    ),
    xAxis: categoryXAxis(MONTHS),
    yAxis: valueYAxis(unit, (v) => fmtNumber(v)),
    series,
  };
}

export function Monthly({ r, prev }: { r: Review; prev: Review | null }) {
  const mode = useMode();
  const units = useUnits();
  const [metric, setMetric] = useState<MonthMetric>("distance");
  const option = useMemo(
    () => monthlyOption(r, prev, metric, units, mode),
    [r, prev, metric, units, mode],
  );
  const any = r.monthly.some((m) => m.distance_m > 0 || m.duration_s > 0);
  return (
    <Card
      title="Month by month"
      className="flex flex-col"
      bodyClassName="flex min-h-[300px] flex-1 flex-col"
      subtitle={
        r.best_month
          ? `Biggest month ${monthName(r.best_month.month)} · ${fmtDistance(r.best_month.distance_m, units, 0)}`
          : "Distance and time per month"
      }
      actions={
        <Segmented
          size="sm"
          label="Monthly metric"
          value={metric}
          onChange={setMetric}
          options={[
            { value: "distance", label: "Distance" },
            { value: "time", label: "Time" },
          ]}
        />
      }
    >
      {!any ? (
        <EmptyState title="No activities this year" />
      ) : (
        <Chart
          option={option}
          height="100%"
          className="min-h-0 flex-1"
          ariaLabel={`${metric === "distance" ? "Distance" : "Moving time"} per month in ${r.year}${prev ? ` compared with ${prev.year}` : ""}`}
        />
      )}
    </Card>
  );
}

/* ---------------------------------------------------------------- heatmap */

export function YearHeatmap({ r, start, end }: { r: Review; start: string; end: string }) {
  const mode = useMode();
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const values = useMemo(() => new Map(r.days.map((d) => [d.day, d.duration_s])), [r.days]);
  const byDay = useMemo(() => new Map(r.days.map((d) => [d.day, d])), [r.days]);
  const bins = useMemo(
    () =>
      quantileBins(
        [...values.values()],
        mode,
        (v) => Math.max(300, Math.round(v / (v < 3600 ? 300 : 900)) * (v < 3600 ? 300 : 900)),
        (v) => fmtHours(v),
      ),
    [values, mode],
  );
  const layout = useMemo(
    () => (width > 0 && start <= end ? heatmapLayout(width, start, end) : null),
    [width, start, end],
  );
  const option = useMemo(
    () =>
      layout
        ? calendarHeatmapOption({
            layout,
            values,
            bins,
            mode,
            label: "duration",
            tooltip: (day) => {
              const d = byDay.get(day);
              const title = tooltipTitle(
                fmtDate(day, { weekday: "short", day: "numeric", month: "short", year: "numeric" }),
              );
              const line = (k: string, v: string) =>
                `<div style="display:flex;justify-content:space-between;gap:16px;min-width:160px"><span>${k}</span><b style="font-variant-numeric:tabular-nums">${v}</b></div>`;
              return d
                ? title +
                    line("Duration", fmtHours(d.duration_s)) +
                    line("Training load", fmtNumber(d.training_load))
                : `${title}<div style="color:${CHROME[mode].muted}">Rest day</div>`;
            },
          })
        : null,
    [layout, values, bins, mode, byDay],
  );
  const chart = option ? (
    <Chart
      option={option}
      height={layout!.height}
      ariaLabel={`Calendar heatmap of daily training time in ${r.year}`}
    />
  ) : null;
  return (
    <Card
      title={`Every day of ${r.year}`}
      subtitle={`Daily training time · ${mode === "dark" ? "brighter" : "darker"} = longer`}
    >
      <div ref={measure} className="w-full">
        {!bins.length ? <EmptyState title="No activities this year" /> : chart}
      </div>
      {bins.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-2">
          {[{ color: restColor(mode), label: "Rest day" }, ...bins].map((b) => (
            <span key={b.label} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block size-2.5 rounded-[3px]"
                style={{ background: b.color }}
              />
              {b.label}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

/* ---------------------------------------------------------------- best efforts */

/** Signed time difference: "no change", "+9 s", "−2 min 13 s". */
function fmtDeltaSeconds(s: number): string {
  if (s === 0) return "no change";
  const a = Math.abs(s);
  const sign = s > 0 ? "+" : "−";
  if (a < 60) return `${sign}${a} s`;
  const m = Math.floor(a / 60);
  const sec = a % 60;
  return `${sign}${m} min${sec ? ` ${sec} s` : ""}`;
}

const EFFORT_LABEL: Record<string, string> = {
  "400": "400 m",
  "1000": "1 km",
  "1609.344": "1 mile",
  "5000": "5K",
  "10000": "10K",
  "15000": "15K",
  "21097.5": "Half marathon",
  "30000": "30K",
  "42195": "Marathon",
};

export function BestEfforts({
  r,
  prev,
  className,
}: {
  r: Review;
  prev: Review | null;
  className?: string;
}) {
  const units = useUnits();
  const before = new Map(prev?.best_efforts.map((e) => [e.distance_m, e.seconds]) ?? []);
  return (
    <Card
      title="Best running efforts"
      className={className}
      subtitle={`Fastest time over each distance in ${r.year}${prev ? ` · compared with ${prev.year}` : ""}`}
    >
      {!r.best_efforts.length ? (
        <EmptyState title="No running efforts this year" />
      ) : (
        <ScrollArea label="Best efforts table" className="-mx-1 overflow-x-auto px-1">
          <table className="w-full text-sm tabular">
            <thead>
              <tr className="border-b border-line text-xs text-ink-3">
                <th scope="col" className="py-2 pr-3 text-left font-medium">
                  Distance
                </th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">
                  Time
                </th>
                <th scope="col" className="hidden py-2 pr-3 text-right font-medium sm:table-cell">
                  Pace
                </th>
                {prev && (
                  <th scope="col" className="py-2 pr-3 text-right font-medium">
                    vs {prev.year}
                  </th>
                )}
                <th scope="col" className="py-2 text-right font-medium">
                  Date
                </th>
              </tr>
            </thead>
            <tbody>
              {r.best_efforts.map((e) => {
                const was = before.get(e.distance_m);
                const diff = was !== undefined ? Math.round(e.seconds - was) : null;
                return (
                  <tr key={e.distance_m} className="border-b border-line last:border-0">
                    <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">
                      {EFFORT_LABEL[String(e.distance_m)] ?? fmtDistance(e.distance_m, units)}
                    </th>
                    <td className="py-2 pr-3 text-right font-semibold text-ink">
                      {fmtDuration(e.seconds)}
                    </td>
                    <td className="hidden py-2 pr-3 text-right whitespace-nowrap text-ink-2 sm:table-cell">
                      {fmtPace(e.distance_m / e.seconds, units)}
                    </td>
                    {prev && (
                      <td className="py-2 pr-3 text-right whitespace-nowrap">
                        {diff === null ? (
                          <span className="text-xs text-ink-3">new</span>
                        ) : (
                          <Delta value={diff} text={fmtDeltaSeconds(diff)} direction="down-good" />
                        )}
                      </td>
                    )}
                    <td className="py-2 text-right whitespace-nowrap">
                      <Link
                        to="/activities/$activityId"
                        params={{ activityId: String(e.activity_id) }}
                        className="text-ink-2 underline-offset-2 hover:text-ink hover:underline"
                      >
                        {fmtDate(e.day, { day: "numeric", month: "short" })}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ScrollArea>
      )}
    </Card>
  );
}

/* ---------------------------------------------------------------- health */

function Fact({
  icon,
  label,
  value,
  sub,
}: {
  icon: LucideIcon;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-surface-2 text-ink-3">
        {createElement(icon, { size: 16, "aria-hidden": true })}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm text-ink-2">{label}</p>
        {sub && <p className="text-xs text-ink-3">{sub}</p>}
      </div>
      <div className="shrink-0 text-right text-sm font-semibold text-ink tabular">{value}</div>
    </div>
  );
}

function FirstLast({
  first,
  last,
  digits,
  unit,
  direction,
}: {
  first: number | null;
  last: number | null;
  digits: number;
  unit: string;
  direction: "up-good" | "down-good";
}) {
  if (first === null || last === null) return <>{DASH}</>;
  const d = last - first;
  return (
    <span className="flex flex-col items-end">
      <span>
        {fmtNumber(first, digits)} → {fmtNumber(last, digits)}
        <span className="ml-1 text-xs font-normal text-ink-3">{unit}</span>
      </span>
      <Delta
        value={Math.round(d * 10 ** digits) / 10 ** digits}
        text={fmtDelta(d, digits)}
        direction={direction}
      />
    </span>
  );
}

export function Health({ r, className }: { r: Review; className?: string }) {
  return (
    <Card title="Health & body" subtitle="Daily data across the year" className={className}>
      <div className="divide-y divide-line">
        <Fact
          icon={BedDouble}
          label="Average sleep"
          sub={r.sleep.avg_score !== null ? `score ${fmtNumber(r.sleep.avg_score)}` : undefined}
          value={fmtHours(r.sleep.avg_duration_s)}
        />
        <Fact
          icon={Footprints}
          label="Steps"
          sub={r.steps.avg !== null ? `${fmtNumber(r.steps.avg)} per day` : undefined}
          value={fmtNumber(r.steps.total)}
        />
        <Fact
          icon={Gauge}
          label="VO2 max (running)"
          sub="first → last reading"
          value={
            <FirstLast
              first={r.vo2max.first}
              last={r.vo2max.last}
              digits={1}
              unit=""
              direction="up-good"
            />
          }
        />
        <Fact
          icon={HeartPulse}
          label="Resting heart rate"
          sub="first vs last 30 days"
          value={
            <FirstLast
              first={r.resting_hr.first_30d_avg}
              last={r.resting_hr.last_30d_avg}
              digits={1}
              unit="bpm"
              direction="down-good"
            />
          }
        />
        <Fact
          icon={Zap}
          label="Training load"
          sub="sum over all activities"
          value={fmtNumber(r.totals.training_load)}
        />
        <Fact
          icon={Flame}
          label="Active calories"
          sub="burned in activities"
          value={`${fmtNumber(Math.round(r.totals.calories / 100) * 100)} kcal`}
        />
      </div>
    </Card>
  );
}
