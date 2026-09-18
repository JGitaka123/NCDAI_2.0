# Sept18Test verification report

18 September 2026 · Local synthetic engineering verification of the NCDAI 2.0 application.

**Result: every check run in this session passed — 20 of 20 complete case workflows, 402 backend tests, 30 frontend tests, 75 dose workflows, 50 consultant workflows, 7 browser workflows and 31 accessibility audits, with zero failures.** That is an engineering statement about the application's code and database behaviour on a local stack. It is not a statement about the hosted deployment, which this environment cannot reach, and not a statement about clinical accuracy, which no automated suite here establishes.

Dataset label: `Sept18Test`. Machine-readable evidence is listed under [Evidence files](#evidence-files).

## What was tested, and against which revision

`backend/app` and `frontend/src` are byte-identical to commit `cae5152f2bd843c05822a0b7031f45e6dd769d6a`. The documentation corrections committed alongside this report change no application source, so these results describe the same application logic that commit contains. The revision published to https://ncdai-2.vercel.app at the time of the run was the earlier `1ded07988c4086ec75bf512e828410993a095e7b`, which differs from `cae5152` only in documentation, tests and scripts.

The stack under test was assembled locally: PostgreSQL 16.13 on loopback, the FastAPI backend, and the Vite frontend with a real Chromium browser driving the user interface. Migrations were applied from empty to head (`20260913_mary_help`), and `alembic check` reported no pending model drift. The consultant workspace was given its own database and reported schema `consultant-20260913-1`. Both revisions match the ones the [clinical-testing release record](clinical-deployment-status.md) names for the deployed service.

The four version identifiers the release record names were confirmed live in the code under test: rules `ncdai-2-rules-0.1.3`, evidence `ncdai-2026-09-13.1`, dose reference `ncdai-dose-reference-0.1.1`, AI prompt `ncdai-briefing-select-v1.5`.

## The 20 complete case workflows

Each case runs the same seven steps end to end against the persisted API: register patient, persist encounter, assess expected safety findings and evidence, review every recommendation and retrieve the immutable decisions, request and accept and complete a referral, export a reviewed FHIR document, and verify audit-chain integrity. Each assessment is checked for required rules, forbidden rules, minimum urgency (no under-triage against the frozen expectation), absence of duplicate rule IDs, and a resolvable evidence source with a section reference for every recommendation.

The 20 cases were selected deterministically from the 66-case frozen catalogue, round-robin across the six clinical domains in catalogue order, so a partial run stays spread across pathways rather than concentrated in one. The same selection is reproducible with `--limit 20`.

| Case | Domain | Title | Urgency | Recommendations | Result |
|---|---|---|---|---|---|
| `NCD-001` | cardiovascular | Stable treated hypertension review | soon | 2 | passed |
| `NCD-002` | cardiovascular | Severe isolated systolic reading | urgent | 2 | passed |
| `NCD-003` | cardiovascular | Severe isolated diastolic reading | urgent | 2 | passed |
| `NCD-004` | cardiovascular | Chest pain despite normal blood pressure | emergency | 1 | passed |
| `NCD-013` | diabetes | Low glucose in mmol per litre | urgent | 1 | passed |
| `NCD-014` | diabetes | Severe low glucose | emergency | 1 | passed |
| `NCD-015` | diabetes | Equivalent low glucose in mg per decilitre | urgent | 1 | passed |
| `NCD-027` | kidney | Severely reduced renal function | urgent | 1 | passed |
| `NCD-028` | kidney | Metformin with eGFR below thirty | urgent | 2 | passed |
| `NCD-029` | kidney | Metformin with moderately impaired renal function | soon | 3 | passed |
| `NCD-039` | respiratory | Low oxygen saturation | emergency | 1 | passed |
| `NCD-040` | respiratory | Asthma low oxygen near severe boundary | emergency | 1 | passed |
| `NCD-041` | respiratory | Borderline oxygenation needs review | urgent | 1 | passed |
| `NCD-049` | cancer referral | Breast lump requires diagnostic pathway | soon | 2 | passed |
| `NCD-050` | cancer referral | Unexplained weight loss | soon | 2 | passed |
| `NCD-051` | cancer referral | Persistent cough requires differential assessment | soon | 2 | passed |
| `NCD-052` | cancer referral | Abnormal bleeding with severity not established | urgent | 1 | passed |
| `NCD-055` | multimorbidity | Pregnancy with severe blood pressure | emergency | 3 | passed |
| `NCD-056` | multimorbidity | Pregnancy outside routine adult NCD treatment scope | urgent | 1 | passed |
| `NCD-057` | multimorbidity | Pregnancy with ACE inhibitor | urgent | 2 | passed |

20 passed, 0 failed, 2.18 seconds of workflow time on PostgreSQL. Six emergency and nine urgent assessments were produced; no case fell below its expected urgency. After the run the audit chain verified valid across 182 events, and the dashboard showed 20 patients, 20 encounters, 20 reviewed, 0 open referrals.

## Supporting suites

| Suite | Result | Notes |
|---|---|---|
| Backend tests | **402 passed, 8 skipped, 0 failed** | Includes the PostgreSQL transaction-pooler, account-lifecycle race and session-timezone regressions against a migrated database |
| Frontend unit tests | **30 passed** across 5 files | Matches the figure the release record cites |
| Dose workflows | **75 passed, 0 failed** | On PostgreSQL at dose reference `0.1.1` |
| Consultant workflows | **50 passed, 0 failed** | Two isolated databases, restricted runtime roles, 2 concurrency checks |
| Main browser workflows | **5 passed** | Desktop 1366×900, tablet 768×1024, mobile 375×812, keyboard-only, administrator navigation |
| Consultant browser workflows | **2 passed** | Desktop 1366×900 and mobile 390×844 |
| Accessibility audits | **31 audits, 0 reported violations** | 23 main views plus 8 consultant views, axe WCAG A/AA rules |

The browser runs exercised the real interface: patient registration, findings entry, evidence inspection, rejection of an incomplete review, review of every recommendation, record locking, referral completion, FHIR bundle download, the independent consultant handoff, and closure with explicit acknowledgement that the encounter had changed since the consultation snapshot.

Two behaviours are worth recording because they were observed rather than asserted. The facility boundary held: a supervisor account provisioned into a different facility saw nothing in the consultant queue, which is the intended isolation. And the append-only audit guard held: the database refused to delete a facility still referenced by retained audit events.

## What this run does not establish

- **The hosted application was not tested.** This verification sandbox cannot reach `ncdai-2.vercel.app`; its network proxy denies the host. Every result here comes from a local stack. The hosted service's own scheduled health workflow was passing independently on the same day.
- **Nothing was deployed.** Publishing is explicit through the Vercel CLI using the owner's credentials, which this environment does not hold. Since the changes committed with this report touch no application source, deploying them would republish identical application code.
- **No live AI request was made.** No DeepSeek key is configured here, so the briefing path was exercised only through its deterministic fallback inside the backend suite.
- **Backup, PITR, hosted recovery, RPO and RTO are untouched** by this run, and remain the open operational item in the release record.
- **PostgreSQL 16.13, Python 3.11 and Chromium build 1194** were used here; CI uses PostgreSQL 18.4, Python 3.12 and a pinned browser build. Engine-version-specific behaviour is therefore evidenced by CI, not by this run.
- **Clinical accuracy is out of scope.** These are workflow and safety-rule regression tests against frozen synthetic cases. They confirm the software does what its specification says; they do not confirm the specification is clinically correct. Independent clinical and pharmacy adjudication and prospective evaluation remain outstanding, as the release record states.

## Reproducing this run

```bash
python -m pip install -r backend/requirements.txt
# migrate an empty PostgreSQL database to head, then:
NCDAI_CASE_DATABASE_URL=postgresql+psycopg://... \
  python scripts/run_case_workflows.py docs/test-results/Sept18Test.json --limit 20 --label Sept18Test
```

`--limit` and `--label` were added to the runner for this report. With neither option the runner behaves exactly as before and executes the whole 66-case catalogue, which is what CI records.

## Evidence files

- [20 complete case workflows](test-results/Sept18Test.json) — per-case steps, rules, urgency, timings, audit state
- [Consolidated run summary](test-results/Sept18Test-summary.json) — every suite, environment, and the exclusions above
- [Main browser and accessibility summary](quality/Sept18Test-browser-summary.json) — 23 audits
- [Consultant browser and accessibility summary](quality/Sept18Test-consultant-browser-summary.json) — 8 audits

No real patient data was created, read or transmitted at any point in this run. All records are fictional.
