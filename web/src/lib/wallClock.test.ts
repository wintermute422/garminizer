import { describe, expect, it } from "vitest";
import { fmtWallDate, fmtWallTime, wallClock, wallMidnight } from "./wallClock";

describe("athlete wall clock", () => {
  it("shows the athlete's local time whatever the browser zone, across DST", () => {
    const berlin = wallClock("Europe/Berlin");
    expect(fmtWallTime(berlin("2026-07-01T10:00:00Z"))).toBe("12:00"); // CEST
    expect(fmtWallTime(berlin("2026-01-01T10:00:00Z"))).toBe("11:00"); // CET
    // The night DST ends: 00:30 UTC is 02:30 CEST, 01:30 UTC is 02:30 CET.
    expect(fmtWallTime(berlin("2026-10-25T00:30:00Z"))).toBe("02:30");
    expect(fmtWallTime(berlin("2026-10-25T01:30:00Z"))).toBe("02:30");
    expect(fmtWallTime(wallClock("Asia/Kolkata")("2026-07-01T10:00:00Z"))).toBe("15:30");
  });

  it("falls back to UTC for a missing or unknown zone", () => {
    expect(fmtWallTime(wallClock(null)("2026-07-01T10:05:00Z"))).toBe("10:05");
    expect(fmtWallTime(wallClock("Not/AZone")("2026-07-01T10:05:00Z"))).toBe("10:05");
  });

  it("puts local midnight of a day on the same frame", () => {
    const m = wallMidnight("2026-10-25");
    expect(m).toBe(Date.UTC(2026, 9, 25));
    expect(fmtWallTime(m)).toBe("00:00");
    expect(fmtWallDate(m, { day: "numeric", month: "numeric", year: "numeric" })).toBe(
      new Date(Date.UTC(2026, 9, 25)).toLocaleDateString(undefined, {
        day: "numeric",
        month: "numeric",
        year: "numeric",
        timeZone: "UTC",
      }),
    );
  });
});
