/**
 * Pure maths of the activity page: the route coloured by a stream (map layers), the stream
 * series with their robust y ranges and smoothing, and split elevation text.
 */
import type { Feature, FeatureCollection, LineString } from "geojson";
import type { Schemas } from "@/api/client";
import type { MapLayer } from "@/components/MapView";
import { niceScale } from "@/lib/charts";
import {
  DASH,
  distanceUnit,
  fmtDuration,
  fmtElevation,
  fmtNumber,
  paceSeconds,
  speedUnit,
  speedValue,
  type UnitSystem,
} from "@/lib/format";
import type { Bounds } from "@/lib/geo";
import { usesPace } from "@/lib/sports";
import { quantile } from "@/lib/stats";
import { CATEGORICAL, CHROME, MEASURE_COLORS, ROUTE_RAMP, STATUS, type Mode } from "@/lib/tokens";

export type Detail = Schemas["ActivityDetail"];
export type Streams = Schemas["Streams"];

export type MapMetric = "speed" | "hr" | "altitude";

export function lerpColor(stops: readonly string[], t: number): string {
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1);
  const i = Math.min(Math.floor(x), stops.length - 2);
  const f = x - i;
  const a = Number.parseInt(stops[i]!.slice(1), 16);
  const b = Number.parseInt(stops[i + 1]!.slice(1), 16);
  const ch = (s: number) => Math.round(((a >> s) & 255) * (1 - f) + ((b >> s) & 255) * f);
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
}

export function routeLayers(
  s: Streams,
  metric: MapMetric,
  mode: Mode,
  cursor: number | null,
): MapLayer[] {
  const raw = metric === "speed" ? s.speed_mps : metric === "hr" ? s.hr : s.altitude_m;
  const finite = raw.filter((v): v is number => v !== null);
  const lo = quantile(finite, 0.05) ?? 0;
  const hi = quantile(finite, 0.95) ?? 0;
  const ramp = ROUTE_RAMP[mode];
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
        "circle-color": ["match", ["get", "kind"], "start", STATUS.good, STATUS.critical],
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

export function bounds(track: Detail["track"]): Bounds | null {
  if (!track) return null;
  return [
    [track.min_lon, track.min_lat],
    [track.max_lon, track.max_lat],
  ];
}

export interface Series {
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
export function yBounds(ser: Series): { min: number; max: number; interval: number } | null {
  const finite = ser.values.filter((v): v is number => v !== null && Number.isFinite(v));
  if (finite.length < 2) return null;
  let lo = quantile(finite, 0.01)!;
  let hi = quantile(finite, 0.99)!;
  if (hi - lo < ser.minSpan) {
    const mid = (lo + hi) / 2;
    lo = mid - ser.minSpan / 2;
    hi = mid + ser.minSpan / 2;
  }
  const { min, max } = niceScale(lo, hi, { steps: [ser.step], even: true });
  return { min, max, interval: (max - min) / 2 };
}

const SMOOTHED = new Set(["pace", "speed", "cad", "pow", "hr"]);

/** Smoothing window (samples) of a stream: ~1/120 of the series, HR a third of that. */
export function smoothingWindow(key: string, samples: number): number {
  const win = SMOOTHED.has(key) ? Math.max(3, Math.round(samples / 120)) : 1;
  return key === "hr" ? Math.max(1, Math.round(win / 3)) : win;
}

export function buildSeries(d: Detail, s: Streams, units: UnitSystem, mode: Mode): Series[] {
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

/** "+42 / −38 m"; "flat" when the split neither climbs nor drops. */
export function elevationText(
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
