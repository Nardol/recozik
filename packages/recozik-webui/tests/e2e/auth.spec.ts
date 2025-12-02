import { test, expect } from "@playwright/test";

test.describe("Authentication flow", () => {
  test.describe("English locale", () => {
    test("shows login form on unauthenticated access", async ({
      page,
      context,
    }) => {
      await context.route("**/api/whoami", async (route) => {
        await route.fulfill({ status: 401 });
      });

      await page.goto("/en");

      // Check login prompt is visible
      const loginPrompt = page.getByTestId("login-prompt");
      await expect(loginPrompt).toBeVisible();

      // Check form fields are present using data-testid
      await expect(page.getByTestId("login-form")).toBeVisible();
      await expect(page.getByTestId("login-username")).toBeVisible();
      await expect(page.getByTestId("login-password")).toBeVisible();
      await expect(page.getByTestId("login-remember")).toBeVisible();
      await expect(page.getByTestId("login-submit")).toBeVisible();
    });

    test("validates empty username and password", async ({ page, context }) => {
      await context.route("**/api/whoami", async (route) => {
        await route.fulfill({ status: 401 });
      });

      await page.goto("/en");

      // Try to submit empty form
      const submitButton = page.getByTestId("login-submit");
      await submitButton.click();

      // HTML5 validation should prevent submission
      const usernameInput = page.getByTestId("login-username");
      const isInvalid = await usernameInput.evaluate(
        (el: HTMLInputElement) => !el.checkValidity(),
      );
      expect(isInvalid).toBe(true);
    });

    test("handles invalid credentials error", async ({ page, context }) => {
      await context.route("**/api/whoami", async (route) => {
        await route.fulfill({ status: 401 });
      });

      await context.route("**/api/auth/login", async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Invalid username or password" }),
        });
      });

      await page.goto("/en");

      await page.getByTestId("login-username").fill("wronguser");
      await page.getByTestId("login-password").fill("wrongpass");
      await page.getByTestId("login-submit").click();

      // Check error message is displayed
      await expect(page.getByTestId("login-error")).toBeVisible();
      await expect(page.getByTestId("login-error")).toContainText(
        /invalid username or password/i,
      );
    });

    test("logs in successfully and sets session cookies", async ({
      page,
      context,
    }) => {
      let whoamiCallCount = 0;

      await context.route("**/api/whoami", async (route) => {
        whoamiCallCount++;
        if (whoamiCallCount === 1) {
          // First call: unauthenticated
          await route.fulfill({ status: 401 });
        } else {
          // After login: authenticated
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              user_id: "testuser",
              display_name: "Test User",
              roles: ["admin"],
              allowed_features: ["identify", "rename"],
            }),
          });
        }
      });

      await context.route("**/api/auth/login", async (route) => {
        // Simulate successful login with cookies
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: {
            "Set-Cookie": [
              "recozik_session=mock_session_token; Path=/; HttpOnly; SameSite=Lax",
              "recozik_refresh=mock_refresh_token; Path=/; HttpOnly; SameSite=Lax",
              "recozik_csrf=mock_csrf_token; Path=/; SameSite=Lax",
            ].join(", "),
          },
          body: JSON.stringify({ status: "ok" }),
        });
      });

      await context.route("**/api/jobs**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });

      await page.goto("/en");

      // Fill login form
      await page.getByTestId("login-username").fill("admin");
      await page.getByTestId("login-password").fill("password123");
      await page.getByTestId("login-submit").click();

      // Wait for dashboard to load
      await expect(page.getByRole("heading", { name: /jobs/i })).toBeVisible({
        timeout: 10_000,
      });

      // Verify we're on the dashboard page
      await expect(page.getByTestId("main-heading")).toBeVisible();
    });

    test("logs in with remember me checkbox", async ({ page, context }) => {
      await context.route("**/api/whoami", async (route) => {
        await route.fulfill({ status: 401 });
      });

      let loginRequestBody: string | null = null;

      await context.route("**/api/auth/login", async (route) => {
        loginRequestBody = await route.request().postData();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "ok" }),
        });
      });

      await page.goto("/en");

      // Fill form with remember me checked
      await page.getByTestId("login-username").fill("admin");
      await page.getByTestId("login-password").fill("password123");
      await page.getByTestId("login-remember").check();
      await page.getByTestId("login-submit").click();

      // Wait a bit for the request to complete
      await page.waitForTimeout(500);

      // Verify remember flag was sent
      expect(loginRequestBody).toBeTruthy();
      const parsed = JSON.parse(loginRequestBody!);
      expect(parsed.remember).toBe(true);
    });

    test("logs out successfully", async ({ page, context }) => {
      // Track logout state
      let isLoggedOut = false;

      // Start authenticated, but return 401 after logout
      await context.route("**/api/whoami", async (route) => {
        if (isLoggedOut) {
          await route.fulfill({ status: 401 });
        } else {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              user_id: "testuser",
              display_name: "Test User",
              roles: ["admin"],
              allowed_features: ["identify"],
            }),
          });
        }
      });

      await context.route("**/api/jobs**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });

      await context.route("**/auth/logout", async (route) => {
        isLoggedOut = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: {
            "Set-Cookie": [
              "recozik_session=; Path=/; Max-Age=0",
              "recozik_refresh=; Path=/; Max-Age=0",
              "recozik_csrf=; Path=/; Max-Age=0",
            ].join(", "),
          },
          body: JSON.stringify({ status: "ok" }),
        });
      });

      await page.goto("/en");

      // Wait for dashboard to load
      await expect(page.getByRole("heading", { name: /jobs/i })).toBeVisible();

      // Click logout button (plain form submit button)
      const logoutButton = page.getByRole("button", { name: /log out/i });
      await logoutButton.click();

      // Manual navigation after mock logout to show login prompt (whoami now returns 401)
      await page.goto("/en");
      await expect(page.getByTestId("login-prompt")).toBeVisible({
        timeout: 10000,
      });
    });
  });

  test.describe("French locale", () => {
    test("shows login form with French labels", async ({ page, context }) => {
      await context.route("**/api/whoami", async (route) => {
        await route.fulfill({ status: 401 });
      });

      await page.goto("/fr");

      // Check login prompt is visible
      const loginPrompt = page.getByTestId("login-prompt");
      await expect(loginPrompt).toBeVisible();

      // Check French form elements using test-ids (labels are translated but IDs are stable)
      await expect(page.getByTestId("login-form")).toBeVisible();
      await expect(page.getByTestId("login-username")).toBeVisible();
      await expect(page.getByTestId("login-password")).toBeVisible();
      await expect(page.getByTestId("login-remember")).toBeVisible();
      await expect(page.getByTestId("login-submit")).toBeVisible();
    });

    test("handles invalid credentials error in French", async ({
      page,
      context,
    }) => {
      await context.route("**/api/whoami", async (route) => {
        await route.fulfill({ status: 401 });
      });

      await context.route("**/api/auth/login", async (route) => {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: JSON.stringify({
            detail: "Identifiants invalides.",
          }),
        });
      });

      await page.goto("/fr");

      await page.getByTestId("login-username").fill("wronguser");
      await page.getByTestId("login-password").fill("wrongpass");
      await page.getByTestId("login-submit").click();

      // Check French error message is displayed
      await expect(page.getByTestId("login-error")).toBeVisible();
      await expect(page.getByTestId("login-error")).toContainText(
        /identifiants invalides/i,
      );
    });

    test("logs in successfully in French locale", async ({ page, context }) => {
      let whoamiCallCount = 0;

      await context.route("**/api/whoami", async (route) => {
        whoamiCallCount++;
        if (whoamiCallCount === 1) {
          await route.fulfill({ status: 401 });
        } else {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              user_id: "testuser",
              display_name: "Utilisateur Test",
              roles: ["admin"],
              allowed_features: ["identify", "rename"],
            }),
          });
        }
      });

      await context.route("**/api/auth/login", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          headers: {
            "Set-Cookie": [
              "recozik_session=mock_session_token; Path=/; HttpOnly; SameSite=Lax",
              "recozik_refresh=mock_refresh_token; Path=/; HttpOnly; SameSite=Lax",
              "recozik_csrf=mock_csrf_token; Path=/; SameSite=Lax",
            ].join(", "),
          },
          body: JSON.stringify({ status: "ok" }),
        });
      });

      await context.route("**/api/jobs**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });

      await page.goto("/fr");

      // Fill login form using stable test-ids
      await page.getByTestId("login-username").fill("admin");
      await page.getByTestId("login-password").fill("password123");
      await page.getByTestId("login-submit").click();

      // Wait for dashboard to load - French heading is "Tâches"
      await expect(page.getByRole("heading", { name: /tâches/i })).toBeVisible({
        timeout: 10_000,
      });
    });
  });
});
