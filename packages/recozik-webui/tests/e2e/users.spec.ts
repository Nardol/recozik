import { test, expect } from "@playwright/test";

test.describe("User Management (Admin)", () => {
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
  });

  test.describe("English locale", () => {
    test("shows user list for admin", async ({ page, context }) => {
      // Mock users API
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
              allowed_features: ["identify", "rename"],
              quota_limits: {},
              created_at: "2024-01-01T00:00:00Z",
            },
            {
              id: 2,
              username: "testuser",
              email: "test@example.com",
              display_name: null,
              is_active: true,
              roles: ["readonly"],
              allowed_features: ["identify"],
              quota_limits: { acoustid_lookup: 100 },
              created_at: "2024-01-02T00:00:00Z",
            },
          ]),
        });
      });

      await page.goto("/en");

      // Wait for page to load
      await expect(
        page.getByRole("heading", { name: /user management/i }),
      ).toBeVisible();

      // Check user rows are displayed
      await expect(page.getByTestId("users-row-1")).toBeVisible();
      await expect(page.getByTestId("users-username-1")).toContainText(
        "Administrator",
      );
      await expect(page.getByTestId("users-email-1")).toContainText(
        "admin@example.com",
      );
      await expect(page.getByTestId("users-status-1")).toContainText("Active");

      await expect(page.getByTestId("users-row-2")).toBeVisible();
      await expect(page.getByTestId("users-username-2")).toContainText(
        "testuser",
      );
      await expect(page.getByTestId("users-email-2")).toContainText(
        "test@example.com",
      );
    });

    test("creates a new user", async ({ page, context }) => {
      // Mock initial user list
      await context.route("**/api/admin/users**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      // Mock user creation
      let createRequestBody: string | null = null;
      await context.route("**/api/auth/register", async (route) => {
        createRequestBody = await route.request().postData();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "ok" }),
        });
      });

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /user management/i }),
      ).toBeVisible();

      // Click create button
      await page.getByTestId("users-create-button").click();

      // Wait for modal to appear
      await expect(page.getByTestId("user-form-modal")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: /create new user/i }),
      ).toBeVisible();

      // Fill form
      await page.getByTestId("user-form-username").fill("newuser");
      await page.getByTestId("user-form-email").fill("newuser@example.com");
      await page.getByTestId("user-form-display-name").fill("New User");
      await page.getByTestId("user-form-password").fill("SecurePass123!");

      // Scope checkboxes within modal to avoid conflicts with token form
      const modal = page.getByTestId("user-form-modal");

      // Check admin role
      const adminCheckbox = modal.locator(
        'input[type="checkbox"][name="role"][value="admin"]',
      );
      await adminCheckbox.check();

      // Check identify feature
      const identifyCheckbox = modal.locator(
        'input[type="checkbox"][name="feature"][value="identify"]',
      );
      await identifyCheckbox.check();

      // Submit form
      await page.getByTestId("user-form-submit").click();

      // Wait a bit for the request
      await page.waitForTimeout(500);

      // Verify payload
      expect(createRequestBody).toBeTruthy();
      const parsed = JSON.parse(createRequestBody!);
      expect(parsed.username).toBe("newuser");
      expect(parsed.email).toBe("newuser@example.com");
      expect(parsed.display_name).toBe("New User");
      expect(parsed.password).toBe("SecurePass123!");
      expect(parsed.roles).toContain("admin");
      expect(parsed.allowed_features).toContain("identify");
    });

    test("edits an existing user", async ({ page, context }) => {
      // Mock users list
      await context.route("**/api/admin/users**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([
              {
                id: 2,
                username: "testuser",
                email: "test@example.com",
                display_name: "Test User",
                is_active: true,
                roles: ["readonly"],
                allowed_features: ["identify"],
                quota_limits: {},
                created_at: "2024-01-02T00:00:00Z",
              },
            ]),
          });
        }
      });

      // Mock update user
      let updateRequestBody: string | null = null;
      await context.route("**/api/admin/users/2", async (route) => {
        if (route.request().method() === "PUT") {
          updateRequestBody = await route.request().postData();
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              id: 2,
              username: "testuser",
              email: "updated@example.com",
              display_name: "Updated User",
              is_active: true,
              roles: ["operator"],
              allowed_features: ["identify", "rename"],
              quota_limits: {},
              created_at: "2024-01-02T00:00:00Z",
            }),
          });
        }
      });

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /user management/i }),
      ).toBeVisible();

      // Click edit button for user 2
      await page.getByTestId("users-edit-2").click();

      // Wait for modal
      await expect(page.getByTestId("user-form-modal")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: /edit user/i }),
      ).toBeVisible();

      // Update email and display name
      await page.getByTestId("user-form-email").clear();
      await page.getByTestId("user-form-email").fill("updated@example.com");
      await page.getByTestId("user-form-display-name").clear();
      await page.getByTestId("user-form-display-name").fill("Updated User");

      // Check operator role (uncheck readonly) - scope within modal
      const modal = page.getByTestId("user-form-modal");
      const readonlyCheckbox = modal.locator(
        'input[type="checkbox"][name="role"][value="readonly"]',
      );
      await readonlyCheckbox.uncheck();

      const operatorCheckbox = modal.locator(
        'input[type="checkbox"][name="role"][value="operator"]',
      );
      await operatorCheckbox.check();

      // Submit
      await page.getByTestId("user-form-submit").click();

      // Wait for request
      await page.waitForTimeout(500);

      // Verify payload
      expect(updateRequestBody).toBeTruthy();
      const parsed = JSON.parse(updateRequestBody!);
      expect(parsed.email).toBe("updated@example.com");
      expect(parsed.display_name).toBe("Updated User");
      expect(parsed.roles).toContain("operator");
    });

    test("deletes a user with confirmation", async ({ page, context }) => {
      // Mock users list
      await context.route("**/api/admin/users**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([
              {
                id: 3,
                username: "deleteuser",
                email: "delete@example.com",
                display_name: null,
                is_active: true,
                roles: ["readonly"],
                allowed_features: [],
                quota_limits: {},
                created_at: "2024-01-03T00:00:00Z",
              },
            ]),
          });
        }
      });

      // Mock delete user
      let deleteRequested = false;
      await context.route("**/api/admin/users/3", async (route) => {
        if (route.request().method() === "DELETE") {
          deleteRequested = true;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ status: "ok" }),
          });
        }
      });

      // Setup dialog handler for confirmation
      page.on("dialog", (dialog) => {
        expect(dialog.type()).toBe("confirm");
        expect(dialog.message()).toContain("deleteuser");
        dialog.accept();
      });

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /user management/i }),
      ).toBeVisible();

      // Click delete button
      await page.getByTestId("users-delete-3").click();

      // Wait for request
      await page.waitForTimeout(500);

      expect(deleteRequested).toBe(true);
    });

    test("resets user password", async ({ page, context }) => {
      // Mock users list
      await context.route("**/api/admin/users**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 4,
              username: "resetuser",
              email: "reset@example.com",
              display_name: null,
              is_active: true,
              roles: ["readonly"],
              allowed_features: [],
              quota_limits: {},
              created_at: "2024-01-04T00:00:00Z",
            },
          ]),
        });
      });

      // Mock password reset
      let resetRequestBody: string | null = null;
      await context.route(
        "**/api/admin/users/4/reset-password",
        async (route) => {
          resetRequestBody = await route.request().postData();
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ status: "ok" }),
          });
        },
      );

      await page.goto("/en");
      await expect(
        page.getByRole("heading", { name: /user management/i }),
      ).toBeVisible();

      // Click reset password button
      await page.getByTestId("users-reset-password-4").click();

      // Wait for modal heading
      await expect(
        page.getByRole("heading", { name: /reset password/i }),
      ).toBeVisible();

      // Fill new password
      const passwordInput = page.locator(
        'input[type="password"][name="new_password"]',
      );
      await passwordInput.fill("NewSecurePass123!");

      // Submit
      const submitButton = page
        .locator('button[type="submit"]')
        .filter({ hasText: /reset/i });
      await submitButton.click();

      // Wait for request
      await page.waitForTimeout(500);

      // Verify payload
      expect(resetRequestBody).toBeTruthy();
      const parsed = JSON.parse(resetRequestBody!);
      expect(parsed.new_password).toBe("NewSecurePass123!");
    });
  });

  test.describe("French locale", () => {
    test("shows user list with French labels", async ({ page, context }) => {
      // Mock users API
      await context.route("**/api/admin/users**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 1,
              username: "admin",
              email: "admin@example.com",
              display_name: "Administrateur",
              is_active: true,
              roles: ["admin"],
              allowed_features: ["identify"],
              quota_limits: {},
              created_at: "2024-01-01T00:00:00Z",
            },
          ]),
        });
      });

      await page.goto("/fr");

      // Wait for French heading
      await expect(
        page.getByRole("heading", { name: /gestion des utilisateurs/i }),
      ).toBeVisible();

      // Check user row is displayed
      await expect(page.getByTestId("users-row-1")).toBeVisible();
      await expect(page.getByTestId("users-username-1")).toContainText(
        "Administrateur",
      );
    });

    test("creates a new user in French", async ({ page, context }) => {
      // Mock initial user list
      await context.route("**/api/admin/users**", async (route) => {
        if (route.request().method() === "GET") {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        }
      });

      // Mock user creation
      await context.route("**/api/auth/register", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "ok" }),
        });
      });

      await page.goto("/fr");
      await expect(
        page.getByRole("heading", { name: /gestion des utilisateurs/i }),
      ).toBeVisible();

      // Click create button - check for French text
      const createButton = page.getByTestId("users-create-button");
      await expect(createButton).toBeVisible();
      await expect(createButton).toContainText(/créer/i);
      await createButton.click();

      // Wait for modal with French title
      await expect(page.getByTestId("user-form-modal")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: /créer un nouvel utilisateur/i }),
      ).toBeVisible();

      // Fill form
      await page.getByTestId("user-form-username").fill("nouvelutilisateur");
      await page.getByTestId("user-form-email").fill("nouveau@example.com");
      await page.getByTestId("user-form-password").fill("MotDePasse123!");

      // Submit
      await page.getByTestId("user-form-submit").click();

      // Modal should close (or show success)
      await page.waitForTimeout(500);
    });
  });
});
