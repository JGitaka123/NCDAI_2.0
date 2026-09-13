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

The application currently covers selected adult NCD assessment/referral pathways, including hypertension/cardiovascular, diabetes, respiratory, renal and cancer warning signs. It does not provide comprehensive treatment for every NCD. Dose support contains four bounded oral starting-dose references: amlodipine, losartan, lisinopril and immediate-release metformin, with documented eligibility exclusions. It does not calculate insulin, oncology, paediatric, obstetric or general renal-adjusted regimens. Confirm the applicable guideline, current patient findings and formulary with the clinical lead.

## Escalation and service interruption

Online consultation is not continuously staffed or an emergency response service. Continue immediate clinical assessment and the hospital's direct referral/escalation process; do not wait for an online reply. No automatic email/SMS consultant alert is configured. The queue refreshes every 30 seconds and has an explicit refresh control; agree who watches it and how the team contacts the consultant directly during testing.

If a request is saved but consultant storage is unavailable, the main database retains it for retry. If saving the primary encounter fails, do not assume it was saved: reload and follow the hospital downtime documentation process. No offline patient-record store is provided. Do not place patient information in GitHub issues or error screenshots.

Jesse coordinates service incidents. Check the primary and consultant health endpoints and the **Mary Help service health** GitHub workflow. Scheduled GitHub checks are best effort; their existence does not prove that email notifications are delivered. Set account notifications and verify the team's direct contact/downtime arrangements before the first session.

## Daily evaluation and close-out

Dr Kamau reviews unresolved disagreements, safety concerns, unsupported cases and any opinion that differed from the primary clinician's eventual action. Jesse/Jane check account access, service failures and unresolved delivery. Preserve case IDs, rule/evidence/dose versions and reasoned decisions; do not overwrite an earlier opinion. Further questions require a new linked consultation.

Consultation totals describe episodes, not unique patients, diagnostic accuracy or patient outcomes. Engineering tests are separate from independent clinical adjudication and prospective clinical evaluation. The validation/pilot documents in `docs/evaluation/` remain the study-planning package.
