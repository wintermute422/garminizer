/**
 * README screenshots (viewport-sized, demo data only). Runs only when README_SHOTS is set —
 * use scripts/screenshots.sh, which verifies the database is the demo database first.
 */
import { expect, test } from "@playwright/test";
import * as path from "node:path";

const OUT = path.resolve(process.cwd(), "..", "docs", "screenshots");

const SHOTS: { name: string; path: string; scrollTo?: string }[] = [
  { name: "overview", path: "/" },
  { name: "activity", path: "/activities/__RUN__" },
  { name: "training", path: "/training?preset=365d" },
  { name: "health", path: "/health?preset=90d" },
  { name: "sleep", path: "/sleep?preset=90d" },
  { name: "records", path: "/records?preset=all" },
  { name: "map", path: "/map?preset=all" },
  { name: "insights", path: "/insights?preset=365d" },
  { name: "calendar", path: "/calendar?preset=730d" },
  { name: "year", path: "/year" },
];

test.skip(!process.env.README_SHOTS, "README screenshots only via scripts/screenshots.sh");

for (const shot of SHOTS) {
  test(`readme ${shot.name}`, async ({ page }, info) => {
    test.skip(!info.project.name.startsWith("desktop"), "desktop only");
    let url = shot.path;
    if (url.includes("__RUN__")) {
      const res = await page.request.get("/api/activities?sport=run&limit=1&sort=distance");
      const body = (await res.json()) as { items: { activity_id: number }[] };
      url = url.replace("__RUN__", String(body.items[0]?.activity_id ?? ""));
    }
    await page.goto(url);
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 30_000 });
    const charts = page.locator('[data-testid="chart"]');
    for (let i = 0; i < Math.min(await charts.count(), 6); i++) {
      await expect(charts.nth(i)).toHaveAttribute("data-chart-ready", "true");
    }
    const maps = page.locator('[data-testid="map"]');
    for (let i = 0; i < (await maps.count()); i++) {
      await expect(maps.nth(i)).toHaveAttribute("data-map-ready", "true", { timeout: 30_000 });
    }
    await page.waitForTimeout(1200); // let map tiles and chart animations settle
    const theme = info.project.name.endsWith("light") ? "light" : "dark";
    await page.screenshot({ path: path.join(OUT, `${shot.name}-${theme}.png`) });
  });
}
