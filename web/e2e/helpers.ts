import type { Page } from "@playwright/test";

/**
 * Content width beyond the configured viewport. Compare with the configured width, not
 * innerWidth: mobile emulation widens the layout viewport to fit oversized content.
 */
export async function pageOverflow(page: Page): Promise<number> {
  const width = page.viewportSize()?.width ?? 0;
  const content = await page.evaluate(() =>
    Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  );
  return content - width;
}
