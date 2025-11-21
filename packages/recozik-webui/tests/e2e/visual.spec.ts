import { test, expect } from "@playwright/test";

// Visual baseline: chromium only to keep snapshots stable.
test.describe("Visual regressions", () => {
  test.skip(({ browserName }) => browserName !== "chromium");

  test("landing page screenshot", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/en");
    await expect(page.getByTestId("main-heading")).toBeVisible();

    await expect(page).toHaveScreenshot("landing-en.png", {
      fullPage: true,
      animations: "disabled",
    });
  });
});
