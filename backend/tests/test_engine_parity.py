"""The offline mobile engine (frontend/mobile/engine.js) must match the backend.

Runs identical cases through Python and the JavaScript port and requires
identical safety findings, urgency and consultant synthesis. Cases: the frozen
66-case catalogue, targeted multimorbidity scenarios and a seeded random fuzz
across every structured field. Skips only when Node.js is unavailable.
"""

import json
import pathlib
import random
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from app.clinical import assess

ROOT = pathlib.Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for the mobile engine parity check")

MEDICINES = ["metformin", "insulin", "glibenclamide", "gliclazide", "empagliflozin", "dapagliflozin", "sitagliptin", "liraglutide",
             "pioglitazone", "lisinopril", "enalapril", "losartan", "valsartan", "amlodipine", "nifedipine", "diltiazem",
             "hydrochlorothiazide", "indapamide", "furosemide", "spironolactone", "bisoprolol", "carvedilol", "propranolol",
             "atorvastatin", "rosuvastatin", "simvastatin", "aspirin", "clopidogrel", "warfarin", "rivaroxaban", "apixaban",
             "digoxin", "prednisolone", "salbutamol", "budesonide", "beclometasone", "formoterol", "tiotropium",
             "budesonide_formoterol", "ibuprofen", "diclofenac", "methyldopa", "hydralazine", "ferrous_sulfate"]
SYMPTOMS = ["chest_pain", "breathlessness", "neurological_deficit", "confusion", "seizure", "severe_headache", "visual_disturbance",
            "vomiting", "dehydration", "foot_ulcer", "hypoglycemia_symptoms", "wheeze", "hemoptysis", "unexplained_weight_loss",
            "persistent_cough", "breast_lump", "abnormal_bleeding"]
TRI = ["yes", "no", "unknown"]


def maybe(rng, probability, value):
    return value() if rng.random() < probability else None


def random_case(rng):
    now = datetime.now(timezone.utc)
    sex = rng.choice(["female", "male", "male", "female", "other"])
    age = rng.randint(18, 95)
    systolic = maybe(rng, 0.85, lambda: rng.randint(85, 220))
    data = {
        "systolic_bp": systolic, "diastolic_bp": None if systolic is None else rng.randint(45, min(systolic - 5, 130)),
        "pulse": maybe(rng, 0.6, lambda: rng.randint(38, 150)),
        "oxygen_saturation": maybe(rng, 0.5, lambda: rng.choice([rng.randint(84, 100), round(rng.uniform(85, 99), 1)])),
        "respiratory_rate": maybe(rng, 0.4, lambda: rng.randint(6, 34)),
        "hba1c": maybe(rng, 0.6, lambda: round(rng.uniform(4.8, 13.5), 1)),
        "egfr": maybe(rng, 0.4, lambda: round(rng.uniform(8, 120), 1)),
        "creatinine_umol": maybe(rng, 0.4, lambda: rng.randint(45, 600)),
        "urine_acr_mg_mmol": maybe(rng, 0.4, lambda: round(rng.uniform(0.2, 90), 1)),
        "potassium": maybe(rng, 0.5, lambda: round(rng.uniform(2.4, 7.0), 1)),
        "weight_kg": maybe(rng, 0.5, lambda: round(rng.uniform(40, 140), 1)),
        "height_cm": maybe(rng, 0.5, lambda: rng.randint(145, 195)),
        "waist_cm": maybe(rng, 0.3, lambda: rng.randint(65, 140)),
        "total_cholesterol_mmol": maybe(rng, 0.45, lambda: round(rng.uniform(3.0, 9.0), 1)),
        "hdl_mmol": maybe(rng, 0.45, lambda: round(rng.uniform(0.6, 2.2), 1)),
        "ldl_mmol": maybe(rng, 0.4, lambda: round(rng.uniform(1.0, 6.0), 1)),
        "hemoglobin_g_dl": maybe(rng, 0.3, lambda: round(rng.uniform(7, 16), 1)),
        "glucose_context": rng.choice(["fasting", "random", "unknown"]),
        "exacerbations_past_year": maybe(rng, 0.3, lambda: rng.randint(0, 4)),
        "reliever_use_per_week": maybe(rng, 0.3, lambda: rng.randint(0, 10)),
        "hypoglycaemia_episodes_3m": maybe(rng, 0.3, lambda: rng.randint(0, 3)),
        "eye_screen": rng.choice(["within_12_months", "over_12_months", "never", "unknown"]),
        "foot_exam": rng.choice(["within_12_months", "over_12_months", "never", "unknown"]),
        "tobacco_use": rng.choice(["unknown", "current", "former", "never"]),
        "adherence": rng.choice(["taking", "missed", "unknown"]),
        "medicine_availability": rng.choice(["available", "limited", "unknown"]),
        "pregnancy_status": rng.choice(["no", "unknown", "not_applicable"]) if sex != "female" or age > 50 or rng.random() > 0.15 else "yes",
        "symptoms": rng.sample(SYMPTOMS, rng.choice([0, 0, 0, 1, 2])),
        "allergies": rng.choice([[], [], ["enalapril - angioedema"], ["aspirin"], ["penicillin rash"]]),
        "medications": [{"code": code, "name": code.replace("_", "/").title(), **({"dose": float(rng.choice([10, 20, 40, 80])), "unit": "mg", "frequency": "once daily"} if rng.random() < 0.5 else {})}
                        for code in rng.sample(MEDICINES, rng.choice([0, 1, 2, 3, 4, 5]))],
        "medications_reviewed": rng.random() < 0.8, "allergies_reviewed": rng.random() < 0.8, "symptoms_reviewed": rng.random() < 0.8,
        "observed_at": rng.choice([None, (now - timedelta(hours=1)).isoformat(), (now - timedelta(hours=30)).isoformat()]),
        "dosing_context": {"frailty": rng.choice(["yes", "no", "unknown"])},
    }
    if data["systolic_bp"] and rng.random() < 0.5:
        data["repeat_systolic_bp"] = max(data["systolic_bp"] + rng.randint(-15, 10), data["diastolic_bp"] + 6)
        data["repeat_diastolic_bp"] = data["diastolic_bp"] + rng.randint(-5, 3)
    if rng.random() < 0.5:
        data["glucose"], data["glucose_unit"] = (round(rng.uniform(2.5, 25), 1), "mmol/L") if rng.random() < 0.8 else (rng.randint(50, 450), "mg/dL")
    if data["hdl_mmol"] is not None and data["total_cholesterol_mmol"] is not None and data["hdl_mmol"] >= data["total_cholesterol_mmol"]:
        data["hdl_mmol"] = None
    for field in ("known_hypertension", "known_diabetes", "known_asthma", "known_copd", "known_ckd", "known_cancer", "known_ascvd",
                  "prior_stroke_tia", "known_heart_failure", "known_atrial_fibrillation", "acutely_unwell", "acute_kidney_injury"):
        data[field] = rng.choice(TRI + ["no", "yes"])
    return {"data": {k: v for k, v in data.items() if v is not None or k == "observed_at"}, "age": age, "sex": sex}


def scenario_cases():
    now = datetime.now(timezone.utc).isoformat()
    base = {"medications_reviewed": True, "allergies_reviewed": True, "symptoms_reviewed": True, "observed_at": now, "pregnancy_status": "not_applicable", "glucose_unit": "mmol/L"}
    specs = [
        (dict(systolic_bp=162, diastolic_bp=98, repeat_systolic_bp=158, repeat_diastolic_bp=96, hba1c=9.2, creatinine_umol=130, urine_acr_mg_mmol=12, potassium=4.3, known_hypertension="yes", known_diabetes="yes",
              tobacco_use="current", weight_kg=92, height_cm=172, total_cholesterol_mmol=5.6, hdl_mmol=1.0, ldl_mmol=3.4, medications=[{"code": "amlodipine", "name": "Amlodipine"}, {"code": "metformin", "name": "Metformin"}, {"code": "ibuprofen", "name": "Ibuprofen"}]), 58, "male"),
        (dict(glucose=38.25, glucose_unit="mg/dL", known_diabetes="yes"), 60, "female"),  # exact rounding tie in the glucose text
        (dict(oxygen_saturation=93.5, symptoms=["wheeze"], known_asthma="yes", reliever_use_per_week=5, medications=[{"code": "salbutamol", "name": "Salbutamol"}]), 30, "female"),
        (dict(known_atrial_fibrillation="yes", known_heart_failure="yes", known_hypertension="yes", systolic_bp=132, diastolic_bp=80, pulse=120, egfr=40, potassium=5.3,
              medications=[{"code": "aspirin", "name": "Aspirin"}, {"code": "spironolactone", "name": "Spironolactone"}, {"code": "digoxin", "name": "Digoxin"}]), 81, "male"),
        (dict(pregnancy_status="yes", systolic_bp=165, diastolic_bp=112, medications=[{"code": "lisinopril", "name": "Lisinopril"}]), 28, "female"),
        (dict(creatinine_umol=90), 44, "other"),
    ]
    return [{"data": {**base, **data}, "age": age, "sex": sex} for data, age, sex in specs]


def catalogue_cases():
    catalogue = json.loads((ROOT / "tests" / "cases" / "clinical_cases.json").read_text())
    now = datetime.now(timezone.utc).isoformat()
    cases = []
    for case in catalogue["cases"]:
        data = {key: value for key, value in case["data"].items() if key not in ("dosing_requests",)}
        data.setdefault("observed_at", now)
        cases.append({"data": data, "age": case["age"], "sex": case["sex"]})
    return cases


def python_result(case):
    try:
        result = assess(json.loads(json.dumps(case["data"])), case["age"], case["sex"])
    except ValueError as error:
        return {"error": str(error)}
    return json.loads(json.dumps(result))


def normalise(result):
    for key in ("id", "generated_at", "dosing"):
        result.pop(key, None)
    return result


def run_node(cases):
    completed = subprocess.run([NODE, str(ROOT / "scripts" / "mobile_engine_runner.cjs")], input=json.dumps({"cases": cases}),
                               capture_output=True, text=True, encoding="utf-8", timeout=120, check=True)
    return json.loads(completed.stdout)


def compare(cases):
    js = run_node(cases)
    assert len(js) == len(cases)
    for index, (case, js_result) in enumerate(zip(cases, js)):
        py_result = python_result(case)
        if "error" in py_result or "error" in js_result:
            assert ("error" in py_result) == ("error" in js_result), (index, case, py_result, js_result)
            continue
        assert normalise(js_result) == normalise(py_result), f"case {index} diverged: {json.dumps(case)[:600]}"


def test_evidence_export_is_current():
    sys.path.insert(0, str(ROOT / "scripts"))
    from export_mobile_evidence import TARGET, render
    assert TARGET.read_text(encoding="utf-8") == render(), "Run scripts/export_mobile_evidence.py"


def test_versions_match():
    source = (ROOT / "frontend" / "mobile" / "engine.js").read_text()
    from app.clinical import RULESET_VERSION
    from app.reasoning import REASONING_VERSION
    assert f"'{RULESET_VERSION}'" in source and f"'{REASONING_VERSION}'" in source


def test_catalogue_and_scenarios_match():
    compare(catalogue_cases() + scenario_cases())


def test_seeded_fuzz_matches():
    rng = random.Random(20260929)
    compare([random_case(rng) for _ in range(1500)])


def test_missing_tobacco_backend_mobile_match():
    cases = []
    for tobacco in (None, "unknown", "absent"):
        for measurements in (dict(total_cholesterol_mmol=5.5, hdl_mmol=1.2), dict(weight_kg=80, height_cm=175)):
            data = {"systolic_bp": 120, "diastolic_bp": 75, **measurements}
            if tobacco != "absent":
                data["tobacco_use"] = tobacco
            cases.append({"data": data, "age": 50, "sex": "male"})
    compare(cases)
