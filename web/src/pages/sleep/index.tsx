import { AlarmClock, BedDouble, Brain, Hourglass, MoonStar, Star } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { api, type Schemas } from "@/api/client";
import { usePageFilters } from "@/app/pageFilters";
import { Chart, type ChartInstance } from "@/components/Chart";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
  type DeltaDirection,
} from "@/components/ui";
import { Change, MetricTile, Spark, TileSkeletons } from "@/components/kit";
import { dayExtent, dayOfPoint, outlineFill } from "@/lib/charts";
import { fmtDate, fmtHours, fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { diff, mean, previousPeriod, spanDays, stdev, weekly } from "@/lib/stats";
import { measureColors, SLEEP_STAGES } from "@/lib/tokens";
import { NARROW, useMediaQuery } from "@/lib/useMediaQuery";
import { NightDetail } from "./NightDetail";
import {
  asleep,
  distributionOption,
  scheduleOption,
  scoreOption,
  stagesOption,
  weekdayDurationOption,
  weekdayScheduleOption,
  weekdayScoreOption,
} from "./options";

type Night = Schemas["SleepNight"];
type Stats = Schemas["SleepStats"];

const TILE_GRID = "grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6";

/** Stage share of time in bed (deep + light + REM + awake), so the four stages sum to 100 %. */
function share(part: number | null | undefined, n: Night | Stats, kind: "night" | "stats") {
  const parts =
    kind === "night"
      ? [(n as Night).deep_s, (n as Night).light_s, (n as Night).rem_s, (n as Night).awake_s]
      : [
          (n as Stats).avg_deep_s,
          (n as Stats).avg_light_s,
          (n as Stats).avg_rem_s,
          (n as Stats).avg_awake_s,
        ];
  const total = parts.reduce<number>((s, v) => s + (v ?? 0), 0);
  return part == null || !total ? null : (part / total) * 100;
}

function delta(
  d: number | null,
  digits: number,
  unit: string,
  direction: DeltaDirection,
  days: number,
): ReactNode {
  return (
    <Change
      value={d}
      digits={digits}
      unit={unit}
      direction={direction}
      title={`Change vs the previous ${days} days`}
    />
  );
}

function Tiles({
  nights,
  stats,
  prev,
  days,
}: {
  nights: Night[];
  stats: Stats;
  prev: Stats | undefined;
  days: number;
}) {
  const mode = useMode();
  const col = measureColors(mode);
  const stage = SLEEP_STAGES[mode];
  const wk = (get: (n: Night) => number | null) =>
    weekly(nights, (n) => n.day, get).map((w) => w.value);
  const deep = share(stats.avg_deep_s, stats, "stats");
  const rem = share(stats.avg_rem_s, stats, "stats");
  const prevDeep = prev ? share(prev.avg_deep_s, prev, "stats") : null;
  const prevRem = prev ? share(prev.avg_rem_s, prev, "stats") : null;
  const durDiff = diff(stats.avg_duration_s, prev?.avg_duration_s);
  const scoreDiff = diff(stats.avg_score, prev?.avg_score);
  const sdDiff = diff(stats.bedtime_sd_min, prev?.bedtime_sd_min);
  const last7 = nights.slice(-7);
  const need = mean(last7.map((n) => n.sleep_need_min));
  return (
    <div className={TILE_GRID}>
      <MetricTile
        label="Average sleep"
        icon={<MoonStar size={14} />}
        value={fmtHours(stats.avg_duration_s)}
        delta={delta(durDiff == null ? null : durDiff / 60, 0, "min", "up-good", days)}
        sub={`${fmtNumber(stats.nights)} nights`}
        spark={
          <Spark
            values={wk((n) => asleep(n))}
            color={col.sleep}
            label="Sleep duration, weekly averages"
          />
        }
      />
      <MetricTile
        label="Sleep score"
        icon={<Star size={14} />}
        value={fmtNumber(stats.avg_score)}
        unit="/ 100"
        delta={delta(scoreDiff, 1, "", "up-good", days)}
        spark={
          <Spark
            values={wk((n) => n.score)}
            color={col.sleep}
            label="Sleep score, weekly averages"
          />
        }
      />
      <MetricTile
        label="Deep sleep"
        icon={<Brain size={14} />}
        value={fmtNumber(deep)}
        unit="%"
        delta={delta(diff(deep, prevDeep), 1, "pp", "neutral", days)}
        sub={fmtHours(stats.avg_deep_s)}
        spark={
          <Spark
            values={wk((n) => share(n.deep_s, n, "night"))}
            color={stage.deep}
            label="Deep sleep share, weekly averages"
          />
        }
      />
      <MetricTile
        label="REM sleep"
        icon={<BedDouble size={14} />}
        value={fmtNumber(rem)}
        unit="%"
        delta={delta(diff(rem, prevRem), 1, "pp", "neutral", days)}
        sub={fmtHours(stats.avg_rem_s)}
        spark={
          <Spark
            values={wk((n) => share(n.rem_s, n, "night"))}
            color={stage.rem}
            label="REM sleep share, weekly averages"
          />
        }
      />
      <MetricTile
        label="Bedtime consistency"
        icon={<AlarmClock size={14} />}
        value={stats.bedtime_sd_min == null ? "–" : `±${fmtNumber(stats.bedtime_sd_min)}`}
        unit="min"
        delta={delta(sdDiff, 0, "min", "down-good", days)}
        sub={stats.waketime_sd_min == null ? null : `wake ±${fmtNumber(stats.waketime_sd_min)} min`}
        spark={
          <Spark
            values={weekly(
              nights,
              (n) => n.day,
              (n) => n.bedtime_min,
              stdev,
            ).map((w) => w.value)}
            color={col.weekday}
            label="Bedtime spread per week"
          />
        }
      />
      <MetricTile
        label="Sleep debt · 7 nights"
        icon={<Hourglass size={14} />}
        value={fmtHours(stats.sleep_debt_7d_s ?? 0)}
        sub={need == null ? "vs your sleep need" : `need ${fmtHours(need * 60)} a night`}
        spark={
          <Spark
            values={last7.map((n) =>
              n.sleep_need_min == null || asleep(n) == null
                ? null
                : Math.max(0, n.sleep_need_min * 60 - asleep(n)!) / 3600,
            )}
            color={col.weekend}
            label="Nightly shortfall over the last 7 nights"
          />
        }
      />
    </div>
  );
}

/** Weekday = solid, weekend = outlined wash (the same encoding as the bed & wake chart). */
function GroupLegend() {
  const mode = useMode();
  const col = measureColors(mode);
  return (
    <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
      <span className="inline-flex items-center gap-1.5">
        <span
          className="inline-block size-2.5 rounded-swatch"
          style={{ background: col.weekday }}
          aria-hidden
        />
        Weekday nights
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span
          className="inline-block size-2.5 rounded-swatch border-[1.5px]"
          style={{ background: outlineFill(col.weekend, mode), borderColor: col.weekend }}
          aria-hidden
        />
        Weekend nights
      </span>
    </div>
  );
}

export default function SleepPage() {
  const range = usePageFilters();
  const mode = useMode();
  const narrow = useMediaQuery(NARROW);
  const days = spanDays(range.start, range.end);
  const opts = range.options;
  const nightsQ = api.useQuery("get", "/api/sleep", { params: { query: range.dates } }, opts);
  const statsQ = api.useQuery("get", "/api/sleep/stats", { params: { query: range.dates } }, opts);
  const prevQ = api.useQuery(
    "get",
    "/api/sleep/stats",
    { params: { query: previousPeriod(range.dates) } },
    opts,
  );
  const meta = api.useQuery("get", "/api/meta");
  const [picked, setPicked] = useState<string | null>(null);

  const nights = useMemo(() => nightsQ.data ?? [], [nightsQ.data]);
  const known = useMemo(() => new Set(nights.map((n) => n.day)), [nights]);
  const selected = picked && known.has(picked) ? picked : (nights[nights.length - 1]?.day ?? null);
  const ext = useMemo(() => dayExtent(range.start, range.end), [range.start, range.end]);
  const stages = useMemo(
    () =>
      nights.length
        ? stagesOption(
            nights,
            mode,
            ext,
            selected,
            narrow ? nights.length > 40 : nights.length > 150,
          )
        : null,
    [nights, mode, ext, selected, narrow],
  );
  const score = useMemo(
    () => (nights.some((n) => n.score != null) ? scoreOption(nights, mode, ext) : null),
    [nights, mode, ext],
  );
  const schedule = useMemo(
    () => (nights.some((n) => n.bedtime_min != null) ? scheduleOption(nights, mode, ext) : null),
    [nights, mode, ext],
  );
  const stats = statsQ.data;
  const weekdayWeekend = useMemo(
    () =>
      stats && stats.weekday.nights > 0 && stats.weekend.nights > 0
        ? {
            duration: weekdayDurationOption(stats, mode),
            score: weekdayScoreOption(stats, mode),
            schedule: weekdayScheduleOption(stats, mode),
          }
        : null,
    [stats, mode],
  );
  const distribution = useMemo(
    () =>
      stats && nights.some((n) => n.score != null) ? distributionOption(nights, stats, mode) : null,
    [nights, stats, mode],
  );

  // A click anywhere in a night's column picks that night.
  const onStagesReady = (chart: ChartInstance) => {
    chart.getZr().on("click", (e: { offsetX: number; offsetY: number }) => {
      if (!chart.containPixel({ gridIndex: 0 }, [e.offsetX, e.offsetY])) return;
      const x = chart.convertFromPixel({ xAxisIndex: 0 }, e.offsetX) as unknown as number;
      setPicked(dayOfPoint(x));
    });
  };

  const loading = !nightsQ.data || !statsQ.data;
  const error = nightsQ.error ?? statsQ.error;
  return (
    <>
      <PageHeader
        title="Sleep"
        description={`${fmtDate(range.start)} – ${fmtDate(range.end)} · nightly averages; arrows compare with the previous ${days} days.`}
      />
      <div className="flex flex-col gap-5">
        {error ? (
          <ErrorState error={error} />
        ) : loading ? (
          <TileSkeletons n={6} className={TILE_GRID} />
        ) : nights.length === 0 || !stats ? (
          <EmptyState title="No sleep recorded in this period">
            Wear your watch to bed and sync it with Garmin Connect; nights appear here after the
            next Garminizer sync.
          </EmptyState>
        ) : (
          <>
            <Tiles nights={nights} stats={stats} prev={prevQ.data} days={days} />
            <div className="grid gap-5 lg:grid-cols-2">
              <Card
                title="Sleep stages per night"
                subtitle="Hours in each stage against your sleep need · click a night for details"
                className="lg:col-span-2"
              >
                {stages ? (
                  <Chart
                    option={stages}
                    height={260}
                    ariaLabel="Deep, light, REM and awake time per night with sleep need"
                    onReady={onStagesReady}
                  />
                ) : (
                  <Skeleton height={260} />
                )}
              </Card>
              {selected && (
                <NightDetail
                  day={selected}
                  nights={nights}
                  onPick={setPicked}
                  timeZone={meta.data?.athlete?.time_zone}
                />
              )}
              <Card
                title="Sleep score"
                subtitle="Nightly score and 7-night mean with Garmin's quality bands"
              >
                {score ? (
                  <Chart option={score} height={240} ariaLabel="Sleep score per night" />
                ) : (
                  <EmptyState title="No sleep scores in this period" />
                )}
              </Card>
              <Card
                title="Bed & wake times"
                subtitle="Each bar runs from falling asleep to waking up"
              >
                {schedule ? (
                  <Chart
                    option={schedule}
                    height={240}
                    ariaLabel="Bedtime to wake time per night, weekday and weekend nights"
                  />
                ) : (
                  <EmptyState title="No bed or wake times in this period" />
                )}
              </Card>
              <Card
                title="Weekdays vs weekends"
                subtitle={`${stats.weekday.nights} weekday and ${stats.weekend.nights} weekend nights (ending Sat or Sun)`}
              >
                {weekdayWeekend ? (
                  <>
                    <GroupLegend />
                    <div className="grid grid-cols-3 gap-3">
                      <Chart
                        option={weekdayWeekend.duration}
                        height={200}
                        ariaLabel="Average time asleep, weekday vs weekend nights"
                      />
                      <Chart
                        option={weekdayWeekend.score}
                        height={200}
                        ariaLabel="Average sleep score, weekday vs weekend nights"
                      />
                      <Chart
                        option={weekdayWeekend.schedule}
                        height={200}
                        ariaLabel="Average bedtime and wake time, weekday vs weekend nights"
                      />
                    </div>
                  </>
                ) : (
                  <EmptyState title="Needs both weekday and weekend nights in the period" />
                )}
              </Card>
              <Card
                title="Score distribution"
                subtitle="Nights per 5-point score bin, shaded by Garmin's quality class"
              >
                {distribution ? (
                  <Chart
                    option={distribution}
                    height={200}
                    ariaLabel="Distribution of nightly sleep scores by quality"
                  />
                ) : (
                  <EmptyState title="No sleep scores in this period" />
                )}
              </Card>
            </div>
          </>
        )}
      </div>
    </>
  );
}
