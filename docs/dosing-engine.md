# Bounded Kenya medicine-reference engine

Version `ncdai-dose-reference-0.1.0` · 12 September 2026

This extension supplies selected adult oral starting-dose references and checks a clinician-entered dose against the configured reference. It does not select a drug, issue a prescription, prescribe a titration schedule, calculate renal/weight adjustments or establish that a proposed regimen is clinically appropriate. Reviewed output is an immutable decision record; FHIR export remains a document and observations, not a medication order.

## Source verification and supported medicines

The Kenya Ministry of Health [Protocols for Management of Selected NCDs at Primary Care Setting](https://health.go.ke/sites/default/files/2025-07/FINAL_NCD%20protocols.pdf) was downloaded from the ministry, text-extracted and relevant pages visually inspected. The downloaded PDF is 5,599,713 bytes, 132 pages, SHA256 `e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8`. An explicit edition date was not found in the opening pages; July 2025 is its hosting path, not an asserted publication date. The complete PDF is retained privately for source review and not redistributed in this repository.

| Medicine/formulation | Kenya starting reference | Configured daily ceiling | Exact anchor |
|---|---|---|---|
| Amlodipine, single-ingredient oral tablet | 5 mg once daily | 10 mg | Table 4, printed16/PDF25 |
| Losartan, single-ingredient potassium-salt oral tablet | 50 mg once daily | 100 mg | Table 4, printed16/PDF25 |
| Lisinopril, single-ingredient oral tablet | 10 mg once daily | 40 mg | Table 4, printed16/PDF25 |
| Metformin, single-ingredient immediate-release oral tablet | 500 mg once daily | 2,000 mg, with no more than1,000 mg per administration | Section4.5, printed35/PDF44; ceiling from1g twice daily |
| Felodipine, single-ingredient prolonged-release tablet | 5 mg once daily | 10 mg | Table 4, printed16/PDF25 |
| Hydrochlorothiazide, single-ingredient tablet | 12.5 mg once daily | 25 mg | Table 4, printed16/PDF25 |
| Chlorthalidone, single-ingredient tablet | 25 mg once daily | 50 mg | Table 4, printed16/PDF25 |
| Indapamide, single-ingredient 2.5 mg immediate-release tablet | 2.5 mg once daily | 5 mg | Table 4, printed16/PDF25 |
| Ramipril, single-ingredient capsule or tablet | 2.5 mg once daily | 10 mg | Table 4, printed16/PDF25 |
| Candesartan cilexetil, single-ingredient tablet | 8 mg once daily | 32 mg | Table 4, printed16/PDF25 |
| Irbesartan, single-ingredient tablet | 150 mg once daily | 300 mg | Table 4, printed16/PDF25 |
| Telmisartan, single-ingredient tablet | 40 mg once daily | 80 mg | Table 4, printed16/PDF25 |
| Valsartan, single-ingredient tablet | 80 mg once daily | 160 mg | Table 4, printed16/PDF25 |

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


## Catalogue expansion and treatment options, revision 0.2.0 (17 September 2026)

Clinician feedback from supervised testing was that the section's purpose was unclear and that four medicines were too few. The section is renamed **Starting-dose check**, states its purpose and three steps in the interface, lists the medicines it covers, and shows a live checklist of the intake prerequisites (the server still makes every eligibility decision and explains each withheld reference).

Nine further Table 4 rows were added after re-verifying the same PDF (SHA256 `e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8`) on 17 September 2026: felodipine, hydrochlorothiazide, chlorthalidone, indapamide 2.5 mg, ramipril, candesartan, irbesartan, telmisartan and valsartan. Enalapril (range given as divided doses), captopril (divided schedule), perindopril (two salt-dependent strengths) and nifedipine (no maximum printed) remain excluded because a single unambiguous once-daily start and maximum cannot be transcribed. Gliclazide, glimepiride and pioglitazone appear in the treatment options as protocol text with their printed ranges, but are not dose-reference entries because the protocol does not state their formulation and frequency.

The potassium and dual-therapy gates now apply by ingredient class rather than by two hard-coded medicine IDs: every ACE inhibitor, ARB and thiazide-type entry requires a separately dated potassium of 3.5-5.0 mmol/L within seven days, and a RAS reference is withheld when any ACE inhibitor or ARB is already recorded or a second RAS medicine is requested. The catalogue version advances to `ncdai-dose-reference-0.2.0` and the manifest hash changes accordingly.

Separately, `backend/app/treatment.py` introduces **guideline treatment options** (`TX_*`). Unlike this starting-dose module, they are not gated on the full elective-initiation checklist: they name the medicines and Kenya doses that the protocol's step chart indicates for a patient whose diagnosis is recorded and whose readings are above target, and are withheld in urgent, emergency, acutely unwell and pregnancy contexts. They remain mandatory review items, carry no prescribing authority, and require the same independent clinical and pharmacy adjudication as every other rule before clinical reliance.
