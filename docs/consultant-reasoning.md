# Consultant reasoning engine

Version `ncdai-consultant-1.0.0` · rules `ncdai-2-rules-0.2.0` · evidence `ncdai-2026-09-29.1`

Every assessment now carries a **consultant synthesis** (`assessment.consultant`) alongside the safety rules. It turns the structured encounter into what a consultant physician writes after a clinic review: a patient-specific one-line summary, derived measures, a ranked problem list with individual targets, stepwise guideline-linked plans, a medication review, diagnostic considerations, monitoring, follow-up and a copyable plain-text summary for notes or referral letters.

Source: [`backend/app/reasoning.py`](../backend/app/reasoning.py). Tests: [`test_reasoning.py`](../backend/tests/test_reasoning.py), [`test_engine_parity.py`](../backend/tests/test_engine_parity.py).

## Boundaries

- Deterministic: no network, no model inference, no free-text interpretation. The same inputs always give the same output.
- The safety rules keep sole control of urgency. The synthesis reads the final urgency and, when it is urgent or emergency, leads with "stabilise first".
- Plans name drug classes and guideline steps for the clinician to decide. They never prescribe or set doses; the bounded Kenya dose module remains the only dose reference. Statin intensity is described by its guideline class definition.
- Blank inputs stay unknown. They appear as data gaps ("would sharpen this assessment"), never as normal values.
- Pregnancy withholds chronic treatment reasoning and routes to the obstetric-medicine pathway.
- It is preserved in the reviewed assessment snapshot and in the FHIR review document, so the record shows exactly what the clinician saw.
- Every source is in the versioned evidence registry and still requires independent clinician sign-off (`proposed_requires_independent_clinician_signoff`).

## What it derives

| Measure | Method | Source |
|---|---|---|
| eGFR from creatinine | Race-free CKD-EPI 2021 (female/male sex required). An entered laboratory eGFR always wins. The safety rules also use the calculated value, with a warning. | Inker, NEJM 2021 |
| Kidney stage and risk | KDIGO G1–G5 × A1–A3 heat map; monitoring frequency per year | KDIGO 2024 |
| HbA1c IFCC | (NGSP − 2.15) × 10.929 | ADA 2025 |
| BMI, waist risk | WHO categories; waist 80/88 cm (female), 94/102 cm (male) | WHO |
| Cardiovascular risk | Established ASCVD, diabetes with organ damage or 3+ risk factors, and severe CKD are very high risk without a calculator (ESC 2019). Otherwise Framingham 2008 general CVD (laboratory or BMI model, age 30–74), categorised <10 / 10–<20 / ≥20% (WHO). Framingham is not calibrated for Kenya; the output says so and points to the WHO Eastern sub-Saharan Africa chart. | D'Agostino 2008; WHO 2019 |
| CHA2DS2-VA | ESC 2024 score without the sex category; reports a minimum score when factors are unknown | ESC AF 2024 |

## Clinical logic by domain

- **Hypertension.** Diagnosis at ≥140/90 with confirmation on a second visit; individual targets (<130/80 with CVD, diabetes, CKD or high risk; <140/90 at 80+ or with frailty). Escalation follows the combination sequence: start a combination (single pill preferred) → second class → ACE inhibitor/ARB + CCB + thiazide-like diuretic → resistant hypertension work-up with spironolactone only if potassium ≤4.5 and eGFR ≥45. ACE inhibitor/ARB is prioritised for albuminuria/CKD; heart failure defers to HF pillars. Secondary-cause prompts for age <40 and hypokalaemia (aldosterone-renin ratio). Overtreatment check for low BP in older or frail adults.
- **Diabetes.** Individual HbA1c target (<7.0%, relaxed to <8.0% for frailty, age 75+, eGFR <30 or recent hypoglycaemia on insulin/sulfonylurea). SGLT2 inhibitor for CKD, heart failure or ASCVD independent of HbA1c; GLP-1 RA for ASCVD. Metformin first-line and capped at 1000 mg/day at eGFR 30–44. Intensification choice by BMI, cost and hypoglycaemia risk; insulin when HbA1c ≥10% or catabolic. De-intensification when HbA1c <6.5% on insulin/sulfonylurea in older adults. Eye, foot and ACR care gaps. Atypical-diabetes and HbA1c-reliability prompts (anaemia, haemoglobin variants including sickle-cell trait, advanced CKD).
- **Kidney.** Chronicity confirmation, ACR, ACE inhibitor/ARB for albuminuria with the 2–4 week creatinine/potassium check and the 30% creatinine-rise rule, SGLT2 inhibitor per KDIGO 2024 Rec 3.7.1, sick-day guidance, anaemia work-up, nephrology referral criteria.
- **Lipids and prevention.** Statin indications (ASCVD, diabetes 40+, CKD 50+, high calculated risk), LDL goals by risk category, intensification then ezetimibe, antiplatelet for secondary prevention.
- **Heart failure.** Four HFrEF pillars with the missing ones named; echocardiographic phenotype; MRA potassium/eGFR limits.
- **Atrial fibrillation.** Anticoagulation by CHA2DS2-VA, DOAC preference with the Kenyan caveat to exclude rheumatic mitral stenosis, aspirin is not stroke prevention, bleeding-risk reduction, rate control.
- **Asthma and COPD.** GINA 2025 (no SABA-only treatment, ICS-formoterol, control and exacerbation risk). GOLD 2025 (spirometry, LABA + LAMA, GOLD E and eosinophils, ICS monotherapy flagged, oxygen assessment, biomass exposure). Pulse-oximetry bias in darker skin.
- **Weight, tobacco, TB.** Weight-loss goals and GLP-1 RA in diabetes; WHO 2024 tobacco-cessation pharmacotherapy; TB testing before attributing cough, haemoptysis or weight loss to cancer or chronic lung disease.
- **Medication review.** NSAID "triple whammy" and NSAID with CKD, heart failure, anticoagulation or raised BP; non-selective beta-blocker in asthma; pioglitazone or diltiazem/verapamil in heart failure; anticoagulant plus antiplatelet; primary-prevention aspirin; ACE inhibitor after angioedema; hypoglycaemia risk; MRA with high potassium or low eGFR; digoxin toxicity risk; steroids in diabetes; diuretic hypokalaemia; within-class duplication.

## New structured inputs

All optional and unknown by default: weight, height, waist, creatinine, urine ACR, total/HDL/LDL cholesterol, haemoglobin, glucose timing, coronary/peripheral arterial disease, previous stroke/TIA, heart failure, atrial fibrillation, hypoglycaemia episodes, eye and foot examination status, exacerbations and reliever use. They are stored in the existing encounter JSON; no database migration is required.

## Verification

- 21 reasoning tests: published reference values (CKD-EPI 2021, Framingham), KDIGO boundaries, guideline sequences, safety boundaries (pregnancy, emergency, no input mutation), and the API → review snapshot → FHIR path.
- The full backend suite and all 66 end-to-end synthetic case workflows pass with the engine active.
- The offline mobile engine is checked for identical output on the 66 catalogue cases, targeted scenarios and 1,500 seeded random patients (see [mobile app](mobile-app.md)).

These are engineering checks against the stated guideline logic. They do not establish clinical accuracy; clinician adjudication of the synthesis on the case catalogue is the next validation step.
