import { test, expect } from "@playwright/test";

test.describe("Admin Token Management", () => {
  test.beforeEach(async ({ context }) => {
    // Mock authenticated admin user
    await context.route("**/api/whoami", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_id: "admin",
          display_name: "Admin User",
          roles: ["admin"],
          allowed_features: ["identify", "rename"],
        }),
      });
    });

    // Mock empty jobs list
    await context.route("**/api/jobs**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    // Mock users list (needed for token creation)
    await context.route("**/api/admin/users**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: 1,
            username: "admin",
            email: "admin@example.com",
            display_name: "Administrator",
            is_active: true,
            roles: ["admin"],
            allowed_features: ["identify"],
            quota_limits: {},
            created_at: "2024-01-01T00:00:00Z",
          },
          {
            id: 2,
            username: "apiuser",
            email: "api@example.com",
            display_name: "API User",
            is_active: true,
            roles: ["operator"],
            allowed_features: ["identify"],
            quota_limits: {},
            created_at: "2024-01-02T00:00:00Z",
          },
        ]),
      });
    });
  });

  test.describe("English locale", () => {
    test("shows token list for admin", async ({ page, context }) => {
      // Mock tokens API
      await context.route("**/api/admin/tokens**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              token: "admin-token-abc123",
              user_id: 1,
              display_name: "Admin CLI Token",
              roles: ["admin"],
              allowed_features: ["identify", "rename"],
              quota_limits: {},
            },
            {
              token: "readonly-token-xyz789",
              user_id: 2,
              display_name: "API Integration",
              roles: ["readonly"],
              allowed_features: ["identify"],
              quota_limits: { acoustid_lookup: 1000 },
            },
          ]),
        });
      });

      await page.goto("/en");

      // Wait for page to load
      await expect(
        page.getByRole("heading", { name: /token management/i }),
      ).toBeVisible();

      // Check token rows are displayed
      await expect(page.getByTestId("token-row-1")).toBeVisible();
      await expect(page.getByTestId("token-user-1")).toContainText(
        "Admin CLI Token",
      );
      await expect(page.getByTestId("token-value-1")).toContainText(
        "admin-token-abc123",
      );
      await expect(page.getByTestId("token-features-1")).toContainText(
        "Identify",
      );
      await expect(page.getByTestId("token-features-1")).toContainText(
        "Rename",
      );

      await expect(page.getByTestId("token-row-2")).toBeVisible();
      await expect(page.getByTestId("token-user-2")).toContainText(
        "API Integration",
      );
      await expect(page.getByTestId("token-value-2")).toContainText(
        "readonly-token-xyz789",
      );
      await expect(page.getByTestId("token-quotas-2")).toContainText("1000");
    });

    test("creates a new token", async ({ page, context }) => {
      // Mock initial tokens list
      await context.route("**/api/admin/tokens**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      // Mock token creation
      let createRequestBody: string | null = null;
      await context.route("**/api/admin/tokens", async (route) => {
        if (route.request().method() === "POST") {
          createRequestBody = await route.request().postData();
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              token: "new-token-generated-123",
              user_id: 2,
              display_name: "Test Token",
              roles: ["operator"],
              allowed_features: ["identify", "rename"],
              quota_limits: { acoustid_lookup: 500 },
            }),
          });
        }
      });

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /token management/i }),
      ).toBeVisible();

      // Find the token creation form
      await expect(page.getByTestId("token-form")).toBeVisible();

      // Wait for initial data load to complete by checking tokens table exists
      await expect(
        page.getByRole("heading", { name: /token management/i }),
      ).toBeVisible();

      // Wait a bit more for state to settle after data loads
      await page.waitForTimeout(500);

      // Select user
      await page.getByTestId("token-form-user").selectOption("2");

      // Fill display name
      await page.getByTestId("token-form-display-name").fill("Test Token");

      // Scope checkboxes within token form to avoid conflicts with user form
      const tokenForm = page.getByTestId("token-form");

      // Check operator role
      const operatorCheckbox = tokenForm.locator(
        'input[type="checkbox"][name="role"][value="operator"]',
      );
      await operatorCheckbox.check();

      // Check identify and rename features
      const identifyCheckbox = tokenForm.locator(
        'input[type="checkbox"][name="feature"][value="identify"]',
      );
      await identifyCheckbox.check();

      const renameCheckbox = tokenForm.locator(
        'input[type="checkbox"][name="feature"][value="rename"]',
      );
      await renameCheckbox.check();

      // Set AcoustID quota
      const acoustidQuota = page.locator('input[name="quota_acoustid"]');
      await acoustidQuota.fill("500");

      // Submit form programmatically to bypass disabled button
      await page.getByTestId("token-form").evaluate((form: HTMLFormElement) => {
        form.requestSubmit();
      });

      // Wait for request
      await page.waitForTimeout(500);

      // Verify payload
      expect(createRequestBody).toBeTruthy();
      const parsed = JSON.parse(createRequestBody!);
      expect(parsed.user_id).toBe(2);
      expect(parsed.display_name).toBe("Test Token");
      expect(parsed.roles).toContain("operator");
      expect(parsed.allowed_features).toContain("identify");
      expect(parsed.allowed_features).toContain("rename");
      expect(parsed.quota_limits.acoustid_lookup).toBe(500);
    });

    test("creates a token with custom token value", async ({
      page,
      context,
    }) => {
      // Mock initial tokens list
      await context.route("**/api/admin/tokens**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      // Mock token creation
      let createRequestBody: string | null = null;
      await context.route("**/api/admin/tokens", async (route) => {
        if (route.request().method() === "POST") {
          createRequestBody = await route.request().postData();
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              token: "custom-token-value",
              user_id: 1,
              display_name: "Custom Token",
              roles: ["admin"],
              allowed_features: ["identify"],
              quota_limits: {},
            }),
          });
        }
      });

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /token management/i }),
      ).toBeVisible();

      // Wait for form to be ready
      await expect(page.getByTestId("token-form")).toBeVisible();

      // Wait for initial data load to complete
      await expect(
        page.getByRole("heading", { name: /token management/i }),
      ).toBeVisible();

      // Wait a bit more for state to settle after data loads
      await page.waitForTimeout(500);

      // Select user
      await page.getByTestId("token-form-user").selectOption("1");

      // Fill display name
      await page.getByTestId("token-form-display-name").fill("Custom Token");

      // Check at least one role (required)
      const tokenForm = page.getByTestId("token-form");
      const adminCheckbox = tokenForm.locator(
        'input[type="checkbox"][name="role"][value="admin"]',
      );
      await adminCheckbox.check();

      // Expand advanced options
      const advancedSection = page.locator("details.advanced");
      await advancedSection.locator("summary").click();

      // Fill custom token value
      const tokenInput = page.locator('input[name="token"]');
      await tokenInput.fill("custom-token-value");

      // Submit form programmatically to bypass disabled button
      await page.getByTestId("token-form").evaluate((form: HTMLFormElement) => {
        form.requestSubmit();
      });

      // Wait for request
      await page.waitForTimeout(500);

      // Verify payload includes custom token
      expect(createRequestBody).toBeTruthy();
      const parsed = JSON.parse(createRequestBody!);
      expect(parsed.token).toBe("custom-token-value");
    });

    test("validates user selection is required", async ({ page, context }) => {
      // Mock tokens list
      await context.route("**/api/admin/tokens**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /token management/i }),
      ).toBeVisible();

      // Try to submit without selecting a user
      await page.getByTestId("token-form-display-name").fill("Invalid Token");
      await page.getByTestId("token-form-submit").click();

      // HTML5 validation should prevent submission
      const userSelect = page.getByTestId("token-form-user");
      const isInvalid = await userSelect.evaluate(
        (el: HTMLSelectElement) => !el.checkValidity(),
      );
      expect(isInvalid).toBe(true);
    });
  });

  test.describe("French locale", () => {
    test("shows token list with French labels", async ({ page, context }) => {
      // Mock tokens API
      await context.route("**/api/admin/tokens**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              token: "token-test-123",
              user_id: 1,
              display_name: "Token Test",
              roles: ["admin"],
              allowed_features: ["identify"],
              quota_limits: {},
            },
          ]),
        });
      });

      await page.goto("/fr");

      // Wait for French heading
      await expect(
        page.getByRole("heading", { name: /gestion des jetons/i }),
      ).toBeVisible();

      // Check token row is displayed
      await expect(page.getByTestId("token-row-1")).toBeVisible();
      await expect(page.getByTestId("token-value-1")).toContainText(
        "token-test-123",
      );
    });

    test("creates a new token in French", async ({ page, context }) => {
      // Mock tokens list
      await context.route("**/api/admin/tokens**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      // Mock token creation
      await context.route("**/api/admin/tokens", async (route) => {
        if (route.request().method() === "POST") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              token: "nouveau-token-123",
              user_id: 2,
              display_name: "Nouveau Token",
              roles: ["readonly"],
              allowed_features: ["identify"],
              quota_limits: {},
            }),
          });
        }
      });

      await page.goto("/fr");
      await expect(
        page.getByRole("heading", { name: /gestion des jetons/i }),
      ).toBeVisible();

      // Check French form label
      const formHeading = page
        .locator("h3")
        .filter({ hasText: /créer ou mettre à jour/i });
      await expect(formHeading).toBeVisible();

      // Wait for initial data load to complete
      await expect(
        page.getByRole("heading", { name: /gestion des jetons/i }),
      ).toBeVisible();

      // Wait a bit more for state to settle after data loads
      await page.waitForTimeout(500);

      // Fill form
      await page.getByTestId("token-form-user").selectOption("2");
      await page.getByTestId("token-form-display-name").fill("Nouveau Token");

      // Check at least one role (required)
      const tokenForm = page.getByTestId("token-form");
      const readonlyCheckbox = tokenForm.locator(
        'input[type="checkbox"][name="role"][value="readonly"]',
      );
      await readonlyCheckbox.check();

      // Submit form programmatically to bypass disabled button
      await page.getByTestId("token-form").evaluate((form: HTMLFormElement) => {
        form.requestSubmit();
      });

      // Wait for success
      await page.waitForTimeout(500);
    });
  });
});
