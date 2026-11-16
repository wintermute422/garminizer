import { describe, expect, it } from "vitest";
import { firstRunStage, historyLoading } from "./firstRun";

const cursor = (complete: boolean) => ({
  dataset: "sleep",
  oldest_day: "2026-01-01",
  newest_day: "2026-01-31",
  complete,
  updated_at: "2026-01-31T10:00:00Z",
});
const base = { is_demo: false, connected: false, first_day: null, cursors: [] };

describe("firstRunStage", () => {
  it("welcomes a fresh install without a Garmin connection", () => {
    expect(firstRunStage(base)).toBe("welcome");
  });

  it("waits for the first sync once connected and still empty", () => {
    expect(firstRunStage({ ...base, connected: true })).toBe("first-sync");
  });

  it("is ready as soon as one day of data exists", () => {
    expect(firstRunStage({ ...base, connected: true, first_day: "2026-01-31" })).toBe("ready");
  });

  it("never holds back the demo or a restored database without tokens", () => {
    expect(firstRunStage({ ...base, is_demo: true })).toBe("ready");
    expect(firstRunStage({ ...base, first_day: "2020-05-01" })).toBe("ready");
  });
});

describe("historyLoading", () => {
  const ready = { ...base, connected: true, first_day: "2026-01-01" };

  it("is on while a dataset has not reached the first Garmin day", () => {
    expect(historyLoading({ ...ready, cursors: [cursor(true), cursor(false)] })).toBe(true);
  });

  it("is off when every dataset is complete or nothing is tracked", () => {
    expect(historyLoading({ ...ready, cursors: [cursor(true)] })).toBe(false);
    expect(historyLoading(ready)).toBe(false);
  });

  it("is off before the first data, for the demo and without a connection", () => {
    const loading = [cursor(false)];
    expect(historyLoading({ ...base, connected: true, cursors: loading })).toBe(false);
    expect(historyLoading({ ...ready, is_demo: true, cursors: loading })).toBe(false);
    expect(historyLoading({ ...ready, connected: false, cursors: loading })).toBe(false);
  });
});
