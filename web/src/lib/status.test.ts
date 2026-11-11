import { describe, expect, it } from "vitest";
import { acwrState, hrvState, readinessState, sleepState, trainingState } from "./status";

describe("Garmin state → status colour (one table for every page)", () => {
  it.each([
    ["PRIME", "good"],
    ["HIGH", "good"],
    ["MODERATE", null],
    ["LOW", "warning"],
    ["POOR", "critical"],
  ])("readiness %s → %s", (key, status) => {
    expect(readinessState(key).status).toBe(status);
  });

  it.each([
    ["EXCELLENT", "good"],
    ["GOOD", "good"],
    ["FAIR", "warning"],
    ["POOR", "critical"],
  ])("sleep %s → %s", (key, status) => {
    expect(sleepState(key).status).toBe(status);
  });

  it.each([
    ["BALANCED", "good"],
    ["UNBALANCED", "warning"],
    ["LOW", "serious"],
    ["POOR", "critical"],
  ])("hrv %s → %s", (key, status) => {
    expect(hrvState(key).status).toBe(status);
  });

  it("labels and unknown keys", () => {
    expect(readinessState("MODERATE").label).toBe("Moderate");
    expect(trainingState("STRAINED").status).toBe("critical");
    expect(acwrState("VERY_HIGH").status).toBe("critical");
    expect(hrvState("SOMETHING_NEW")).toEqual({ status: null, label: "Something New" });
    expect(sleepState(null)).toEqual({ status: null, label: "No status" });
  });
});
