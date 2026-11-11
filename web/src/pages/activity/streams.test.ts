import type { FeatureCollection } from "geojson";
import { describe, expect, it } from "vitest";
import { CATEGORICAL, ROUTE_RAMP, STATUS } from "@/lib/tokens";
import {
  bounds,
  buildSeries,
  elevationText,
  lerpColor,
  routeLayers,
  smoothingWindow,
  yBounds,
  type Detail,
  type Series,
  type Streams,
} from "./streams";

/** Synthetic streams: a straight line of `n` points (no real coordinates). */
function streams(n: number, over: Partial<Streams> = {}): Streams {
  const idx = Array.from({ length: n }, (_, i) => i);
  return {
    points: n,
    source_points: n,
    t_s: idx,
    distance_m: idx.map((i) => i * 3),
    lat: idx.map((i) => 10 + i * 1e-4),
    lon: idx.map((i) => 20 + i * 1e-4),
    altitude_m: idx.map((i) => 100 + (i % 10)),
    hr: idx.map((i) => 120 + (i % 30)),
    speed_mps: idx.map((i) => 2.5 + (i % 5) * 0.1),
    cadence: idx.map(() => 0),
    power_w: idx.map(() => null),
    temperature_c: idx.map(() => null),
    ...over,
  };
}

const run = { sport_group: "run", distance_m: 5000, avg_power_w: null } as unknown as Detail;
const ride = { sport_group: "ride", distance_m: 30000, avg_power_w: 180 } as unknown as Detail;

describe("lerpColor", () => {
  it("interpolates along the stops and clamps", () => {
    const stops = ["#000000", "#ffffff"];
    expect(lerpColor(stops, 0)).toBe("rgb(0,0,0)");
    expect(lerpColor(stops, 1)).toBe("rgb(255,255,255)");
    expect(lerpColor(stops, 0.5)).toBe("rgb(128,128,128)");
    expect(lerpColor(stops, -3)).toBe("rgb(0,0,0)");
    expect(lerpColor(stops, 7)).toBe("rgb(255,255,255)");
    expect(lerpColor(["#ff0000", "#00ff00", "#0000ff"], 0.75)).toBe("rgb(0,128,128)");
  });
});

describe("routeLayers", () => {
  const data = (layers: ReturnType<typeof routeLayers>, id: string) =>
    layers.find((l) => l.id === id)!.data as FeatureCollection;

  it("colours each segment by the stream between its 5th and 95th percentile", () => {
    const s = streams(50);
    const layers = routeLayers(s, "hr", "light", null);
    expect(layers.map((l) => l.id)).toEqual(["route-casing", "route", "ends", "cursor"]);
    const route = data(layers, "route");
    expect(route.features).toHaveLength(49);
    const colors = route.features.map((f) => f.properties!.color as string);
    // Low HR at the start of each 30-sample cycle, high at its end.
    expect(colors[0]).toBe(lerpColor(ROUTE_RAMP.light, 0));
    expect(colors[28]).toBe(lerpColor(ROUTE_RAMP.light, 1));
    const ends = data(layers, "ends").features.map((f) => f.properties!.kind);
    expect(ends).toEqual(["start", "end"]);
    expect(data(layers, "cursor").features).toHaveLength(0);
    expect(layers.find((l) => l.id === "ends")!.paint!["circle-color"]).toEqual([
      "match",
      ["get", "kind"],
      "start",
      STATUS.good,
      STATUS.critical,
    ]);
  });

  it("skips gaps, centres a flat stream and marks the cursor", () => {
    const s = streams(6, {
      lat: [1, 1.001, null, 1.003, 1.004, null],
      altitude_m: [5, 5, 5, 5, 5, 5],
    });
    const layers = routeLayers(s, "altitude", "dark", 3);
    const route = data(layers, "route");
    expect(route.features).toHaveLength(2); // 0→1 and 3→4 only
    expect(new Set(route.features.map((f) => f.properties!.color))).toEqual(
      new Set([lerpColor(ROUTE_RAMP.dark, 0.5)]),
    );
    const ends = data(layers, "ends").features;
    expect(ends.map((f) => (f.geometry as { coordinates: number[] }).coordinates)).toEqual([
      [s.lon[0], 1],
      [s.lon[4], 1.004],
    ]);
    expect(data(layers, "cursor").features).toHaveLength(1);
    expect(layers.find((l) => l.id === "cursor")!.paint!["circle-color"]).toBe(CATEGORICAL.dark[0]);
  });

  it("copes with a stream without values", () => {
    const s = streams(3, { speed_mps: [null, null, null] });
    const route = data(routeLayers(s, "speed", "light", null), "route");
    expect(route.features).toHaveLength(2);
  });
});

describe("bounds", () => {
  it("turns the track box into map bounds", () => {
    expect(bounds(null)).toBeNull();
    const track = { min_lon: 1, min_lat: 2, max_lon: 3, max_lat: 4 } as Detail["track"];
    expect(bounds(track)).toEqual([
      [1, 2],
      [3, 4],
    ]);
  });
});

describe("yBounds", () => {
  const ser = (values: (number | null)[], minSpan = 30, step = 10): Series => ({
    key: "hr",
    label: "Heart rate",
    unit: "bpm",
    values,
    color: "#000000",
    format: String,
    minSpan,
    step,
  });

  it("ignores a first-minute spike (1st–99th percentile) and keeps an even step count", () => {
    const values = [200, ...Array.from({ length: 199 }, (_, i) => 120 + (i % 41))];
    const b = yBounds(ser(values))!;
    // 120–160 (the 200 bpm spike is beyond the 99th percentile), 4 steps of 10.
    expect(b).toEqual({ min: 120, max: 160, interval: 20 });
    // 120–170 is five steps: the top grows by one so the middle tick (150) is round.
    const wide = Array.from({ length: 199 }, (_, i) => 120 + (i % 51));
    expect(yBounds(ser(wide))).toEqual({ min: 120, max: 180, interval: 30 });
  });

  it("widens a steady signal to the minimum span", () => {
    expect(yBounds(ser([171, 172, 171, 172, 171]))).toEqual({ min: 150, max: 190, interval: 20 });
  });

  it("needs two values", () => {
    expect(yBounds(ser([null, 140]))).toBeNull();
  });
});

describe("buildSeries", () => {
  it("runs: elevation, HR and pace (capped, inverted); zero cadence is dropped", () => {
    const s = streams(40, { speed_mps: [0.2, ...Array.from({ length: 39 }, () => 3.2)] });
    const out = buildSeries(run, s, "metric", "light");
    expect(out.map((x) => x.key)).toEqual(["alt", "hr", "pace"]);
    const pace = out.find((x) => x.key === "pace")!;
    expect(pace.inverse).toBe(true);
    expect(pace.unit).toBe("/km");
    expect(pace.values[0]).toBeNull(); // standing still is no pace
    expect(pace.values[1]).toBeCloseTo(1000 / 3.2);
  });

  it("rides: speed, cadence and power in imperial units", () => {
    const s = streams(10, { cadence: Array(10).fill(85), power_w: Array(10).fill(200) });
    const out = buildSeries(ride, s, "imperial", "dark");
    expect(out.map((x) => x.key)).toEqual(["alt", "hr", "speed", "cad", "pow"]);
    expect(out[0]!.unit).toBe("ft");
    expect(out[0]!.values[0]).toBeCloseTo(100 * 3.28084);
    expect(out.find((x) => x.key === "speed")!.unit).toBe("mph");
    expect(out.find((x) => x.key === "cad")!.unit).toBe("rpm");
  });
});

describe("smoothingWindow", () => {
  it("scales with the series and is lighter for HR", () => {
    expect(smoothingWindow("pace", 120)).toBe(3);
    expect(smoothingWindow("pace", 1200)).toBe(10);
    expect(smoothingWindow("hr", 1200)).toBe(3);
    expect(smoothingWindow("hr", 100)).toBe(1);
    expect(smoothingWindow("alt", 5000)).toBe(1);
  });
});

describe("elevationText", () => {
  it("summarises a split's climb and drop", () => {
    expect(elevationText(null, undefined, "metric")).toBe("–");
    expect(elevationText(0.3, 0.2, "metric")).toBe("flat");
    expect(elevationText(42, 0, "metric")).toBe("+42 m");
    expect(elevationText(0, 38, "metric")).toBe("−38 m");
    expect(elevationText(42, 38, "metric")).toBe("+42 / −38 m");
    expect(elevationText(10, 0, "imperial")).toBe("+33 ft");
  });
});
