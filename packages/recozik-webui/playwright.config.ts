import { defineConfig, devices } from "@playwright/test";

const PORT = process.env.PORT || 4000;
const baseURL = process.env.BASE_URL || `http://localhost:${PORT}`;
const MOCK_API_PORT = process.env.MOCK_API_PORT || "10099";
const apiBase =
  process.env.NEXT_PUBLIC_RECOZIK_API_BASE ||
  `http://localhost:${MOCK_API_PORT}/api`;
const internalApiBase = process.env.RECOZIK_INTERNAL_API_BASE || apiBase;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  use: {
    baseURL,
    trace: "on-first-retry",
    video: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: {
        ...devices["Desktop Firefox"],
        // Firefox-specific workarounds for context lifecycle issues
        launchOptions: {
          firefoxUserPrefs: {
            // Disable various Firefox features that can interfere with automation
            "media.navigator.streams.fake": true,
            "media.navigator.permission.disabled": true,
            "permissions.default.microphone": 1,
            "permissions.default.camera": 1,
            // Disable sandboxing-related features that can cause crashes
            "security.sandbox.content.level": 0,
          },
        },
      },
      // Force sequential execution for Firefox to avoid context lifecycle issues
      fullyParallel: false,
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
  webServer: {
    command: `npm run start -- --hostname 0.0.0.0 --port ${PORT}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      PORT: String(PORT),
      BASE_URL: baseURL,
      MOCK_API_PORT: MOCK_API_PORT,
      NEXT_PUBLIC_RECOZIK_API_BASE: apiBase,
      RECOZIK_WEB_API_BASE: apiBase,
      RECOZIK_INTERNAL_API_BASE: internalApiBase,
    },
  },
});
