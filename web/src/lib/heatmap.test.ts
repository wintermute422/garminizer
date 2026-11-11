import { describe, expect, it } from "vitest";
import { HEAT_RAMP, quantileBins } from "./heatmap";

const fmt = (v: number) => String(v);
const id = (v: number) => v;

describe("quantileBins", () => {
  it("cuts the positive values at their quartiles into 4 bins across the ramp", () => {
    const values = [0, 0, ...Array.from({ length: 100 }, (_, i) => i + 1)];
    const bins = quantileBins(values, "light", id, fmt);
    expect(bins.map((b) => [b.min, b.max])).toEqual([
      [0, 26],
      [26, 51],
      [51, 75],
      [75, null],
    ]);
    expect(bins.map((b) => b.color)).toEqual(HEAT_RAMP.light);
    expect(bins.map((b) => b.label)).toEqual(["up to 26", "26–51", "51–75", "over 75"]);
  });

  it("merges cuts that round to the same value (nice) and spreads colours over the ends", () => {
    const values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
    const tens = (v: number) => Math.round(v / 5) * 5; // 3.25 → 5, 5.5 → 5, 7.75 → 10
    const bins = quantileBins(values, "dark", tens, fmt);
    expect(bins.map((b) => [b.min, b.max])).toEqual([
      [0, 5],
      [5, null],
    ]);
    expect(bins.map((b) => b.color)).toEqual([HEAT_RAMP.dark[0], HEAT_RAMP.dark[3]]);
  });

  it("one bin when every value is the same; none without activity", () => {
    const bins = quantileBins([3, 3, 3], "light", id, fmt);
    expect(bins).toEqual([{ min: 0, max: null, color: HEAT_RAMP.light[3], label: "Active" }]);
    expect(quantileBins([0, 0], "light", id, fmt)).toEqual([]);
    expect(quantileBins([], "light", id, fmt)).toEqual([]);
  });
});
