import { defineConfig, devices } from "@playwright/test";

/**
 * e2e runs against the production build served by FastAPI (scripts/e2e.sh starts it on
 * E2E_BASE_URL with a deterministic demo database). Four variants per page: desktop/mobile ×
 * dark/light.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8421";

const variants = [
  {
    name: "desktop-dark",
    device: devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    theme: "dark",
  },
  {
    name: "desktop-light",
    device: devices["Desktop Chrome"],
    viewport: { width: 1440, height: 900 },
    theme: "light",
  },
  {
    name: "mobile-dark",
    device: devices["Pixel 7"],
    viewport: { width: 390, height: 844 },
    theme: "dark",
  },
  {
    name: "mobile-light",
    device: devices["Pixel 7"],
    viewport: { width: 390, height: 844 },
    theme: "light",
  },
] as const;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: variants.map((v) => ({
    name: v.name,
    use: {
      ...v.device,
      viewport: v.viewport,
      colorScheme: v.theme,
      storageState: {
        cookies: [],
        origins: [
          {
            origin: baseURL,
            localStorage: [
              { name: "gz.theme", value: v.theme },
              { name: "gz.units", value: "metric" },
            ],
          },
        ],
      },
    },
  })),
});
