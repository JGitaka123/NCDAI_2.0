# Oct1Test: deployed-release verification across both delivery surfaces

1 October 2026 · deployed commit `e3c077c` · deployment `dpl_91RnnyUg7Gyh4ZL3AzY2vgSYWkP3`

**Status: all four suites passed.** 50 end-to-end cases through the installable clinical workspace, the same
50 through the offline mobile app, the same 50 through the persisted API workflow, plus 19 PWA capability
checks, 15 accessibility audits and the engine parity suite. This is synthetic engineering verification of
the deployed release. It is not clinical validation, and it says nothing about clinical accuracy,
effectiveness or adoption.

## What was tested, and against what

| | |
|---|---|
| Hosted application | https://ncdai-2.vercel.app |
| Deployed commit | `e3c077cc51d54221609a50ccd18b46d3f27c21e2` |
| Deployment | `dpl_91RnnyUg7Gyh4ZL3AzY2vgSYWkP3` |
| Clinical rules | `ncdai-2-rules-0.2.0` |
| Consultant reasoning | `ncdai-consultant-1.0.0` |
| Evidence set | `ncdai-2026-09-29.1` |
| Dose reference | `ncdai-dose-reference-0.1.1` |

The frontend under test is the **deployed production bundle**: every file was fetched from
`ncdai-2.vercel.app` and hashed identical to a local build of the deployed commit, so the code exercised
below is the code clinicians receive. The API and database are local, because the hosted clinical workflow
needs provisioned accounts that are delivered privately and were not available. **Nothing in this run wrote
to the hosted Mary Help database.**

- Database: PostgreSQL 16.14, local, loopback only, synthetic facilities only
- Browser: Chromium 141.0.7390.37 via Playwright 1.63.0
- Live AI requests: 0 · Real patient data: no · Hosted writes: 0

## The Oct1Test case set

50 of the frozen 66-case catalogue (`tests/cases/clinical_cases.json`, version 1.0), chosen by the runner's
deterministic round-robin across domains so the set stays clinically spread rather than front-loaded on one domain.

- Domains: cancer referral 6 · cardiovascular 9 · diabetes 9 · kidney 9 · multimorbidity 9 · respiratory 8
- Triage outcomes exercised: emergency 17 · soon 13 · urgent 20

The same 50 cases drive all three workflow suites, which is what makes the cross-surface comparison meaningful.

## 1. Installable clinical workspace (PWA), 50 end-to-end cases

**50/50 passed.** Each case was driven through the real UI:
register a patient, start an encounter, enter vital signs, symptoms, NCD history, laboratory results,
medicines, allergies and notes, run **Assess & review**, open every recommendation, confirm each one carries
evidence links, accept it, and lock the encounter.

- Triage agreement with the backend assessment: **50/50**
- Recommendations individually reviewed and locked: 80
- Evidence links present on those recommendations: 125
- After locking, the accept controls were disabled on every case, so the immutability guard held through the UI.

Two cases failed on first attempt and were re-run. The cause was a duplicate record ID left by the harness's
own smoke test; the application correctly refused to create a second patient with the same record ID in the
same facility, which is the unique `(facility, record ID)` constraint doing its job. That is a harness
artifact, not a product defect, and it is recorded as such in the evidence file.

## 2. Offline mobile app, the same 50 cases

**50/50 passed**, driven through the deployed
`/mobile/` UI at phone width: clear the form with **New patient**, enter the case, generate the consult,
and read what the app actually rendered.

- Triage agreement with the backend: **50/50**
- **Full rule-set agreement with the backend: 50/50** — not just
  the urgency band but the exact set of rule IDs, captured from the engine call the UI itself makes
- Console errors across all 50: 0

Getting to exact agreement surfaced two things worth recording:

- **The mobile form cannot express every catalogue field.** It has no input for `medicine_availability` or
  free-text `notes`, and it is fixed to mmol/L, so the two mg/dL glucose cases were converted on entry. None
  of these changed a triage outcome, but they are real differences in what the two surfaces can capture.
- **Feeding the backend engine exactly what the mobile UI collected produced identical results on 50/50** —
  same rule sets, same urgency, zero divergence. Where the two surfaces differ, it is because they were given
  different inputs, never because the engines disagree. The parity suite backs this up independently across
  the catalogue, targeted scenarios and 1500 seeded fuzz cases (4/4 tests pass).

## 3. Persisted API workflow, the same 50 cases

**50/50 passed** on PostgreSQL
(run `ea6ad23910`), seven steps per case:

1. register patient
1. persist encounter
1. assess expected safety findings and evidence
1. review every action; retrieve immutable decisions
1. request, accept and complete referral
1. export reviewed FHIR document
1. verify audit integrity

## 4. PWA capability checks

**19/19 passed**, covering what makes this an
installable app rather than a web page:

- Both manifests serve as `application/manifest+json`, declare every installability field, run standalone,
  scope correctly (`/` and `/mobile/`), and ship 192px, 512px and maskable icons that all resolve.
- The service worker registers and activates, and production serves `/sw.js` with `cache-control: no-cache`
  so clinicians get each new release rather than a stale cached one.
- With the network off, `/mobile/` still loads from the cache **and the on-device engine still triages** —
  severe BP with chest pain returned `emergency` offline.
- **No `/api/` response appears in any cache**, and with the network off a clinical API call fails rather than
  being answered from stale cache. This is the safety property the service worker claims, confirmed empirically.

## 5. Accessibility

15 axe audits against wcag2a, wcag2aa, wcag21aa, wcag22aa across the
workspace and consultant sign-in views and every state of the offline app, at 1366x900, 768x1024 and 375x812:
**0 serious or critical violations and
0 views with horizontal page overflow.**

## Database: the Oct1Test set

Persisted in `ncdai_oct1test` on local PostgreSQL:

| Item | Count |
|---|---|
| Patients (API workflow) | 50 |
| Patients (PWA UI) | 52 |
| Encounters | 102 |
| Encounters assessed | 102 |
| Encounters reviewed and locked | 102 |
| Referrals requested, accepted and completed | 50 |
| Audit events | 664 |
| Non-synthetic patients | **0** |

Both facilities are `synthetic`; no clinical-testing facility was enabled. 52 PWA UI patients because two cases were created once by a harness smoke test and once on re-run after a correct duplicate-record-ID rejection.

## Boundaries

- No test touched the hosted Mary Help database; every record here is synthetic and local.
- The hosted clinical workflow against the live deployment still needs provisioned accounts and was not run.
- No live AI provider request was made.
- Engineering verification only. These results say nothing about clinical accuracy, effectiveness or adoption.

## Evidence

- [Oct1Test set summary](test-results/Oct1Test-summary.json)
- [API workflow, 50 cases](test-results/Oct1Test.json)
- [PWA UI, 50 cases](test-results/Oct1Test-pwa.json)
- [Offline mobile app, 50 cases](test-results/Oct1Test-mobile.json)
- [PWA capability checks](test-results/Oct1Test-pwa-capability.json)
