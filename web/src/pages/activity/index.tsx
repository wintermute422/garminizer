import { Link, useParams } from "@tanstack/react-router";
import type { Feature, FeatureCollection, LineString } from "geojson";
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
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { MapView, type MapLayer } from "@/components/MapView";
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
import { axisTooltip, GRID, line, tooltipRow, valueYAxis } from "@/lib/charts";
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
  type UnitSystem,
} from "@/lib/format";
import type { Bounds } from "@/lib/geo";
import { useMode, useUnits } from "@/lib/preferences";
import { sportColor, sportLabel, usesPace } from "@/lib/sports";
import { BLUE, CATEGORICAL, CHROME, MEASURE_COLORS, ZONE_RAMP, type Mode } from "@/lib/tokens";

type Detail = Schemas["ActivityDetail"];
type Streams = Schemas["Streams"];
type MapMetric = "speed" | "hr" | "altitude";

function lerpColor(stops: readonly string[], t: number): string {
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const f = x - i;
  const a = Number.parseInt(stops[i]!.slice(1), 16);
  const b = Number.parseInt(stops[i + 1]!.slice(1), 16);
  const ch = (s: number) => Math.round(((a >> s) & 255) * (1 - f) + ((b >> s) & 255) * f);
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
}

function quantile(values: number[], q: number): number {
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))] ?? 0;
}

function routeLayers(s: Streams, metric: MapMetric, mode: Mode, cursor: number | null): MapLayer[] {
  const raw = metric === "speed" ? s.speed_mps : metric === "hr" ? s.hr : s.altitude_m;
  const finite = raw.filter((v): v is number => v !== null);
  const lo = quantile(finite, 0.05);
  const hi = quantile(finite, 0.95);
  const ramp =
    mode === "dark" ? [BLUE[400]!, "#eda100", "#e66767"] : [BLUE[450]!, "#eda100", "#e34948"];
  const features: Feature<LineString>[] = [];
  for (let i = 1; i < s.lat.length; i++) {
    const [a0, o0, a1, o1] = [s.lat[i - 1], s.lon[i - 1], s.lat[i], s.lon[i]];
    if (a0 == null || o0 == null || a1 == null || o1 == null) continue;
    const v = raw[i];
    const t = v == null || hi === lo ? 0.5 : (v - lo) / (hi - lo);
    features.push({
      type: "Feature",
      properties: { color: lerpColor(ramp, t) },
      geometry: {
        type: "LineString",
        coordinates: [
          [o0, a0],
          [o1, a1],
        ],
      },
    });
  }
  const route: FeatureCollection = { type: "FeatureCollection", features };
  const ends: FeatureCollection = { type: "FeatureCollection", features: [] };
  const firstIdx = s.lat.findIndex((v) => v !== null);
  let lastIdx = -1;
  for (let i = s.lat.length - 1; i >= 0; i--)
    if (s.lat[i] !== null) {
      lastIdx = i;
      break;
    }
  for (const [idx, kind] of [
    [firstIdx, "start"],
    [lastIdx, "end"],
  ] as const) {
    if (idx >= 0)
      ends.features.push({
        type: "Feature",
        properties: { kind },
        geometry: { type: "Point", coordinates: [s.lon[idx]!, s.lat[idx]!] },
      });
  }
  const cur: FeatureCollection = { type: "FeatureCollection", features: [] };
  if (cursor !== null && s.lat[cursor] != null && s.lon[cursor] != null) {
    cur.features.push({
      type: "Feature",
      properties: {},
      geometry: { type: "Point", coordinates: [s.lon[cursor]!, s.lat[cursor]!] },
    });
  }
  const surface = CHROME[mode].surface;
  return [
    {
      id: "route-casing",
      type: "line",
      data: route,
      paint: { "line-color": surface, "line-width": 7, "line-opacity": 0.9 },
      layout: { "line-cap": "round", "line-join": "round" },
    },
    {
      id: "route",
      type: "line",
      data: route,
      paint: { "line-color": ["get", "color"], "line-width": 4 },
      layout: { "line-cap": "round", "line-join": "round" },
    },
    {
      id: "ends",
      type: "circle",
      data: ends,
      paint: {
        "circle-radius": 6,
        "circle-color": ["match", ["get", "kind"], "start", "#0ca30c", "#d03b3b"],
        "circle-stroke-color": surface,
        "circle-stroke-width": 2,
      },
    },
    {
      id: "cursor",
      type: "circle",
      data: cur,
      paint: {
        "circle-radius": 7,
        "circle-color": CATEGORICAL[mode][0]!,
        "circle-stroke-color": surface,
        "circle-stroke-width": 3,
      },
    },
  ];
}

function bounds(track: Detail["track"]): Bounds | null {
  if (!track) return null;
  return [
    [track.min_lon, track.min_lat],
    [track.max_lon, track.max_lat],
  ];
}

interface Series {
  key: string;
  label: string;
  unit: string;
  values: (number | null)[];
  color: string;
  format: (v: number) => string;
  /** Smallest y span shown (so a steady cadence isn't blown up into noise) and tick step. */
  minSpan: number;
  step: number;
  inverse?: boolean;
  area?: boolean;
}

/**
 * Robust y range: 1st–99th percentile (a strap's first-minute spike can't flatten the rest),
 * at least `minSpan` wide, snapped to `step` with an even number of steps so the middle tick
 * is round too.
 */
function yBounds(ser: Series): { min: number; max: number; interval: number } | null {
  const finite = ser.values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (finite.length < 2) return null;
  let lo = quantile(finite, 0.01);
  let hi = quantile(finite, 0.99);
  if (hi - lo < ser.minSpan) {
    const mid = (lo + hi) / 2;
    lo = mid - ser.minSpan / 2;
    hi = mid + ser.minSpan / 2;
  }
  const min = Math.floor(lo / ser.step) * ser.step;
  let max = Math.ceil(hi / ser.step) * ser.step;
  if (Math.round((max - min) / ser.step) % 2 === 1) max += ser.step;
  return { min, max, interval: (max - min) / 2 };
}

function buildSeries(d: Detail, s: Streams, units: UnitSystem, mode: Mode): Series[] {
  const c = MEASURE_COLORS[mode];
  const out: Series[] = [];
  const has = (a: (number | null)[]) => a.some((v) => v !== null && v !== 0);
  if (has(s.altitude_m)) {
    const f = units === "metric" ? 1 : 3.28084;
    out.push({
      key: "alt",
      label: "Elevation",
      unit: units === "metric" ? "m" : "ft",
      values: s.altitude_m.map((v) => (v == null ? null : v * f)),
      color: c.elevation,
      format: (v) => fmtNumber(v),
      minSpan: units === "metric" ? 20 : 60,
      step: units === "metric" ? 10 : 25,
      area: true,
    });
  }
  if (has(s.hr))
    out.push({
      key: "hr",
      label: "Heart rate",
      unit: "bpm",
      values: s.hr,
      color: c.hr,
      format: (v) => fmtNumber(v),
      minSpan: 30,
      step: 10,
    });
  if (has(s.speed_mps) && d.distance_m) {
    if (usesPace(d.sport_group) && d.sport_group !== "swim") {
      const moving = s.speed_mps.filter((v): v is number => v !== null && v > 0.5);
      const cap = paceSeconds(quantile(moving, 0.05) || 1, units);
      out.push({
        key: "pace",
        label: "Pace",
        unit: `/${distanceUnit(units)}`,
        values: s.speed_mps.map((v) =>
          v == null || v < 0.5 ? null : Math.min(paceSeconds(v, units), cap),
        ),
        color: c.pace,
        format: (v) => fmtDuration(v),
        minSpan: 60,
        step: 15,
        inverse: true,
      });
    } else {
      out.push({
        key: "speed",
        label: "Speed",
        unit: speedUnit(units),
        values: s.speed_mps.map((v) => (v == null ? null : speedValue(v, units))),
        color: c.pace,
        format: (v) => fmtNumber(v, 1),
        minSpan: 6,
        step: 2,
      });
    }
  }
  if (has(s.cadence))
    out.push({
      key: "cad",
      label: "Cadence",
      unit: d.sport_group === "ride" ? "rpm" : "spm",
      values: s.cadence.map((v) => (v ? v : null)),
      color: c.cadence,
      format: (v) => fmtNumber(v),
      minSpan: 20,
      step: 5,
    });
  if (has(s.power_w))
    out.push({
      key: "pow",
      label: "Power",
      unit: "W",
      values: s.power_w,
      color: c.power,
      format: (v) => fmtNumber(v),
      minSpan: 100,
      step: 25,
    });
  return out;
}

const SMOOTHED = new Set(["pace", "speed", "cad", "pow", "hr"]);

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
          const win = SMOOTHED.has(ser.key) ? Math.max(3, Math.round(ser.values.length / 120)) : 1;
          const values = smooth(
            ser.values,
            ser.key === "hr" ? Math.max(1, Math.round(win / 3)) : win,
          );
          const data = values.map((v, i) => [x[i], v]);
          const bounds = yBounds(ser);
          const option: ChartOption = {
            grid: { ...GRID, top: 28, bottom: idx === series.length - 1 ? 4 : 0 },
            title: {
              text: `${ser.label} (${ser.unit})`,
              left: 0,
              top: 0,
              textStyle: { fontSize: 12, fontWeight: 500, color: CHROME[mode].text2 },
            },
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
          itemStyle: { color: ZONE_RAMP[mode][i], borderRadius: [0, 4, 4, 0] },
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

/** "+42 / −38 m"; "flat" when the split neither climbs nor drops. */
function elevationText(
  gain: number | null | undefined,
  loss: number | null | undefined,
  units: UnitSystem,
): string {
  if (gain == null && loss == null) return DASH;
  const up = Math.round(gain ?? 0);
  const down = Math.round(loss ?? 0);
  if (up === 0 && down === 0) return "flat";
  if (down === 0) return `+${fmtElevation(up, units)}`;
  if (up === 0) return `−${fmtElevation(down, units)}`;
  return `+${fmtElevation(up, units).split(" ")[0]} / −${fmtElevation(down, units)}`;
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
                        className="block h-2 rounded-full"
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
            className="rounded-xl px-3 py-1.5 text-sm text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            All activities
          </Link>
          {d.previous_id && (
            <Link
              to="/activities/$activityId"
              params={{ activityId: String(d.previous_id) }}
              aria-label="Previous activity"
              className="rounded-xl p-2 text-ink-2 hover:bg-surface-2 hover:text-ink"
            >
              <ChevronLeft size={18} />
            </Link>
          )}
          {d.next_id && (
            <Link
              to="/activities/$activityId"
              params={{ activityId: String(d.next_id) }}
              aria-label="Next activity"
              className="rounded-xl p-2 text-ink-2 hover:bg-surface-2 hover:text-ink"
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
                  className="h-1.5 w-28 rounded-full"
                  style={{
                    background: `linear-gradient(90deg, ${mode === "dark" ? BLUE[400] : BLUE[450]}, #eda100, ${mode === "dark" ? "#e66767" : "#e34948"})`,
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
