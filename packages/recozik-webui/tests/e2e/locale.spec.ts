import { test, expect } from "@playwright/test";

test.describe("Locale and landing flow", () => {
  test("redirects to /en and shows unauthenticated landing", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/en$/);
    await expect(page.getByTestId("main-heading")).toHaveText(
      "Recozik Web Console",
    );
    await expect(page.getByTestId("login-prompt")).toBeVisible();
  });

  test("renders French locale route", async ({ page }) => {
    await page.context().setExtraHTTPHeaders({
      "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    });
    await page.goto("/");
    await expect(page).toHaveURL(/\/fr$/);
    await expect(page.getByTestId("main-heading")).toHaveText(
      "Console Web Recozik",
    );
    await expect(page.getByTestId("login-prompt")).toBeVisible();
  });
});
