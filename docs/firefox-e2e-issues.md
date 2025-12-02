# Firefox E2E test issues (status 2025-12-02)

## Commands executed

- Local: `npm run test:e2e -- --project=firefox` (after `npm run build`).
- CI (before Firefox was removed): Playwright config included a `firefox`
  project and ran `playwright test --project=firefox`.

## Error observed

- **Message:**
  `browserContext.newPage: Target page, context or browser has been closed`
  (raised before the first navigation in each spec).
- Seen across most/all Firefox specs; the run ends with every Firefox test
  failing. Retries hit the same error or time out.

## Frequency / conditions

- Reproducible **100%** of the time on branch `feature/pragma-ssr` (2025-12-02).
- Occurs while Chromium/WebKit runs are green with the same mock API setup
  (global setup starts `tests/e2e/mock-api-server.js` on port 10099).
- CI currently excludes Firefox for stability; local runs continue to fail consistently.

## Context & notes

- Playwright version: **1.57.0**.
- Mock API: port **10099** via global setup; no issues reported for Chromium/WebKit against this mock.
- No crash traces captured; the browser appears to close immediately after context creation.

## Next steps (suggested)

1. Re-enable Firefox locally with verbose logging:
   `DEBUG=pw:browser,pw:api npx playwright test --project=firefox --headed`.
2. Force a fresh Firefox download:
   `npx playwright install firefox --with-deps && rm -rf ~/.cache/ms-playwright/firefox-*`.
3. Try pinning Playwright to 1.56.x to rule out a regression.
4. If still failing, enable `trace:on` + `video:on` on a single spec to inspect the crash.
