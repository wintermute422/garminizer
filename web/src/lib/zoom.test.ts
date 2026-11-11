import { describe, expect, it } from "vitest";
import {
  DAY_MS,
  dayAxis,
  dayExtent,
  dayX,
  GRID,
  isZoomed,
  withZoom,
  ZOOM_MIN_SPAN,
  ZOOM_SLIDER_SPACE,
  zoomAround,
  zoomedDayTicks,
} from "./charts";
import { CHROME } from "./tokens";

type Obj = Record<string, unknown>;

const ext = dayExtent("2025-11-12", "2026-11-11");
const timeOption = (): Obj => ({
  grid: { ...GRID, right: 40 },
  xAxis: dayAxis(ext.min, ext.max),
  yAxis: { type: "value" },
  series: [{ type: "line", data: [[dayX("2026-01-01"), 80]] }],
});
const zooms = (o: Obj) => o.dataZoom as Obj[];

describe("withZoom", () => {
  it("adds one visible slider under the plot and keeps the option otherwise", () => {
    const base = timeOption();
    const z = withZoom(base, "light");
    expect(zooms(z)).toHaveLength(1);
    const s = zooms(z)[0]!;
    expect(s).toMatchObject({ type: "slider", show: true, xAxisIndex: 0, filterMode: "filter" });
    expect(s.minValueSpan).toBe(ZOOM_MIN_SPAN);
    expect(s.fillerColor).toBe(CHROME.light.zoom);
    expect(z.series).toBe(base.series);
    expect(base.dataZoom).toBeUndefined();
  });

  it("makes room for the slider below the axis labels", () => {
    const z = withZoom(timeOption(), "dark");
    expect(z.grid).toMatchObject({
      bottom: GRID.bottom + ZOOM_SLIDER_SPACE,
      right: 40,
      outerBounds: { left: 0, right: 0, top: 0, bottom: ZOOM_SLIDER_SPACE },
    });
    const s = zooms(z)[0]!;
    expect((s.bottom as number) + (s.height as number)).toBeLessThan(ZOOM_SLIDER_SPACE);
    expect(s.right).toBe(48);
  });

  it("never adds an inside zoom (it would swallow page scrolling over the chart)", () => {
    for (const slider of [true, false]) {
      const types = zooms(withZoom(timeOption(), "light", slider)).map((d) => d.type);
      expect(types).not.toContain("inside");
    }
  });

  it("linked charts get a hidden slider and keep their layout", () => {
    const base = timeOption();
    const z = withZoom(base, "light", false);
    expect(zooms(z)).toEqual([expect.objectContaining({ type: "slider", show: false })]);
    expect(z.grid).toBe(base.grid);
  });

  it("only time axes get a minimum window", () => {
    const z = withZoom({ xAxis: { type: "category", data: ["a", "b"] } }, "light");
    expect(zooms(z)[0]!.minValueSpan).toBeUndefined();
  });
});

describe("isZoomed", () => {
  it("is false for the full axis and true for any smaller window", () => {
    expect(isZoomed(undefined)).toBe(false);
    expect(isZoomed({ start: 0, end: 100 })).toBe(false);
    expect(isZoomed({ start: 0, end: 99.5 })).toBe(true);
    expect(isZoomed({ start: 20, end: 100 })).toBe(true);
  });
});

describe("zoomAround", () => {
  // Full axis 0…1000, showing 200…600 (20 % – 60 %).
  const w = { start: 20, end: 60, startValue: 200, endValue: 600 };

  it("keeps the value under the pointer in place", () => {
    const next = zoomAround(w, 300, 0.5)!;
    expect(next.endValue - next.startValue).toBeCloseTo(200);
    // 300 was 25 % into the window before and still is.
    expect((300 - next.startValue) / (next.endValue - next.startValue)).toBeCloseTo(0.25);
  });

  it("zooming out stops at the full axis", () => {
    expect(zoomAround(w, 400, 10)).toEqual({ startValue: 0, endValue: 1000 });
    const near = zoomAround(w, 590, 2)!;
    expect(near.endValue).toBeLessThanOrEqual(1000);
    expect(near.startValue).toBeGreaterThanOrEqual(0);
    expect(near.endValue - near.startValue).toBeCloseTo(800);
  });

  it("zooming in stops at the minimum span", () => {
    const next = zoomAround(w, 400, 0.001, 50)!;
    expect(next.endValue - next.startValue).toBeCloseTo(50);
  });

  it("works on the unzoomed axis and needs values to act on", () => {
    const full = { start: 0, end: 100, startValue: 0, endValue: 10 * DAY_MS };
    const next = zoomAround(full, 5 * DAY_MS, 0.5, ZOOM_MIN_SPAN)!;
    expect(next).toEqual({ startValue: 2.5 * DAY_MS, endValue: 7.5 * DAY_MS });
    expect(zoomAround({ start: 0, end: 100 }, 1, 0.5)).toBeNull();
  });
});

describe("zoomedDayTicks", () => {
  it("recomputes dayAxis ticks for the visible window only", () => {
    const from = dayX("2026-09-01");
    const to = dayX("2026-10-15");
    const patch = zoomedDayTicks(timeOption(), {
      start: 80,
      end: 92,
      startValue: from,
      endValue: to,
    });
    const label = (patch?.xAxis as Obj).axisLabel as { customValues: number[] };
    expect(label.customValues.length).toBeGreaterThan(2);
    for (const v of label.customValues) {
      expect(v).toBeGreaterThanOrEqual(from - DAY_MS);
      expect(v).toBeLessThanOrEqual(to + DAY_MS);
    }
    // A 6-week window gets fortnightly Mondays, not the year view's month starts.
    const full = (dayAxis(ext.min, ext.max).axisLabel as { customValues: number[] }).customValues;
    expect(label.customValues).not.toEqual(full.filter((v) => v >= from && v <= to));
    // Patch keeps the zoom window: no min/max.
    expect(patch?.xAxis).not.toHaveProperty("min");
  });

  it("leaves other axes alone", () => {
    const w = { start: 10, end: 20, startValue: 1, endValue: 2 };
    expect(zoomedDayTicks({ xAxis: { type: "time" } }, w)).toBeNull();
    expect(zoomedDayTicks({ xAxis: { type: "category", data: [] } }, w)).toBeNull();
    expect(zoomedDayTicks(timeOption(), { start: 10, end: 20 })).toBeNull();
  });
});
