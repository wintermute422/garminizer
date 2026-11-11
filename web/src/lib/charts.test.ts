import { describe, expect, it } from "vitest";
import {
  asParams,
  axisTooltip,
  DAY_MS,
  dayExtent,
  dayOfPoint,
  dayPoint,
  dayTitle,
  dayTooltip,
  dayX,
  itemTooltip,
  niceScale,
  niceStep,
  roundStackTops,
  rowAt,
  tooltipTitle,
} from "./charts";
import { addDays } from "./range";
import { barEnd, CHROME } from "./tokens";

describe("day scale", () => {
  it("places a day at local noon and maps it back", () => {
    const x = dayX("2026-03-29");
    expect(new Date(x).getHours()).toBe(12);
    expect(dayOfPoint(x)).toBe("2026-03-29");
    expect(dayPoint("2026-03-29", 7)).toEqual([x, 7]);
    expect(dayPoint("2026-03-29", undefined)).toEqual([x, null]);
  });

  it.each(["Europe/Berlin", "America/New_York", "Australia/Lord_Howe", "UTC"])(
    "round-trips every day of two years in %s, whatever the DST rules",
    (tz) => {
      // Node re-reads TZ when it changes (the app tsconfig has no Node types, hence the cast).
      const env = (globalThis as unknown as { process: { env: Record<string, string> } }).process
        .env;
      const saved = Intl.DateTimeFormat().resolvedOptions().timeZone;
      env.TZ = tz;
      try {
        // The zone switch took effect (Berlin is UTC+1 in January).
        if (tz === "Europe/Berlin") expect(new Date("2026-01-15T12:00:00Z").getHours()).toBe(13);
        let day = "2025-01-01";
        for (let i = 0; i < 730; i++) {
          expect(dayOfPoint(dayX(day))).toBe(day);
          // DST days are 23 or 25 h long: an hour inside half a day stays on the same day.
          expect(dayOfPoint(dayX(day) - DAY_MS / 2 + 3_600_000)).toBe(day);
          expect(dayOfPoint(dayX(day) + DAY_MS / 2 - 3_600_000)).toBe(day);
          expect(addDays(day, 1) > day).toBe(true);
          day = addDays(day, 1);
        }
        expect(day).toBe("2027-01-01");
      } finally {
        env.TZ = saved;
      }
    },
  );

  it("pads half a day around the first and last noon marks", () => {
    const e = dayExtent("2026-10-01", "2026-10-31");
    expect(e.min).toBe(dayX("2026-10-01") - DAY_MS / 2);
    expect(e.max).toBe(dayX("2026-10-31") + DAY_MS / 2);
  });

  it("midnight bounds cover start 00:00 to the midnight after end", () => {
    const e = dayExtent("2026-10-01", "2026-10-31", "midnight");
    expect(e.min).toBe(new Date("2026-10-01T00:00:00").getTime());
    expect(e.max).toBe(new Date("2026-11-01T00:00:00").getTime());
    expect(new Date(e.max).getHours()).toBe(0);
  });

  it("titles a day with weekday and year", () => {
    const title = dayTitle("2026-10-31");
    expect(title).toBe(
      tooltipTitle(
        new Date("2026-10-31T12:00:00").toLocaleDateString(undefined, {
          weekday: "short",
          day: "numeric",
          month: "short",
          year: "numeric",
        }),
      ),
    );
    expect(title).toContain("2026");
  });
});

describe("tooltips", () => {
  const rows = [
    { day: "2026-10-01", v: 1 },
    { day: "2026-10-02", v: 2 },
    { day: "2026-10-04", v: 4 },
  ];
  const byX = new Map(rows.map((r) => [dayX(r.day), r]));

  it("normalises ECharts params to an array", () => {
    expect(asParams([{ dataIndex: 1 }])).toEqual([{ dataIndex: 1 }]);
    expect(asParams({ dataIndex: 2 })).toEqual([{ dataIndex: 2 }]);
    expect(asParams(undefined)).toEqual([]);
  });

  it("axis and item tooltips hand formatters normalised params", () => {
    const axis = axisTooltip((arr) => arr.map((p) => p.seriesName).join(","));
    const fmt = axis.formatter as (p: unknown) => string;
    expect(fmt([{ seriesName: "a" }, { seriesName: "b" }])).toBe("a,b");
    expect(fmt({ seriesName: "solo" })).toBe("solo");
    expect(axis).toMatchObject({ trigger: "axis", axisPointer: { type: "line" }, confine: true });
    expect(axisTooltip(undefined, { axisPointer: { type: "shadow" } })).toEqual({
      trigger: "axis",
      axisPointer: { type: "shadow" },
      confine: true,
    });
    const item = itemTooltip<{ name: string }>((p) => p.name);
    expect((item.formatter as (p: unknown) => string)({ name: "x" })).toBe("x");
    expect(itemTooltip()).toEqual({ trigger: "item", confine: true });
  });

  it("finds the hovered row from the first known [x, …] value", () => {
    const params = [
      { value: [dayX("2026-09-01"), 5] }, // not a row (e.g. a padding point)
      { value: 3 }, // not an array
      { value: [dayX("2026-10-02"), 2] },
    ];
    expect(rowAt(params, byX)).toBe(rows[1]);
    expect(rowAt({ value: [dayX("2026-10-04"), null] }, byX)).toBe(rows[2]);
  });

  it("falls back to the day under the axis pointer", () => {
    // A pointer anywhere on the 1st (not just at noon) resolves to that day's row.
    const x = new Date("2026-10-01T18:30:00").getTime();
    expect(rowAt([{ value: undefined, axisValue: x }], byX)).toBe(rows[0]);
    expect(rowAt([{ axisValue: dayX("2026-10-03") }], byX)).toBeUndefined();
    expect(rowAt([], byX)).toBeUndefined();
  });

  it("dayTooltip renders the hovered row with its index, nothing between days", () => {
    const fmt = dayTooltip(
      rows,
      (r) => r.day,
      (r, i) => `${r.day}#${i}=${r.v}`,
    );
    expect(fmt([{ value: [dayX("2026-10-04"), 4] }])).toBe("2026-10-04#2=4");
    expect(fmt([{ seriesName: "x", value: [dayX("2026-10-03"), 1] }])).toBe("");
  });
});

describe("roundStackTops", () => {
  it("rounds the highest non-empty segment of each column, not just the last series", () => {
    const series = [
      {
        name: "a",
        data: [
          [1, 2],
          [2, 3],
          [3, 0],
        ],
      },
      {
        name: "b",
        data: [
          [1, 4],
          [2, null],
          [3, 0],
        ],
      },
      {
        name: "c",
        data: [
          [1, 0],
          [2, 0],
          [3, 0],
        ],
      },
    ];
    const out = roundStackTops(series, "light");
    const rounded = { borderRadius: barEnd("up"), borderColor: CHROME.light.surface };
    expect(out[0]!.data).toEqual([[1, 2], { value: [2, 3], itemStyle: rounded }, [3, 0]]);
    expect(out[1]!.data).toEqual([{ value: [1, 4], itemStyle: rounded }, [2, null], [3, 0]]);
    expect(out[2]!.data).toEqual(series[2]!.data);
    expect(out.every((s) => (s.emphasis as { focus: string }).focus === "none")).toBe(true);
  });
});

// ---------------------------------------------------------------- round axes

// The page-local variants niceScale replaced, kept verbatim as the reference.
const legacy = {
  performance(lo: number, hi: number, steps: number[], ticks = 4) {
    const raw = Math.max(hi - lo, 1e-9) / ticks;
    const interval = steps.find((s) => s >= raw) ?? steps[steps.length - 1]!;
    return {
      min: Math.floor(lo / interval) * interval,
      max: Math.ceil(hi / interval) * interval,
      interval,
    };
  },
  gear(v: number, ticks = 4) {
    if (!(v > 0)) return { max: 1, interval: 0.25 };
    const raw = v / ticks;
    const p = 10 ** Math.floor(Math.log10(raw));
    const f = raw / p;
    const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 3 ? 3 : f <= 5 ? 5 : 10) * p;
    return { max: Math.ceil(v / step) * step, interval: step };
  },
  records(lo: number, hi: number) {
    if (hi - lo < lo * 0.02) {
      lo -= lo * 0.02;
      hi += hi * 0.02;
    }
    const steps = [1, 2, 5, 10, 15, 20, 30, 60, 120, 180, 240, 300, 600, 900, 1800, 3600];
    const interval = steps.find((s) => s >= (hi - lo) / 4) ?? 3600;
    return {
      min: Math.max(0, Math.floor(lo / interval) * interval),
      max: Math.ceil(hi / interval) * interval,
      interval,
    };
  },
  activity(lo: number, hi: number, step: number) {
    const min = Math.floor(lo / step) * step;
    let max = Math.ceil(hi / step) * step;
    if (Math.round((max - min) / step) % 2 === 1) max += step;
    return { min, max, interval: (max - min) / 2 };
  },
  training(lo: number, hi: number) {
    const raw = (hi - lo) / 4;
    const interval =
      [5, 10, 20, 25, 30, 50, 100].find((s) => s >= raw) ?? Math.ceil(raw / 100) * 100;
    return {
      min: Math.floor(lo / interval) * interval,
      max: Math.ceil(hi / interval) * interval,
      interval,
    };
  },
};

/** Deterministic pseudo-random samples (no Math.random in tests). */
function samples(n: number, scale: number): [number, number][] {
  const out: [number, number][] = [[0, 0]];
  let s = 7;
  const next = () => {
    s = (s * 48271) % 2147483647;
    return s / 2147483647;
  };
  for (let i = 0; i < n; i++) {
    const a = (next() - 0.3) * scale;
    const b = a + next() * scale * (i % 3 === 0 ? 0.01 : 1);
    out.push([a, b]);
  }
  return out;
}

describe("niceScale reproduces every former page variant", () => {
  const PERF_STEPS = [5, 10, 15, 20, 30, 60, 120, 300, 600, 900, 1800];
  const RECORD_STEPS = [1, 2, 5, 10, 15, 20, 30, 60, 120, 180, 240, 300, 600, 900, 1800, 3600];

  it("performance (step list, ticks)", () => {
    for (const [lo, hi] of samples(400, 4000)) {
      expect(niceScale(lo, hi, { steps: PERF_STEPS })).toEqual(
        legacy.performance(lo, hi, PERF_STEPS),
      );
      expect(niceScale(lo, hi, { steps: [1, 2, 5, 10], ticks: 3 })).toEqual(
        legacy.performance(lo, hi, [1, 2, 5, 10], 3),
      );
    }
  });

  it("gear (1-2-2.5-3-5 decades from zero)", () => {
    for (const [, v] of samples(400, 50_000)) {
      if (!(v > 0)) continue;
      const { max, interval } = niceScale(0, v, { steps: niceStep });
      expect({ max, interval }).toEqual(legacy.gear(v));
    }
  });

  it("records (durations, floor at zero)", () => {
    for (const [a, b] of samples(400, 20_000)) {
      let lo = Math.abs(a);
      let hi = lo + Math.abs(b - a);
      const ref = legacy.records(lo, hi);
      if (hi - lo < lo * 0.02) {
        lo -= lo * 0.02;
        hi += hi * 0.02;
      }
      expect(niceScale(lo, hi, { steps: RECORD_STEPS, floor: 0 })).toEqual(ref);
    }
  });

  it("activity streams (fixed step, even number of steps)", () => {
    for (const step of [2, 5, 10, 15, 25]) {
      for (const [lo, hi] of samples(200, 300)) {
        const b = niceScale(lo, hi, { steps: [step], even: true });
        expect({ ...b, interval: (b.max - b.min) / 2 }).toEqual(legacy.activity(lo, hi, step));
      }
    }
  });

  it("training form axis (step list, then hundreds)", () => {
    const steps = (raw: number) =>
      [5, 10, 20, 25, 30, 50, 100].find((s) => s >= raw) ?? Math.ceil(raw / 100) * 100;
    for (const [lo, hi] of samples(400, 2000)) {
      expect(niceScale(lo, hi, { steps })).toEqual(legacy.training(lo, hi));
    }
  });
});
