/**
 * A9 + A10: every page loads without console errors, every chart draws data, every map loads,
 * and axe finds no serious/critical accessibility violations. Screenshots of each page are
 * written to ../artifacts/screenshots/<variant>/ for review (demo data only).
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";

export const PAGES: { name: string; path: string }[] = [
  { name: "overview", path: "/" },
  { name: "activities", path: "/activities?preset=90d" },
  { name: "activity", path: "/activities/__RUN__" },
  { name: "training", path: "/training?preset=365d" },
  { name: "performance", path: "/performance?preset=365d" },
  { name: "records", path: "/records?preset=all" },
  { name: "health", path: "/health?preset=90d" },
  { name: "sleep", path: "/sleep?preset=90d" },
  { name: "body", path: "/body?preset=365d" },
  { name: "calendar", path: "/calendar?preset=365d" },
  { name: "map", path: "/map?preset=all" },
  { name: "insights", path: "/insights?preset=365d" },
  { name: "gear", path: "/gear" },
  { name: "year", path: "/year" },
  { name: "sync", path: "/sync" },
];

const SHOT_DIR = path.resolve(process.cwd(), "..", "artifacts", "screenshots");

/**
 * Content width beyond the configured viewport. Compare with the configured width, not
 * innerWidth: mobile emulation widens the layout viewport to fit oversized content.
 */
async function pageOverflow(page: Page): Promise<number> {
  const width = page.viewportSize()?.width ?? 0;
  const content = await page.evaluate(() =>
    Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  );
  return content - width;
}

test("overflow check detects a too-wide page (self-test)", async ({ page }) => {
  await page.goto("/sync");
  await expect(page.locator("main h1").first()).toBeVisible();
  expect(await pageOverflow(page)).toBeLessThanOrEqual(1);
  await page.evaluate(() => {
    const wide = document.createElement("div");
    wide.style.width = "2000px";
    wide.style.height = "10px";
    document.querySelector("main")?.appendChild(wide);
  });
  expect(await pageOverflow(page)).toBeGreaterThan(100);
});

async function runActivityId(page: Page): Promise<string> {
  const res = await page.request.get("/api/activities?sport=run&limit=1&sort=distance&preset=all");
  const body = (await res.json()) as { items: { activity_id: number }[] };
  return String(body.items[0]?.activity_id ?? "");
}

for (const p of PAGES) {
  test(`page ${p.name}`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("response", (res) => {
      if (res.url().includes("/api/") && res.status() >= 400)
        errors.push(`HTTP ${res.status()} ${res.url()}`);
    });

    let url = p.path;
    if (url.includes("__RUN__")) url = url.replace("__RUN__", await runActivityId(page));
    await page.goto(url);
    await expect(page.locator("main h1").first()).toBeVisible();
    // Data loaded = no skeleton placeholders left (map tiles may keep streaming).
    await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 30_000 });

    const charts = page.locator('[data-testid="chart"]');
    const nCharts = await charts.count();
    for (let i = 0; i < nCharts; i++) {
      const chart = charts.nth(i);
      await chart.scrollIntoViewIfNeeded();
      await expect(chart, `chart ${i} renders`).toHaveAttribute("data-chart-ready", "true");
      const points = Number(await chart.getAttribute("data-points"));
      const label = await chart.getAttribute("aria-label");
      expect(points, `chart "${label}" has data`).toBeGreaterThan(0);
      const box = await chart.boundingBox();
      expect(box?.width ?? 0, `chart "${label}" has width`).toBeGreaterThan(50);
    }
    const maps = page.locator('[data-testid="map"]');
    for (let i = 0; i < (await maps.count()); i++) {
      await maps.nth(i).scrollIntoViewIfNeeded();
      await expect(maps.nth(i)).toHaveAttribute("data-map-ready", "true", { timeout: 30_000 });
    }

    // No horizontal page scroll at any width (see pageOverflow).
    expect(await pageOverflow(page), "no horizontal page overflow").toBeLessThanOrEqual(1);

    await page.evaluate(() => window.scrollTo(0, 0));
    fs.mkdirSync(path.join(SHOT_DIR, info.project.name), { recursive: true });
    await page.screenshot({
      path: path.join(SHOT_DIR, info.project.name, `${p.name}.png`),
      fullPage: true,
    });

    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    const serious = axe.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map(
        (v) =>
          `${v.id} (${v.impact}): ${v.help} — ${v.nodes
            .slice(0, 3)
            .map((n) => n.target.join(" "))
            .join(" | ")}`,
      );
    expect(serious, "no serious/critical axe violations").toEqual([]);

    const relevant = errors.filter((e) => !/Download the React DevTools/.test(e));
    expect(relevant, "no console errors").toEqual([]);
  });
}
