# Bounded Kenya medicine-reference engine

Version `ncdai-dose-reference-0.1.1` · 13 September 2026 (supersedes `0.1.0` of 12 September 2026)

Version `0.1.1` changed eligibility only: a starting-dose reference is withheld unless both `acutely_unwell` and `acute_kidney_injury` are explicitly recorded as `no`. The four-medicine catalogue and its manifest hash are unchanged from `0.1.0`.

This extension supplies selected adult oral starting-dose references and checks a clinician-entered dose against the configured reference. It does not select a drug, issue a prescription, prescribe a titration schedule, calculate renal/weight adjustments or establish that a proposed regimen is clinically appropriate. Reviewed output is an immutable decision record; FHIR export remains a document and observations, not a medication order.

## Source verification and supported medicines

The Kenya Ministry of Health [Protocols for Management of Selected NCDs at Primary Care Setting](https://health.go.ke/sites/default/files/2025-07/FINAL_NCD%20protocols.pdf) was downloaded from the ministry, text-extracted and relevant pages visually inspected. The downloaded PDF is 5,599,713 bytes, 132 pages, SHA256 `e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8`. An explicit edition date was not found in the opening pages; July 2025 is its hosting path, not an asserted publication date. The complete PDF is retained privately for source review and not redistributed in this repository.

| Medicine/formulation | Kenya starting reference | Configured daily ceiling | Exact anchor |
|---|---|---|---|
| Amlodipine, single-ingredient oral tablet | 5 mg once daily | 10 mg | Table 4, printed16/PDF25 |
| Losartan, single-ingredient potassium-salt oral tablet | 50 mg once daily | 100 mg | Table 4, printed16/PDF25 |
| Lisinopril, single-ingredient oral tablet | 10 mg once daily | 40 mg | Table 4, printed16/PDF25 |
| Metformin, single-ingredient immediate-release oral tablet | 500 mg once daily | 2,000 mg, with no more than1,000 mg per administration | Section4.5, printed35/PDF44; ceiling from1g twice daily |

The API returns a manifest hash and source versions. Clinical contraindication and monitoring checklists accompany the references. [Amlodipine label](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=090f3e51-8129-4b5d-97f9-ab410e14df2d), [losartan label](https://www.dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=1bf520a2-a50e-a6ae-0fdf-9be4e69729c0), [lisinopril label](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=03a497fe-fb09-4b2c-8ee0-2019600192b8), [metformin label](https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=54bb8030-8e80-4b38-8deb-89c99d73bf09).

Important conflicts: the Kenya diabetes flowchart branches above30 for metformin, while the referenced label discourages initiation at eGFR30–45 and contraindicates below30. This implementation supplies no dose reference below60 or with known CKD; it does not choose between conflicting renal protocols. Kenya's500mg once-daily initiation and2g/day titration ceiling are retained instead of silently replacing them with the US immediate-release label's different schedule. Nifedipine's maximum is blank in the inspected table; captopril and perindopril have unit/salt or schedule ambiguities. They are deliberately absent. Automatic insulin, sulfonylurea, inhaler, diuretic, anticoagulant, oncology and paediatric dosing is not implemented.

The adult hypoglycaemia anchor was also checked visually: section4.8, printed41/PDF50 uses glucose at or below3.9mmol/L. This confirms the adult threshold already implemented; the paediatric section's different wording must not replace it.

## Population and conservative implementation policy

The first scope is uncomplicated selected adult initiation references at ages18–64, confirmed relevant diagnosis, no known CKD, eGFR at least60, no frailty, hepatic impairment, dialysis, acute illness, pregnancy or breastfeeding. Unknown context prevents a reference. Recorded allergies require individual review rather than limited string matching. Any current symptom or urgent/emergency assessment withholds elective starting-dose advice. These exclusions describe software coverage, not universal drug contraindications.

Additional conservative engineering policies: clinical observations within24hours; renal result within7days; separately dated potassium within7days and3.5–5.0mmol/L for ACE inhibitor/ARB references; blood pressure not below100 systolic or60 diastolic; exact formulation availability; complete medication schedules. These windows/limits are scope controls awaiting independent clinical/pharmacy adjudication, not falsely attributed national guideline requirements. A normal repeat cannot erase a low initial value.

The current interaction catalogue contains only these four ingredients. Other current medicines, ambiguous name/code combinations, duplicate entries, an already recorded selected medicine, or combined ACE inhibitor/ARB requests withhold the reference. Full current therapy changes are outside the initiation scope. Clinicians must explicitly attest that the medicine-specific contraindications and complete product information were reviewed and that no unresolved exclusion or interaction remains; a checkbox does not itself prove those facts. The engine does not interpret free-text notes or infer negative findings from blanks.

## Calculation and accountability

JSON inputs require finite positive numeric dose in **mg** and an integer daily frequency, either both supplied or both absent. Unknown fields/units/routes, duplicate selections and incomplete schedules are rejected. Each formulation has a stable ID. Decimal multiplication checks proposed daily exposure; no mg/microgram conversion, tablet splitting, dispensing quantity or guessed frequency occurs. A proposal outside the covered dose/frequency range is marked `outside_reference`, with no reference dose returned. That status is not a determination that every such regimen is clinically wrong.

Every result, including withholding, becomes a mandatory review item in the assessment. Changes to inputs invalidate the assessment. Review records retain the dose manifest, sources and clinician decision; modifications need a reason and replacement text. Accountable review cannot bypass the database's immutable reviewed-record controls. The frontend obtains the catalogue from the server and contains no duplicate dose calculations.

The AI adapter may select a known dose recommendation identifier, just as it selects other canonical recommendations. It receives identifiers/category/severity, never dose values or free-text clinical context, and cannot supply alternative dosage text. Unsupported dose IDs cause safe briefing fallback. Prompt version is advanced to `ncdai-briefing-select-v1.3`. The [knowledge strategy](knowledge-and-training-strategy.md) describes future controlled RAG; neither fine-tuning nor unrestricted generation is claimed here.

## Verification and remaining evaluation

`backend/tests/test_dosing_safety.py` contains explicitly authored boundary, withholding, unsafe-input, access-control and AI-output checks, plus a complete API lifecycle for every dose case. This supplements the existing66 general NCD workflows. These are engineering tests authored during development, not an independent clinical panel or patient study. Actual run results are recorded in the release verification addendum after execution.

The owner confirms DHA and ethics approval covers care and medicine recommendations, with records in office files. No additional permission is sought to implement these engineering checks. Independent clinician/pharmacist adjudication of this exact rule/source manifest, broader disease/medicine coverage, subgroup validation and supervised implementation remain substantive evidence work; the existing hosted synthetic preview is not represented as a clinically validated prescribing service.


## Acute-context revision 0.1.1

Both the general encounter's `acutely_unwell` and `acute_kidney_injury` fields must explicitly be `no` before a starting-dose reference is displayed. Existing `dosing_context.acute_illness` checks also remain required. A missing or unknown new field withholds the reference, including older draft records until reassessed. Historical reviewed records keep their original version and are not rewritten. The numerical four-medicine catalogue is unchanged; the dosing version advances because eligibility changed.
