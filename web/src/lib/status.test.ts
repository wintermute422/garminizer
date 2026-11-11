import { describe, expect, it } from "vitest";
import {
  acwrState,
  hrvState,
  pressureStatus,
  readinessState,
  sleepState,
  stressLabel,
  todaysCall,
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

describe("stress bands", () => {
  it.each([
    [null, "No data"],
    [0, "Resting"],
    [25, "Resting"],
    [26, "Low"],
    [50, "Low"],
    [75, "Medium"],
    [76, "High"],
  ])("%s → %s", (v, label) => {
    expect(stressLabel(v)).toBe(label);
  });
});

describe("todaysCall", () => {
  const good = {
    readiness: { score: 85, level: "HIGH", recovery_time_min: 60 },
    hrv: { status: "BALANCED" },
    sleep: { duration_s: 8 * 3600, score: 88 },
    tsb: 2,
    acwrStatus: "OPTIMAL",
    batteryAtWake: 80,
  };

  it("says nothing without readiness, HRV and sleep", () => {
    expect(todaysCall({ ...good, readiness: null, hrv: { status: null }, sleep: null })).toBeNull();
  });

  it("green light needs good readiness and no flags", () => {
    expect(todaysCall(good)).toEqual({
      tone: "go",
      status: "good",
      headline: "Green light for a hard session",
      reasons: ["readiness 85 (high)", "HRV balanced", "form +2"],
    });
    // Without fresh form it mentions the sleep instead.
    expect(todaysCall({ ...good, tsb: -8 })!.reasons).toEqual([
      "readiness 85 (high)",
      "HRV balanced",
      "slept 8h 00m",
    ]);
  });

  it("amber flags keep it steady", () => {
    const call = todaysCall({
      ...good,
      readiness: { score: 62, level: "MODERATE", recovery_time_min: 8 * 60 },
      sleep: { duration_s: 6.5 * 3600, score: 70 },
      tsb: -25,
    })!;
    expect(call.tone).toBe("steady");
    expect(call.status).toBe("warning");
    // At most three reasons, in rule order.
    expect(call.reasons).toEqual(["readiness 62", "sleep 6h 30m", "8h recovery left"]);
  });

  it("no readiness score today is steady, not green", () => {
    const call = todaysCall({ ...good, readiness: null })!;
    expect(call.tone).toBe("steady");
    expect(call.reasons).toEqual(["no readiness score for today"]);
  });

  it("any red flag wins over amber ones and lists the red ones first", () => {
    const call = todaysCall({
      ...good,
      hrv: { status: "UNBALANCED" },
      acwrStatus: "VERY_HIGH",
      batteryAtWake: 20,
    })!;
    expect(call).toMatchObject({ tone: "easy", status: "serious", headline: "Take it easy today" });
    expect(call.reasons).toEqual([
      "acute load very high",
      "body battery 20 at wake",
      "HRV unbalanced",
    ]);
    expect(
      todaysCall({ ...good, readiness: { score: 30, level: "POOR", recovery_time_min: 0 } })!
        .reasons,
    ).toEqual(["readiness 30"]);
    expect(
      todaysCall({ ...good, readiness: { score: 80, level: null, recovery_time_min: 1800 } })!
        .reasons,
    ).toEqual(["30h recovery left"]);
  });
});
