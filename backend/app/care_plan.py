"""Patient-specific summary built from recorded data and the rules that fired.

Display-only: it restates this patient's values against their targets and
collects the monitoring the cited sources specify. It adds no advice beyond the
recommendations, which remain the items the clinician decides on. Intervals
appear only where a source states one.
"""
from .treatment import (ACE, ARB, BETA_BLOCKER, CCB, DPP4, HTN_TABLE4, OTHER_BP, SGLT2, STATINS, SULFONYLUREA, THIAZIDE, TZD,
                        _dose_position, _statin_position, cvd_status, is_insulin)

CLASSES = [
    (CCB, "Calcium channel blocker"), (THIAZIDE, "Thiazide-type diuretic"), (ACE, "ACE inhibitor"), (ARB, "ARB"),
    (BETA_BLOCKER, "Beta blocker"), (OTHER_BP, "Other BP-lowering"), ({"metformin"}, "Biguanide"), (SULFONYLUREA, "Sulfonylurea"),
    (DPP4, "DPP-4 inhibitor"), (SGLT2, "SGLT2 inhibitor"), (TZD, "Thiazolidinedione"), (STATINS, "Statin"), ({"aspirin"}, "Antiplatelet"),
]


def _class_of(code):
    if is_insulin(code):
        return "Insulin"
    for members, label in CLASSES:
        if code in members:
            return label
    if any(name in code for name in ("salbutamol", "formoterol", "salmeterol", "ipratropium", "tiotropium", "beclometasone", "beclomethasone", "budesonide", "fluticasone")):
        return "Inhaler"
    return "Other"


def build(data: dict, age: int, sex: str, meds: list[dict], assessment: dict) -> dict:
    rules = {rec["rule_id"] for rec in assessment["recommendations"]}
    derived = assessment.get("derived") or {}
    yes = lambda field: (cvd_status(data) if field == "known_cvd" else data.get(field)) == "yes"
    sbp, dbp = data.get("systolic_bp"), data.get("diastolic_bp")
    rsbp, rdbp = data.get("repeat_systolic_bp"), data.get("repeat_diastolic_bp")
    control = (rsbp, rdbp) if rsbp is not None and rdbp is not None else (sbp, dbp) if sbp is not None and dbp is not None else None
    hba1c, egfr = data.get("hba1c"), data.get("egfr")
    fasting = data.get("glucose") if data.get("glucose_context") == "fasting" and data.get("glucose_unit") == "mmol/L" else None
    codes = {m["_code"] for m in meds}
    problems = []

    def problem(name, status, tone):
        problems.append({"name": name, "status": status, "tone": tone})

    critical = [rec["title"] for rec in assessment["recommendations"] if rec["severity"] == "critical"]
    if critical:
        problem("Acute findings", "; ".join(critical) + ". Routine treatment options are withheld until these are addressed." if assessment["urgency"] in {"urgent", "emergency"} else "; ".join(critical), "urgent")
    if yes("pregnancy_status"):
        problem("Pregnancy", "Recorded; obstetric pathway applies", "urgent")
    if yes("known_hypertension"):
        target = 150 if age >= 80 and not (yes("known_diabetes") or yes("known_ckd")) else 140
        if control:
            above = control[0] >= target or control[1] >= 90
            problem("Hypertension", f"BP {control[0]:g}/{control[1]:g} mmHg{' (repeat)' if control == (rsbp, rdbp) else ''}: {'above' if above else 'at'} target (<{target}/90)", "attention" if above else "ok")
        else:
            problem("Hypertension", "No BP recorded at this visit", "unknown")
    elif control and (control[0] >= 140 or control[1] >= 90):
        problem("Raised blood pressure", f"BP {control[0]:g}/{control[1]:g} mmHg without a recorded diagnosis: confirm on repeat readings", "attention")
    if yes("known_diabetes"):
        if hba1c is not None:
            problem("Type 2 diabetes", f"HbA1c {hba1c:g}%: " + (f"{hba1c - 7:.1f} above" if hba1c >= 7 else "within") + " target (<7.0%)", "attention" if hba1c >= 7 else "ok")
        elif fasting is not None:
            problem("Type 2 diabetes", f"Fasting glucose {fasting:g} mmol/L: {'above' if fasting > 7.2 else 'within'} target (4.4-7.2)", "attention" if fasting > 7.2 else "ok")
        else:
            problem("Type 2 diabetes", "No HbA1c or fasting glucose recorded", "unknown")
    elif "DIABETES_CONFIRM" in rules:
        problem("Possible diabetes", "Diagnostic threshold met once: confirmatory test needed", "attention")
    elif "PREDIABETES" in rules:
        problem("Prediabetes", "In the prediabetes range: lifestyle intervention", "attention")
    statins = [m for m in meds if m["_code"] in STATINS]
    high_risk = [label for field, label in (("known_cvd", "cardiovascular disease"), ("known_diabetes", "diabetes"), ("known_ckd", "kidney disease")) if yes(field)]
    tc, hdl, ldl = data.get("total_cholesterol_mmol"), data.get("hdl_mmol"), data.get("ldl_mmol")
    non_hdl = round(tc - hdl, 1) if tc is not None and hdl is not None else None
    lipids = ", ".join(x for x in (f"LDL {ldl:g}" if ldl is not None else None, f"non-HDL {non_hdl:g}" if non_hdl is not None else None,
                                   f"total {tc:g}" if tc is not None and non_hdl is None else None) if x)
    if high_risk or statins or (tc is not None and tc >= 8):
        if statins:
            daily, level = _statin_position(statins[0])
            therapy = f"on {statins[0]['_label']}" + (f" {daily:g} mg ({level or 'unclassified'} intensity)" if daily is not None else "")
        else:
            therapy = "no statin recorded"
        target = " (target LDL ≤2.0 or non-HDL ≤2.6)" if yes("known_cvd") else ""
        above = yes("known_cvd") and ((ldl is not None and ldl > 2.0) or (non_hdl is not None and non_hdl > 2.6))
        problem("Cardiovascular risk", ("High, from " + " and ".join(high_risk) + "; " if high_risk else "") + therapy
                + (f"; lipids {lipids} mmol/L{target}" if lipids else "; no lipid profile recorded"),
                "attention" if not statins or above or not lipids else "ok")
    if egfr is not None and egfr < 60 or yes("known_ckd"):
        category = None if egfr is None else "G3a" if egfr >= 45 else "G3b" if egfr >= 30 else "G4" if egfr >= 15 else "G5"
        problem("Kidney function", (f"eGFR {egfr:g} (KDIGO {category})" if egfr is not None else "Known CKD; no eGFR recorded")
                + ("" if yes("known_ckd") else ": chronicity not yet established"), "urgent" if egfr is not None and egfr < 30 else "attention")
    if derived.get("bmi") is not None:
        bmi = derived["bmi"]
        problem("Weight", f"BMI {bmi:g} kg/m² ({derived['bmi_category']})" + (f", {data['weight_kg']:g} kg" if data.get("weight_kg") is not None else ""),
                "ok" if 18.5 <= bmi < 25 else "attention")
    inhalers = [m["_label"] for m in meds if _class_of(m["_code"]) == "Inhaler"]
    if yes("known_asthma"):
        problem("Asthma", "Inhalers: " + (", ".join(inhalers) if inhalers else "none recorded") + ("; no inhaled corticosteroid" if "TX_ASTHMA_ICS" in rules else ""),
                "attention" if "TX_ASTHMA_ICS" in rules else "ok")
    if yes("known_copd"):
        problem("COPD", "Inhalers: " + (", ".join(inhalers) if inhalers else "none recorded"), "ok" if inhalers else "attention")
    if data.get("tobacco_use") == "current":
        problem("Tobacco", "Current smoker", "attention")
    if data.get("adherence") == "missed":
        problem("Adherence", "Missed doses reported", "attention")

    medicines = []
    for m in meds:
        dose = " ".join(str(x) for x in (f"{m['dose']:g}" if isinstance(m.get("dose"), (int, float)) else None, m.get("unit"), m.get("frequency")) if x) or "dose not recorded"
        note = None
        position = _dose_position(m)
        if position:
            note = "at the Table 4 maximum" if position[0] >= position[1] else f"below the Table 4 maximum of {position[1]:g} mg"
        elif m["_code"] in STATINS:
            daily, level = _statin_position(m)
            note = f"{level} intensity (NICE)" if level else None
        medicines.append({"name": m["_label"], "dose": dose, "class": _class_of(m["_code"]), "note": note})

    monitoring = []

    def monitor(item, when, source):
        monitoring.append({"item": item, "when": when, "source_id": source})

    if yes("known_hypertension"):
        monitor("Blood pressure", "Monthly until below 140/90 mmHg, then every 4-6 months", "KENYA_HTN_STEPS")
    if codes & (ACE | ARB) or rules & {"TX_HTN_START", "TX_HTN_STEP_UP"}:
        monitor("Potassium and creatinine/eGFR", "After starting or changing an ACE inhibitor or ARB", "LOSARTAN_LABEL")
    if statins or "TX_STATIN_START" in rules:
        monitor("Full lipid profile and ALT/AST", "2-3 months after starting or changing a statin", "NICE_LIPIDS_NG238")
        monitor("ALT/AST", "At 12 months, then only if clinically indicated", "NICE_LIPIDS_NG238")
        monitor("Full lipid profile", "Annually, at the medication review", "NICE_LIPIDS_NG238")
    if high_risk:
        monitor("Cardiovascular risk review", "Every 3 months; refer if risk has not fallen after 6 months", "KENYA_CVD_RISK")
    if any(is_insulin(c) for c in codes) or "TX_DM_INSULIN" in rules:
        monitor("Fasting glucose", "Titrate basal insulin by 2-4 units every 3 days to 4-7 mmol/L", "KENYA_DM_TREATMENT")
    if "PREDIABETES" in rules:
        monitor("HbA1c", "Every 3-6 months while in the prediabetes range", "KENYA_PREDIABETES")
    if egfr is not None and egfr < 60 and not yes("known_ckd"):
        monitor("eGFR and urine albumin", "Repeat to confirm: CKD needs abnormality for more than 3 months", "KDIGO_CKD_2024")
    if "metformin" in codes or "TX_DM_METFORMIN" in rules:
        monitor("Kidney function and vitamin B12", "During long-term metformin treatment", "METFORMIN_LABEL")

    conditions = [label for field, label in (("known_hypertension", "hypertension"), ("known_diabetes", "type 2 diabetes"), ("known_ckd", "chronic kidney disease"),
                                             ("known_cvd", "cardiovascular disease"), ("known_asthma", "asthma"), ("known_copd", "COPD"), ("known_cancer", "cancer")) if yes(field)]
    person = {"female": "woman", "male": "man"}.get(sex, "adult")
    headline = f"{age}-year-old {person}" + (f" with {', '.join(conditions[:-1]) + (' and ' if len(conditions) > 1 else '') + conditions[-1]}" if conditions else " with no recorded NCD diagnosis") \
        + (f" on {len(meds)} recorded medicine{'s' if len(meds) != 1 else ''}" if meds else ", no medicines recorded") + f". Clinical priority: {assessment['urgency']}."
    return {"headline": headline, "problems": problems, "medicines": medicines, "monitoring": monitoring}
