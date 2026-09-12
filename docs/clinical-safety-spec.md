# Clinical safety specification

Version 0.1, 12 September 2026. **Proposed engineering specification; independent clinical approval is pending.** This implementation is for synthetic development and verification. Software tests do not establish clinical safety, diagnostic accuracy, effectiveness, approval, or superiority to other systems.

## Intended use and scope

The intended user is an authenticated clinician who retains responsibility for assessment, treatment and disposition. The executable service supports selected adult NCD workflows: hypertension/CVD warning symptoms, diabetes review, kidney-function review, asthma/COPD assessment prompts, and selected possible cancer warning symptoms with referral tracking. It does not implement comprehensive care for every NCD. In particular, this release does not provide cancer staging or therapy, sickle cell or neurological disease management, advanced heart failure management, comprehensive CVD risk scoring, pediatric pathways, or obstetric treatment. Pregnancy triggers an appropriate alternate care pathway.

The engine has no prescribing output. Medication names on a reconciliation list do not become new orders. It does not calculate doses, suggest replacement prescriptions, administer emergency treatment, diagnose from one abnormal result, or pronounce a patient safe for discharge. The UI and external language model must preserve these boundaries. A clinician's acceptance of an alert is a recorded decision, not an appropriateness label.

## Executable contract and input semantics

`backend/app/clinical.py:assess(data, age, sex)` is a network-independent function. It returns rule identifiers, category, severity, explanatory text, sources, missing information, maximum urgency, evidence version and a development status. The backend records an immutable assessment with its input snapshot and authorizes every read, write and review. The function provides an assessment UUID and UTC time for standalone use; backend-assigned identity/time may replace them.

Urgency is an **operational routing label**: `emergency` means immediate clinician assessment; `urgent` means same-day assessment, with immediate action for low glucose; `soon` requires a clinically confirmed review interval; `routine` means complete the clinician review. No label is an automated disposition. Alerts are sorted critical before warning before information. Any critical new trigger keeps or increases the maximum urgency. A normal repeat measurement cannot hide a previous critical reading.

Measurements are nullable and have explicit semantics. BP is mmHg, eGFR mL/min/1.73 m2, potassium mmol/L, HbA1c percent, SpO2 percent and respiratory rate breaths/minute. Glucose requires an explicit unit; mg/dL is divided by 18 for comparison in mmol/L. The original value/unit remains in the encounter. Missing values are never converted to zero. Non-finite values, impossible supported-range values and inverted BP pairs fail validation. These bounds are input validation, not normal ranges.

Six disease-history fields are `yes`, `no` or `unknown`. Empty medication, allergy and symptom lists are not assessed negatives unless their corresponding `*_reviewed` flags are true. Pregnancy is explicitly `yes`, `no`, `unknown` or `not_applicable`; applicability is not inferred solely from recorded sex. Free text is not silently interpreted as structured evidence. A note mentioning an emergency does not activate a rule unless confirmed in structured fields; this limitation must be visible during use. A notes-extraction feature must retain clinician confirmation before changing such fields.

Each encounter currently has a shared observation timestamp. Missing time is surfaced; observations older than 24 hours prompt confirmation of current status. The 24-hour limit is an engineering heuristic, not a laboratory validity policy. A production observation model needs individual collection times, source system, author/device, method, position, specimen, quality flags, reference ranges, oxygen use and revision status. Historical danger observations remain visible because stale information must not become a false negative.

## Evidence registry and exact source anchors

`backend/app/evidence.py` holds bibliographic metadata, exact sections, access dates and source IDs. Its `is_ready()` checks technical completeness only. `REVIEW_STATUS` remains `proposed_requires_independent_clinician_signoff`. Live source URLs may change; a governed release must additionally archive permitted evidence snapshots, content hashes, licenses, supersession dates and the signed approval record. Whole licensed documents are not redistributed here.

| Source | Exact anchor used | Role and qualification |
|---|---|---|
| [WHO hypertension guideline](https://www.ncbi.nlm.nih.gov/books/NBK573627/) | 2021, sections 3.1, 3.2, 3.6, 3.7 | Adult non-pregnancy BP review and follow-up. Local treatment algorithms still require approval. |
| [WHO HEARTS-D](https://iris.who.int/bitstream/handle/10665/331710/WHO-UCN-NCD-20.1-eng.pdf?sequence=1) | 2020, acute complications p19, referral criteria p26 | Acute glucose/BP/renal/foot warnings. Conservative triage adaptations below are not verbatim WHO rules. |
| [Kenya MOH NCD primary-care protocols](https://health.go.ke/sites/default/files/2025-07/FINAL_NCD%20protocols.pdf) | Sections 4.2 p32, 4.5 p35, 4.8 p41, 5 p52 | Local diabetes and cancer pathway reference. The official July 2025-hosted copy and relevant indexed sections were located; full edition-date/source-archive verification remains open because direct retrieval timed out. |
| [WHO PEN](https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf?sequence=1) | 2020, section 2.3; asthma exacerbation p35 | Respiratory prompts; not a complete asthma/COPD protocol. |
| [NICE NG133](https://www.nice.org.uk/guidance/ng133/chapter/recommendations) | Recommendations 1.3.2-1.3.3; 1.4.3 Table 1 | Pregnancy exception and severe-BP safety referral; no Kenyan obstetric treatment substitution. |
| [Metformin prescribing information](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=54bb8030-8e80-4b38-8deb-89c99d73bf09) | Sections 2.3, 4, 5.1 | Renal contraindication/review flags. Verify the locally supplied product label. |
| [Lisinopril prescribing information](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=03a497fe-fb09-4b2c-8ee0-2019600192b8) | Label 11 Apr 2025; sections 5.1, 5.3, 5.5, 7.1, 7.3, 7.4 | Selected RAS/diuretic/NSAID safety principles; class mappings are proposed operational adaptations. |
| [Jardiance prescribing information](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=faf3dd6a-9cd0-39c2-0d2e-232cb3f67565) | Jan 2026; sections 5.1-5.2 | SGLT2-associated acute illness; class extension needs pharmacist approval. |
| [WHO HEARTS treatment protocols](https://iris.who.int/bitstream/handle/10665/260421/WHO-NMH-NVI-18.2-eng.pdf) | 2018; medicine table p39 | Older-adult glibenclamide review. |
| [NICE NG28 initial medicines](https://www.nice.org.uk/guidance/NG28/chapter/initial-medicines) | Updated 18 Feb 2026; kidney-disease rationale | Sulfonylurea risk review. UK formulary selections are not imported as Kenyan prescriptions. |
| [UK Kidney Association potassium guideline](https://www.ukkidney.org/health-professionals/guidelines/treatment-acute-hyperkalaemia-adults-0) | July 2026 update; 1.2.1-1.2.3 and 4.1-4.2 | High-potassium assessment/referral. |
| [NHS Lothian hypokalaemia guidance](https://www.rightdecisions.scot.nhs.uk/electrolyte-disturbance/hypokalaemia/?organization=nhs-lothian) | Think; Treat: severe/moderate; escalation | Low-potassium safety flag; no replacement protocol. |
| [RCP NEWS2 report](https://www.rcp.ac.uk/media/a4ibkkbf/news2-final-report_0_0.pdf) | 2017; Chart 1 physiological parameters and Chart 3 observation chart | Selected abnormal-vital-sign triggers only; not a validated NEWS2 score or its complete response protocol. |
| [KDIGO CKD guideline](https://kdigo.org/wp-content/uploads/2024/03/KDIGO-2024-CKD-Guideline.pdf) | 2024; 1.1.1.1-1.1.1.2 and 1.1.3.1-1.1.3.2 | Kidney assessment and chronicity; no CKD diagnosis from an isolated eGFR. |
| [NCI symptom guidance](https://www.cancer.gov/about-cancer/diagnosis-staging/symptoms) and [WHO early-diagnosis guide](https://www.who.int/publications/i/item/guide-to-cancer-early-diagnosis) | Symptom categories; diagnostic/referral capacity | Diagnostic evaluation and continuity prompts; no positive cancer prediction. |

## Traceable risk and rule matrix

All rows are proposed implementations awaiting independent local clinical approval. Listed minimum tests are acceptance requirements, not a claim they all passed. Independent workflow test results belong in the verification report.

| Hazard / requirement | Rule identifiers and executable trigger | Minimum discriminating tests |
|---|---|---|
| Acute illness hidden by apparently normal chronic-disease measurements | `EMERGENCY_SYMPTOMS`: chest pain, breathlessness, neurological deficit, confusion or seizure -> emergency irrespective of measurements | Normal BP with stroke symptom; missing BP with chest pain; conflicting notes cannot cancel structured symptoms |
| Abnormal vital signs outside a chronic disease pathway ignored | `LOW_BP`: any SBP <=90 urgent; `PULSE_EXTREME`: pulse <=40 or >=131 urgent; `RESP_SLOW`: RR <=8 emergency | Exact boundaries; low initial BP with normal repeat; no complete early-warning-score claim |
| Severe BP incorrectly treated as routine | `BP_CRISIS`: any SBP >=180 or DBP >=110 plus headache/vision/vomiting -> emergency; otherwise `BP_SEVERE` -> urgent | Isolated high diastolic; exactly threshold; normal repeat after critical initial; acute care not delayed by missing repeat |
| Pregnancy processed by a general adult pathway | `PREGNANCY_SCOPE`; `PREGNANCY_SEVERE_BP` at 160/110; `PREGNANCY_WARNING`; `RAS_PREGNANCY` | Routine treatment prompts absent in pregnancy; severe systolic alone; unknown pregnancy with RAS medicine; sex does not override pregnancy |
| Low glucose overlooked or unit-dependent | `HYPOGLYCEMIA` at <=3.9 mmol/L; emergency below 3 or neurological compromise; `SUSPECTED_HYPOGLYCEMIA` for symptoms without matching low result | 3.9 boundary; mg/dL equivalence; missing unit rejected; impaired consciousness; stale normal value |
| Acute metabolic deterioration missed | `HYPERGLYCEMIC_CRISIS` when glucose >=18 plus vomiting/dehydration/confusion; `GLUCOSE_HIGH` without these; `SGLT2_ACUTE_ILLNESS` for acute illness with SGLT2 medicine | Hyperglycaemia with dehydration; high glucose alone; SGLT2 symptoms with glucose in ordinary range |
| Respiratory danger missed or oxygen automatically prescribed | `RESP_HYPOXEMIA`: SpO2 <92 emergency, 92-94 urgent; `RESP_TACHYPNEA` RR >25 urgent; `RESP_WHEEZE` urgent | SpO2 91.9/92/94/95; respiratory-rate boundary; missing oxygen measurement; no oxygen dose/target |
| Warning symptoms dismissed or converted into a cancer diagnosis | `HEMOPTYSIS` urgent; `CANCER_WARNING` soon, or urgent for bleeding with unspecified severity; `CANCER_SCOPE` continuity | Breast lump in any sex; cough without cancer history; abnormal bleeding; no malignancy label; referral tracked |
| Renal impairment overlooked or mislabeled chronic | `RENAL_SEVERE` eGFR <30 urgent; `CKD_REVIEW` known CKD or eGFR <60 | Exactly 30 and 60; low value without prior history; no autonomous CKD stage/diagnosis |
| Important electrolyte derangement omitted | `POTASSIUM_HIGH` >=5.5, urgent >=6, emergency >=6.5; `POTASSIUM_LOW` <3.5, urgent <3, emergency <2.5 | Each boundary plus adjacent values; simultaneous high BP cannot downgrade potassium alert |
| Medication-related harm | `METFORMIN_RENAL` below 30; `METFORMIN_REVIEW` 30-44.99; `DUAL_RAS`; `NSAID_RENAL`; `POTASSIUM_MEDICATION_RISK`; `GLIBENCLAMIDE_OLDER_ADULT` age >=60; `SULFONYLUREA_RENAL` eGFR <60 | Renal boundaries; ACE+ARB; ACE+NSAID with/without diuretic; spironolactone combination; age boundary; alias equivalence |
| Incomplete medication or allergy record falsely called safe | `ALLERGY_CONFLICT` exact normalized ingredient/name match; `DUPLICATE_MEDICATION`; `MEDICATION_UNSUPPORTED`; schedule completeness warning | Empty unreviewed list; reviewed empty list; exact allergy overlap; unknown ingredient; duplicates with separate schedules |
| Limb-threatening complication overlooked | `FOOT_ULCER` -> urgent assessment because infection/ischaemia status is not structured | Ulcer without glucose; ulcer plus systemic danger; no assumption ulcer is uninfected |
| Chronic-care opportunity missed or distracts from acute care | `BP_HIGH`, `BP_REVIEW`, `HTN_FOLLOWUP`, `DIABETES_CONFIRM`, `DIABETES_REVIEW`, `RESP_CHRONIC_REVIEW`, `TOBACCO_SUPPORT`, `ADHERENCE_REVIEW` | Routine complete encounter; acute trigger suppresses routine planning; high HbA1c is not automatic intensification |
| False reassurance from missing information | `DATA_COMPLETENESS`; fallback `CLINICIAN_REVIEW` | Null versus zero; missing observation time; all tri-state histories unknown; all assessed negatives; no empty assessment |

## Conservative adaptations that require explicit approval

These rules deliberately ask for assessment earlier than some source pathways. The operational choices are traceable to this specification, not presented as direct quotations or universally agreed guideline cutoffs:

- Any recorded acute symptom in the emergency vocabulary triggers immediate assessment because onset/severity qualifiers are absent. This may over-triage chronic stable breathlessness; a production form must collect acuity without hiding acute symptoms.
- Isolated severe vital-sign observations prompt review without computing NEWS2; the required complete observations and context are not present. A very low respiratory rate is conservatively routed to immediate assessment.
- BP danger thresholds are inclusive, and a severe reading is not averaged with a lower repeat. This is not a diagnostic criterion for hypertensive emergency.
- Marked glucose alone is escalated without first proving treatment failure. Low glucose below 3 is routed as emergency even without documented dependence on assistance; severity grading still requires clinical assessment.
- The asthma SpO2/respiratory-rate warning principles are conservatively applied to an undifferentiated adult NCD encounter. SpO2 92-94 is a local review threshold. COPD baseline/hypercapnia and measurement uncertainty are not available; no oxygen target follows from the screen.
- Any foot ulcer, hemoptysis or unexplained bleeding prompts same-day assessment because severity, infection, perfusion and blood-loss details are missing.
- The sulfonylurea eGFR <60 review threshold, SGLT2 class mapping, HbA1c >=9 priority flag and 24-hour observation warning are proposed safeguards, not independently validated decision thresholds.

## Medication safety completeness and required next capabilities

The dictionary recognizes a small set of common ingredient codes and two explicit aliases. It is not a licensed comprehensive medication knowledge base. Current checks omit many drug interactions, allergy cross-reactivity, dose/frequency/route/formulation appropriateness, cumulative exposure, maximum doses, renal-dose calculations, pregnancy-specific safety for every ingredient, hepatic disease, QT risk, nutrition, HIV/TB interactions, OTC/herbal exposure, anticoagulants, insulin formulations and chemotherapy. The screen always states these limits.

Before a prescribing-support claim, implement a governed national formulary mapping with exact product/ingredient/formulation/route, medication status and start/stop dates; allergy reaction/severity/verification; pharmacist-reviewed interaction mechanisms and severity; renal/hepatic and pregnancy/lactation logic; prospective order checks; override accountability; and independent adversarial cases. Dose rules must have a complete clinical context and explicit author/reviewer/version. Unknown medicines and contraindication context must result in abstention, not extrapolated drug advice.

## Release and change control

1. A Kenyan clinical lead, pharmacist and relevant specialty reviewers independently approve each source interpretation, mapping, threshold, wording, care level and referral destination. Resolve source disagreement explicitly; publishing an engineering test is not approval.
2. Protect a held-out synthetic/clinician-authored case set from rule development. Include omitted-input, contradictory-data, wrong-unit, boundary, pregnancy, multimorbidity, older adult, limited-resource and acute-deterioration cases. Record expected actions and severity adjudication before running the system.
3. Require every recommendation to have a resolvable versioned source or an explicitly identified engineering-policy reference. An LLM cannot remove alerts, lower urgency, add treatment recommendations or label a rule clinically approved.
4. Test function behavior, API identity/authorization, immutable review snapshots, concurrent changes, referral follow-through, failure recovery and browser usability. Record executable versions and observed results. Fifty workflows are engineering coverage, not fifty clinical validations.
5. Apply clinical approval, data protection, institutional authorization, deployment controls and supervised evaluation requirements before patient use. Keep the synthetic-only restriction until the applicable gates have evidence. Validation/pilot/grant documents are intentionally deferred under the user's requested sequence.

Any guideline, threshold, medication mapping, model or interface change invalidates affected test assumptions. Retain prior assessments with their source/rule version; never retrospectively rewrite clinical records to match a new rule. Use a reviewed release record, rollback and incident review for any safety-relevant update.
