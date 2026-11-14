import { describe, expect, it } from "vitest";
import {
  activityNote,
  checkpointState,
  dayNotes,
  daysBetween,
  fmtRate,
  formErrors,
  newestFirst,
  targetAt,
} from "./goal";

const run = {
  activity_id: 1,
  name: "Run",
  sport_group: "run",
  sport_type: "running",
  start_time_local: "2026-10-29T18:21:35",
  duration_s: 2517,
  distance_m: 7110,
  avg_hr: 146,
  calories: 558,
  active_kcal: 510,
};

describe("goal notes", () => {
  it("summarises an activity", () => {
    expect(activityNote(run, "metric")).toMatch(/^Run 7[.,]11 km · 41:57 · 146 bpm · 558 kcal$/);
  });

  it("leaves out missing parts and falls back to the sport label", () => {
    const a = { ...run, name: null, distance_m: null, avg_hr: null, calories: null };
    expect(activityNote(a, "metric")).toBe("Running · 41:57");
  });

  it("joins meal names and lists activities on their own lines", () => {
    const lines = dayNotes({ meal_names: ["Oats", "Pasta"], activities: [run] }, "metric");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toBe("Oats · Pasta");
    expect(dayNotes({ meal_names: [], activities: [] }, "metric")).toEqual([]);
  });
});

describe("checkpoints", () => {
  it("offers to accept missed or unweighed checkpoints and to undo accepted ones", () => {
    expect(checkpointState({ status: "missed" }).action).toEqual({
      accepted: true,
      label: "Count as reached",
    });
    expect(checkpointState({ status: "no_weigh_in" }).action?.accepted).toBe(true);
    expect(checkpointState({ status: "accepted" }).action).toEqual({
      accepted: false,
      label: "Undo",
    });
    expect(checkpointState({ status: "reached" }).action).toBeNull();
    expect(checkpointState({ status: "upcoming" }).action).toBeNull();
    expect(checkpointState({ status: "reached" }).status).toBe("good");
  });
});

describe("target line", () => {
  const line = [
    { day: "2026-09-20", target_kg: 72 },
    { day: "2026-09-27", target_kg: 71.75 },
    { day: "2026-09-27", target_kg: 71 },
    { day: "2026-10-11", target_kg: 70.5 },
  ];

  it("interpolates inside a segment and takes the stepped-down value on an anchor day", () => {
    expect(targetAt(line, "2026-09-20")).toBe(72);
    expect(targetAt(line, "2026-09-27")).toBe(71);
    expect(targetAt(line, "2026-10-04")).toBeCloseTo(70.75);
    expect(targetAt(line, "2026-09-19")).toBeNull();
    expect(targetAt(line, "2026-10-12")).toBeNull();
  });

  it("counts days across DST changes", () => {
    expect(daysBetween("2026-10-20", "2026-11-03")).toBe(14);
  });
});

describe("form helpers", () => {
  it("maps FastAPI 422 details to fields", () => {
    const e = formErrors({
      detail: [
        { loc: ["body", "rate_kg_per_week"], msg: "Input should be greater than 0" },
        { loc: ["body"], msg: "Value error, end_day must be after start_day" },
      ],
    });
    expect(e.fields).toEqual({ rate_kg_per_week: "Input should be greater than 0" });
    expect(e.general).toEqual(["end_day must be after start_day"]);
  });

  it("keeps a plain detail string", () => {
    expect(formErrors({ detail: "no weight goal is set" }).general).toEqual([
      "no weight goal is set",
    ]);
    expect(formErrors(null)).toEqual({ fields: {}, general: [] });
  });

  it("formats the rate and sorts the log", () => {
    expect(fmtRate(0.25)).toMatch(/^−0[.,]25 kg\/week$/);
    expect(fmtRate(0.5)).toMatch(/^−0[.,]5 kg\/week$/);
    expect(newestFirst([{ day: "2026-01-01" }, { day: "2026-01-03" }]).map((d) => d.day)).toEqual([
      "2026-01-03",
      "2026-01-01",
    ]);
  });
});
