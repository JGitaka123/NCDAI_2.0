# Browser verification

Start the local backend and Vite frontend using the repository setup guide. Tests target `http://127.0.0.1:5173` by default; set `NCDAI_BROWSER_URL` for an alternative test deployment. The service must contain a synthetic clinician or supervisor account.

Supply `NCDAI_BROWSER_EMAIL` and `NCDAI_BROWSER_PASSWORD` in the process environment. For local development the runner also supports the ignored `.runtime/demo-access.json` fixture at repository root. Never commit this fixture or place credentials in a test source file.

From `frontend`, run:

```text
npm ci
npx playwright install chromium
npm run test:browser
```

The suite performs one complete synthetic emergency scenario at desktop 1366×900, tablet 768×1024 and mobile 375×812 viewports. It registers a patient, records current findings, inspects evidence, rejects incomplete review, reviews every recommendation, verifies locking, records and completes a referral, checks recognizable patient identifiers, and downloads/inspects a FHIR Bundle. Additional tests exercise keyboard-only interaction and administrator navigation. The administrator test simulates API responses to isolate UI authorization behavior; backend access-control tests are separate.

Axe checks the login, overview, registration, intake, assessment, referral and mobile navigation views against WCAG A/AA rules supported by axe. Serious or critical violations fail the suite. Layout assertions fail on horizontal **page** overflow; patient tables may scroll within their bounded container. These automated checks are not a WCAG certification or a substitute for screen-reader testing with clinicians.

JSON accessibility/layout evidence is written under `.runtime/browser`; Playwright HTML output is under `frontend/playwright-report`. Both are ignored by Git. Screenshots in `docs/images` contain fictional test records only. Traces and video are disabled because recordings can retain authentication input.

The runner creates new records on each run and preserves the audit history. Use a dedicated synthetic database; do not run it against live patient care. Login rate limits apply normally. No browser test calls an external AI provider, sends an EMR message, or signs a prescription.
