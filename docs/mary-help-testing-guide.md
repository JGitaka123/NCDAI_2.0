# Mary Help Hospital testing guide

Planned start: **14 September 2026**, Mary Help Hospital, Thika. Clinical lead: **Dr David Kamau**. Administrators: **Jesse Gitaka and Jane Ngure**. Incident lead: **Jesse Gitaka**. The owner confirms the existing approvals cover care/medication recommendations and the Frankfurt/DeepSeek data-handling arrangement. Named contact addresses are held in private deployment configuration and the authenticated application.

## Sign in and prepare the team

- Main workspace: https://ncdai-2.vercel.app
- Consultant workspace: https://ncdai-2.vercel.app/consultant
- Each named user receives an individual temporary password through the owner. The application requires a password change before record access. No credentials are published in the repository and no email has been sent automatically.
- Jesse or Jane opens **User access** and creates a **clinician** account for each primary health worker. Give each person their own initial password through the hospital's approved channel. These accounts also require a first-login password change. Names/emails for these workers have been requested; no shared clinical account has been substituted.
- Dr Kamau's **supervisor** account can review consultations. The requester cannot answer their own consultation, and the consultant cannot also record the primary team's final disposition.

## Start with a fictional rehearsal

1. Sign in under the correct facility. In Patients, register a **Fictional case — staff rehearsal**. Record type is explicit; it cannot later be relabelled as a real patient.
2. Enter observations, relevant disease history, medications/allergies and acute-illness/kidney-injury context. Unknown values remain unknown. Select **Assess & review**.
3. Review the deterministic findings. The optional DeepSeek briefing selects existing findings; it does not create new prescribing advice. Patient names, raw observations and free-text notes are excluded from provider input.
4. For a disagreement or uncertainty, choose **Request consultant review**, select the relevant recommendation(s), enter the question/reason and describe immediate actions already taken. Submit, then confirm delivery. If delivery is pending, the question remains stored; retry delivery.
5. Dr Kamau opens the consultant workspace, verifies patient identity and the preserved observations, and records agreement, assessment, recommended action, urgency, rationale and source references.
6. The primary clinician reads the opinion and records the **actual action taken** and reasons. If the encounter changed meanwhile, the application requires explicit acknowledgement that current findings were checked. The original assessment remains unchanged.
7. Complete normal clinician review, tracked referrals and follow-up. For a subsequent assessment, create a new encounter rather than altering a reviewed record.
8. Check **Evaluation**: fictional rehearsals and real-patient episodes are separated. Confirm requests, consultant responses and primary actions are accounted for.

## Supervised patient testing

Only the explicitly enabled Mary Help facility can register **Real patient — supervised clinical testing** records. Follow the hospital's approved protocol, consent arrangements and professional responsibilities. The demonstration facility cannot register real records. Administrative accounts cannot read clinical charts or provide consultant opinions.

The application currently covers selected adult NCD assessment/referral pathways, including hypertension/cardiovascular, diabetes, respiratory, renal and cancer warning signs. It does not provide comprehensive treatment for every NCD. The starting-dose check contains thirteen bounded oral starting-dose references from Kenya MOH Table 4 and section 4.5, with documented eligibility exclusions. It does not calculate insulin, oncology, paediatric, obstetric or general renal-adjusted regimens. Confirm the applicable guideline, current patient findings and formulary with the clinical lead.

## What changed after the September 2026 clinician feedback

Built in September 2026 in response to the review by Dr Kamau and colleagues, and released to the hospital workspace on 11 October 2026 (ruleset `ncdai-2-rules-0.4.0`), alongside the consultant synthesis that was already live. Please re-test these specifically and report what is still unclear.

1. **Section 06 is now "Starting-dose check."** It states what it does, gives three steps, lists the medicines it covers, and shows a live checklist of what is still missing before a dose can be displayed. Use it only when you are considering *starting* one of the listed medicines.
2. **Weight, height, waist and BMI** are in section 01. BMI is calculated and categorised as you type, and appears on the assessment.
3. **Laboratory results** now open by default and hold the full lipid profile (total cholesterol, LDL, HDL, triglycerides), and glucose is recorded as **fasting (FBS)** or **random (RBS)** so the diagnostic thresholds apply correctly (FBS at or above 7.0, RBS at or above 11.1 mmol/L). The history section records coronary or peripheral arterial disease and previous stroke or TIA separately; either one counts as established cardiovascular disease for the statin options, and both must be answered before the application treats cardiovascular disease as absent.
4. **Treatment recommendations now name medicines and doses.** For a patient with recorded hypertension or type 2 diabetes whose readings are above target, the assessment lists the Kenya MOH step that applies with specific medicines and transcribed doses (for example a step 1 combination, increasing to the Table 4 maximum, adding a sulfonylurea, or starting basal insulin), plus statin treatment with NICE NG238 doses (atorvastatin 20 mg for diabetes without cardiovascular disease, 80 mg with established cardiovascular disease, 20 mg in kidney disease), statin intensification when LDL is above target, and asthma inhaler review. These options are **withheld** in urgent, emergency, acutely unwell and pregnancy contexts, and are proposals for the prescriber, not prescriptions. **Dr Kamau approved these options on 11 October 2026, covering both the clinical and the pharmacy review. They remain proposals for the prescriber: keep reviewing them critically and record any disagreement.**
5. **Recommendations show the values they are based on** ("BP used for control: 164/100 mmHg", "HbA1c 9.1%", current medicines) instead of generic wording.
6. **Citations are visible on each card** as a labelled source chip with the table and printed page, linking directly to that page of the source document, and are collected in a numbered reference list at the end of the assessment.
7. **Review is faster:** recommendations are grouped into Act now, Treatment options, Review and For information; **Accept remaining non-critical** decides the routine items in one action while every critical item still needs its own decision; reasons for modify, defer and reject can be chosen from one-tap suggestions; and decided cards collapse with a progress bar.
8. **Every recommendation is written for the individual patient** (revision 0.3.0, 19 September 2026): it quotes their readings, names their own medicines and doses, and computes their targets (for example the weight-loss range in kg or the non-HDL cholesterol goal). A **Patient summary** at the top of the assessment lists each problem against its target, the reconciled medicine list and a monitoring plan, and can be copied into the paper file. Hypoglycaemia guidance now gives the Kenya protocol doses.
9. **The overview page** opens with a patient search, quick actions and **Continue where you left off**, listing unreviewed encounters most urgent first; selecting one opens that patient's encounter directly.

### Two kinds of guidance on one assessment

Each assessment can now show both the **consultant synthesis** (problem list, targets and stepwise plans citing WHO, ISH, ESC, ADA, KDIGO, GINA and GOLD, naming drug classes but never doses) and the **Treatment options** group (named medicines and doses, citing the Kenya MOH protocol for blood pressure and diabetes and NICE NG238 for statins). Their targets can differ. For example, the consultant synthesis may give a blood pressure target of <130/80 mmHg with diabetes, kidney disease or cardiovascular disease, and ESC LDL goals by risk category, while the treatment options use the Kenya target of <140/90 mmHg and the NICE statin doses and lipid targets. Each statement shows its source; the prescriber decides. Please record which you followed, and tell the clinical lead whenever the two disagree for a patient. Dr Kamau approved these treatment options on 11 October 2026, covering both the clinical and the pharmacy review.

The offline **NCDAI Consult** mobile app runs the same rules and is tested to produce identical output, so it lists the same treatment options. The patient summary is shown only in the online workspace.

## Escalation and service interruption

Online consultation is not continuously staffed or an emergency response service. Continue immediate clinical assessment and the hospital's direct referral/escalation process; do not wait for an online reply. No automatic email/SMS consultant alert is configured. The queue refreshes every 30 seconds and has an explicit refresh control; agree who watches it and how the team contacts the consultant directly during testing.

If a request is saved but consultant storage is unavailable, the main database retains it for retry. If saving the primary encounter fails, do not assume it was saved: reload and follow the hospital downtime documentation process. No offline patient-record store is provided. Do not place patient information in GitHub issues or error screenshots.

Jesse coordinates service incidents. Check the primary and consultant health endpoints and the **Mary Help service health** GitHub workflow. Scheduled GitHub checks are best effort; their existence does not prove that email notifications are delivered. Set account notifications and verify the team's direct contact/downtime arrangements before the first session.

## Record continuity during testing

Keep the hospital's existing documentation process alongside NCDAI during supervised testing. Both databases passed logical snapshot/restore checks, but actual managed backup/PITR retention has not yet been inspected because Neon requires owner email verification before console access. Complete that verification and confirm retention/recovery arrangements before relying on NCDAI as the sole patient record.

## Daily evaluation and close-out

Dr Kamau reviews unresolved disagreements, safety concerns, unsupported cases and any opinion that differed from the primary clinician's eventual action. Jesse/Jane check account access, service failures and unresolved delivery. Preserve case IDs, rule/evidence/dose versions and reasoned decisions; do not overwrite an earlier opinion. Further questions require a new linked consultation.

Consultation totals describe episodes, not unique patients, diagnostic accuracy or patient outcomes. Engineering tests are separate from independent clinical adjudication and prospective clinical evaluation. The validation/pilot documents in `docs/evaluation/` remain the study-planning package.
