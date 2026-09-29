"""Versioned, inspectable source registry. Sources are not clinical approval.

Only short bibliographic descriptions are stored; no licensed guideline corpus is
redistributed. See docs/clinical-safety-spec.md for operational adaptations.
"""

from copy import deepcopy

EVIDENCE_VERSION = "ncdai-2026-09-29.1"
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


# Consultant-reasoning sources (added 2026-09-29). Bibliographic citations with the
# specific recommendation sections the reasoning engine operationalizes. Like every
# entry above, they are proposed for independent clinician sign-off.
_CITED = "bibliographic citation added 2026-09-29; requires clinician sign-off"
SOURCES.update({item["source_id"]: item for item in [
    {"source_id": "ISH_HTN_2020", "title": "2020 International Society of Hypertension Global Hypertension Practice Guidelines (Hypertension 2020;75:1334-1357)",
     "url": "https://www.ahajournals.org/doi/10.1161/HYPERTENSIONAHA.120.15026",
     "section": "Diagnosis and classification; BP targets (<130/80 if tolerated, <140/90 in older adults); drug-treatment protocol (A+C, then A+C+D, then spironolactone); resistant hypertension",
     "version": "2020; " + _CITED},
    {"source_id": "ESC_HTN_2024", "title": "2024 ESC Guidelines for the management of elevated blood pressure and hypertension (Eur Heart J 2024;45:3912-4018)",
     "url": "https://academic.oup.com/eurheartj/article/45/38/3912/7741010",
     "section": "Section 8 treatment targets (120-129 mmHg systolic if tolerated); single-pill combination initiation; resistant hypertension and secondary-cause screening; frailty and age 85+",
     "version": "2024; " + _CITED},
    {"source_id": "ADA_SOC_2025", "title": "American Diabetes Association Standards of Care in Diabetes-2025 (Diabetes Care 2025;48 Suppl 1)",
     "url": "https://diabetesjournals.org/care/issue/48/Supplement_1",
     "section": "Sec 2 diagnosis; Sec 6 glycaemic goals and hypoglycaemia; Sec 9 pharmacological approaches (cardiorenal-protective agents independent of HbA1c); Sec 10 statin and BP; Sec 12 retinopathy and foot care; Sec 13 older adults",
     "version": "2025; " + _CITED},
    {"source_id": "KDIGO_DM_CKD_2022", "title": "KDIGO 2022 Clinical Practice Guideline for Diabetes Management in Chronic Kidney Disease (Kidney Int 2022;102(5S))",
     "url": "https://kdigo.org/wp-content/uploads/2022/10/KDIGO-2022-Clinical-Practice-Guideline-for-Diabetes-Management-in-CKD.pdf",
     "section": "Chapter 1 RAS inhibition with albuminuria and SGLT2i with eGFR >=20; Chapter 4 metformin dose adjustment by eGFR (reduce at eGFR 30-44; stop below 30)",
     "version": "2022; " + _CITED},
    {"source_id": "KDIGO_CKD_2024_TX", "title": "KDIGO 2024 guideline for evaluation and management of CKD: risk, progression and treatment",
     "url": "https://kdigo.org/wp-content/uploads/2024/03/KDIGO-2024-CKD-Guideline.pdf",
     "section": "Fig 2 GFR/albuminuria risk heat map and monitoring frequency; Rec 3.6.1 RAS inhibition for albuminuria; Rec 3.7.1 SGLT2i (T2D with eGFR >=20; CKD with ACR >=20 mg/mmol or heart failure); lipid management; 5.1 referral to specialist kidney care",
     "version": "2024; " + _CITED},
    {"source_id": "CKD_EPI_2021", "title": "Inker LA et al. New creatinine- and cystatin C-based equations to estimate GFR without race (N Engl J Med 2021;385:1737-1749)",
     "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2102953",
     "section": "2021 CKD-EPI creatinine equation (race-free), adults",
     "version": "2021; " + _CITED},
    {"source_id": "FRAMINGHAM_2008", "title": "D'Agostino RB Sr et al. General cardiovascular risk profile for use in primary care: the Framingham Heart Study (Circulation 2008;117:743-753)",
     "url": "https://www.ahajournals.org/doi/10.1161/CIRCULATIONAHA.107.699579",
     "section": "Table 2 laboratory-based and office (BMI) sex-specific 10-year general CVD models; validated age 30-74 without prior CVD",
     "version": "2008; " + _CITED + "; not recalibrated for Kenya"},
    {"source_id": "WHO_CVD_RISK_2019", "title": "WHO CVD Risk Chart Working Group. World Health Organization cardiovascular disease risk charts: revised models for 21 global regions (Lancet Glob Health 2019;7:e1332-e1345)",
     "url": "https://doi.org/10.1016/S2214-109X(19)30318-3",
     "section": "Region-specific laboratory and non-laboratory charts (Eastern sub-Saharan Africa); risk categories <10%, 10-<20%, >=20%",
     "version": "2019; " + _CITED},
    {"source_id": "WHO_HEARTS_RISK_2020", "title": "WHO HEARTS technical package: Risk-based CVD management",
     "url": "https://www.who.int/publications/i/item/9789240001367",
     "section": "Statin therapy for established CVD, diabetes age 40+, and 10-year CVD risk >=20%; aspirin for secondary prevention only",
     "version": "2020; " + _CITED},
    {"source_id": "ESC_LIPIDS_2019", "title": "2019 ESC/EAS Guidelines for the management of dyslipidaemias (Eur Heart J 2020;41:111-188)",
     "url": "https://academic.oup.com/eurheartj/article/41/1/111/5556353",
     "section": "Table 4 risk categories (diabetes with organ damage, CKD); LDL-C goals (<1.4 mmol/L very high, <1.8 high, <2.6 moderate risk); statin intensity; add ezetimibe",
     "version": "2019; " + _CITED},
    {"source_id": "ESC_DM_CVD_2023", "title": "2023 ESC Guidelines for the management of cardiovascular disease in patients with diabetes (Eur Heart J 2023;44:4043-4140)",
     "url": "https://academic.oup.com/eurheartj/article/44/39/4043/7238227",
     "section": "SGLT2 inhibitor and/or GLP-1 RA with proven CV benefit for ASCVD independent of HbA1c; SGLT2i for heart failure and CKD",
     "version": "2023; " + _CITED},
    {"source_id": "ESC_HF_2021", "title": "2021 ESC Guidelines for heart failure with 2023 focused update (Eur Heart J 2021;42:3599-3726)",
     "url": "https://academic.oup.com/eurheartj/article/42/36/3599/6358045",
     "section": "HFrEF: ACEi/ARNI, evidence-based beta-blocker, MRA and SGLT2i; drugs to avoid (NSAIDs, thiazolidinediones, non-dihydropyridine CCBs); echocardiographic classification",
     "version": "2021/2023; " + _CITED},
    {"source_id": "ESC_AF_2024", "title": "2024 ESC Guidelines for the management of atrial fibrillation (Eur Heart J 2024;45:3314-3414)",
     "url": "https://academic.oup.com/eurheartj/article/45/36/3314/7738779",
     "section": "CHA2DS2-VA score: oral anticoagulation recommended at >=2, considered at 1; DOAC preferred over VKA except mechanical valve or moderate-severe mitral stenosis; antiplatelets not for stroke prevention",
     "version": "2024; " + _CITED},
    {"source_id": "GINA_2025", "title": "Global Initiative for Asthma: Global Strategy for Asthma Management and Prevention, 2025 update",
     "url": "https://ginasthma.org/reports/",
     "section": "SABA-only treatment not recommended for adults; ICS-containing controller for all; symptom control and exacerbation-risk assessment; inhaler technique and adherence before step-up",
     "version": "2025; " + _CITED},
    {"source_id": "GOLD_2025", "title": "Global Initiative for Chronic Obstructive Lung Disease: 2025 report",
     "url": "https://goldcopd.org/2025-gold-report/",
     "section": "Spirometric confirmation; ABE assessment (E: >=2 moderate or >=1 hospitalized exacerbation); LABA+LAMA initial therapy; ICS by eosinophils; smoking cessation, vaccination, pulmonary rehabilitation, oxygen assessment",
     "version": "2025; " + _CITED},
    {"source_id": "PULSE_OXIMETRY_BIAS", "title": "Sjoding MW et al. Racial bias in pulse oximetry measurement (N Engl J Med 2020;383:2477-2478)",
     "url": "https://www.nejm.org/doi/full/10.1056/NEJMc2029240",
     "section": "Occult hypoxaemia (SaO2 <88% with SpO2 92-96%) more frequent in Black patients",
     "version": "2020; " + _CITED},
    {"source_id": "WHO_HBA1C_2011", "title": "WHO: Use of glycated haemoglobin (HbA1c) in the diagnosis of diabetes mellitus",
     "url": "https://www.who.int/publications/i/item/use-of-glycated-haemoglobin-(-hba1c)-in-diagnosis-of-diabetes-mellitus",
     "section": "HbA1c 6.5% diagnostic cut-point; conditions affecting reliability (anaemia, haemoglobinopathies, CKD, pregnancy)",
     "version": "2011; " + _CITED},
    {"source_id": "WHO_TOBACCO_2024", "title": "WHO clinical treatment guideline for tobacco cessation in adults",
     "url": "https://iris.who.int/handle/10665/377825",
     "section": "Brief health-worker advice; behavioural support; varenicline, nicotine replacement, bupropion and cytisine",
     "version": "2024 (ISBN 978-92-4-009643-1); " + _CITED},
    {"source_id": "WHO_TB_SCREENING_2021", "title": "WHO consolidated guidelines on tuberculosis: Module 2 screening - systematic screening for tuberculosis disease",
     "url": "https://www.who.int/publications/i/item/9789240022676",
     "section": "Screening of people with diabetes and other risk groups; symptom screen and rapid molecular testing",
     "version": "2021; " + _CITED},
    {"source_id": "ENDO_PA_2016", "title": "Funder JW et al. Management of primary aldosteronism: Endocrine Society clinical practice guideline (J Clin Endocrinol Metab 2016;101:1889-1916)",
     "url": "https://academic.oup.com/jcem/article/101/5/1889/2804729",
     "section": "Screen with aldosterone-renin ratio: resistant hypertension, hypertension with spontaneous or diuretic-induced hypokalaemia, early-onset hypertension",
     "version": "2016; " + _CITED},
    {"source_id": "WHO_OBESITY", "title": "WHO: Obesity and overweight fact sheet; waist circumference and waist-hip ratio report (2008)",
     "url": "https://www.who.int/news-room/fact-sheets/detail/obesity-and-overweight",
     "section": "Adult BMI classification (overweight >=25, obesity >=30); waist circumference risk thresholds",
     "version": "Live WHO guidance; " + _CITED},
]})


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
