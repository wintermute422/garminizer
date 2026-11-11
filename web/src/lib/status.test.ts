import { describe, expect, it } from "vitest";
import {
  acwrState,
  hrvState,
  pressureStatus,
  readinessState,
  sleepState,
  trainingKey,
  trainingState,
} from "./status";

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

describe("training status keys", () => {
  it.each([
    ["PRODUCTIVE_3", "PRODUCTIVE"],
    ["productive", "PRODUCTIVE"],
    ["OVERREACHING_12", "OVERREACHING"],
    ["MAINTAINING", "MAINTAINING"],
    ["NO_STATUS", null],
    ["NO_STATUS_1", null],
    ["NONE", null],
    ["", null],
    [null, null],
    [undefined, null],
  ])("%s → %s", (raw, key) => {
    expect(trainingKey(raw)).toBe(key);
  });

  it("every caller of trainingState gets the normalised key", () => {
    expect(trainingState("PRODUCTIVE_3")).toEqual({ status: "good", label: "Productive" });
    expect(trainingState("strained_2")).toEqual({ status: "critical", label: "Strained" });
    expect(trainingState("NO_STATUS")).toEqual({ status: null, label: "No status" });
    expect(trainingState("RECOVERY")).toEqual({ status: null, label: "Recovery" });
  });
});

describe("blood pressure categories", () => {
  it.each([
    ["NORMAL", "good"],
    ["LOW", "good"],
    ["ELEVATED", "warning"],
    ["HIGH_STAGE_1", "serious"],
    ["STAGE_2_HYPERTENSION", "critical"],
    ["HYPERTENSIVE_CRISIS", "critical"],
    ["", null],
    [null, null],
    ["UNKNOWN", null],
  ])("%s → %s", (category, status) => {
    expect(pressureStatus(category)).toBe(status);
  });
});
