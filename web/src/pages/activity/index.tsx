import { Link, useParams } from "@tanstack/react-router";
import {
  ChevronLeft,
  ChevronRight,
  CloudSun,
  Flame,
  Footprints,
  Gauge,
  HeartPulse,
  Mountain,
  Timer,
  Zap,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { api } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { MapView } from "@/components/MapView";
import { SportBadge } from "@/components/SportIcon";
import {
  Card,
  EmptyState,
  ErrorState,
  LegendItem,
  Segmented,
  ShowAllButton,
  Skeleton,
  StatTile,
} from "@/components/ui";
import { axisTooltip, GRID, line, smallTitle, tooltipRow, valueYAxis } from "@/lib/charts";
import {
  DASH,
  distanceUnit,
  distanceValue,
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  fmtHours,
  fmtLocalTime,
  fmtNumber,
  fmtPace,
  fmtSpeed,
  fmtTemperature,
  paceSeconds,
  speedUnit,
  smooth,
  speedValue,
  teLabel,
  titleCase,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { sportColor, sportLabel, usesPace } from "@/lib/sports";
import { CHROME, MEASURE_COLORS, ROUTE_RAMP, ZONE_RAMP, barEnd } from "@/lib/tokens";
import {
  bounds,
  buildSeries,
  elevationText,
  routeLayers,
  smoothingWindow,
  yBounds,
  type Detail,
  type MapMetric,
  type Streams,
} from "./streams";

function StreamCharts({
  d,
  s,
  onHover,
}: {
  d: Detail;
  s: Streams;
  onHover: (i: number | null) => void;
}) {
  const mode = useMode();
  const units = useUnits();
  const [xMode, setXMode] = useState<"distance" | "time">(d.distance_m ? "distance" : "time");
  const series = useMemo(() => buildSeries(d, s, units, mode), [d, s, units, mode]);
  const x =
    xMode === "distance"
      ? s.distance_m.map((v) => (v == null ? null : distanceValue(v, units)))
      : s.t_s;
  const xLabel = (v: number) =>
    xMode === "distance" ? `${fmtNumber(v, 1)} ${distanceUnit(units)}` : fmtDuration(v);

  return (
    <Card
      title="Streams"
      subtitle="Hover or tap a chart to follow the route on the map"
      actions={
        d.distance_m ? (
          <Segmented
            size="sm"
            label="X axis"
            value={xMode}
            onChange={setXMode}
            options={[
              { value: "distance", label: "Distance" },
              { value: "time", label: "Time" },
            ]}
          />
        ) : undefined
      }
    >
      <div className="flex flex-col gap-1">
        {series.map((ser, idx) => {
          const values = smooth(ser.values, smoothingWindow(ser.key, ser.values.length));
          const data = values.map((v, i) => [x[i], v]);
          const bounds = yBounds(ser);
          const option: ChartOption = {
            grid: { ...GRID, top: 28, bottom: idx === series.length - 1 ? 4 : 0 },
            title: smallTitle(`${ser.label} (${ser.unit})`, mode),
            tooltip: axisTooltip((p) => {
              const arr = p as { dataIndex: number; value: [number, number | null] }[];
              const first = arr[0];
              if (!first) return "";
              const v = first.value[1];
              return `<div style="color:${CHROME[mode].muted};margin-bottom:4px">${xLabel(first.value[0])}</div>${tooltipRow(ser.color, ser.label, v == null ? DASH : `${ser.format(v)} ${ser.unit}`)}`;
            }),
            xAxis: {
              type: "value",
              min: "dataMin",
              max: "dataMax",
              axisLabel: { show: idx === series.length - 1, formatter: xLabel },
              splitLine: { show: false },
            },
            yAxis: valueYAxis(undefined, ser.format, {
              inverse: ser.inverse ?? false,
              scale: true,
              ...(bounds ?? {}),
            }),
            series: [
              {
                ...line(ser.label, data, ser.color, { area: ser.area ?? false }),
                sampling: "lttb",
                clip: true,
              },
            ],
          };
          return (
            <Chart
              key={`${ser.key}-${xMode}-${units}`}
              option={option}
              height={idx === series.length - 1 ? 156 : 134}
              group="activity-streams"
              ariaLabel={`${ser.label} over ${xMode}`}
              onEvents={{
                updateAxisPointer: (e) => {
                  const info = (e as { dataIndex?: number }).dataIndex;
                  onHover(typeof info === "number" ? info : null);
                },
                globalout: () => onHover(null),
              }}
            />
          );
        })}
      </div>
    </Card>
  );
}

function Zones({ d }: { d: Detail }) {
  const mode = useMode();
  const hr = d.zones.filter((z) => z.kind === "hr").sort((a, b) => a.zone - b.zone);
  if (!hr.length) return null;
  const total = hr.reduce((s, z) => s + z.seconds, 0) || 1;
  const option: ChartOption = {
    grid: { left: 4, right: 64, top: 4, bottom: 4 },
    tooltip: {
      trigger: "item",
      formatter: (p: unknown) => {
        const it = p as { name: string; value: number };
        return `${it.name}<br/><b>${fmtHours(it.value)}</b> · ${fmtNumber((it.value / total) * 100)} %`;
      },
    },
    xAxis: { type: "value", show: false },
    yAxis: {
      type: "category",
      inverse: true,
      data: hr.map((z) => `Zone ${z.zone}${z.low_value ? ` · ${fmtNumber(z.low_value)}+` : ""}`),
      axisLine: { show: false },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        data: hr.map((z, i) => ({
          value: z.seconds,
          itemStyle: { color: ZONE_RAMP[mode][i], borderRadius: barEnd("right") },
        })),
        label: {
          show: true,
          position: "right",
          color: CHROME[mode].text2,
          formatter: (p: { value: number }) => `${fmtNumber((p.value / total) * 100)} %`,
        },
      },
    ],
  };
  return (
    <Card title="Heart-rate zones" subtitle="Time in each zone">
      <Chart option={option} height={190} ariaLabel="Time in heart-rate zones" />
    </Card>
  );
}

const SPLITS_COLLAPSED = 15;

function SplitsTable({ d }: { d: Detail }) {
  const units = useUnits();
  const mode = useMode();
  const [all, setAll] = useState(false);
  const splits = units === "metric" ? d.splits_km : d.splits_mi;
  if (!splits.length) return null;
  const pace = usesPace(d.sport_group);
  const speeds = splits.map((s) => s.distance_m / s.duration_s);
  // Bars span this activity's own range (slowest → fastest), so pacing differences show.
  const lo = Math.min(...speeds);
  const hi = Math.max(...speeds);
  const avg =
    splits.reduce((a, s) => a + s.distance_m, 0) / splits.reduce((a, s) => a + s.duration_s, 0);
  const width = (v: number) => (hi - lo < 1e-6 ? 100 : 25 + (75 * (v - lo)) / (hi - lo));
  const fmtV = (v: number) => (pace ? fmtPace(v, units) : fmtSpeed(v, units)).split(" ")[0];
  const shown = all ? splits : splits.slice(0, SPLITS_COLLAPSED);
  const color = sportColor(d.sport_group, mode);
  return (
    <Card
      title={`Splits per ${distanceUnit(units)}`}
      subtitle={`Bar length from slowest to fastest split · average ${pace ? fmtPace(avg, units) : fmtSpeed(avg, units)}`}
    >
      <table className="w-full text-sm tabular">
        <thead className="text-xs text-ink-3">
          <tr>
            <th scope="col" className="py-1.5 text-left font-medium">
              #
            </th>
            <th scope="col" className="py-1.5 text-left font-medium">
              {pace ? "Pace" : "Speed"}
            </th>
            <th scope="col" className="py-1.5 pl-4 text-right font-medium">
              HR
            </th>
            <th scope="col" className="py-1.5 pl-4 text-right font-medium">
              Elevation
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((s, i) => {
            const v = speeds[i]!;
            return (
              <tr key={s.split_index} className="border-t border-line">
                <td className="py-1.5 pr-2 text-ink-3">{s.split_index}</td>
                <td className="w-full py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="w-12 shrink-0 text-ink">{fmtV(v)}</span>
                    <span className="relative h-2 flex-1" aria-hidden>
                      <span
                        className="block h-2 rounded-bar"
                        style={{ width: `${width(v)}%`, background: color }}
                      />
                      <span
                        className="absolute -top-1 h-4 w-px bg-ink-2"
                        style={{ left: `${width(avg)}%` }}
                      />
                    </span>
                  </div>
                </td>
                <td className="py-1.5 pl-4 text-right text-ink-2">
                  {s.avg_hr ? fmtNumber(s.avg_hr) : DASH}
                </td>
                <td className="py-1.5 pl-4 text-right whitespace-nowrap text-ink-2">
                  {elevationText(s.elevation_gain_m, s.elevation_loss_m, units)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {splits.length > SPLITS_COLLAPSED && (
        <ShowAllButton
          total={splits.length}
          noun="splits"
          expanded={all}
          onToggle={() => setAll((v) => !v)}
        />
      )}
      <p className="mt-2 text-xs text-ink-3">
        Longer bar = faster · the thin line marks your average {pace ? "pace" : "speed"}
      </p>
    </Card>
  );
}

const LAPS_COLLAPSED = 12;

function LapsTable({ d }: { d: Detail }) {
  const units = useUnits();
  const [all, setAll] = useState(false);
  if (d.laps.length < 2) return null;
  const laps = all ? d.laps : d.laps.slice(0, LAPS_COLLAPSED);
  const pace = usesPace(d.sport_group);
  const speed = (l: Detail["laps"][number]) =>
    pace
      ? fmtPace(l.avg_speed_mps, units, d.sport_group === "swim")
      : fmtSpeed(l.avg_speed_mps, units);
  return (
    <Card title="Laps" subtitle={`${d.laps.length} laps`}>
      {/* Phones: two-line rows instead of a table that would need sideways scrolling */}
      <div className="sm:hidden">
        <ul className="divide-y divide-line text-sm tabular">
          {laps.map((l) => (
            <li key={l.lap_index} className="flex items-center gap-3 py-2">
              <span className="w-6 shrink-0 text-ink-3">{l.lap_index + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-ink">
                  {fmtDistance(l.distance_m, units)} · {fmtDuration(l.duration_s)}
                </span>
                <span className="block text-xs text-ink-3">
                  {titleCase(l.intensity)} · {l.avg_hr ? `${l.avg_hr} bpm` : DASH}
                </span>
              </span>
              <span className="shrink-0 text-ink-2">{speed(l)}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="hidden sm:block">
        <table className="w-full text-sm tabular">
          <thead className="text-xs text-ink-3">
            <tr>
              {["Lap", "Distance", "Time", pace ? "Pace" : "Speed", "Avg HR", "Type"].map((h) => (
                <th key={h} scope="col" className="py-1.5 pr-3 text-left font-medium last:pr-0">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {laps.map((l) => (
              <tr key={l.lap_index} className="border-t border-line">
                <td className="py-1.5 pr-3 text-ink-3">{l.lap_index + 1}</td>
                <td className="py-1.5 pr-3 text-ink">{fmtDistance(l.distance_m, units)}</td>
                <td className="py-1.5 pr-3 text-ink">{fmtDuration(l.duration_s)}</td>
                <td className="py-1.5 pr-3 text-ink-2">{speed(l)}</td>
                <td className="py-1.5 pr-3 text-ink-2">{l.avg_hr ?? DASH}</td>
                <td className="py-1.5 text-ink-3">{titleCase(l.intensity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.laps.length > LAPS_COLLAPSED && (
        <ShowAllButton
          total={d.laps.length}
          noun="laps"
          expanded={all}
          onToggle={() => setAll((v) => !v)}
        />
      )}
    </Card>
  );
}

/** Round durations for the log-scaled x axis of the best-effort curve (seconds). */
const DURATION_TICKS = [1, 5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, 10800, 18000];

function BestEfforts({ d }: { d: Detail }) {
  const mode = useMode();
  const units = useUnits();
  const metric =
    d.sport_group === "ride" && d.avg_power_w ? "power" : d.distance_m ? "speed" : "hr";
  // Runners think in pace: plot min/km on an inverted axis (faster = higher).
  const asPace = metric === "speed" && usesPace(d.sport_group) && d.sport_group !== "swim";
  const q = api.useQuery("get", "/api/activities/{activity_id}/curve", {
    params: { path: { activity_id: d.activity_id }, query: { metric } },
  });
  if (q.isPending) return <Skeleton height={280} />;
  if (q.error) return <ErrorState error={q.error} />;
  const pts = q.data.points;
  if (pts.length < 3) return null;
  const conv = (v: number) =>
    asPace ? paceSeconds(v, units) : metric === "speed" ? speedValue(v, units) : v;
  const fmtV = (v: number) => (asPace ? fmtDuration(v) : fmtNumber(v, metric === "speed" ? 1 : 0));
  const unit = asPace
    ? `min/${distanceUnit(units)}`
    : metric === "power"
      ? "W"
      : metric === "hr"
        ? "bpm"
        : speedUnit(units);
  const what = asPace
    ? "pace"
    : metric === "speed"
      ? "speed"
      : metric === "power"
        ? "power"
        : "heart rate";
  const durLabel = (s: number) =>
    s < 60
      ? `${s}s`
      : s < 3600
        ? `${Math.round(s / 60)}m`
        : `${fmtNumber(s / 3600, s % 3600 ? 1 : 0)}h`;
  const mine = MEASURE_COLORS[mode][metric === "speed" ? "pace" : metric];
  const best = CHROME[mode].muted;
  const maxDur = pts[pts.length - 1]!.duration_s;
  const span = DURATION_TICKS.filter((t) => t <= maxDur);
  // At most ~6 labels: thin the list evenly, keep the longest one.
  const step = Math.ceil(span.length / 6);
  const ticks = span.filter((_, i) => i % step === 0 || i === span.length - 1).map(Math.log10);
  const option: ChartOption = {
    grid: { ...GRID, top: 12 },
    tooltip: axisTooltip((p) => {
      const arr = p as { seriesName: string; color: string; value: [number, number] }[];
      return (
        `<div style="margin-bottom:4px">${durLabel(Math.round(10 ** (arr[0]?.value[0] ?? 0)))}</div>` +
        arr.map((a) => tooltipRow(a.color, a.seriesName, `${fmtV(a.value[1])} ${unit}`)).join("")
      );
    }),
    // log10(seconds) on a value axis, so the ticks can sit on round durations
    xAxis: {
      type: "value",
      min: 0,
      max: Math.log10(maxDur),
      axisTick: { customValues: ticks },
      axisLabel: {
        customValues: ticks,
        formatter: (v: number) => durLabel(Math.round(10 ** v)),
        hideOverlap: true,
      },
      splitLine: { show: false },
    },
    yAxis: valueYAxis(undefined, fmtV, { scale: true, inverse: asPace }),
    series: [
      line(
        "This activity",
        pts.map((p) => [Math.log10(p.duration_s), conv(p.value)]),
        mine,
      ),
      line(
        "All-time best",
        pts.filter((p) => p.best != null).map((p) => [Math.log10(p.duration_s), conv(p.best!)]),
        best,
        { dashed: true },
      ),
    ],
  };
  return (
    <Card
      title={`Best ${what} by duration`}
      subtitle={`Your best ${what} held for each duration (${unit}), vs your all-time bests in ${sportLabel(d.sport_group).toLowerCase()}`}
    >
      <div className="mb-2 flex flex-wrap gap-4">
        <LegendItem color={mine} label="This activity" shape="line" />
        <LegendItem color={best} label="All-time best" shape="line" />
      </div>
      <Chart
        option={option}
        height={240}
        ariaLabel={`Best ${what} by duration: this activity vs all-time best`}
      />
    </Card>
  );
}

function Fact({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <span className="text-ink-3">{icon}</span>
      <span className="flex-1 text-sm text-ink-2">{label}</span>
      <span className="text-sm font-medium text-ink tabular">{value}</span>
    </div>
  );
}

function Facts({ d }: { d: Detail }) {
  const units = useUnits();
  return (
    <Card title="Details">
      <div className="divide-y divide-line">
        <Fact
          icon={<Zap size={16} />}
          label="Training effect"
          value={
            d.aerobic_te != null
              ? `${fmtNumber(d.aerobic_te, 1)} aerobic · ${fmtNumber(d.anaerobic_te, 1)} anaerobic`
              : DASH
          }
        />
        <Fact
          icon={<Gauge size={16} />}
          label="Training load"
          value={`${fmtNumber(d.training_load)}${d.trimp ? ` · TRIMP ${fmtNumber(d.trimp)}` : ""}`}
        />
        {d.efficiency_factor != null && (
          <Fact
            icon={<HeartPulse size={16} />}
            label="Efficiency factor"
            value={fmtNumber(d.efficiency_factor, 2)}
          />
        )}
        {d.aerobic_decoupling_pct != null && (
          <Fact
            icon={<HeartPulse size={16} />}
            label="Aerobic decoupling"
            value={`${fmtNumber(d.aerobic_decoupling_pct, 1)} %`}
          />
        )}
        <Fact icon={<Flame size={16} />} label="Calories" value={`${fmtNumber(d.calories)} kcal`} />
        {d.steps ? (
          <Fact icon={<Footprints size={16} />} label="Steps" value={fmtNumber(d.steps)} />
        ) : null}
        {d.weather && (
          <Fact
            icon={<CloudSun size={16} />}
            label="Weather"
            value={`${fmtTemperature(d.weather.temperature_c, units)} · ${d.weather.condition ?? ""}`}
          />
        )}
        {d.gear.length > 0 && (
          <Fact
            icon={<Mountain size={16} />}
            label="Gear"
            value={d.gear.map((g) => g.display_name).join(", ")}
          />
        )}
        {d.total_sets ? (
          <Fact
            icon={<Timer size={16} />}
            label="Sets · reps"
            value={`${d.total_sets} · ${d.total_reps}`}
          />
        ) : null}
        {d.avg_swolf ? (
          <Fact
            icon={<Timer size={16} />}
            label="SWOLF · pool"
            value={`${fmtNumber(d.avg_swolf, 1)} · ${fmtNumber(d.pool_length_m)} m`}
          />
        ) : null}
      </div>
    </Card>
  );
}

export default function ActivityPage() {
  const { activityId } = useParams({ from: "/activities/$activityId" });
  const id = Number(activityId);
  const units = useUnits();
  const mode = useMode();
  const [metric, setMetric] = useState<MapMetric>("speed");
  const [cursor, setCursor] = useState<number | null>(null);
  const detail = api.useQuery("get", "/api/activities/{activity_id}", {
    params: { path: { activity_id: id } },
  });
  const streams = api.useQuery("get", "/api/activities/{activity_id}/streams", {
    params: { path: { activity_id: id }, query: { points: 1500 } },
  });
  const layers = useMemo(
    () =>
      streams.data && streams.data.points ? routeLayers(streams.data, metric, mode, cursor) : [],
    [streams.data, metric, mode, cursor],
  );

  if (detail.error) return <ErrorState error={detail.error} />;
  if (!detail.data) return <Skeleton height={480} />;
  const d = detail.data;
  const pace = usesPace(d.sport_group);
  const speed = pace
    ? fmtPace(d.avg_speed_mps, units, d.sport_group === "swim")
    : fmtSpeed(d.avg_speed_mps, units);
  const [speedNum, ...speedUnitParts] = speed.split(" ");

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <SportBadge group={d.sport_group} size={44} />
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-ink">
              {d.name ?? sportLabel(d.sport_group)}
            </h1>
            <p className="text-sm text-ink-2">
              {fmtDate(d.start_time_local, {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
              })}{" "}
              · {fmtLocalTime(d.start_time_local)}
              {d.location_name ? ` · ${d.location_name}` : ""}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Link
            to="/activities"
            search={(p: Record<string, unknown>) => p}
            className="rounded-control px-3 py-1.5 text-sm text-ink-2 hover:bg-hover hover:text-ink"
          >
            All activities
          </Link>
          {d.previous_id && (
            <Link
              to="/activities/$activityId"
              params={{ activityId: String(d.previous_id) }}
              aria-label="Previous activity"
              className="rounded-control p-2 text-ink-2 hover:bg-hover hover:text-ink"
            >
              <ChevronLeft size={18} />
            </Link>
          )}
          {d.next_id && (
            <Link
              to="/activities/$activityId"
              params={{ activityId: String(d.next_id) }}
              aria-label="Next activity"
              className="rounded-control p-2 text-ink-2 hover:bg-hover hover:text-ink"
            >
              <ChevronRight size={18} />
            </Link>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {d.distance_m ? (
          <StatTile
            label="Distance"
            value={fmtDistance(d.distance_m, units).split(" ")[0]}
            unit={distanceUnit(units)}
          />
        ) : null}
        <StatTile
          label="Moving time"
          value={fmtDuration(d.moving_s ?? d.duration_s)}
          sub={
            d.elapsed_s && d.moving_s && d.elapsed_s - d.moving_s > 60
              ? `${fmtHours(d.elapsed_s)} elapsed`
              : undefined
          }
        />
        {d.distance_m ? (
          <StatTile
            label={pace ? "Avg pace" : "Avg speed"}
            value={speedNum}
            unit={speedUnitParts.join(" ")}
          />
        ) : null}
        {d.elevation_gain_m ? (
          <StatTile
            label="Elevation gain"
            value={fmtElevation(d.elevation_gain_m, units).split(" ")[0]}
            unit={units === "metric" ? "m" : "ft"}
          />
        ) : null}
        <StatTile
          label="Avg heart rate"
          value={d.avg_hr ?? DASH}
          unit="bpm"
          sub={d.max_hr ? `max ${d.max_hr}` : undefined}
        />
        {d.normalized_power_w ? (
          <StatTile
            label="Normalized power"
            value={fmtNumber(d.normalized_power_w)}
            unit="W"
            sub={d.avg_power_w ? `avg ${fmtNumber(d.avg_power_w)} W` : undefined}
          />
        ) : (
          <StatTile
            label="Training load"
            value={fmtNumber(d.training_load)}
            sub={teLabel(d.training_effect_label)}
          />
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
        <div className="flex flex-col gap-5 xl:col-span-3">
          {d.track && streams.data && streams.data.points > 0 ? (
            <Card
              title="Route"
              actions={
                <Segmented
                  size="sm"
                  label="Colour route by"
                  value={metric}
                  onChange={setMetric}
                  options={[
                    { value: "speed", label: pace ? "Pace" : "Speed" },
                    { value: "hr", label: "Heart rate" },
                    { value: "altitude", label: "Elevation" },
                  ]}
                />
              }
            >
              <MapView
                layers={layers}
                bounds={bounds(d.track)}
                height={420}
                ariaLabel={`Map of ${d.name ?? "activity"}`}
              />
              <div className="mt-2 flex items-center gap-2 text-xs text-ink-3">
                <span>low</span>
                <span
                  className="h-1.5 w-28 rounded-bar"
                  style={{
                    background: `linear-gradient(90deg, ${ROUTE_RAMP[mode].join(", ")})`,
                  }}
                  aria-hidden
                />
                <span>
                  high{" "}
                  {metric === "speed"
                    ? pace
                      ? "speed"
                      : "speed"
                    : metric === "hr"
                      ? "heart rate"
                      : "elevation"}
                </span>
              </div>
            </Card>
          ) : null}
          {streams.isPending ? (
            <Skeleton height={420} />
          ) : streams.data && streams.data.points > 0 ? (
            <StreamCharts d={d} s={streams.data} onHover={setCursor} />
          ) : (
            <Card title="Streams">
              <EmptyState title="No per-second data for this activity" />
            </Card>
          )}
          <BestEfforts d={d} />
        </div>
        <div className="flex flex-col gap-5 xl:col-span-2">
          <Facts d={d} />
          <Zones d={d} />
          <SplitsTable d={d} />
          <LapsTable d={d} />
        </div>
      </div>
      <p className="text-xs text-ink-3">
        Activity {d.activity_id} · {fmtHours(d.duration_s)} total · {sportLabel(d.sport_group)}
      </p>
    </div>
  );
}
