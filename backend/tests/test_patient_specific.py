"""Statin dosing (NICE NG238), sourced acute doses, and patient-specific wording.

Expected values are transcribed from NICE NG238 recommendations (read 2026-09-19)
and the Kenya MOH NCD protocol (PDF pages 50, 61-62, 92-93), not derived from the
implementation. Engineering checks only, not clinical validation.
"""
import pytest

from app.ai import GAP_IDS, RULE_IDS
from app.clinical import assess
from test_treatment import data, med, rules


@pytest.mark.parametrize("overrides, dose", [
    (dict(known_diabetes="yes", hba1c=6.6, egfr=85), "atorvastatin 20 mg"),          # NICE 1.6.7 primary prevention
    (dict(known_ascvd="yes", egfr=85), "atorvastatin 80 mg"),                            # NICE 1.7.2 secondary prevention
    (dict(known_ascvd="yes", known_ckd="yes", egfr=50), "atorvastatin 20 mg"),           # NICE 1.8.1 CKD
])
def test_statin_start_dose_follows_nice_population(overrides, dose):
    option = rules(assess(data(**overrides), 58, "male"))["TX_STATIN_START"]
    assert option["title"] == f"Start a statin: {dose} once daily"
    assert "2-3 months" in option["detail"] and "12 months" in option["detail"]


def test_primary_prevention_target_is_computed_from_this_patients_non_hdl():
    option = rules(assess(data(known_diabetes="yes", hba1c=6.6, egfr=85, total_cholesterol_mmol=6.0, hdl_mmol=1.0), 58, "male"))["TX_STATIN_START"]
    assert "from the current 5 mmol/L that means below 3.0 mmol/L" in option["detail"]
    assert "Non-HDL 5 mmol/L (total minus HDL)" in option["basis"]


def test_statin_pregnancy_counselling_for_women_of_childbearing_age():
    option = rules(assess(data(known_diabetes="yes", hba1c=6.6, egfr=85, pregnancy_status="unknown"), 34, "female"))["TX_STATIN_START"]
    assert "confirm pregnancy status" in option["detail"] and "3 months before trying to conceive" in option["detail"]
    pregnant = rules(assess(data(pregnancy_status="yes", medications=[med("atorvastatin", 20)]), 30, "female"))
    assert "STATIN_PREGNANCY" in pregnant and "TX_STATIN_START" not in pregnant


def test_statin_optimisation_in_cardiovascular_disease():
    on_20 = rules(assess(data(known_ascvd="yes", egfr=85, ldl_mmol=3.1, medications=[med("atorvastatin", 20, frequency="nocte")]), 60, "male"))["TX_STATIN_OPTIMISE"]
    assert "Atorvastatin 20 mg daily (high intensity)" in on_20["detail"] and "atorvastatin 80 mg" in on_20["detail"]
    on_80 = rules(assess(data(known_ascvd="yes", egfr=85, ldl_mmol=2.6, medications=[med("atorvastatin", 80)]), 60, "male"))["TX_STATIN_OPTIMISE"]
    assert "ezetimibe" in on_80["detail"]
    simva = rules(assess(data(known_ascvd="yes", egfr=85, medications=[med("simvastatin", 20)]), 60, "male"))["TX_STATIN_OPTIMISE"]
    assert "medium intensity" in simva["detail"] and "atorvastatin 80 mg" in simva["detail"]
    at_target = rules(assess(data(known_ascvd="yes", egfr=85, ldl_mmol=1.8, medications=[med("atorvastatin", 80)]), 60, "male"))
    assert "TX_STATIN_OPTIMISE" not in at_target


def test_lipid_specialist_thresholds_and_aspirin_primary_prevention():
    assert "familial" in rules(assess(data(total_cholesterol_mmol=9.5), 45, "male"))["LIPID_SPECIALIST"]["detail"]
    assert "urgent specialist review" in rules(assess(data(triglycerides_mmol=22), 45, "male"))["LIPID_SPECIALIST"]["detail"]
    assert "5 days and within 2 weeks" in rules(assess(data(triglycerides_mmol=12), 45, "male"))["LIPID_SPECIALIST"]["detail"]
    assert "TX_ASPIRIN_REVIEW" in rules(assess(data(known_ascvd="no", prior_stroke_tia="no", medications=[med("aspirin", 75)]), 55, "male"))
    assert "TX_ASPIRIN_REVIEW" not in rules(assess(data(known_ascvd="yes", medications=[med("aspirin", 75)]), 55, "male"))


def test_asthma_without_inhaled_corticosteroid():
    result = rules(assess(data(known_asthma="yes", medications=[med("salbutamol", 100, unit="mcg", frequency="as needed")]), 30, "female"))
    assert "Salbutamol is recorded without an inhaled corticosteroid" in result["TX_ASTHMA_ICS"]["detail"]
    assert "budesonide-formoterol" in result["TX_ASTHMA_ICS"]["detail"]
    assert "TX_ASTHMA_ICS" not in rules(assess(data(known_asthma="yes", medications=[med("salbutamol", 100, unit="mcg"), med("beclometasone", 200, unit="mcg")]), 30, "female"))


def test_hypoglycaemia_gives_kenya_doses_and_names_the_likely_cause():
    result = rules(assess(data(known_diabetes="yes", glucose=2.8, medications=[med("gliclazide", 80, frequency="twice daily")]), 66, "female"))
    detail = result["HYPOGLYCEMIA"]["detail"]
    for text in ("15-20 g oral carbohydrate", "25 g (50 ml) of 50% dextrose", "glucagon 1 mg IM", "10% dextrose 500 ml", "Gliclazide is recorded"):
        assert text in detail


def test_rules_name_this_patients_medicines_and_values():
    low_bp = rules(assess(data(known_hypertension="yes", systolic_bp=86, diastolic_bp=54, medications=[med("amlodipine", 10), med("losartan", 100)]), 70, "male"))["LOW_BP"]
    assert "Amlodipine and Losartan" in low_bp["detail"] and "86 mmHg" in low_bp["detail"]
    potassium = rules(assess(data(potassium=5.8, medications=[med("losartan", 50)]), 60, "male"))["POTASSIUM_HIGH"]
    assert "Potassium-raising medicines recorded: Losartan" in potassium["detail"] and "within three days" in potassium["detail"]
    cancer = rules(assess(data(symptoms=["breast_lump"], symptoms_reviewed=True), 48, "female"))["CANCER_WARNING"]
    assert "refer to a surgeon" in cancer["detail"]
    severe = rules(assess(data(known_hypertension="yes", systolic_bp=186, diastolic_bp=112, medications=[med("amlodipine", 5)]), 55, "male"))["BP_SEVERE"]
    assert "recheck BP after 1 hour" in severe["detail"] and "Amlodipine" in severe["detail"]
    gaps = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=95), 50, "female"))["DATA_COMPLETENESS"]
    assert "repeat blood pressure (a raised reading must be confirmed" in gaps["detail"]


def test_care_plan_summarises_problems_medicines_and_sourced_monitoring():
    result = assess(data(known_hypertension="yes", known_diabetes="yes", systolic_bp=158, diastolic_bp=96, hba1c=8.6, egfr=52,
                         weight_kg=88, height_cm=163, medications=[med("amlodipine", 5), med("atorvastatin", 20)]), 63, "female")
    plan = result["care_plan"]
    assert plan["headline"].startswith("63-year-old woman with hypertension and type 2 diabetes on 2 recorded medicines")
    problems = {p["name"]: p for p in plan["problems"]}
    assert problems["Hypertension"]["status"] == "BP 158/96 mmHg: above target (<140/90)"
    assert problems["Type 2 diabetes"]["status"] == "HbA1c 8.6%: 1.6 above target (<7.0%)"
    assert "KDIGO G3a" in problems["Kidney function"]["status"]
    assert {"name": "Amlodipine", "dose": "5 mg once daily", "class": "Calcium channel blocker", "note": "below the Table 4 maximum of 10 mg"} in plan["medicines"]
    assert all(item["source_id"] for item in plan["monitoring"])
    assert {"item": "Blood pressure", "when": "Monthly until below 140/90 mmHg, then every 4-6 months", "source_id": "KENYA_HTN_STEPS"} in plan["monitoring"]


def test_every_new_rule_and_gap_is_known_to_the_ai_contract():
    produced, gaps = set(), set()
    for scenario in [
        dict(known_ascvd="yes", egfr=85, ldl_mmol=3.1, medications=[med("atorvastatin", 20)]),
        dict(known_diabetes="yes", hba1c=6.6, egfr=85, triglycerides_mmol=22, known_ascvd="unknown"),
        dict(known_ascvd="no", prior_stroke_tia="no", medications=[med("aspirin", 75)]),
        dict(known_asthma="yes", medications=[med("salbutamol", 100, unit="mcg")]),
        dict(pregnancy_status="yes", medications=[med("atorvastatin", 20)]),
    ]:
        result = assess(data(**scenario), 50, "female")
        produced |= {rec["rule_id"] for rec in result["recommendations"]}
        gaps |= set(result["missing_data"])
    assert produced - RULE_IDS == set() and gaps - GAP_IDS == set()
    assert "known_cvd_for_statin_choice" in gaps


def test_kdigo_category_covers_g1_to_g5():
    # KDIGO 2024 GFR categories: G1 >=90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 <15.
    for egfr, stage in ((95, "G1"), (75, "G2"), (59, "G3a"), (44, "G3b"), (29, "G4"), (12, "G5")):
        result = assess(data(known_ckd="yes", egfr=egfr), 60, "male")
        if egfr >= 30:  # below 30 the urgent renal flag replaces the routine review
            assert f"KDIGO category {stage})" in rules(result)["CKD_REVIEW"]["detail"]
        kidney = [p for p in result["care_plan"]["problems"] if p["name"] == "Kidney function"][0]
        assert f"(KDIGO {stage})" in kidney["status"]


def test_patient_summary_uses_calculated_egfr_and_converted_glucose():
    result = assess(data(creatinine_umol=300), 70, "female")
    assert any(p["name"] == "Kidney function" for p in result["care_plan"]["problems"])
    fasting = assess(data(known_diabetes="yes", glucose=180, glucose_unit="mg/dL", glucose_context="fasting"), 55, "male")
    diabetes = [p for p in fasting["care_plan"]["problems"] if p["name"] == "Type 2 diabetes"][0]
    assert diabetes["status"].startswith("Fasting glucose 10 mmol/L")


def test_prediabetes_quotes_the_measurement_in_range():
    detail = rules(assess(data(hba1c=5.0, glucose=6.0, glucose_context="fasting"), 45, "male"))["PREDIABETES"]["detail"]
    assert detail.startswith("Fasting glucose 6.0 mmol/L is in the prediabetes range")


def test_established_cvd_marks_high_cardiovascular_risk_in_bp_advice():
    detail = rules(assess(data(systolic_bp=150, diastolic_bp=92, known_ascvd="yes"), 60, "male"))["BP_REVIEW"]["detail"]
    assert "With coronary or peripheral arterial disease on record, cardiovascular risk is high." in detail


def test_treatment_options_are_only_announced_when_listed():
    at_target_repeat = rules(assess(data(known_hypertension="yes", systolic_bp=150, diastolic_bp=92, repeat_systolic_bp=132, repeat_diastolic_bp=82,
                                         medications=[med("amlodipine", 5)]), 60, "male"))
    assert "TX_HTN_STEP_UP" not in at_target_repeat and "separate recommendation" not in at_target_repeat["BP_REVIEW"]["detail"]
    unwell = rules(assess(data(known_diabetes="yes", hba1c=8.2, acutely_unwell="yes", medications=[med("metformin", 500)]), 55, "male"))
    assert not any(r.startswith("TX_") for r in unwell)
    if "DIABETES_REVIEW" in unwell:
        assert "listed separately" not in unwell["DIABETES_REVIEW"]["detail"]


def test_lipid_risk_text_keeps_unit_case():
    detail = rules(assess(data(hdl_mmol=0.8, total_cholesterol_mmol=5.0, triglycerides_mmol=3.0), 50, "female"))["LIPID_RISK_FACTOR"]["detail"]
    assert detail.startswith("HDL 0.8 mmol/L (below 0.90); Triglycerides 3 mmol/L (above 2.82).")
