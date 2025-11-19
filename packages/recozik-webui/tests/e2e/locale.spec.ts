import { test, expect } from "@playwright/test";

test.describe("Locale and landing flow", () => {
  test("redirects to /en and shows unauthenticated landing", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/en$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Recozik Web Console",
    );
    await expect(page.getByText("Connect with an API token")).toBeVisible();
  });
});
