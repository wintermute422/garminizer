/**
 * Demo tour video for announcements (demo data only). Runs only when DEMO_TOUR is set — use
 * scripts/demo_tour.sh, which verifies the database is the demo database first and copies the
 * recording to artifacts/demo-tour.webm.
 */
import { expect, test, type Page } from "@playwright/test";

const SIZE = { width: 1280, height: 720 };

test.skip(!process.env.DEMO_TOUR, "demo tour only via scripts/demo_tour.sh");
// Unlike the page tests, the tour keeps chart animations: it is watched, not compared.
test.use({
  viewport: SIZE,
  video: { mode: "on", size: SIZE },
  contextOptions: { reducedMotion: "no-preference" },
});

/** The page behind `url` has its data, charts and maps. */
async function settle(page: Page, url: RegExp): Promise<void> {
  await page.waitForURL(url);
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(page.locator(".animate-pulse")).toHaveCount(0, { timeout: 30_000 });
  const maps = page.locator('[data-testid="map"]');
  for (let i = 0; i < (await maps.count()); i++) {
    await expect(maps.nth(i)).toHaveAttribute("data-map-ready", "true", { timeout: 30_000 });
  }
}

/** Scroll by `dy` pixels in small steps, so the recording glides instead of jumping. */
async function glide(page: Page, dy: number): Promise<void> {
  const steps = Math.max(1, Math.round(Math.abs(dy) / 20));
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, dy / steps);
    await page.waitForTimeout(30);
  }
}

async function open(page: Page, label: string, url: RegExp): Promise<void> {
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: label, exact: true })
    .click();
  await settle(page, url);
}

test("demo tour", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop-dark", "one recording: desktop, dark");
  test.setTimeout(240_000);

  await page.goto("/");
  await settle(page, /\/$/);
  await page.mouse.move(SIZE.width / 2, SIZE.height / 2);
  await page.waitForTimeout(3000);
  await glide(page, 800);
  await page.waitForTimeout(2000);

  await open(page, "Activities", /\/activities/);
  await page.waitForTimeout(1500);
  // A run has what the detail page is about: the route on the map and linked charts.
  const activities = page.locator('main a[href^="/activities/"]');
  const runs = activities.filter({ hasText: /run/i });
  await ((await runs.count()) > 0 ? runs : activities).first().click();
  await settle(page, /\/activities\/\d+/);
  await page.waitForTimeout(2500);
  // Move along the first chart: the map cursor follows.
  const chart = page.locator('[data-testid="chart"]').first();
  await chart.scrollIntoViewIfNeeded();
  const box = await chart.boundingBox();
  if (box) {
    for (let i = 0; i <= 40; i++) {
      await page.mouse.move(box.x + 60 + ((box.width - 100) * i) / 40, box.y + box.height / 2);
      await page.waitForTimeout(60);
    }
  }
  await page.waitForTimeout(1000);
  await glide(page, 700);
  await page.waitForTimeout(1500);

  await open(page, "Training load", /\/training/);
  await page.waitForTimeout(2500);
  await glide(page, 600);
  await page.waitForTimeout(1500);

  await open(page, "Sleep", /\/sleep/);
  await page.waitForTimeout(2500);
  await glide(page, 500);
  await page.waitForTimeout(1500);

  await open(page, "Map", /\/map/);
  await page.waitForTimeout(3500);

  await open(page, "Insights", /\/insights/);
  await page.waitForTimeout(2500);
  await glide(page, 600);
  await page.waitForTimeout(1500);

  await open(page, "Year in review", /\/year/);
  await page.waitForTimeout(3000);
});
