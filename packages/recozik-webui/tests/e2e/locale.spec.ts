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
    await page.goto("/fr");
    await expect(page).toHaveURL(/\/fr$/);
    await expect(page.getByTestId("main-heading")).toHaveText(
      "Console Web Recozik",
    );
    await expect(page.getByTestId("login-prompt")).toBeVisible();
  });

  test("redirects / to /fr when Accept-Language prefers French", async ({
    request,
  }) => {
    const response = await request.get("/", {
      headers: {
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
      },
      maxRedirects: 0,
    });

    expect([307, 308]).toContain(response.status());
    expect(response.headers()["location"]).toBe("/fr");
  });
});
