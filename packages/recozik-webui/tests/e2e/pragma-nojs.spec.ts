import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

test("no-JS flow: SSR jobs + admin tokens still visible", async ({
  browser,
  baseURL,
  request,
}) => {
  let mock: ReturnType<typeof spawn> | null = null;
  let reuseExisting = false;
  const mockPort = process.env.MOCK_API_PORT || "10099";
  const mockBase = `http://localhost:${mockPort}`;

  try {
    const health = await request.get(`${mockBase}/health`);
    reuseExisting = health.ok();
  } catch {
    reuseExisting = false;
  }

  if (!reuseExisting) {
    mock = spawn("node", ["tests/e2e/mock-api-server.js"], {
      cwd: __dirname + "/..",
      env: { ...process.env, MOCK_API_PORT: mockPort },
      stdio: "ignore",
    });

    // Wait for server health
    let ready = false;
    for (let i = 0; i < 10; i++) {
      await delay(200);
      try {
        const res = await request.get(`${mockBase}/health`);
        if (res.ok()) {
          ready = true;
          break;
        }
      } catch {
        // keep trying
      }
    }
    if (!ready) {
      if (mock && !mock.killed) mock.kill("SIGTERM");
      throw new Error(`Mock API did not become ready on port ${mockPort}`);
    }
  }

  const context = await browser.newContext({
    javaScriptEnabled: false,
    baseURL,
  });
  await context.addCookies([
    {
      name: "recozik_session",
      value: "mock-session",
      domain: "localhost",
      path: "/",
    },
    {
      name: "recozik_csrf",
      value: "mock_csrf",
      domain: "localhost",
      path: "/",
    },
  ]);

  const page = await context.newPage();
  await page.goto("/en");

  await expect(page.getByRole("heading", { name: /jobs/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /refresh/i })).toBeVisible();

  // Admin no-JS panel should be visible (SSR)
  await expect(
    page.getByRole("heading", { name: /token management/i }),
  ).toBeVisible();
  await expect(page.getByText(/demo-token/i)).toBeVisible();

  // Submit token form (HTML) and observe table growth
  const table = page.getByTestId("admin-token-table");
  const before = await table.locator("tbody tr").count();
  await page.selectOption("select[name='user_id']", "2");
  await page.fill("input[name='display_name']", "NoJS token");
  await page.click("input[name='feature'][value='identify']");
  const tokenForm = page.getByTestId("token-form");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded" }),
    tokenForm.getByRole("button", { type: "submit" }).click(),
  ]);
  await delay(300);
  const after = await table.locator("tbody tr").count();
  expect(after).toBeGreaterThan(before);

  // Submit user form (HTML) and observe user table growth
  const userTable = page.getByTestId("admin-user-table");
  const slug = Date.now();
  await page.fill("input[name='username']", `nouser${slug}`);
  const email = `nouser${slug}@example.com`;
  await page.fill("input[name='email']", email);
  await page.fill("input[name='password']", "StrongPassw0rd!");
  const userForm = page.getByTestId("user-form");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "domcontentloaded" }),
    userForm.getByRole("button", { type: "submit" }).click(),
  ]);
  await delay(300);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(userTable.locator("tbody")).toContainText(email);

  await context.close();
  if (mock && !mock.killed) {
    mock.kill("SIGTERM");
  }
});
