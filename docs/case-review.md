# Independent synthetic case and boundary review

12 September 2026. Workstream 8: independent engineering review of the proposed clinical screen. This review is separate from the rule authoring workstream; it is not an independent licensed clinician's adjudication, clinical validation, or evidence of patient benefit.

## Review outcome

An independent set of 107 discriminating test instances covers exact routing, negative controls, boundaries, units, missing values, repeat readings, medication synonyms, unsupported inputs, and preservation of emergency alerts. The tests are in `backend/tests/test_clinical_independent.py`; they do not derive expected answers from implementation constants or alter the original 66-case catalogue. Exact routine controls use HbA1c 5.4%, with reviewed negative histories, to avoid a confounder in that catalogue.

The first run of 106 instances had 104 passes and two failures. Both failures demonstrated a medication-allergy synonym defect: the engine recognized glyburide as glibenclamide and HCTZ as hydrochlorothiazide in medication codes, but did not recognize those same equivalences in the allergy record. A known allergy could therefore miss an allergy-conflict alert. The correction applies the already-supported two aliases consistently to ingredient codes, explicit medicine names and allergy text. All 106 original instances passed after the correction; an additional explicit-name/unmapped-code regression extends coverage to 107 instances. Final command and observed result are recorded below.

This correction does not establish allergy cross-reactivity support, a complete medication dictionary, or safety of an unrecognized medicine. Unsupported medicines still prompt manual review. The persistent warning explicitly describes the lack of comprehensive interaction, dose and class-allergy assessment.

The corrected assessment records `rules_version=ncdai-2-rules-0.1.1`. The evidence version remains unchanged because the source documents did not change. The separate 66 live-provider/PostgreSQL workflows completed before this alias correction; they cannot be presented as a run of version 0.1.1. The additional independent tests verify the correction, and final release checks must record the code version they actually run.

## Frozen 66-case catalogue: coverage and limitations

The reviewed catalogue was `tests/cases/clinical_cases.json`, version 1.0, SHA-256:

`16cd695e4c433298e41d5420b7f9ebe84dff78c5ff284f66f750b1467ea90230`

No catalogue input or expected outcome was changed during this review. Its cases are suitable for exercising the application workflow across selected cardiovascular, diabetes, kidney, respiratory, cancer-warning and multimorbidity scenarios. The catalogue itself is not a clinical gold standard.

- 49 of 66 cases contain HbA1c 6.5% with `known_diabetes=no`. This can trigger a diabetes-confirmation prompt in otherwise stable cases. It is plausible as a possible new diagnosis, but it is not a clean normal control and may distract from the condition named in the title.
- 11 cases allow a minimum urgency of `routine`; minimum-only assertions also accept `soon`, `urgent` or `emergency`. Such assertions help detect under-triage but cannot establish specificity or exclude unnecessary escalation.
- 13 cases have no mandatory rule identifiers. Forbidden-rule checks can still be useful, but an empty mandatory list does not establish that the intended positive action occurred.
- The catalogue omits observation timestamps; the full workflow runner must supply a current timestamp explicitly. Without that fixture step, completeness alerts would further confound cases intended to be complete.
- Many medication examples omit dose, unit or frequency, appropriately producing incomplete-schedule warnings. These are reconciliation tests, not complete prescribing cases.
- Case titles and a successful workflow do not prove that clinical priorities, referral timing, diagnosis, or treatment are correct. The expected minimum urgency is a proposed engineering assertion.

The independent test set addresses selected precision gaps without rewriting this baseline. A future clinically adjudicated evaluation should include balanced normal controls, exact acceptable actions and unacceptable actions, validated symptom acuity, prior observations, medication schedules, locally available services, and clinician-authored held-out cases. That evaluation remains outside the present engineering test claim.

## Discriminating checks

| Area | Independent checks and interpretation |
|---|---|
| Normal control | Exactly `routine`, no missing data, no diabetes-confirmation alert; the result still gives no clinical clearance. |
| Diabetes | HbA1c immediately below/at/above 6.5; confirmation prompt rather than an asserted diagnosis. Glucose 2.99/3.0/3.9/3.91 mmol/L checked with equivalent mg/dL values. Missing glucose is not zero; symptoms without a measurement still request acute assessment. |
| Electrolytes | Exact low-potassium routing at 2.5, 3.0 and 3.5; high-potassium routing at 5.5, 6.0 and 6.5; adjacent values distinguish inclusive/exclusive behavior. These are the specification's proposed operational labels. |
| Respiration and pulse | Oxygen boundary at 92 and 95; respiratory rate 8/9 and 25/26; pulse 40/41 and 130/131. These checks do not calculate or validate a NEWS2 score. |
| Blood pressure | Severe systolic alone, severe diastolic alone, partial repeat readings, and normal repeat after severe initial reading. Missing paired measurements cannot cancel recorded danger. Low systolic boundary at 90/91. |
| Pregnancy and age | A recorded pregnancy is honored regardless of sex field; severe BP and warning symptoms with missing BP retain emergency routing. Unsupported ages and noninteger ages fail closed; adult bounds 18 and 120 are accepted. |
| Unknowns and time | Each unknown history, unreviewed empty list, absent timestamp, and stale critical observation stays explicit. Staleness cannot downgrade an emergency. |
| Medication review | Existing metformin renal boundaries, known medicine aliases in both allergy directions, unknown product code with recognized name, and explicit limits on class cross-reactivity. |
| Adversarial input | Conflicting notes cannot suppress each configured acute symptom. Nonfinite glucose and unsupported units are rejected; API model measurement bounds are tested. Input records are not mutated and all triggered alerts retain source metadata. |

## Source basis and clinical limits

The operational expectations are tied to `docs/clinical-safety-spec.md`, which identifies conservative adaptations and review requirements. Primary reference checking in this review confirmed that the referenced [metformin product label, sections 2.3 and 4](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=54bb8030-8e80-4b38-8deb-89c99d73bf09) distinguishes eGFR below 30 from review of ongoing treatment below 45. Its displayed label update is August 2018; a current locally supplied product label and Kenyan pharmacist review remain necessary. This engineering screen does not issue the label's medication instructions automatically.

The [UK Kidney Association guideline page](https://www.ukkidney.org/health-professionals/guidelines/treatment-acute-hyperkalaemia-adults-0) was available during the review. Potassium routing assertions refer to the exact proposed implementation matrix and its cited sections; this review does not represent a full rereading and clinical adjudication of that guideline. Direct retrieval of the NICE pregnancy recommendations returned HTTP 403 during this review; the existing specification's reference was retained, and no new NICE clinical claim was inferred from the failed retrieval.

Remaining material limitations include undifferentiated symptom acuity, a single shared observation timestamp, limited NCD coverage, absence of a comprehensive medication knowledge base, lack of patient outcome evidence, and pending independent clinical approval. Passing these tests does not remove those limitations.

## Reproduction and result

From `backend`, run:

```text
python -m pytest tests/test_clinical_independent.py -q
```

Recorded run: 107 passed. The run reports two upstream TestClient deprecation warnings; no test failure. These are function/model assertions, not 107 additional patient workflows. The separate 66-workflow run used its frozen catalogue; release reporting must retain its observed code revision and distinguish it from this subsequent alias correction.
