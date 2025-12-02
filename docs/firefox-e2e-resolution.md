# Firefox E2E Test Resolution (2025-12-02)

## Issue Summary

Firefox E2E tests were experiencing `browserContext.newPage: Target page, context or browser has
been closed` errors on some environments, causing 100% test failures. Firefox had been disabled in
the Playwright configuration to maintain CI stability.

## Root Cause Analysis

The issue appears to be environment-specific and related to Firefox's context lifecycle management
in Playwright. While the error could not be reproduced in all environments, the reported symptoms
suggested Firefox-specific automation interference.

## Solution Implemented

Re-enabled Firefox with defensive configuration:

1. **Firefox-specific launch options** added to `playwright.config.ts`:
   - Disabled media navigator streams
   - Disabled permission prompts for microphone/camera
   - Set fake media streams for automation

2. **Configuration changes**:

```typescript
{
  name: "firefox",
  use: {
    ...devices["Desktop Firefox"],
    launchOptions: {
      firefoxUserPrefs: {
        "media.navigator.streams.fake": true,
        "media.navigator.permission.disabled": true,
        "permissions.default.microphone": 1,
        "permissions.default.camera": 1,
      },
    },
  },
}
```

## Testing Results

After implementing the fix:

### Local Testing (Environment A - Cannot Reproduce Original Issue)

- ✅ 28/28 tests passed with 1 worker
- ✅ 56/56 tests passed with 6 workers (2 repetitions)
- ✅ No context lifecycle errors observed
- ✅ Stable across multiple runs

### Expected Testing (Environment B - Original Issue Reporter)

- Testing needed to confirm resolution in the environment where issue was 100% reproducible
- If issue persists, additional workarounds available:
  - Force `workers: 1` for Firefox project only
  - Add explicit delays before context creation
  - Investigate Firefox version-specific issues

## Verification Steps

To verify the fix:

```bash
cd packages/recozik-webui
npm run build
npx playwright test --project=firefox --workers=6
```

Expected: All tests pass without `browserContext.newPage` errors.

## Rollback Plan

If Firefox remains unstable:

1. Remove Firefox from `projects` array in `playwright.config.ts`
2. Add comment documenting the issue
3. File detailed Playwright/Firefox bug report with reproduction steps

## Next Steps

1. Merge this change
2. Monitor CI for Firefox stability
3. Collect feedback from environment where original issue occurred
4. If issues persist, implement additional mitigations:
   - Reduce Firefox worker count
   - Add per-test retries for Firefox
   - Investigate Firefox version pinning

## References

- Original report: `docs/firefox-e2e-claude-report.md`
- Playwright Firefox docs: <https://playwright.dev/docs/browsers#firefox>
- Issue tracking: PR #179
