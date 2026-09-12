# NCDAI 2.0 clinical workspace

Standalone, clinician-supervised research interface for synthetic adult NCD cases. This build does not claim clinical approval, live EMR connectivity, autonomous prescribing, or offline clinical saves.

## Run locally

Start the backend on `127.0.0.1:8010` using the platform setup guide, then run from this directory:

```sh
npm ci
npm run dev
```

The Vite development server proxies `/api` to the local backend. Use the local address printed by Vite. Sign in with an explicitly provisioned synthetic facility account. No account or password is built into the frontend.

```sh
npm run build
npm test
npm audit
```

`dist/` contains the static production build. Deploy it on the same origin as the API, with appropriate TLS and response headers; the local development server is not a production server. All requests include session cookies, mutations include the session's anti-CSRF token, and no authentication tokens or clinical drafts are persisted in local storage.

## Clinical workflow

1. Find or register a synthetic adult patient and confirm their record ID.
2. Review the longitudinal encounter history.
3. Start an encounter. Enter current observations with units, explicitly record unknowns, and confirm symptom, medication, and allergy reconciliation.
4. Optionally bring forward prior chronic history and previously reviewed medication/allergy lists. This action clears reconciliation flags and does not copy current symptoms, pregnancy status, measurements, laboratory results, or timestamps.
5. Save and assess. Inspect urgency, missing information, rule evidence, and limitations. Emergency findings must not wait for documentation.
6. Optionally request an AI-assisted review focus, if a backend provider is configured. The full rule-based assessment remains visible when the provider fails or is disabled. AI does not generate prescriptions in this interface.
7. Explicitly accept, modify, defer, or reject each recommendation. Every non-acceptance requires a reason; modification also requires replacement action text. Completing review locks the encounter.
8. Record referrals and follow their status through accepted, completed, or cancelled. Recording a request does not notify a receiving facility.

FHIR downloads are authorized file exports, not live exchange with another medical record system. Audit activity is visible to supervisor/admin roles within their facility.

## Verification

The 21 frontend tests cover blank/unknown semantics, reconciliation, safe historical context reuse, complete review decisions, cookie/CSRF behavior, stale-record conflicts, connectivity errors, expired sessions, explicit login, symptoms entry, emergency visibility, modified action submission, and preservation of safety guidance when optional AI fails. The shared platform tests cover complete synthetic API case workflows. Browser and independent clinical validation are separate activities.

Vitest uses one worker thread to avoid filesystem contention and worker startup timeouts in the synchronized Windows workspace. The interface uses local system font fallbacks and does not request fonts from a third party.
