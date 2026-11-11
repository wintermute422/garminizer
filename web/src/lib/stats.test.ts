import { describe, expect, it } from "vitest";
import { DAY_MS } from "./charts";
import {
  diff,
  maxOf,
  mean,
  minOf,
  previousPeriod,
  quantile,
  spanDays,
  stdev,
  trailingByTime,
  weekly,
} from "./stats";

describe("stats", () => {
  it("counts days inclusively and finds the previous period of the same length", () => {
    expect(spanDays("2026-10-01", "2026-10-31")).toBe(31);
    // Across the end of DST (25 h day) it is still a whole number of days.
    expect(spanDays("2026-10-20", "2026-11-05")).toBe(17);
    expect(previousPeriod({ start: "2026-10-01", end: "2026-10-31" })).toEqual({
      start: "2026-08-31",
      end: "2026-09-30",
    });
  });

  it("ignores missing values", () => {
    const v = [3, null, 1, undefined, Number.NaN, 5];
    expect(mean(v)).toBe(3);
    expect(minOf(v)).toBe(1);
    expect(maxOf(v)).toBe(5);
    expect(stdev(v)).toBe(2);
    expect(stdev([4])).toBeNull();
    expect(mean([])).toBeNull();
    expect(diff(5, 3)).toBe(2);
    expect(diff(null, 3)).toBeNull();
  });

  it("quantile picks the nearest-rank value of the present values", () => {
    const v = [10, 1, null, 7, 3, 5];
    expect(quantile(v, 0)).toBe(1);
    expect(quantile(v, 0.5)).toBe(5);
    expect(quantile(v, 1)).toBe(10);
    expect(quantile(v, 0.05)).toBe(1);
    expect(quantile(v, 0.99)).toBe(10);
    expect(quantile([], 0.5)).toBeNull();
    // The input is not reordered.
    expect(v).toEqual([10, 1, null, 7, 3, 5]);
  });

  it("aggregates per ISO week (Monday start)", () => {
    const rows = [
      { day: "2026-11-01", v: 1 }, // Sunday → week of Oct 26
      { day: "2026-11-02", v: 2 }, // Monday
      { day: "2026-11-08", v: 4 }, // Sunday, same week
      { day: "2026-11-09", v: null },
    ];
    expect(
      weekly(
        rows,
        (r) => r.day,
        (r) => r.v,
      ),
    ).toEqual([
      { week: "2026-10-26", value: 1 },
      { week: "2026-11-02", value: 3 },
      { week: "2026-11-09", value: null },
    ]);
  });

  it("trailing mean over calendar days, not samples", () => {
    const t = (d: number) => d * DAY_MS;
    const pts = [
      { t: t(0), v: 10 },
      { t: t(1), v: 20 },
      { t: t(8), v: 30 }, // the first two are 7+ days back
      { t: t(9), v: null },
    ];
    expect(trailingByTime(pts, 7)).toEqual([10, 15, 30, 30]);
  });
});
