# Firefox E2E Test Resolution (2025-12-02)

## Issue Summary

Firefox E2E tests were experiencing `browserContext.newPage: Target page, context or browser has
been closed` errors on some environments, causing 100% test failures. Firefox had been disabled in
the Playwright configuration to maintain CI stability.

## Root Cause Analysis

The issue is environment-specific and related to Firefox sandboxing on Linux systems. Debug output
from the affected environment showed:

- `sandbox uid_map EACCES` errors
- `dconf EACCES` errors
- `glxtest/libEGL` warnings
- `NS_ERROR_FAILURE` in Firefox Helper.js

These errors caused Firefox to crash immediately after launch, before Playwright could establish
proper control, resulting in `browserContext.newPage: Target page, context or browser has been closed`.

## Solution Implemented

Re-enabled Firefox with content sandboxing disabled via Firefox preferences:

1. **Firefox sandbox preference** - `security.sandbox.content.level: 0`
   - Disables Firefox content sandboxing to avoid sandbox uid_map EACCES errors
   - This is the proper Firefox way to disable sandboxing (not Chromium flags)

2. **Firefox user preferences** for automation:
   - Disabled media navigator streams
   - Disabled permission prompts for microphone/camera
   - Set fake media streams for automation

3. **Sequential execution** - `fullyParallel: false` to avoid race conditions

4. **Complete configuration**:

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
        "security.sandbox.content.level": 0,
      },
    },
  },
  fullyParallel: false,
}
```

## Testing Results

After implementing the sandboxing fix:

### Local Testing (Environment A - Development Machine)

With `security.sandbox.content.level: 0` preference:

- ✅ 9/9 auth tests passed with 1 worker
- ✅ 28/28 total tests passed (1 skipped visual test)
- ✅ No browserContext.newPage errors
- ✅ Firefox launches and runs stably

### Environment B (Previously Affected System) - VERIFIED FIX

**CONFIRMED**: The sandbox preference resolved the issue:

- ✅ 9/9 auth tests now pass (previously 100% failure)
- ✅ No more `sandbox uid_map EACCES` errors
- ✅ Firefox launches and completes all tests successfully
- ✅ No more browserContext.newPage crashes

If issues reoccur, additional investigation may be needed:

- Examine display/X11 configuration (glxtest/libEGL errors)
- Check dconf/gsettings permissions
- Consider running in Xvfb or headful mode
- Investigate Firefox version compatibility

## Verification Steps

To verify the sandboxing fix on the affected system:

```bash
cd packages/recozik-webui

# Rebuild (ensure latest code)
npm run build

# Test with 1 worker first (original failure scenario)
npx playwright test --project=firefox --workers=1 tests/e2e/auth.spec.ts --reporter=line

# If successful, test full suite
npx playwright test --project=firefox --reporter=line
```

**Expected result**: All Firefox tests pass without
`browserContext.newPage: Target page, context or browser has been closed` errors.

**If tests still fail**:

1. Capture debug output:
   `DEBUG=pw:browser npx playwright test --project=firefox --workers=1 tests/e2e/auth.spec.ts --max-failures=1`
2. Check if sandbox errors are gone from debug output
3. Verify `security.sandbox.content.level: 0` is set in firefoxUserPrefs
4. If new errors appear, update investigation direction

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
