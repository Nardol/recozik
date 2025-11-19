import { test, expect } from "@playwright/test";

test.describe("Locale and landing flow", () => {
  test("redirects to /en and allows switching to /fr without token", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page).toHaveURL(/\/en$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Recozik Web Console",
    );
    await expect(page.getByText("Connect with an API token")).toBeVisible();

    const select = page.getByRole("combobox", { name: "Interface language" });
    await select.selectOption("fr");

    await expect(page).toHaveURL(/\/fr$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(
      "Console Web Recozik",
    );
    await expect(page.getByText("Connexion avec un jeton API")).toBeVisible();

    await select.selectOption("en");
    await expect(page).toHaveURL(/\/en$/);
  });
});
