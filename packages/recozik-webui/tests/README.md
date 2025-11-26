# E2E helpers

- `tests/e2e/bootstrap-auth.js`: tiny helper to generate a Playwright storage state with mocked session/profile/locale
  cookies for `localhost`. Run `npm run test:e2e:make-storage` from `packages/recozik-webui` to regenerate
  `tests/e2e/storage/auth.json` (not committed by default). Useful when you need a pre-baked logged-in context for
  ad-hoc debugging.
