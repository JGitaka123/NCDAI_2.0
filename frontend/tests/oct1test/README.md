# Oct1Test surface runners

Three Playwright runners that drive the **deployed** frontend bundle, used for the
[Oct1Test report](../../../docs/Oct1Test-report.md). They complement `scripts/run_case_workflows.py`,
which covers the persisted API workflow; all three read the case list from that runner's report so
every surface is measured on the same cases.

Mirror the deployed bundle (or point at any build) and serve it with the API proxied to a local
backend, then run a surface:

```bash
# PLAYWRIGHT_CHROMIUM_PATH pins a prebuilt Chromium if Playwright's own is unavailable.
node frontend/tests/oct1test/serve-bundle.mjs <bundle-dir> 8902 8010   # frontend + /api proxy
node frontend/tests/oct1test/pwa-e2e.mjs        http://127.0.0.1:8902 docs/test-results/Oct1Test-pwa.json
node frontend/tests/oct1test/mobile-e2e.mjs     http://127.0.0.1:8902 docs/test-results/Oct1Test-mobile.json
node frontend/tests/oct1test/pwa-capability.mjs http://127.0.0.1:8902 docs/test-results/Oct1Test-pwa-capability.json
```

`pwa-e2e.mjs` signs in with the ignored `.runtime/demo-access.json` fixture, so point that at an
isolated synthetic database and never at a clinical-testing facility. `mobile-e2e.mjs` and
`pwa-capability.mjs` need no account. All three create records only through the API they are given.

Response headers set in `vercel.json` (for example `cache-control` on `/sw.js`) are not reproduced by
the local host; `pwa-capability.mjs` checks those against the live deployment and labels them.
