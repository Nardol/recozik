// Generate a Playwright storage state with session/profile/locale cookies for localhost
// Usage: node tests/e2e/bootstrap-auth.js

/* eslint-disable @typescript-eslint/no-require-imports */
const { chromium } = require("playwright");
const path = require("path");

(async () => {
  const profile = {
    user_id: "demo",
    display_name: "Demo",
    roles: ["admin"],
    allowed_features: ["identify", "rename"],
  };

  const encodedProfile = encodeURIComponent(JSON.stringify(profile));
  const expires = Math.floor(Date.now() / 1000) + 3600; // +1h

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();

  await context.addCookies([
    // NOTE: Relaxed settings for local E2E (no HttpOnly/Secure, SameSite=Lax) so
    // Playwright can inspect cookies on http://localhost. Production uses
    // HttpOnly, Secure, and SameSite=Strict.
    {
      name: "recozik_session",
      value: "session",
      domain: "localhost",
      path: "/",
      httpOnly: false,
      secure: false,
      sameSite: "Lax",
      expires,
    },
    {
      name: "recozik_profile",
      value: encodedProfile,
      domain: "localhost",
      path: "/",
      httpOnly: false,
      secure: false,
      sameSite: "Lax",
      expires,
    },
    {
      name: "recozik_locale",
      value: "en",
      domain: "localhost",
      path: "/",
      httpOnly: false,
      secure: false,
      sameSite: "Lax",
      expires,
    },
  ]);

  const outPath = path.join(__dirname, "storage", "auth.json");
  await context.storageState({ path: outPath });
  await browser.close();
  console.log(`storage state written to ${outPath}`);
})();
