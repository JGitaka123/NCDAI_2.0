"""Consultant synthesis: derived measures, guideline steps and safety boundaries.

Reference values come from the published equations (CKD-EPI 2021, Framingham
2008) and guideline thresholds, not from the implementation's own constants.
"""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.clinical import assess
from app.reasoning import a_stage, ckd_epi_2021, framingham, g_stage
from app.schemas import ClinicalData


def complete(**changes):
    data = {
        "systolic_bp": 120, "diastolic_bp": 75, "pulse": 72, "respiratory_rate": 16, "oxygen_saturation": 98,
        "pregnancy_status": "not_applicable", "known_hypertension": "no", "known_diabetes": "no",
        "known_asthma": "no", "known_copd": "no", "known_ckd": "no", "known_cancer": "no",
        "medications": [], "allergies": [], "symptoms": [], "medications_reviewed": True,
        "allergies_reviewed": True, "symptoms_reviewed": True, "medicine_availability": "available",
        "adherence": "taking", "tobacco_use": "never", "glucose_unit": "mmol/L",
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    data.update(changes)
    return data


def meds(*names, **doses):
    return [{"code": name, "name": name.title(), **({"dose": doses[name], "unit": "mg"} if name in doses else {})} for name in names]


def consult(age=55, sex="male", **changes):
    return assess(complete(**changes), age, sex)["consultant"]


def problem(result, pid):
    return next(entry for entry in result["problems"] if entry["id"] == pid)


def plan_text(result, pid):
    return " ".join(step["text"] for step in problem(result, pid)["plan"])


def test_ckd_epi_2021_reference_points():
    # Published 2021 equation values: creatinine 1.0 mg/dL (88.4 µmol/L).
    assert ckd_epi_2021(88.4, 50, "male") == pytest.approx(91.7, abs=0.5)
    assert ckd_epi_2021(88.4, 60, "female") == pytest.approx(64.5, abs=0.5)
    assert ckd_epi_2021(88.4, 60, "other") is None


def test_kdigo_stage_boundaries():
    assert [g_stage(v) for v in (90, 89.9, 60, 45, 44.9, 30, 15, 14.9)] == ["G1", "G2", "G2", "G3a", "G3b", "G3b", "G4", "G5"]
    assert [a_stage(v) for v in (2.9, 3, 30, 30.1)] == ["A1", "A2", "A2", "A3"]


def test_framingham_behaves_like_the_published_model():
    base = framingham("male_lipid", 50, 130, False, False, False, tc=200 / 38.67, hdl=45 / 38.67)
    assert base == pytest.approx(0.092, abs=0.003)
    assert framingham("male_lipid", 50, 130, False, True, False, tc=200 / 38.67, hdl=45 / 38.67) > base
    assert framingham("male_lipid", 50, 130, True, False, False, tc=200 / 38.67, hdl=45 / 38.67) > base
    assert framingham("female_lipid", 50, 130, False, False, False, tc=200 / 38.67, hdl=45 / 38.67) < base


@pytest.mark.parametrize("tobacco", [None, "unknown"])
@pytest.mark.parametrize("measurements", [dict(total_cholesterol_mmol=5.5, hdl_mmol=1.2), dict(weight_kg=80, height_cm=175)])
def test_missing_tobacco_withholds_numeric_risk(tobacco, measurements):
    result = consult(50, tobacco_use=tobacco, **measurements)
    assert result["cardiovascular_risk"] is None
    assert any(gap["field"] == "tobacco_use" for gap in result["data_gaps"])


def test_missing_tobacco_preserves_established_disease_risk():
    result = consult(50, tobacco_use="unknown", known_diabetes="yes", total_cholesterol_mmol=5.5, hdl_mmol=1.2)
    assert result["cardiovascular_risk"]["category"] == "high"
    assert result["cardiovascular_risk"]["percent"] is None


@pytest.mark.parametrize("tobacco", [None, "unknown", "absent"])
def test_unestimated_risk_does_not_claim_statin_target_met(tobacco):
    data = complete(systolic_bp=135, diastolic_bp=80, known_hypertension="yes",
                    total_cholesterol_mmol=6, hdl_mmol=1, ldl_mmol=3,
                    medications=meds("atorvastatin"), tobacco_use=tobacco)
    if tobacco == "absent":
        data.pop("tobacco_use")
    result = assess(data, 70, "male")["consultant"]
    lipids = problem(result, "cv_prevention")
    assert result["cardiovascular_risk"] is None
    assert lipids["status"] == "needs_data"
    assert not lipids["targets"]
    text = plan_text(result, "cv_prevention")
    assert "no target is established" in text
    assert "Continue the statin; recheck lipids annually" not in text


def test_established_diabetes_still_judges_statin_against_existing_goal():
    result = consult(70, tobacco_use="unknown", known_diabetes="yes",
                     ldl_mmol=3, medications=meds("atorvastatin"))
    assert problem(result, "cv_prevention")["status"] == "above_target"


@pytest.mark.parametrize("changes,category", [
    ({"known_ascvd": "yes"}, "very high"),
    ({"known_diabetes": "yes"}, "high"),
    ({"egfr": 25}, "very high"), ({"egfr": 50}, "high"),
    ({"total_cholesterol_mmol": 8.5}, "high"),
])
def test_missing_tobacco_preserves_disease_based_targets(changes, category):
    result = consult(45, tobacco_use="unknown", systolic_bp=150, diastolic_bp=95,
                     known_hypertension="yes", ldl_mmol=3, medications=meds("atorvastatin"), **changes)
    assert result["cardiovascular_risk"]["category"] == category
    assert problem(result, "cv_prevention")["status"] == "above_target"
    assert problem(result, "cv_prevention")["targets"]
    assert any("<130/80" in target for target in problem(result, "hypertension")["targets"])


@pytest.mark.parametrize("sex", ["female", "male"])
@pytest.mark.parametrize("measurements", [dict(total_cholesterol_mmol=6, hdl_mmol=1), dict(weight_kg=80, height_cm=175)])
def test_missing_tobacco_does_not_create_risk_based_statin_start(sex, measurements):
    result = consult(70, sex, tobacco_use="unknown", systolic_bp=135, diastolic_bp=80,
                     known_hypertension="yes", **measurements)
    assert result["cardiovascular_risk"] is None
    assert not any(entry["id"] == "cv_prevention" for entry in result["problems"])
    assert any(gap["field"] == "tobacco_use" for gap in result["data_gaps"])


@pytest.mark.parametrize("tobacco", ["never", "former", "current"])
def test_known_tobacco_keeps_numeric_risk(tobacco):
    result = consult(50, tobacco_use=tobacco, total_cholesterol_mmol=5.5, hdl_mmol=1.2)
    assert result["cardiovascular_risk"]["percent"] is not None


def test_creatinine_derives_egfr_for_safety_rules_but_entered_egfr_wins():
    calculated = assess(complete(creatinine_umol=300, known_diabetes="yes", medications=meds("metformin")), 70, "female")
    rules = {rec["rule_id"] for rec in calculated["recommendations"]}
    assert {"METFORMIN_RENAL", "RENAL_SEVERE"} <= rules
    assert any("CKD-EPI 2021" in warning for warning in calculated["warnings"])
    entered = assess(complete(creatinine_umol=300, egfr=75, known_diabetes="yes", medications=meds("metformin")), 70, "female")
    assert "METFORMIN_RENAL" not in {rec["rule_id"] for rec in entered["recommendations"]}


def test_multimorbidity_plan_is_patient_specific():
    result = consult(58, "male", systolic_bp=162, diastolic_bp=98, repeat_systolic_bp=158, repeat_diastolic_bp=96,
                     known_hypertension="yes", known_diabetes="yes", hba1c=9.2, creatinine_umol=130,
                     urine_acr_mg_mmol=12, potassium=4.3, tobacco_use="current", weight_kg=92, height_cm=172,
                     total_cholesterol_mmol=5.6, hdl_mmol=1.0, ldl_mmol=3.4, medications=meds("amlodipine", "metformin", "ibuprofen"))
    assert result["one_liner"].startswith("58-year-old man with hypertension and diabetes, current smoker.")
    assert "BP 160/97 mmHg" in result["one_liner"]
    derived = {entry["id"]: entry for entry in result["derived"]}
    assert derived["kdigo"]["value"] == "G3aA2" and "high" in derived["kdigo"]["interpretation"]
    assert derived["hba1c_ifcc"]["value"] == "77"
    htn = problem(result, "hypertension")
    assert htn["status"] == "uncontrolled" and htn["targets"][0].startswith("<130/80")
    assert "Add an ACE inhibitor or ARB as the second class" in plan_text(result, "hypertension")
    assert "SGLT2 inhibitor for chronic kidney disease" in plan_text(result, "diabetes")
    assert "high-intensity statin" in plan_text(result, "cv_prevention")
    assert any(entry["id"] == "nsaid" for entry in result["medication_review"])
    assert [entry["rank"] for entry in result["problems"]] == list(range(1, len(result["problems"]) + 1))
    assert {source["source_id"] for source in result["sources"]} >= {"KDIGO_CKD_2024_TX", "ADA_SOC_2025", "ISH_HTN_2020"}


def test_undiagnosed_bp_uses_diagnostic_threshold_not_treatment_target():
    result = consult(52, systolic_bp=128, diastolic_bp=82, total_cholesterol_mmol=5.9, hdl_mmol=1.1, tobacco_use="current")
    assert problem(result, "hypertension")["status"] == "at_risk"
    confirmed = consult(52, systolic_bp=150, diastolic_bp=92)
    assert problem(confirmed, "hypertension")["status"] == "unconfirmed"
    assert "Confirm the diagnosis" in plan_text(confirmed, "hypertension")


def test_hypertension_escalation_follows_the_combination_sequence():
    two = consult(60, systolic_bp=150, diastolic_bp=90, known_hypertension="yes", medications=meds("amlodipine", "losartan"))
    assert "adding thiazide-like diuretic" in plan_text(two, "hypertension")
    resistant = consult(60, systolic_bp=150, diastolic_bp=90, known_hypertension="yes", potassium=4.1, egfr=70,
                        medications=meds("amlodipine", "losartan", "indapamide"))
    text = plan_text(resistant, "hypertension")
    assert "resistant hypertension" in text and "spironolactone (potassium 4.1" in text
    high_k = consult(60, systolic_bp=150, diastolic_bp=90, known_hypertension="yes", potassium=4.9, egfr=70,
                     medications=meds("amlodipine", "losartan", "indapamide"))
    assert "needs potassium ≤4.5" in plan_text(high_k, "hypertension")


def test_young_hypokalaemic_hypertension_prompts_secondary_screen():
    result = consult(32, systolic_bp=168, diastolic_bp=104, potassium=3.1)
    ids = {entry["id"] for entry in result["considerations"]}
    assert {"secondary_htn_young", "primary_aldosteronism"} <= ids


def test_older_adult_on_sulfonylurea_is_de_intensified():
    result = consult(79, "female", known_diabetes="yes", hba1c=6.2, egfr=40, hypoglycaemia_episodes_3m=2,
                     medications=meds("glibenclamide"))
    dm = problem(result, "diabetes")
    assert dm["status"] == "review" and dm["targets"][0].startswith("HbA1c <8.0%")
    assert "De-intensify" in plan_text(result, "diabetes")
    assert any(entry["id"] == "hypoglycaemia_risk" for entry in result["medication_review"])


def test_metformin_dose_ceiling_at_egfr_30_to_44():
    result = consult(64, known_diabetes="yes", hba1c=7.5, egfr=38, medications=meds("metformin"))
    assert "maximum of 1000 mg/day" in plan_text(result, "diabetes")


def test_atrial_fibrillation_cha2ds2_va_and_aspirin():
    result = consult(76, "female", known_atrial_fibrillation="yes", known_hypertension="yes", known_heart_failure="yes",
                     prior_stroke_tia="no", known_ascvd="no", systolic_bp=128, diastolic_bp=76, medications=meds("aspirin"))
    score = next(entry for entry in result["derived"] if entry["id"] == "cha2ds2_va")
    assert score["value"] == "4"  # HF 1 + hypertension 1 + age ≥75 2; female sex no longer scores
    text = plan_text(result, "atrial_fibrillation")
    assert "anticoagulation is recommended" in text and "rheumatic mitral stenosis" in text and "Aspirin alone" in text


def test_heart_failure_pillars_and_harmful_drugs():
    result = consult(66, known_heart_failure="yes", known_diabetes="yes", hba1c=7.0,
                     medications=meds("enalapril", "pioglitazone", "diltiazem"))
    assert "1 of 4" in problem(result, "heart_failure")["assessment"]
    review_ids = {entry["id"] for entry in result["medication_review"]}
    assert {"tzd_hf", "nondhp_hf"} <= review_ids


def test_asthma_saba_only_and_non_selective_beta_blocker():
    result = consult(34, "female", known_asthma="yes", reliever_use_per_week=5, medications=meds("salbutamol", "propranolol"))
    assert "SABA-only treatment is not recommended" in plan_text(result, "asthma")
    assert any(entry["id"] == "bb_asthma" and entry["severity"] == "high" for entry in result["medication_review"])


def test_copd_group_e_and_ics_monotherapy():
    result = consult(67, known_copd="yes", exacerbations_past_year=3, tobacco_use="former", medications=meds("salbutamol", "beclometasone"))
    text = plan_text(result, "copd")
    assert "GOLD E" in text and "ICS without a long-acting bronchodilator" in text


def test_triple_whammy_and_angioedema():
    result = consult(60, known_hypertension="yes", systolic_bp=130, diastolic_bp=80, allergies=["Enalapril - angioedema"],
                     medications=meds("lisinopril", "hydrochlorothiazide", "diclofenac"))
    review_ids = {entry["id"] for entry in result["medication_review"]}
    assert {"triple_whammy", "acei_angioedema"} <= review_ids


def test_pregnancy_withholds_chronic_treatment_reasoning():
    result = consult(29, "female", pregnancy_status="yes", systolic_bp=150, diastolic_bp=95, known_diabetes="yes", hba1c=8.5,
                     medications=meds("losartan", "atorvastatin"))
    assert [entry["id"] for entry in result["problems"]] == ["pregnancy"]
    assert result["acute_first"] is True


def test_emergency_keeps_acute_priority_and_does_not_change_urgency():
    data = complete(systolic_bp=210, diastolic_bp=125, symptoms=["severe_headache"], known_hypertension="yes")
    original = deepcopy(data)
    result = assess(data, 61, "male")
    assert data == original
    assert result["urgency"] == "emergency"
    assert result["consultant"]["acute_first"] and result["consultant"]["impression"].startswith("Acute findings take priority")
    assert problem(result["consultant"], "hypertension")["status"] == "acute"


def test_unknown_inputs_become_data_gaps_not_assumptions():
    result = consult(58, systolic_bp=150, diastolic_bp=92, known_hypertension="yes", known_diabetes="yes", tobacco_use="unknown")
    fields = {entry["field"] for entry in result["data_gaps"]}
    assert {"hba1c", "urine_acr_mg_mmol", "tobacco_use"} <= fields
    assert problem(result, "diabetes")["status"] == "needs_data"


def test_every_cited_source_exists_and_summary_is_complete():
    result = consult(58, "male", systolic_bp=150, diastolic_bp=95, known_hypertension="yes", known_diabetes="yes", hba1c=8.1, egfr=50)
    cited = {sid for entry in result["problems"] for sid in entry["source_ids"]}
    assert cited <= {source["source_id"] for source in result["sources"]}
    assert "Follow-up:" in result["summary_text"] and "not a prescription" in result["summary_text"]


def test_schema_accepts_consultant_fields_and_rejects_implausible_lipids():
    ClinicalData.model_validate(complete(weight_kg=80, height_cm=170, total_cholesterol_mmol=5, hdl_mmol=1.2, exacerbations_past_year=2))
    with pytest.raises(ValidationError):
        ClinicalData.model_validate(complete(total_cholesterol_mmol=4, hdl_mmol=4.5))
    with pytest.raises(ValidationError):
        ClinicalData.model_validate(complete(exacerbations_past_year=1.5))


def test_api_assessment_carries_synthesis_into_review_and_fhir(client):
    import base64
    from conftest import assess as api_assess, encounter as api_encounter, review_payload
    record = api_assess(client, api_encounter(client, {"systolic_bp": 158, "diastolic_bp": 96, "known_hypertension": "yes",
                                                     "creatinine_umol": 120, "weight_kg": 84, "height_cm": 165,
                                                     "medications": [{"code": "amlodipine", "name": "Amlodipine"}]}))
    synthesis = record["assessment"]["consultant"]
    assert synthesis["version"].startswith("ncdai-consultant-")
    assert any(entry["id"] == "egfr_ckd_epi" for entry in synthesis["derived"])
    reviewed = client.post(f"/api/encounters/{record['id']}/review", json=review_payload(record))
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review"]["assessment_snapshot"]["consultant"] == synthesis
    bundle = client.get(f"/api/fhir/Bundle/{record['id']}").json()
    document = next(e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "DocumentReference")
    text = base64.b64decode(document["content"][0]["attachment"]["data"]).decode()
    assert "Consultant synthesis" in text and synthesis["one_liner"] in text
