/**
 * First-run experience: a fresh install shows a welcome screen with the Garmin sign-in, then
 * the first sync's progress, and the dashboards once data exists. The e2e database is the demo
 * (always "ready"), so the earlier stages are produced by answering /api/sync/status here.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { pageOverflow } from "./helpers";

const SHOT_DIR = path.resolve(process.cwd(), "..", "artifacts", "screenshots");

const EMPTY = {
  connected: false,
  is_demo: false,
  running: false,
  mfa_pending: false,
  last_runs: [],
  cursors: [],
  recent_errors: [],
  first_day: null,
  last_day: null,
};

const RUNNING = {
  ...EMPTY,
  connected: true,
  running: true,
  last_runs: [
    {
      id: 1,
      kind: "incremental",
      started_at: "2026-10-31T08:00:00Z",
      finished_at: null,
      status: "running",
      requests: 42,
      items_written: 1234,
      message: null,
    },
  ],
};

const HISTORY_LOADING = {
  ...EMPTY,
  connected: true,
  first_day: "2026-08-01",
  last_day: "2026-10-31",
  cursors: [
    {
      dataset: "sleep",
      oldest_day: "2026-08-01",
      newest_day: "2026-10-31",
      complete: false,
      updated_at: "2026-10-31T08:00:00Z",
    },
  ],
};

/** Answer the status request with `status` and hide the demo athlete from /api/meta. */
async function mockStatus(page: Page, status: object): Promise<void> {
  await page.route("**/api/sync/status", (route) => route.fulfill({ json: status }));
  await page.route("**/api/meta", async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ response, json: { ...body, athlete: null } });
  });
}

async function seriousAxe(page: Page): Promise<string[]> {
  const axe = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return axe.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help}`);
}

async function shot(page: Page, project: string, name: string): Promise<void> {
  fs.mkdirSync(path.join(SHOT_DIR, project), { recursive: true });
  await page.screenshot({ path: path.join(SHOT_DIR, project, `${name}.png`), fullPage: true });
}

test("first run: welcome screen instead of empty dashboards", async ({ page }, info) => {
  await mockStatus(page, EMPTY);
  for (const url of ["/", "/training", "/sync"]) {
    await page.goto(url);
    await expect(page.locator("main h1")).toHaveText("Welcome to Garminizer");
  }
  await expect(page.locator('[data-testid="first-run"]')).toHaveAttribute("data-stage", "welcome");
  await expect(page.getByLabel("Garmin e-mail")).toBeVisible();
  await expect(page.getByLabel("Garmin password")).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect Garmin" })).toBeVisible();
  await expect(page.locator('[data-testid="chart"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="demo-banner"]')).toHaveCount(0);
  expect(await pageOverflow(page), "no horizontal page overflow").toBeLessThanOrEqual(1);
  await shot(page, info.project.name, "first-run-welcome");
  expect(await seriousAxe(page), "no serious/critical axe violations").toEqual([]);
});

test("first run: sync progress after connecting", async ({ page }, info) => {
  await mockStatus(page, RUNNING);
  await page.goto("/");
  await expect(page.locator("main h1")).toHaveText("Your first sync is running");
  await expect(page.locator('[data-testid="first-run"]')).toHaveAttribute(
    "data-stage",
    "first-sync",
  );
  await expect(page.getByRole("status")).toContainText("42 requests");
  await expect(page.getByRole("status")).toContainText("1,234 items");
  expect(await pageOverflow(page), "no horizontal page overflow").toBeLessThanOrEqual(1);
  await shot(page, info.project.name, "first-run-sync");
  expect(await seriousAxe(page), "no serious/critical axe violations").toEqual([]);

  // The details stay reachable while the first sync runs.
  await page.locator("main").getByRole("link", { name: "Sync & settings" }).click();
  await expect(page.locator("main h1")).toHaveText("Sync & settings");
});

test("first run: a stalled first sync can be started by hand", async ({ page }) => {
  await mockStatus(page, { ...RUNNING, running: false, last_runs: [] });
  await page.goto("/");
  await expect(page.locator("main h1")).toHaveText("Connected to Garmin");
  await expect(page.getByRole("button", { name: "Sync now" })).toBeVisible();
});

test("first run: the demo goes straight to the dashboards", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(page.locator('[data-testid="chart"]').first()).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('[data-testid="first-run"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="history-banner"]')).toHaveCount(0);
});

test("first run: a note while older history is loading, until dismissed", async ({ page }) => {
  await mockStatus(page, HISTORY_LOADING);
  await page.goto("/");
  const banner = page.locator('[data-testid="history-banner"]');
  await expect(banner).toContainText("Older history is still loading");
  await expect(page.locator('[data-testid="first-run"]')).toHaveCount(0);
  await banner.getByRole("button", { name: "Hide this note" }).click();
  await expect(banner).toHaveCount(0);
  await page.reload();
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(banner).toHaveCount(0);
});
