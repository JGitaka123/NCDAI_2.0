"""Versioned, inspectable source registry. Sources are not clinical approval.

Only short bibliographic descriptions are stored; no licensed guideline corpus is
redistributed. See docs/clinical-safety-spec.md for operational adaptations.
"""

from copy import deepcopy

EVIDENCE_VERSION = "ncdai-2026-09-12.2"
REVIEW_STATUS = "proposed_requires_independent_clinician_signoff"
REVIEWED_ON = "2026-09-12"

SOURCES = {
    "WHO_HTN_2021": {
        "source_id": "WHO_HTN_2021",
        "title": "WHO: Guideline for the pharmacological treatment of hypertension in adults",
        "url": "https://www.ncbi.nlm.nih.gov/books/NBK573627/",
        "section": "3.1 thresholds; 3.2 investigations; 3.6 targets; 3.7 reassessment",
        "version": "2021; accessed 2026-09-12",
    },
    "WHO_HEARTS_D_2020": {
        "source_id": "WHO_HEARTS_D_2020",
        "title": "WHO HEARTS-D: Diagnosis and management of type 2 diabetes",
        "url": "https://iris.who.int/bitstream/handle/10665/331710/WHO-UCN-NCD-20.1-eng.pdf?sequence=1",
        "section": "2 diagnosis; 3 management and acute complications (p19); 4 referral (p26)",
        "version": "2020; accessed 2026-09-12",
    },
    "KENYA_NCD_PROTOCOLS": {
        "source_id": "KENYA_NCD_PROTOCOLS",
        "title": "Kenya Ministry of Health: Protocols for Management of Selected NCDs at Primary Care Setting",
        "url": "https://health.go.ke/sites/default/files/2025-07/FINAL_NCD%20protocols.pdf",
        "section": "4.2 diagnosis (p32); 4.5 management (p35); 4.8 acute complications (p41); 5 cancer early detection (p52)",
        "version": "MOH July 2025 hosted copy; 132 pages, no explicit edition date found; verified 2026-09-12; SHA256 e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8",
    },
    "WHO_HEARTS_MEDS_2018": {
        "source_id": "WHO_HEARTS_MEDS_2018",
        "title": "WHO HEARTS: Evidence-based treatment protocols",
        "url": "https://iris.who.int/bitstream/handle/10665/260421/WHO-NMH-NVI-18.2-eng.pdf",
        "section": "Medicine table: sulphonylurea practice points (p39)",
        "version": "2018; accessed 2026-09-12",
    },
    "NICE_DIABETES_2026": {
        "source_id": "NICE_DIABETES_2026",
        "title": "NICE NG28: Type 2 diabetes in adults; initial medicines",
        "url": "https://www.nice.org.uk/guidance/NG28/chapter/initial-medicines",
        "section": "Kidney disease: rationale concerning sulfonylurea hypoglycaemia risk",
        "version": "Updated 2026-02-18; accessed 2026-09-12",
    },
    "WHO_PEN_2020": {
        "source_id": "WHO_PEN_2020",
        "title": "WHO package of essential noncommunicable disease interventions for primary health care",
        "url": "https://iris.who.int/bitstream/handle/10665/334186/9789240009226-eng.pdf?sequence=1",
        "section": "2.3 Chronic respiratory diseases; asthma exacerbations (p35)",
        "version": "2020; accessed 2026-09-12",
    },
    "NICE_PREGNANCY": {
        "source_id": "NICE_PREGNANCY",
        "title": "NICE NG133: Hypertension in pregnancy: diagnosis and management",
        "url": "https://www.nice.org.uk/guidance/ng133/chapter/recommendations",
        "section": "1.3.2-1.3.3 ACE inhibitor/ARB review; 1.4.3 Table 1 severe hypertension",
        "version": "NG133 recommendations; accessed 2026-09-12",
    },
    "METFORMIN_LABEL": {
        "source_id": "METFORMIN_LABEL",
        "title": "DailyMed: Metformin hydrochloride prescribing information",
        "url": "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=54bb8030-8e80-4b38-8deb-89c99d73bf09",
        "section": "2.3 Renal impairment; 4 contraindications; 5.1 lactic acidosis",
        "version": "Set ID 54bb8030-8e80-4b38-8deb-89c99d73bf09; accessed 2026-09-12",
    },
    "SGLT2_LABEL": {
        "source_id": "SGLT2_LABEL",
        "title": "DailyMed: Jardiance (empagliflozin) prescribing information",
        "url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=faf3dd6a-9cd0-39c2-0d2e-232cb3f67565",
        "section": "5.1 Ketoacidosis; 5.2 volume depletion",
        "version": "Revised January 2026; accessed 2026-09-12",
    },
    "LISINOPRIL_LABEL": {
        "source_id": "LISINOPRIL_LABEL",
        "title": "DailyMed: Lisinopril prescribing information",
        "url": "https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=03a497fe-fb09-4b2c-8ee0-2019600192b8",
        "section": "5.1 fetal toxicity; 5.3 renal impairment; 5.5 potassium; 7.1, 7.3, 7.4 interactions",
        "version": "Label updated 2025-04-11; accessed 2026-09-12",
    },
    "AMLODIPINE_LABEL": {
        "source_id": "AMLODIPINE_LABEL",
        "title": "DailyMed: Amlodipine besylate tablets prescribing information",
        "url": "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=090f3e51-8129-4b5d-97f9-ab410e14df2d",
        "section": "2.1 adult dosing; 5 warnings; 7 interactions; 8 special populations",
        "version": "Set ID 090f3e51-8129-4b5d-97f9-ab410e14df2d; accessed 2026-09-12",
    },
    "LOSARTAN_LABEL": {
        "source_id": "LOSARTAN_LABEL",
        "title": "DailyMed: Losartan potassium prescribing information",
        "url": "https://www.dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=1bf520a2-a50e-a6ae-0fdf-9be4e69729c0",
        "section": "2 dosing; 4 contraindications; 5 warnings; 7 interactions",
        "version": "Set ID 1bf520a2-a50e-a6ae-0fdf-9be4e69729c0; accessed 2026-09-12",
    },
    "UKKA_POTASSIUM_2026": {
        "source_id": "UKKA_POTASSIUM_2026",
        "title": "UK Kidney Association: Management of hyperkalaemia in adults",
        "url": "https://www.ukkidney.org/health-professionals/guidelines/treatment-acute-hyperkalaemia-adults-0",
        "section": "July 2026 downloadable guideline, 1.2.1-1.2.3 and 4.1-4.2",
        "version": "July 2026 update; accessed 2026-09-12",
    },
    "RCP_NEWS2": {
        "source_id": "RCP_NEWS2",
        "title": "Royal College of Physicians: National Early Warning Score 2",
        "url": "https://www.rcp.ac.uk/media/a4ibkkbf/news2-final-report_0_0.pdf",
        "section": "Chart 1 physiological parameters; Chart 3 observation chart",
        "version": "2017 report; accessed 2026-09-12; selected parameters only, not a NEWS2 calculation",
    },
    "NHS_LOW_POTASSIUM": {
        "source_id": "NHS_LOW_POTASSIUM",
        "title": "NHS Lothian: Hypokalaemia",
        "url": "https://www.rightdecisions.scot.nhs.uk/electrolyte-disturbance/hypokalaemia/?organization=nhs-lothian",
        "section": "Think; Treat: severe and moderate; Do I need to escalate?",
        "version": "Live institutional guidance; accessed 2026-09-12",
    },
    "KDIGO_CKD_2024": {
        "source_id": "KDIGO_CKD_2024",
        "title": "KDIGO 2024 guideline for evaluation and management of chronic kidney disease",
        "url": "https://kdigo.org/wp-content/uploads/2024/03/KDIGO-2024-CKD-Guideline.pdf",
        "section": "1.1 Detection and evaluation; practice points 1.1.1.1-1.1.1.2, 1.1.3.1-1.1.3.2",
        "version": "2024; accessed 2026-09-12; focused treatment update underway",
    },
    "NCI_CANCER_SYMPTOMS": {
        "source_id": "NCI_CANCER_SYMPTOMS",
        "title": "US National Cancer Institute: Symptoms of cancer",
        "url": "https://www.cancer.gov/about-cancer/diagnosis-staging/symptoms",
        "section": "Symptoms: breast changes, bleeding, cough, weight change; diagnostic assessment",
        "version": "Live NCI guidance; accessed 2026-09-12",
    },
    "WHO_CANCER_DIAGNOSIS": {
        "source_id": "WHO_CANCER_DIAGNOSIS",
        "title": "WHO: Guide to cancer early diagnosis",
        "url": "https://www.who.int/publications/i/item/guide-to-cancer-early-diagnosis",
        "section": "Diagnostic and referral capacity; timely access to treatment",
        "version": "2017; accessed 2026-09-12",
    },
    "NCDAI_SAFETY_SPEC": {
        "source_id": "NCDAI_SAFETY_SPEC",
        "title": "NCDAI 2.0 clinical safety specification (proposed engineering policy)",
        "url": "https://github.com/JGitaka123/NCDAI_2.0/blob/6415fed12a8efa817705b653776794f3af512725/docs/clinical-safety-spec.md",
        "section": "Input semantics, conservative triage adaptations, scope, and release gates",
        "version": "0.1; 2026-09-12; NOT clinician approved",
    },
}


for _key, _section in {
    "KENYA_DOSES_HTN": "Table 4, printed page 16 (PDF page 25); selected oral antihypertensive starting and maximum doses",
    "KENYA_DOSES_DM": "4.5, printed page 35 (PDF page 44); metformin initial dose and titration ceiling; renal scope restricted by NCDAI policy",
}.items():
    SOURCES[_key] = {**SOURCES["KENYA_NCD_PROTOCOLS"], "source_id": _key, "section": _section}


def evidence(*source_ids: str) -> list[dict]:
    """Unknown source IDs are build defects, never silently dropped citations."""
    return [deepcopy(SOURCES[source_id]) for source_id in source_ids]


def registry() -> dict:
    return {
        "version": EVIDENCE_VERSION,
        "review_status": REVIEW_STATUS,
        "reviewed_on": REVIEWED_ON,
        "sources": deepcopy(list(SOURCES.values())),
    }


def is_ready() -> bool:
    """Technical completeness only: explicitly does not assert clinical readiness."""
    return bool(SOURCES) and all(
        all(item.get(key) for key in ("source_id", "title", "url", "section", "version"))
        for item in SOURCES.values()
    )
