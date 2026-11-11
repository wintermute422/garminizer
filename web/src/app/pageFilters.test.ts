import { describe, expect, it } from "vitest";
import { navItemFor } from "./nav";
import { resolvePageFilters } from "./pageFilters";

const meta = { last_day: "2026-06-30", first_day: "2024-01-01" };

describe("resolvePageFilters", () => {
  it("uses the page's default preset from nav.ts when the URL has none", () => {
    const calendar = resolvePageFilters({}, navItemFor("/calendar"), meta);
    expect(calendar).toMatchObject({
      start: "2025-07-01",
      end: "2026-06-30",
      preset: "365d",
      defaultPreset: "365d",
    });
    expect(resolvePageFilters({}, navItemFor("/body"), meta).preset).toBe("365d");
    expect(resolvePageFilters({}, navItemFor("/health"), meta)).toMatchObject({
      start: "2026-04-02",
      preset: "90d",
      defaultPreset: "90d",
    });
  });

  it("an explicit preset or custom range wins over the default", () => {
    expect(resolvePageFilters({ preset: "30d" }, navItemFor("/calendar"), meta).start).toBe(
      "2026-06-01",
    );
    const custom = resolvePageFilters(
      { start: "2026-02-01", end: "2026-03-01", preset: "30d" },
      navItemFor("/calendar"),
      meta,
    );
    expect(custom).toMatchObject({ start: "2026-02-01", end: "2026-03-01", preset: null });
  });

  it("adds the chosen sport to the query on sport-filtered pages", () => {
    const f = resolvePageFilters({ sport: "ride" }, navItemFor("/activities"), meta);
    expect(f.sport).toBe("ride");
    expect(f.query).toEqual({ start: f.start, end: f.end, sport: "ride" });
    expect(f.dates).toEqual({ start: f.start, end: f.end });
    const all = resolvePageFilters({}, navItemFor("/map"), meta);
    expect(all.sport).toBeNull();
    expect(all.query).toEqual(all.dates);
    expect("sport" in all.query).toBe(false);
  });

  it("ignores a sport left in the URL on pages without a sport filter", () => {
    const f = resolvePageFilters({ sport: "ride" }, navItemFor("/health"), meta);
    expect(f.sport).toBeNull();
    expect(f.query).toEqual(f.dates);
  });

  it("falls back to the page's default sport (records: run)", () => {
    expect(resolvePageFilters({}, navItemFor("/records"), meta).sport).toBe("run");
    expect(resolvePageFilters({ sport: "swim" }, navItemFor("/records"), meta).sport).toBe("swim");
  });

  it("works before the data extent is known and on pages outside the nav", () => {
    const f = resolvePageFilters({ preset: "30d" }, undefined, undefined);
    expect(f.defaultPreset).toBe("90d");
    expect(f.preset).toBe("30d");
    expect(f.sport).toBeNull();
    expect(f.end).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
