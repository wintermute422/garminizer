import { describe, expect, it } from "vitest";
import {
  fmtClockFromNoon,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  fmtHours,
  fmtPace,
  fmtSpeed,
  fmtTimeDelta,
  shown,
  signed,
  titleCase,
} from "./format";
import { addDays, resolveRange } from "./range";
import { bySlot, sportColor } from "./sports";

describe("format", () => {
  it("formats distance in both unit systems", () => {
    expect(fmtDistance(10_000, "metric")).toMatch(/^10[.,]0 km$/);
    expect(fmtDistance(1609.344, "imperial")).toMatch(/^1[.,]00 mi$/);
    expect(fmtDistance(null, "metric")).toBe("–");
  });

  it("formats durations", () => {
    expect(fmtDuration(59)).toBe("0:59");
    expect(fmtDuration(3725)).toBe("1:02:05");
    expect(fmtHours(3 * 3600 + 5 * 60)).toBe("3h 05m");
    expect(fmtHours(42 * 60)).toBe("42m");
  });

  it("formats pace and speed", () => {
    expect(fmtPace(1000 / 300, "metric")).toBe("5:00 /km");
    expect(fmtPace(100 / 120, "metric", true)).toBe("2:00 /100 m");
    expect(fmtPace(0, "metric")).toBe("–");
    expect(fmtSpeed(10, "metric")).toMatch(/^36[.,]0 km\/h$/);
  });

  it("formats elevation, signs, clock and keys", () => {
    expect(fmtElevation(100, "imperial")).toBe("328 ft");
    expect(signed(3)).toBe("+3");
    expect(signed(-2.5, 1)).toMatch(/^−2[.,]5$/);
    expect(fmtClockFromNoon(690)).toBe("23:30");
    expect(fmtClockFromNoon(1140)).toBe("07:00");
    expect(titleCase("LACTATE_THRESHOLD")).toBe("Lactate Threshold");
  });

  it("formats time deltas (records and race predictions share it)", () => {
    expect(fmtTimeDelta(0)).toBe("no change");
    expect(fmtTimeDelta(0.4)).toBe("no change");
    expect(fmtTimeDelta(18)).toBe("+18 s");
    expect(fmtTimeDelta(-18.4)).toBe("−18 s");
    expect(fmtTimeDelta(-59.6)).toBe("−1:00");
    expect(fmtTimeDelta(83)).toBe("+1:23");
    expect(fmtTimeDelta(-3725)).toBe("−1:02:05");
  });

  it("rounds values the way they are shown", () => {
    expect(shown(0.04, 1)).toBe(0);
    expect(shown(-0.4, 0)).toBe(0);
    expect(shown(0.06, 1)).toBe(0.06);
    expect(shown(null, 1)).toBeNull();
  });
});

describe("range", () => {
  it("resolves presets relative to the last data day", () => {
    expect(resolveRange({ preset: "30d" }, "2026-06-30", "2025-01-01")).toEqual({
      start: "2026-06-01",
      end: "2026-06-30",
      preset: "30d",
    });
    expect(resolveRange({ preset: "ytd" }, "2026-06-30", null).start).toBe("2026-01-01");
    expect(resolveRange({ preset: "all" }, "2026-06-30", "2025-01-01").start).toBe("2025-01-01");
    expect(resolveRange({ start: "2026-02-01", end: "2026-03-01" }, "2026-06-30", null)).toEqual({
      start: "2026-02-01",
      end: "2026-03-01",
      preset: null,
    });
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});

describe("sports", () => {
  it("keeps colour with the entity and sorts by slot", () => {
    expect(sportColor("run", "light")).toBe("#2a78d6");
    expect(sportColor("ride", "dark")).toBe("#d95926");
    expect(sportColor("unknown", "light")).toBe("#898781");
    expect(["hike", "run", "ride"].sort(bySlot)).toEqual(["run", "ride", "hike"]);
  });
});
