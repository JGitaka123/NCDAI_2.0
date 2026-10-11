"""Authored checks for guideline treatment options, lipids, BMI and diagnosis thresholds.

Expected values are transcribed from the Kenya MOH NCD protocol (Table 4, PDF page 25;
steps, PDF page 20; section 4.5, PDF pages 44-45; Table 6, PDF page 41), not derived
from the implementation. Engineering checks only, not clinical validation.
"""
from datetime import datetime, timezone

import pytest

from app.ai import GAP_IDS, RULE_IDS
from app.clinical import assess
from app.evidence import SOURCES


def med(code, dose=None, unit="mg", frequency="once daily"):
    return {"code": code, "name": code.title(), "dose": dose, "unit": unit, "frequency": frequency}


def data(**overrides):
    base = dict(observed_at=datetime.now(timezone.utc).isoformat(), medications_reviewed=True, allergies_reviewed=True,
                symptoms_reviewed=True, pregnancy_status="no", known_hypertension="no", known_diabetes="no", known_asthma="no",
                known_copd="no", known_ckd="no", known_cancer="no", known_ascvd="no", prior_stroke_tia="no", acutely_unwell="no", acute_kidney_injury="no",
                adherence="taking", medicine_availability="available", glucose_unit="mmol/L", medications=[], symptoms=[], allergies=[])
    base.update(overrides)
    return base


def rules(result):
    return {rec["rule_id"]: rec for rec in result["recommendations"]}


def test_untreated_grade2_hypertension_gets_step1_combination_with_table4_doses():
    result = rules(assess(data(known_hypertension="yes", systolic_bp=168, diastolic_bp=102, repeat_systolic_bp=166, repeat_diastolic_bp=101), 50, "male"))
    option = result["TX_HTN_START"]
    assert option["category"] == "treatment"
    for text in ("amlodipine 5 mg", "losartan 50 mg", "lisinopril 10 mg", "hydrochlorothiazide 12.5 mg"):
        assert text in option["detail"]
    assert "166/101 mmHg (repeat reading)" in option["basis"][0]
    assert {e["source_id"] for e in option["evidence"]} == {"KENYA_HTN_STEPS", "KENYA_DOSES_HTN"}


def test_grade1_low_risk_allows_lifestyle_first():
    option = rules(assess(data(known_hypertension="yes", systolic_bp=148, diastolic_bp=92), 45, "female"))["TX_HTN_START"]
    assert "lifestyle management for up to 3 months" in option["detail"]


def test_monotherapy_below_maximum_suggests_second_class_or_increase():
    option = rules(assess(data(known_hypertension="yes", systolic_bp=152, diastolic_bp=94, medications=[med("amlodipine", 5)]), 55, "female"))["TX_HTN_STEP_UP"]
    assert "losartan 50 mg" in option["detail"] and "Amlodipine 5 mg once daily to up to 10 mg" in option["detail"]


def test_dual_therapy_below_maximum_increases_dose_step2():
    option = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=90, medications=[med("amlodipine", 10), med("losartan", 50)]), 55, "female"))["TX_HTN_STEP_UP"]
    assert "step 2" in option["title"] and "Losartan 50 mg once daily to up to 100 mg" in option["detail"]


def test_full_dose_dual_therapy_adds_missing_class_step3():
    option = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=90, medications=[med("amlodipine", 10), med("losartan", 100)]), 55, "female"))["TX_HTN_STEP_UP"]
    assert "step 3" in option["title"] and "hydrochlorothiazide 12.5 mg" in option["detail"]


def test_unclear_frequency_is_not_compared():
    option = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=90, medications=[med("amlodipine", 10, frequency="as directed"), med("losartan", 100)]), 55, "female"))["TX_HTN_STEP_UP"]
    assert "schedule is unclear for: Amlodipine" in option["detail"]


def test_triple_therapy_goes_to_physician_and_missed_doses_address_adherence():
    triple = [med("amlodipine", 10), med("losartan", 100), med("hydrochlorothiazide", 25)]
    assert "TX_HTN_SPECIALIST" in rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=95, medications=triple), 55, "female"))
    result = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=95, medications=triple, adherence="missed"), 55, "female"))
    assert "TX_HTN_ADHERENCE" in result and "TX_HTN_SPECIALIST" not in result


def test_controlled_bp_and_age80_threshold_withhold_step_up():
    assert not any(r.startswith("TX_HTN") for r in rules(assess(data(known_hypertension="yes", systolic_bp=132, diastolic_bp=82, medications=[med("amlodipine", 5)]), 55, "female")))
    assert not any(r.startswith("TX_HTN") for r in rules(assess(data(known_hypertension="yes", systolic_bp=146, diastolic_bp=84, medications=[med("amlodipine", 5)]), 82, "female")))


@pytest.mark.parametrize("overrides", [
    dict(pregnancy_status="yes"),
    dict(symptoms=["chest_pain"]),
    dict(acutely_unwell="yes"),
    dict(systolic_bp=190, diastolic_bp=115),
])
def test_treatment_options_withheld_in_pregnancy_acute_or_urgent_contexts(overrides):
    base = dict(known_hypertension="yes", known_diabetes="yes", systolic_bp=165, diastolic_bp=100, hba1c=9.0, egfr=80)
    base.update(overrides)
    result = rules(assess(data(**base), 50, "female"))
    assert not any(rule.startswith("TX_") for rule in result)


def test_diabetes_pathway_steps():
    first = rules(assess(data(known_diabetes="yes", hba1c=8.0, egfr=80), 50, "female"))["TX_DM_METFORMIN"]
    assert "500 mg once daily" in first["detail"] and "1 g twice daily" in first["detail"]
    borderline = rules(assess(data(known_diabetes="yes", hba1c=8.0, egfr=40), 50, "female"))["TX_DM_METFORMIN"]
    assert "advises against starting it at eGFR 30-45" in borderline["detail"]
    # An eGFR below 30 is itself an urgent finding, so every elective option is withheld.
    assert not any(r.startswith("TX_") for r in rules(assess(data(known_diabetes="yes", hba1c=8.0, egfr=25), 50, "female")))
    from app.treatment import diabetes_options
    low = diabetes_options(dict(age=50, meds=[], codes=set(), diabetic=True, renal_disease=False, cvd=False, egfr=25,
                                hba1c=8.0, glucose=None, glucose_timing="unknown", weight=None, adherence="taking", tobacco="never"))
    assert "contraindicated" in low[0]["detail"] and "SGLT2" in low[0]["detail"]
    second = rules(assess(data(known_diabetes="yes", hba1c=8.0, egfr=80, medications=[med("metformin", 1000, frequency="twice daily")]), 62, "female"))["TX_DM_INTENSIFY"]
    assert "gliclazide 40-160 mg" in second["detail"] and "glimepiride 1-4 mg" in second["detail"] and "Avoid glibenclamide" in second["detail"]
    third = rules(assess(data(known_diabetes="yes", hba1c=8.5, egfr=80, weight_kg=90,
                              medications=[med("metformin", 1000, frequency="twice daily"), med("gliclazide", 80, frequency="twice daily")]), 50, "female"))["TX_DM_INTENSIFY"]
    assert "pioglitazone 15-30 mg" in third["detail"] and "9-18 units" in third["detail"]
    insulin = rules(assess(data(known_diabetes="yes", hba1c=8.5, egfr=80, medications=[med("metformin", 1000), med("insulin_nph", 20, unit="units")]), 50, "female"))
    assert "TX_DM_INSULIN" in insulin and "2-4 units every 3 days" in insulin["TX_DM_INSULIN"]["detail"]


def test_diabetes_at_target_has_no_intensification_but_cardiorenal_sglt2_note():
    result = rules(assess(data(known_diabetes="yes", known_ascvd="yes", hba1c=6.6, egfr=70, medications=[med("metformin", 500)]), 55, "male"))
    assert "TX_DM_INTENSIFY" not in result and "TX_DM_CARDIORENAL" in result


def test_fasting_glucose_threshold_and_random_prompts_fbs():
    fasting = rules(assess(data(glucose=7.1, glucose_context="fasting"), 45, "male"))
    assert "DIABETES_CONFIRM" in fasting and "Fasting glucose 7.1" in fasting["DIABETES_CONFIRM"]["detail"]
    assert "DIABETES_CONFIRM" not in rules(assess(data(glucose=7.1, glucose_context="random"), 45, "male"))
    random = rules(assess(data(glucose=12.0, glucose_context="random"), 45, "male"))["DIABETES_CONFIRM"]
    assert "fasting blood sugar" in random["detail"]
    prediabetes = rules(assess(data(glucose=6.2, glucose_context="fasting"), 45, "male"))
    assert "PREDIABETES" in prediabetes
    assert "glucose_context" in assess(data(glucose=8.0), 45, "male")["missing_data"]


def test_statin_indication_lipids_and_weight():
    diabetic = rules(assess(data(known_diabetes="yes", hba1c=6.5, egfr=90), 50, "female"))
    assert "TX_STATIN_START" in diabetic and "atorvastatin 20 mg" in diabetic["TX_STATIN_START"]["detail"]
    assert "TX_STATIN_START" not in rules(assess(data(known_diabetes="yes", hba1c=6.5, egfr=90, medications=[med("atorvastatin", 20)]), 50, "female"))
    assert "TX_STATIN_START" in rules(assess(data(total_cholesterol_mmol=8.2), 50, "female"))
    assert "LIPID_RISK_FACTOR" in rules(assess(data(hdl_mmol=0.8), 50, "female"))
    result = assess(data(known_hypertension="yes", systolic_bp=128, diastolic_bp=80, weight_kg=90, height_cm=160), 50, "female")
    assert result["derived"] == {"bmi": 35.2, "bmi_category": "obesity"}
    assert rules(result)["WEIGHT_MANAGEMENT"]["title"].startswith("Obesity")
    assert "WEIGHT_MANAGEMENT" in rules(assess(data(waist_cm=101), 50, "male"))
    gaps = assess(data(known_hypertension="yes", systolic_bp=128, diastolic_bp=80), 50, "female")["missing_data"]
    assert {"lipid_profile", "weight_and_height"} <= set(gaps)


def test_recommendations_show_values_and_page_anchored_sources():
    result = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=95), 50, "female"))
    assert "BP 150/95 mmHg" in result["BP_REVIEW"]["basis"]
    assert SOURCES["KENYA_DOSES_HTN"]["url"].endswith("#page=25")
    assert SOURCES["KENYA_DM_TREATMENT"]["url"].endswith("#page=44")


def test_every_new_rule_and_gap_is_selectable_by_ai_contract():
    produced, gaps = set(), set()
    scenarios = [
        dict(known_hypertension="yes", known_diabetes="yes", systolic_bp=168, diastolic_bp=102, hba1c=9.0, egfr=80, weight_kg=95, height_cm=165, glucose=8.0),
        dict(known_hypertension="yes", systolic_bp=150, diastolic_bp=95, medications=[med("amlodipine", 10), med("losartan", 100), med("chlorthalidone", 50)]),
        dict(known_hypertension="yes", systolic_bp=150, diastolic_bp=95, medications=[med("amlodipine", 5)], adherence="missed"),
        dict(known_diabetes="yes", known_ascvd="yes", hba1c=6.5, egfr=70, medications=[med("metformin", 500), med("atorvastatin", 20)]),
        dict(known_diabetes="yes", hba1c=9.0, egfr=70, medications=[med("metformin", 500), med("insulin", 10, unit="units")]),
        dict(hba1c=6.0, hdl_mmol=0.7),
    ]
    for scenario in scenarios:
        result = assess(data(**scenario), 50, "female")
        produced |= {rec["rule_id"] for rec in result["recommendations"]}
        gaps |= set(result["missing_data"])
    assert produced - RULE_IDS == set()
    assert gaps - GAP_IDS == set()
