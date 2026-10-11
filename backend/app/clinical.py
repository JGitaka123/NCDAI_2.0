"""Deterministic, advisory adult NCD safety rules; not a prescribing engine.

Every rule is a proposed implementation requiring independent clinical approval.
No external network or LLM participates in these calculations. Never infer a
negative clinical finding from an empty field or from unstructured notes.
"""

from collections import Counter
from datetime import datetime, timezone, timedelta
import math
import re
from uuid import uuid4

from .evidence import EVIDENCE_VERSION, REVIEW_STATUS, evidence
from .reasoning import g_stage
from .treatment import STATINS, cvd_status

RULESET_VERSION = "ncdai-2-rules-0.4.0"

ACE = {"lisinopril", "enalapril", "ramipril", "captopril", "perindopril"}
ARB = {"losartan", "valsartan", "candesartan", "telmisartan", "irbesartan"}
DIURETIC = {"hydrochlorothiazide", "chlorthalidone", "indapamide", "furosemide", "spironolactone"}
NSAID = {"ibuprofen", "diclofenac", "naproxen", "celecoxib"}
SULFONYLUREA = {"glibenclamide", "gliclazide", "glimepiride"}
SGLT2 = {"empagliflozin", "dapagliflozin", "canagliflozin"}
SUPPORTED = ACE | ARB | DIURETIC | NSAID | SULFONYLUREA | SGLT2 | {
    "metformin", "insulin", "amlodipine", "nifedipine", "aspirin", "atorvastatin",
    "salbutamol", "budesonide", "beclometasone", "formoterol", "salmeterol",
    "ipratropium", "tiotropium", "prednisolone",
}
ALIASES = {"glyburide": "glibenclamide", "hctz": "hydrochlorothiazide"}
PRIORITY = {"routine": 0, "soon": 1, "urgent": 2, "emergency": 3}
SEVERITY = {"critical": 0, "warning": 1, "info": 2}
ACUTE_SYMPTOMS = {"chest_pain", "breathlessness", "neurological_deficit", "confusion", "seizure"}
BP_DANGER_SYMPTOMS = {"severe_headache", "visual_disturbance", "vomiting"}
# Why each gap matters, shown with the gap so the request is specific to this patient.
GAP_REASONS = {
    "repeat_blood_pressure": "a raised reading must be confirmed before diagnosis or treatment changes",
    "egfr": "kidney function decides metformin, sulfonylurea and statin choices",
    "egfr_for_metformin_review": "metformin is recorded and depends on kidney function",
    "egfr_for_RAS_medication_review": "an ACE inhibitor/ARB is recorded",
    "potassium_for_RAS_medication_review": "an ACE inhibitor/ARB is recorded",
    "pregnancy_status_for_RAS_medication_review": "ACE inhibitors/ARBs are harmful in pregnancy",
    "pregnancy_status": "several NCD medicines are unsafe in pregnancy",
    "glycaemic_measurement": "an HbA1c or fasting glucose is needed to judge diabetes control",
    "glucose_context": "fasting (>=7.0) and random (>=11.1) diagnostic thresholds differ",
    "lipid_profile": "needed to choose and monitor statin treatment",
    "weight_and_height": "BMI guides weight targets and treatment",
    "known_cvd_for_statin_choice": "established cardiovascular disease changes the statin dose to atorvastatin 80 mg",
    "current_observations": "the recorded measurements are more than 24 hours old",
    "observed_at": "measurement time is needed to judge whether results are current",
}
KNOWN_FIELDS = ("known_hypertension", "known_diabetes", "known_asthma", "known_copd", "known_ckd", "known_cancer")


def _normal(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _ingredient(value: object) -> str:
    normalized = _normal(value)
    return ALIASES.get(normalized, normalized)


def assess(data: dict, age: int, sex: str) -> dict:
    """Evaluate validated structured observations; backend owns identity and time.

    Max urgency is monotonic across triggered rules. A normal repeat never hides
    an initial critical measurement. Returned UUID/time may be replaced by the
    backend; recommendation IDs remain rule IDs within each assessment.
    """
    if not isinstance(data, dict):
        raise ValueError("Clinical data must be an object")
    if isinstance(age, bool) or not isinstance(age, int) or not 18 <= age <= 120:
        raise ValueError("The adult NCD pathway supports ages 18 through 120 only")
    result = {
        "id": str(uuid4()), "urgency": "routine", "summary": "",
        "recommendations": [], "missing_data": [],
        "warnings": [
            "Clinician verification is required; clinical evaluation of this limited implementation is ongoing.",
            "This is a limited advisory screen, not diagnosis, prescribing, or clearance for discharge.",
            "Unstructured notes are not interpreted by these safety rules; enter critical findings in structured fields.",
        ],
        "model_info": {"mode": "deterministic_rules", "status": REVIEW_STATUS},
        "evidence_version": EVIDENCE_VERSION,
        "rules_version": RULESET_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    recs = result["recommendations"]
    missing = result["missing_data"]

    def add(rule_id, category, severity, urgency, title, detail, *sources, basis=()):
        if any(r["rule_id"] == rule_id for r in recs):
            raise RuntimeError("Duplicate rule identifier")
        # basis lists the recorded values that triggered the rule, so the
        # clinician sees why it applies to this patient.
        recs.append({"id": rule_id, "rule_id": rule_id, "category": category,
                     "severity": severity, "title": title, "detail": detail,
                     "basis": [item for item in basis if item], "evidence": evidence(*sources)})
        if PRIORITY[urgency] > PRIORITY[result["urgency"]]:
            result["urgency"] = urgency

    def num(key, minimum, maximum):
        value = data.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"{key} must be a finite number or null")
        value = float(value)
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError(f"{key} is outside the supported measurement range")
        return value

    sbp, dbp = num("systolic_bp", 40, 300), num("diastolic_bp", 20, 200)
    rsbp, rdbp = num("repeat_systolic_bp", 40, 300), num("repeat_diastolic_bp", 20, 200)
    for s, d in ((sbp, dbp), (rsbp, rdbp)):
        if s is not None and d is not None and s <= d:
            raise ValueError("Systolic pressure must exceed diastolic pressure")
    egfr, potassium = num("egfr", 0, 200), num("potassium", 1, 10)
    creatinine = num("creatinine_umol", 10, 3000)
    calculated_egfr = None
    if egfr is None and creatinine is not None:
        # An entered laboratory eGFR always wins; a calculated value never hides it.
        from .reasoning import ckd_epi_2021, fmt
        calculated_egfr = ckd_epi_2021(creatinine, age, sex)
        egfr = calculated_egfr
    pulse = num("pulse", 20, 250)
    hba1c = num("hba1c", 2, 25)
    spo2, rr = num("oxygen_saturation", 1, 100), num("respiratory_rate", 1, 80)
    glucose = num("glucose", 0.01, 1500)
    unit = data.get("glucose_unit")
    if glucose is not None:
        if unit not in {"mg/dL", "mmol/L"}:
            raise ValueError("A measured glucose requires an explicit supported unit")
        glucose = glucose / 18.0 if unit == "mg/dL" else glucose
        if glucose > 83.34:
            raise ValueError("Glucose outside supported range; verify its units")
    glucose_timing = data.get("glucose_context", "unknown")
    if glucose_timing not in {"fasting", "random", "unknown"}:
        raise ValueError("Unrecognized glucose sample timing")
    weight, height, waist = num("weight_kg", 20, 350), num("height_cm", 100, 250), num("waist_cm", 40, 250)
    total_chol, ldl = num("total_cholesterol_mmol", 1, 20), num("ldl_mmol", 0.2, 15)
    hdl, triglycerides = num("hdl_mmol", 0.2, 5), num("triglycerides_mmol", 0.1, 60)
    bmi = round(weight / (height / 100) ** 2, 1) if weight is not None and height is not None else None
    bmi_category = (None if bmi is None else "underweight" if bmi < 18.5 else "healthy" if bmi < 25
                    else "overweight" if bmi < 30 else "obesity")
    result["derived"] = {"bmi": bmi, "bmi_category": bmi_category}
    symptoms = set(data.get("symptoms") or [])
    meds = data.get("medications") or []
    codes = [_ingredient(m.get("code")) for m in meds]
    code_set = set(codes)
    allergies = {_ingredient(a) for a in data.get("allergies") or []}
    pregnancy = data.get("pregnancy_status", "unknown")
    if pregnancy not in {"yes", "no", "unknown", "not_applicable"}:
        raise ValueError("Unrecognized pregnancy status")
    for field in (*KNOWN_FIELDS, "known_ascvd", "prior_stroke_tia", "acutely_unwell", "acute_kidney_injury"):
        if data.get(field, "unknown") not in {"yes", "no", "unknown"}:
            raise ValueError(f"Unrecognized {field} status")
    pregnant = pregnancy == "yes"
    diabetic = data.get("known_diabetes") == "yes"
    hypertensive = data.get("known_hypertension") == "yes"
    renal_disease = data.get("known_ckd") == "yes"
    cvd_state = cvd_status(data)
    # Use all readings independently. Do not silently average away a danger sign.
    highest_sbp = max((v for v in (sbp, rsbp) if v is not None), default=None)
    highest_dbp = max((v for v in (dbp, rdbp) if v is not None), default=None)

    def bp_at_least(s, d):
        return (highest_sbp is not None and highest_sbp >= s) or (highest_dbp is not None and highest_dbp >= d)

    def reading(s, d):
        return f"{s:g}/{d:g}" if s is not None and d is not None else f"{s:g}/–" if s is not None else f"–/{d:g}" if d is not None else None

    bp_basis = ["BP " + reading(sbp, dbp) + " mmHg" if reading(sbp, dbp) else None,
                "Repeat BP " + reading(rsbp, rdbp) + " mmHg" if reading(rsbp, rdbp) else None]
    timing_label = {"fasting": "Fasting", "random": "Random"}.get(glucose_timing, "Unspecified-timing")
    glucose_basis = (f"{timing_label} glucose {glucose:.1f} mmol/L"
                     + (f" (entered {data.get('glucose'):g} mg/dL)" if unit == "mg/dL" else "")) if glucose is not None else None
    hba1c_basis = f"HbA1c {hba1c:g}%" if hba1c is not None else None
    egfr_basis = f"eGFR {egfr:g} mL/min/1.73 m²" if egfr is not None else None
    potassium_basis = f"Potassium {potassium:g} mmol/L" if potassium is not None else None
    symptom_basis = "Symptoms: " + ", ".join(sorted(s.replace("_", " ") for s in symptoms)) if symptoms else None
    med_names = {c: str(m.get("name") or c) for m, c in zip(meds, codes)}

    from .treatment import (BETA_BLOCKER, CCB, OTHER_BP, THIAZIDE, diabetes_options, hypertension_options,
                            is_insulin, lipid_options, respiratory_options)

    def named(members=None, test=None):
        """Recorded names for a class, so guidance refers to this patient's own medicines."""
        return [med_names[c] for c in dict.fromkeys(codes) if (members is not None and c in members) or (test is not None and test(c))]

    def listing(names):
        return ", ".join(names[:-1]) + (" and " if len(names) > 1 else "") + names[-1] if names else ""

    bp_lowering = named(ACE | ARB | CCB | THIAZIDE | BETA_BLOCKER | OTHER_BP | {"furosemide"})
    glucose_lowering = named(SULFONYLUREA, test=is_insulin)
    comorbid = [label for field, label in (("known_hypertension", "hypertension"), ("known_diabetes", "diabetes"), ("known_ckd", "chronic kidney disease"),
                                          ("known_ascvd", "coronary or peripheral arterial disease"), ("prior_stroke_tia", "previous stroke or TIA"), ("known_copd", "COPD"), ("known_asthma", "asthma")) if data.get(field) == "yes"]

    if symptoms & ACUTE_SYMPTOMS:
        acute_found = sorted(s.replace("_", " ") for s in symptoms & ACUTE_SYMPTOMS)
        add("EMERGENCY_SYMPTOMS", "acute_safety", "critical", "emergency", "Immediate acute assessment",
            f"Recorded now: {listing(acute_found)}. These need immediate clinician assessment and the local emergency pathway"
            + (f"; with {listing(comorbid)} on record, consider acute coronary syndrome, stroke and metabolic causes" if comorbid else "")
            + ". Normal BP or glucose cannot rule out an emergency.",
            "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC", basis=[symptom_basis, *bp_basis, glucose_basis])
    if any(v is not None and v <= 90 for v in (sbp, rsbp)):
        add("LOW_BP", "acute_safety", "warning", "urgent", "Low systolic BP needs assessment",
            f"Lowest systolic reading {min(v for v in (sbp, rsbp) if v is not None):g} mmHg. Assess perfusion, symptoms, hydration and change from baseline now, and verify the measurement. "
            + (f"BP-lowering medicines recorded: {listing(bp_lowering)}; review whether they contribute before the next doses. " if bp_lowering else "No BP-lowering medicine is recorded, so look for other causes. ")
            + "This is an isolated vital-sign flag, not a shock diagnosis or NEWS2 score.", "RCP_NEWS2", "NCDAI_SAFETY_SPEC", basis=[*bp_basis, "BP-lowering medicines: " + (listing(bp_lowering) or "none recorded")])
    if pulse is not None and (pulse <= 40 or pulse >= 131):
        slow = pulse <= 40
        blockers = named(BETA_BLOCKER)
        add("PULSE_EXTREME", "acute_safety", "warning", "urgent", "Marked pulse abnormality",
            f"Pulse {pulse:g}/min ({'bradycardia' if slow else 'tachycardia'}). Confirm manually, check rhythm with an ECG and assess symptoms now. "
            + ((f"{listing(blockers)} is recorded and can slow the heart; review it urgently. " if blockers else "") if slow else
               "Look for fever, dehydration, hypoxaemia, pain, bleeding and arrhythmia. ")
            + "The complete early-warning assessment is outside this screen.", "RCP_NEWS2", "NCDAI_SAFETY_SPEC", basis=[f"Pulse {pulse:g}/min", *(["On " + listing(blockers)] if slow and blockers else [])])
    if rr is not None and rr <= 8:
        add("RESP_SLOW", "acute_safety", "critical", "emergency", "Very low respiratory rate",
            f"Respiratory rate {rr:g}/min. Obtain immediate clinical assessment of airway, breathing and consciousness"
            + (f"; with glucose {glucose:.1f} mmol/L recorded, exclude hypoglycaemia" if glucose is not None and glucose <= 3.9 + 1e-9 else "")
            + ". This flag does not determine the cause or treatment.", "RCP_NEWS2", "NCDAI_SAFETY_SPEC", basis=[f"Respiratory rate {rr:g}/min"])
    if bp_at_least(180, 110) and symptoms & BP_DANGER_SYMPTOMS:
        add("BP_CRISIS", "acute_safety", "critical", "emergency", "Severe BP with warning symptoms",
            f"Highest BP {reading(highest_sbp, highest_dbp)} mmHg with {listing(sorted(s.replace('_', ' ') for s in symptoms & BP_DANGER_SYMPTOMS))}. Assess for hypertension-mediated organ damage now "
            "(fundoscopy, neurological and cardiac examination, ECG, creatinine and urine). The Kenya protocol manages hypertensive emergencies at level 4 and above: stabilise and refer. "
            "Repeat BP when feasible without delaying care; this alert does not diagnose a hypertensive emergency.",
            "KENYA_HTN_STEPS", "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC", basis=[*bp_basis, symptom_basis])
    elif bp_at_least(180, 110):
        add("BP_SEVERE", "hypertension", "critical", "urgent", "Severe blood pressure reading",
            f"Highest BP {reading(highest_sbp, highest_dbp)} mmHg is grade 3 (≥180/110). Without organ damage the Kenya protocol treats this as a hypertensive urgency: rest in a quiet room for at least 30 minutes, "
            + ("optimise the current oral medicines (" + listing(bp_lowering) + ")" if bp_lowering else "initiate oral treatment")
            + ", recheck BP after 1 hour, review baseline investigations and review again in 48-72 hours, aiming for 140/90 or less within 24 hours. "
            "Examine for organ damage today; symptoms not documented cannot be assumed absent.",
            "KENYA_HTN_STEPS", "WHO_HTN_2021", "NCDAI_SAFETY_SPEC", basis=[*bp_basis, "BP-lowering medicines: " + (listing(bp_lowering) or "none recorded")])
    if pregnant:
        teratogens = named(ACE | ARB | STATINS)
        add("PREGNANCY_SCOPE", "scope", "warning", "urgent", "Use the pregnancy care pathway",
            "Pregnancy is recorded. Obtain obstetric review; adult non-pregnancy NCD treatment options are withheld."
            + (f" Medicines needing review in pregnancy: {listing(teratogens)}." if teratogens else ""),
            "NICE_PREGNANCY", "WHO_HTN_2021", basis=["Pregnant", *(["On " + listing(teratogens)] if teratogens else [])])
        if bp_at_least(160, 110):
            add("PREGNANCY_SEVERE_BP", "acute_safety", "critical", "emergency", "Severe BP in pregnancy",
                f"BP {reading(highest_sbp, highest_dbp)} mmHg in pregnancy. Activate immediate obstetric assessment for this severe reading and repeat promptly without delaying escalation.", "NICE_PREGNANCY", basis=bp_basis)
        elif symptoms & BP_DANGER_SYMPTOMS:
            add("PREGNANCY_WARNING", "acute_safety", "critical", "emergency", "Pregnancy warning symptoms",
                f"{listing(sorted(s.replace('_', ' ') for s in symptoms & BP_DANGER_SYMPTOMS)).capitalize()} in pregnancy. Promptly assess possible pre-eclampsia using the obstetric emergency pathway, even when BP is unavailable or below the severe threshold.",
                "NICE_PREGNANCY", "NCDAI_SAFETY_SPEC", basis=[symptom_basis, *bp_basis])
    if glucose is not None and glucose <= 3.9 + 1e-9:
        danger = glucose < 3 or bool(symptoms & {"confusion", "seizure"})
        cause = ""
        sulfonylureas, insulins = named(SULFONYLUREA), named(test=is_insulin)
        if sulfonylureas:
            cause += f" {listing(sulfonylureas)} is recorded: sulfonylurea hypoglycaemia can recur, so observe longer; the Kenya flowchart advises stopping a sulfonylurea after recurrent hypoglycaemia."
        if insulins:
            cause += f" {listing(insulins)} is recorded: find the cause, then reduce the insulin dose by 10-20%."
        add("HYPOGLYCEMIA", "acute_safety", "critical", "emergency" if danger else "urgent", "Low glucose requires action now",
            f"Glucose {glucose:.2f} mmol/L (hypoglycaemia is 3.9 or below). Treat now (Kenya 4.8): if responsive and able to swallow, give 15-20 g oral carbohydrate and recheck capillary glucose in 15 minutes, "
            "repeating until above 3.9, then a meal or snack within 30 minutes. If responsive but nil by mouth, give 15-20 g (30-40 ml) of 50% dextrose IV. If not responsive, give 25 g (50 ml) of 50% dextrose IV, "
            "or glucagon 1 mg IM if there is no IV access, inform the consultant and recheck every 15 minutes; if glucose stays low, refer on a 10% dextrose 500 ml infusion."
            + cause + " Then evaluate the cause and teach the patient how to prevent further episodes.",
            "KENYA_HYPOGLYCAEMIA", "KENYA_DM_TREATMENT", basis=[glucose_basis, symptom_basis, *(["On " + listing(glucose_lowering)] if glucose_lowering else [])])
    elif "hypoglycemia_symptoms" in symptoms:
        add("SUSPECTED_HYPOGLYCEMIA", "acute_safety", "warning", "urgent", "Assess reported hypoglycaemia symptoms now",
            "Hypoglycaemia symptoms are recorded" + (f" in a patient on {listing(glucose_lowering)}" if glucose_lowering else "")
            + ". Check a capillary glucose now; if it is 3.9 mmol/L or below, give 15-20 g oral carbohydrate and recheck in 15 minutes (Kenya 4.8). A missing or older normal result does not resolve these symptoms.",
            "KENYA_HYPOGLYCAEMIA", basis=[symptom_basis, *(["On " + listing(glucose_lowering)] if glucose_lowering else [])])
        missing.append("current_glucose_for_symptoms")
    if glucose is not None and glucose >= 18:
        crisis = bool(symptoms & {"vomiting", "dehydration", "confusion"})
        sglt2 = named(SGLT2)
        add("HYPERGLYCEMIC_CRISIS" if crisis else "GLUCOSE_HIGH", "acute_safety", "critical", "emergency" if crisis else "urgent",
            "Assess possible hyperglycaemic crisis" if crisis else "Markedly elevated glucose",
            f"Glucose {glucose:.1f} mmol/L" + (f" with {listing(sorted(s for s in symptoms & {'vomiting', 'dehydration', 'confusion'}))}" if crisis else "")
            + (" in a patient without a recorded diabetes diagnosis" if not diabetic else "") + ". Assess hydration and conscious level and check urine or blood ketones now"
            + (f"; {listing(sglt2)} is recorded, so ketoacidosis is possible even at lower glucose" if sglt2 else "")
            + ". The Kenya protocol manages DKA and HHS at level 4 facilities and above: stabilise and refer. No insulin or fluid dose is generated here.",
            "KENYA_HYPOGLYCAEMIA", "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC", basis=[glucose_basis, symptom_basis])
    if code_set & SGLT2 and symptoms & {"vomiting", "dehydration"}:
        add("SGLT2_ACUTE_ILLNESS", "medication_safety", "critical", "urgent", "Acute illness with an SGLT2 inhibitor",
            f"{listing(named(SGLT2))} with {listing(sorted(s for s in symptoms & {'vomiting', 'dehydration'}))}. Assess for ketoacidosis, including when glucose is not markedly high; "
            "pause the SGLT2 inhibitor during the illness (sick-day rule) and check ketones. A normal glucose cannot provide clearance.", "SGLT2_LABEL", "NCDAI_SAFETY_SPEC", basis=[symptom_basis])
    if spo2 is not None and spo2 < 95:
        copd = data.get("known_copd") == "yes"
        add("RESP_HYPOXEMIA", "respiratory", "critical" if spo2 < 92 else "warning", "emergency" if spo2 < 92 else "urgent",
            "Low oxygen saturation needs assessment",
            f"SpO2 {spo2:g}%" + (f" with respiratory rate {rr:g}/min" if rr is not None else "") + ". Check the probe and signal, then assess immediately if below 92%. "
            + ("COPD is recorded: compare with the patient's usual saturation; long-term oxygen is considered only when SaO2 is 88% or below on two occasions three weeks apart. " if copd else "Confirm baseline, oxygen use and clinical state. ")
            + "This tool does not set an oxygen dose or target.", "KENYA_COPD" if copd else "WHO_PEN_2020", "NCDAI_SAFETY_SPEC", basis=[f"SpO2 {spo2:g}%", "Known COPD" if copd else None])
    if rr is not None and rr > 25:
        add("RESP_TACHYPNEA", "respiratory", "warning", "urgent", "Raised respiratory rate",
            f"Respiratory rate {rr:g}/min" + (f", SpO2 {spo2:g}%" if spo2 is not None else "") + ". Assess respiratory effort and acute causes now (infection, asthma or COPD exacerbation, heart failure, acidosis); "
            "a chronic respiratory diagnosis must not obscure other causes of rapid breathing.", "WHO_PEN_2020", "NCDAI_SAFETY_SPEC", basis=[f"Respiratory rate {rr:g}/min"])
    inhalers = named(test=lambda c: any(n in c for n in ("salbutamol", "formoterol", "salmeterol", "ipratropium", "tiotropium", "beclometasone", "beclomethasone", "budesonide", "fluticasone")))
    if "wheeze" in symptoms:
        context = "asthma" if data.get("known_asthma") == "yes" else "COPD" if data.get("known_copd") == "yes" else None
        add("RESP_WHEEZE", "respiratory", "warning", "urgent", "Assess current wheeze",
            "Wheeze today" + (f" in known {context}" if context else " without a recorded asthma or COPD diagnosis") + ". Assess severity (ability to speak, respiratory rate, SpO2), give the acute reliever per the local pathway and review response. "
            + (f"Current inhalers: {listing(inhalers)}; check technique and adherence. " if inhalers else "No inhaler is recorded. ")
            + ("Consider heart failure and other causes of wheeze. " if not context else ""), "KENYA_ASTHMA" if context == "asthma" else "KENYA_COPD" if context else "WHO_PEN_2020",
            basis=[symptom_basis, f"SpO2 {spo2:g}%" if spo2 is not None else None, "Inhalers: " + (listing(inhalers) or "none recorded")])
    smoker = data.get("tobacco_use") == "current"
    if "hemoptysis" in symptoms:
        add("HEMOPTYSIS", "referral", "warning", "urgent", "Assess coughing blood today",
            "Coughing blood is recorded" + (" in a current smoker" if smoker else "") + (f", with SpO2 {spo2:g}%" if spo2 is not None else "")
            + ". Establish the amount, haemodynamic stability and respiratory status; test sputum for TB and arrange a chest X-ray. Escalate immediately if unstable. No cancer diagnosis is inferred.",
            "NCI_CANCER_SYMPTOMS", "NCDAI_SAFETY_SPEC", basis=[symptom_basis, "Current smoker" if smoker else None])
    warning_signs = symptoms & {"unexplained_weight_loss", "persistent_cough", "breast_lump", "abnormal_bleeding"}
    if warning_signs:
        actions = []
        if "breast_lump" in warning_signs:
            actions.append("breast lump: examine both breasts and axillae and refer to a surgeon, who arranges imaging and biopsy with a radiologist")
        if "abnormal_bleeding" in warning_signs:
            actions.append(("abnormal bleeding: identify the site; for vaginal bleeding do a speculum examination and biopsy and refer to a gynaecologic oncologist; " if sex == "female" else "abnormal bleeding: identify the site; ")
                           + "blood in the stool needs referral for colonoscopy, and blood in the urine referral to a urologist")
        if "unexplained_weight_loss" in warning_signs:
            actions.append("unexplained weight loss" + (f" (current weight {weight:g} kg; compare with previous records)" if weight is not None else "")
                           + ": with changed bowel habit, anaemia or blood in the stool refer for colonoscopy; with upper abdominal pain or new indigestion refer urgently for endoscopy (OGD); also consider TB, HIV and uncontrolled diabetes")
        if "persistent_cough" in warning_signs:
            actions.append("persistent cough" + (" in a current smoker" if smoker else "") + ": test sputum for TB and arrange a chest X-ray; persistent hoarseness needs ENT referral")
        add("CANCER_WARNING", "referral", "warning", "urgent" if "abnormal_bleeding" in symptoms else "soon", "Arrange diagnostic assessment of warning symptoms",
            "Kenya Table 9 actions for this patient: " + "; ".join(actions) + ". Record symptom duration and set a tracked referral. These symptoms can have non-cancer causes, including infection.",
            "KENYA_CANCER_SIGNS", "WHO_CANCER_DIAGNOSIS", basis=[symptom_basis, "Current smoker" if smoker else None])
    renal_review = named({"metformin"} | SULFONYLUREA | SGLT2 | NSAID | ACE | ARB | {"spironolactone"})
    if egfr is not None and egfr < 30:
        add("RENAL_SEVERE", "kidney", "critical", "urgent", "Severely reduced kidney function",
            f"eGFR {egfr:g} (KDIGO category {'G5' if egfr < 15 else 'G4'}). Arrange prompt clinical assessment and referral planning; assess acute deterioration, hydration, urine output and previous results. "
            + (f"Review these recorded medicines against this eGFR today: {listing(renal_review)}. " if renal_review else "")
            + "A single result cannot establish chronicity.", "WHO_HEARTS_D_2020", "KDIGO_CKD_2024", basis=[egfr_basis, *(["On " + listing(renal_review)] if renal_review else [])])
    if potassium is not None and potassium >= 5.5:
        # A negative dosing-context entry cannot cancel a positive acute finding.
        acute = (data.get("acutely_unwell") == "yes" or
                 data.get("acute_kidney_injury") == "yes" or
                 (data.get("dosing_context") or {}).get("acute_illness") == "yes")
        for field in ("acutely_unwell", "acute_kidney_injury"):
            if data.get(field, "unknown") == "unknown":
                missing.append(field)
        if potassium >= 6.5:
            detail = "Arrange immediate hospital assessment and treatment. Do not delay transfer for a community repeat sample."
        elif acute:
            detail = "Arrange same-day hospital assessment because acute illness or acute kidney injury is recorded. Escalate immediately if unstable; do not wait for routine repeat testing."
        elif potassium >= 6:
            detail = "Arrange same-day clinical review and repeat potassium within one day. Assess whether hospital care is needed."
        else:
            detail = "For an unexpected result, repeat potassium within three days, or sooner as clinically indicated. Confirm clinical stability and previous results before setting follow-up."
        raising = named(ACE | ARB | {"spironolactone"} | NSAID)
        detail = f"Potassium {potassium:g} mmol/L" + (f", eGFR {egfr:g}" if egfr is not None else "") + ". " + detail
        detail += (f" Potassium-raising medicines recorded: {listing(raising)}; review them now." if raising else "")
        detail += " Assess clinical state, ECG, sample validity (haemolysis) and diet. Unknown acute illness or kidney injury must be assessed now; if present, consider hospital assessment today. No potassium-lowering dose is generated."
        add("POTASSIUM_HIGH", "acute_safety", "critical" if potassium >= 6 or acute else "warning",
            "emergency" if potassium >= 6.5 else "urgent" if potassium >= 6 or acute else "soon",
            "Elevated potassium", detail, "UKKA_POTASSIUM_2026", basis=[potassium_basis, "Acutely unwell: " + str(data.get("acutely_unwell", "unknown")), "Acute kidney injury: " + str(data.get("acute_kidney_injury", "unknown")), *(["On " + listing(raising)] if raising else [])])
    if potassium is not None and potassium < 3.5:
        wasting = named(THIAZIDE | {"furosemide"})
        add("POTASSIUM_LOW", "acute_safety", "critical" if potassium < 3 else "warning",
            "emergency" if potassium < 2.5 else "urgent" if potassium < 3 else "soon", "Reduced potassium",
            f"Potassium {potassium:g} mmol/L. " + (f"Potassium-lowering diuretics recorded: {listing(wasting)}; review the dose and need. " if wasting else "")
            + "Review symptoms, ECG, vomiting or diarrhoea, and magnesium. Below 2.5 mmol/L requires immediate supervised assessment; no electrolyte replacement dose is generated.", "NHS_LOW_POTASSIUM", basis=[potassium_basis, *(["On " + listing(wasting)] if wasting else [])])
    if "foot_ulcer" in symptoms:
        add("FOOT_ULCER", "referral", "warning", "urgent", "Assess foot ulcer and limb risk",
            "Foot ulcer recorded" + (f" in a patient with diabetes ({hba1c_basis or glucose_basis or 'no current glycaemic result'})" if diabetic else "")
            + ". Today assess infection (spreading redness, pus, fever), foot pulses and perfusion, and systemic illness; offload the foot. Infection, gangrene or critical ischaemia warrants urgent referral; absence of these findings has not been established.",
            "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC", basis=[symptom_basis, hba1c_basis if diabetic else None])
    if "metformin" in code_set:
        if egfr is None:
            missing.append("egfr_for_metformin_review")
        elif egfr < 30:
            add("METFORMIN_RENAL", "medication_safety", "critical", "urgent", "Metformin renal contraindication flag",
                f"{med_names['metformin']} is recorded with eGFR {egfr:g}, below the label's renal limit of 30. Obtain urgent prescriber review to stop it; the system does not issue a prescription change.", "METFORMIN_LABEL", basis=[egfr_basis, "On metformin"])
        elif egfr < 45:
            add("METFORMIN_REVIEW", "medication_safety", "warning", "soon", "Review metformin with reduced eGFR",
                f"{med_names['metformin']} is recorded with eGFR {egfr:g} (30-44). Review benefit, risk and the current dose, and monitor kidney function more often. Starting metformin is not recommended in this range.", "METFORMIN_LABEL", basis=[egfr_basis, "On metformin"])
    if "glibenclamide" in code_set and age >= 60:
        add("GLIBENCLAMIDE_OLDER_ADULT", "medication_safety", "warning", "soon", "Review glibenclamide in an older adult",
            f"Age {age} on {med_names['glibenclamide']}. The WHO protocol advises avoiding glibenclamide from age 60 because of hypoglycaemia; the Kenya flowchart's sulfonylurea options are gliclazide 40-160 mg or glimepiride 1-4 mg. "
            "Review hypoglycaemia history with the prescriber.", "WHO_HEARTS_MEDS_2018", "KENYA_DM_TREATMENT", basis=[f"Age {age}", "On glibenclamide"])
    if code_set & SULFONYLUREA and egfr is not None and egfr < 60:
        add("SULFONYLUREA_RENAL", "medication_safety", "warning", "soon", "Review sulfonylurea with impaired kidney function",
            f"{listing(named(SULFONYLUREA))} with eGFR {egfr:g}. Reduced kidney function increases hypoglycaemia risk. Ask about hypoglycaemic episodes, meal pattern and monitoring; do not infer a safe dose from this screen.", "NICE_DIABETES_2026", "NCDAI_SAFETY_SPEC", basis=[egfr_basis, "On " + listing(named(SULFONYLUREA))])
    if code_set & (ACE | ARB):
        if pregnant:
            add("RAS_PREGNANCY", "medication_safety", "critical", "urgent", "ACE inhibitor/ARB in pregnancy",
                f"{listing(named(ACE | ARB))} is recorded in pregnancy. Arrange urgent prescriber and obstetric review because of fetal risk. No replacement drug is selected automatically.", "NICE_PREGNANCY", "LISINOPRIL_LABEL", basis=["Pregnant", "On " + listing(named(ACE | ARB))])
        if pregnancy == "unknown":
            missing.append("pregnancy_status_for_RAS_medication_review")
        if egfr is None:
            missing.append("egfr_for_RAS_medication_review")
        if potassium is None:
            missing.append("potassium_for_RAS_medication_review")
    if pregnant and code_set & STATINS:
        add("STATIN_PREGNANCY", "medication_safety", "critical", "urgent", "Statin recorded in pregnancy",
            f"{listing(named(STATINS))} is recorded and statins are contraindicated in pregnancy (NICE 1.5.9). Arrange prescriber review to stop it; do not restart until breastfeeding has finished.",
            "NICE_LIPIDS_NG238", basis=["Pregnant", "On " + listing(named(STATINS))])
    if code_set & ACE and code_set & ARB:
        add("DUAL_RAS", "medication_safety", "warning", "soon", "Combined ACE inhibitor and ARB recorded",
            f"{listing(named(ACE))} and {listing(named(ARB))} are both recorded. Combining an ACE inhibitor with an ARB raises renal, potassium and hypotension risk; reconcile and seek prescriber review to stop one.",
            "LISINOPRIL_LABEL", basis=["On " + listing(named(ACE | ARB)), potassium_basis, egfr_basis])
    if code_set & (ACE | ARB) and "spironolactone" in code_set:
        add("POTASSIUM_MEDICATION_RISK", "medication_safety", "warning", "soon", "Potassium-raising combination",
            f"{listing(named(ACE | ARB))} with {med_names['spironolactone']}" + (f"; latest potassium {potassium:g} mmol/L" if potassium is not None else "; no potassium is recorded") + (f", eGFR {egfr:g}" if egfr is not None else "")
            + ". Verify the indication and arrange regular potassium and kidney-function monitoring; no dose change is inferred.", "LISINOPRIL_LABEL", basis=[potassium_basis, egfr_basis])
    if code_set & NSAID and code_set & (ACE | ARB):
        diuretics = named(THIAZIDE | {"furosemide", "spironolactone"})
        add("NSAID_RENAL", "medication_safety", "warning", "soon", "NSAID with ACE inhibitor/ARB",
            f"{listing(named(NSAID))} with {listing(named(ACE | ARB))}" + (f" and {listing(diuretics)} (the 'triple whammy' for acute kidney injury)" if diuretics else "") + (f"; eGFR {egfr:g}" if egfr is not None else "")
            + ". Review the need for the NSAID, check over-the-counter use and hydration, and arrange supervised medication reconciliation.", "LISINOPRIL_LABEL", basis=["On " + listing(named(NSAID | ACE | ARB)), egfr_basis])
    conflicts = sorted(code_set & allergies)
    conflicts.extend(sorted({c for m, c in zip(meds, codes) if _ingredient(m.get("name")) in allergies} - set(conflicts)))
    if conflicts:
        add("ALLERGY_CONFLICT", "medication_safety", "critical", "urgent", "Medicine overlaps a recorded allergy",
            "Potential exact-match conflict: " + ", ".join(conflicts) + ". Confirm the substance, reaction and severity with a clinician before administration decisions.", "NCDAI_SAFETY_SPEC")
    duplicate = sorted(c for c, count in Counter(codes).items() if count > 1)
    if duplicate:
        add("DUPLICATE_MEDICATION", "medication_safety", "warning", "soon", "Possible duplicate medicine entries",
            "Reconcile duplicate ingredient codes: " + ", ".join(duplicate) + ". Separate schedules may be intentional; never combine doses automatically.", "NCDAI_SAFETY_SPEC")
    unsupported = sorted(code_set - SUPPORTED)
    if unsupported:
        add("MEDICATION_UNSUPPORTED", "medication_safety", "warning", "soon", "Medicines outside the rule dictionary",
            "Manual pharmacist/prescriber review required for: " + ", ".join(med_names[c] for c in unsupported) + ". Absence of an interaction alert does not establish compatibility.", "NCDAI_SAFETY_SPEC")

    # Routine disease review is not allowed to compete with an emergency banner.
    acute = PRIORITY[result["urgency"]] >= PRIORITY["urgent"]
    cvd = cvd_state == "yes"
    # Elective medicine options are withheld whenever the encounter is acute.
    elective = data.get("acutely_unwell") != "yes"
    if not pregnant and not acute:
        use_repeat = rsbp is not None and rdbp is not None
        ctx = {"age": age, "sex": sex, "pregnancy": pregnancy, "meds": [{**m, "_code": c, "_label": med_names[c]} for m, c in zip(meds, codes)], "codes": code_set,
               "control_bp": (rsbp, rdbp) if use_repeat else (sbp, dbp) if sbp is not None and dbp is not None else None,
               "control_is_repeat": use_repeat, "diabetic": diabetic, "renal_disease": renal_disease, "cvd": cvd, "cvd_status": cvd_state,
               "asthma": data.get("known_asthma") == "yes",
               "tobacco": data.get("tobacco_use", "unknown"), "adherence": data.get("adherence", "unknown"),
               "egfr": egfr, "hba1c": hba1c, "glucose": glucose, "glucose_timing": glucose_timing, "weight": weight,
               "total_cholesterol": total_chol, "ldl": ldl, "hdl": hdl, "triglycerides": triglycerides}
        htn_options = hypertension_options(ctx) if hypertensive and elective else []
        grade = "grade 2" if bp_at_least(160, 100) else "grade 1"
        risk = [c for c in comorbid if c in {"diabetes", "chronic kidney disease", "coronary or peripheral arterial disease", "previous stroke or TIA"}]
        next_step = ((" Treatment options for this patient are listed as a separate recommendation." if htn_options else "" if hypertensive else
                      " If hypertension is not yet diagnosed, confirm persistent elevation (SBP ≥140 and/or DBP ≥90 mmHg on repeat readings, the Kenya protocol confirms in the second month) before diagnosing and treating.")
                     + (f" With {listing(risk)} on record, cardiovascular risk is high." if risk else ""))
        if bp_at_least(160, 100):
            add("BP_HIGH", "hypertension", "warning", "soon", "Prompt BP treatment review",
                f"Highest reading {reading(highest_sbp, highest_dbp)} mmHg is in the {grade} hypertension range (≥160/100). Confirm the measurement and review adherence and contraindications without delay; "
                "the Kenya protocol starts medicine for grade 2 hypertension alongside lifestyle changes." + next_step, "KENYA_HTN_STEPS", "WHO_HTN_2021", basis=bp_basis)
        elif bp_at_least(140, 90):
            add("BP_REVIEW", "hypertension", "warning", "soon", "Raised BP needs confirmation and review",
                f"Highest reading {reading(highest_sbp, highest_dbp)} mmHg is in the grade 1 hypertension range (140-159/90-99). Confirm the reading with correct technique and review medicines and adherence." + next_step,
                "KENYA_HTN_STEPS", "WHO_HTN_2021", basis=bp_basis)
        elif hypertensive:
            add("HTN_FOLLOWUP", "hypertension", "info", "routine", "Continue an individualized BP review plan",
                (f"BP {reading(highest_sbp, highest_dbp)} mmHg is at the Kenya target (<140/90)" if highest_sbp is not None else "No BP is recorded at this visit")
                + (f" on {listing(bp_lowering)}" if bp_lowering else "") + ". Continue the current plan; once at target the protocol reviews every 4-6 months, sooner for symptoms such as headache or a persistent cough (ACE inhibitor). "
                "Incomplete data cannot establish control.", "KENYA_HTN_STEPS", basis=[*bp_basis, "Medicines: " + (listing(bp_lowering) or "none recorded")])
        fasting_glucose = glucose if glucose_timing == "fasting" else None
        if hba1c is not None and hba1c >= 6.5 and not diabetic:
            add("DIABETES_CONFIRM", "diabetes", "warning", "soon", "Confirm possible diabetes",
                f"HbA1c {hba1c:g}% meets the diagnostic threshold (≥6.5%). Without classic symptoms, arrange a confirmatory test on a different day (HbA1c or fasting blood sugar) before diagnosing; "
                "HbA1c can be unreliable with anaemia or haemoglobin variants.", "KENYA_DM_DIAGNOSIS", basis=[hba1c_basis, glucose_basis])
        elif fasting_glucose is not None and fasting_glucose >= 7.0 and not diabetic:
            add("DIABETES_CONFIRM", "diabetes", "warning", "soon", "Confirm possible diabetes (fasting glucose)",
                f"Fasting glucose {fasting_glucose:.1f} mmol/L meets the diagnostic threshold (≥7.0). Without classic symptoms, arrange a confirmatory fasting blood sugar or HbA1c on a different day before diagnosing.",
                "KENYA_DM_DIAGNOSIS", basis=[glucose_basis])
        elif glucose is not None and glucose_timing != "fasting" and glucose >= 11.1 and not diabetic:
            add("DIABETES_CONFIRM", "diabetes", "warning", "soon", "Clarify elevated glucose and diagnosis",
                f"{'Random' if glucose_timing == 'random' else 'Unspecified-timing'} glucose {glucose:.1f} mmol/L is ≥11.1. With polyuria, polydipsia or weight loss this supports diabetes; "
                "without symptoms, a confirmatory fasting blood sugar (≥7.0 mmol/L) or HbA1c (≥6.5%) on another day is needed; record it in Laboratory results.", "KENYA_DM_DIAGNOSIS", basis=[glucose_basis])
        elif not diabetic and ((hba1c is not None and 5.7 <= hba1c < 6.5) or (fasting_glucose is not None and 5.6 <= fasting_glucose < 7.0)):
            loss = f" For this patient ({weight:g} kg) that is {weight * 0.05:.0f}-{weight * 0.1:.0f} kg." if weight is not None and bmi is not None and bmi >= 25 else ""
            add("PREDIABETES", "prevention", "info", "routine", "Prediabetes range: lifestyle intervention",
                f"{hba1c_basis if hba1c is not None and 5.7 <= hba1c < 6.5 else glucose_basis} is in the prediabetes range (HbA1c 5.7-6.4% or fasting glucose 5.6-6.9 mmol/L). Advise diet, 30 minutes of physical activity 5 times weekly and sleep hygiene; "
                f"if overweight aim to lose 5-10% of body weight in 12 months.{loss} Repeat HbA1c every 3-6 months. Metformin is considered if BMI is above 35 or there was gestational diabetes"
                + (f" (BMI {bmi:g})." if bmi is not None else "."),
                "KENYA_PREDIABETES", basis=[hba1c_basis, glucose_basis, f"BMI {bmi:g} kg/m²" if bmi is not None else None])
        if diabetic:
            above_target = (hba1c is not None and hba1c >= 7) or (hba1c is None and fasting_glucose is not None and fasting_glucose > 7.2)
            if hba1c is not None:
                status = f"HbA1c {hba1c:g}% is {'%.1f points above' % (hba1c - 7) if hba1c >= 7 else 'within'} the Kenya target (<7.0%). "
            elif fasting_glucose is not None:
                status = f"Fasting glucose {fasting_glucose:.1f} mmol/L is {'above' if fasting_glucose > 7.2 else 'within'} the Kenya fasting target (4.4-7.2). "
            else:
                status = "No HbA1c or fasting glucose is recorded to judge control against the Kenya target (HbA1c <7.0%). "
            add("DIABETES_REVIEW", "diabetes", "warning" if hba1c is not None and hba1c >= 9 else "info",
                "soon" if hba1c is not None and hba1c >= 9 else "routine", "Review diabetes control and complication screening",
                status + ("Treatment options are listed separately. " if above_target and elective else "")
                + (f"Ask about hypoglycaemia on {listing(glucose_lowering)}. " if glucose_lowering else "")
                + "Complication screening: kidney function (eGFR" + (f", last {egfr:g}" if egfr is not None else ", not recorded") + ") and urine albumin, eyes, and feet (pulses, sensation, ulcers).",
                "KENYA_DM_TREATMENT", "NCDAI_SAFETY_SPEC", basis=[hba1c_basis, glucose_basis, egfr_basis, "Glucose-lowering medicines: " + (listing(named({"metformin"} | SULFONYLUREA | SGLT2, test=is_insulin)) or "none recorded")])
        statin_indicated = diabetic or cvd or renal_disease or (total_chol is not None and total_chol >= 8)
        if not statin_indicated and ((hdl is not None and hdl < 0.9) or (triglycerides is not None and triglycerides > 2.82)):
            add("LIPID_RISK_FACTOR", "prevention", "info", "routine", "Abnormal lipids: estimate cardiovascular risk",
                "; ".join(item for item in (f"HDL {hdl:g} mmol/L (below 0.90)" if hdl is not None and hdl < 0.9 else None,
                                            f"Triglycerides {triglycerides:g} mmol/L (above 2.82)" if triglycerides is not None and triglycerides > 2.82 else None) if item)
                + ". These are cardiovascular and diabetes risk factors. Estimate 10-year CVD risk with the WHO chart (age, sex, smoking, systolic BP and cholesterol); a statin is advised above 20%. "
                "Screen for diabetes if not done and advise diet, activity and weight management.",
                "KENYA_DM_SCREENING", "KENYA_CVD_RISK", basis=[f"HDL {hdl:g} mmol/L" if hdl is not None else None, f"Triglycerides {triglycerides:g} mmol/L" if triglycerides is not None else None])
        central = waist is not None and ((sex == "female" and waist >= 90) or (sex == "male" and waist >= 100))
        if (bmi is not None and bmi >= 25) or central:
            goal = ""
            if weight is not None:
                goal = f" A 5-10% loss for this patient is {weight * 0.05:.0f}-{weight * 0.1:.0f} kg over 12 months"
                if height is not None:
                    goal += f"; a BMI below 25 corresponds to under {25 * (height / 100) ** 2:.0f} kg at {height:g} cm"
                goal += "."
            add("WEIGHT_MANAGEMENT", "prevention", "info", "routine",
                f"{'Obesity' if bmi is not None and bmi >= 30 else 'Overweight' if bmi is not None and bmi >= 25 else 'Raised waist circumference'}: agree a weight plan",
                (f"BMI {bmi:g} kg/m² ({bmi_category})" if bmi is not None else "BMI not calculable") + (f", waist {waist:g} cm" + (" (above the Kenya cut-off of " + ("90" if sex == "female" else "100") + " cm)" if central else "") if waist is not None else "") + ". "
                + (f"Weight loss will help lower {listing([c for c in ('blood pressure' if hypertensive else '', 'glucose' if diabetic else '') if c])} and cardiovascular risk. " if hypertensive or diabetic
                   else "Overweight is a diabetes and cardiovascular risk factor; screen for diabetes and estimate CVD risk. ")
                + "Advise reduced salt, sugar and saturated fat and moderate aerobic activity 30 minutes on 5-7 days weekly." + goal + " Record weight at each visit.",
                "KENYA_HTN_LIFESTYLE", "KENYA_DM_SCREENING",
                basis=[f"BMI {bmi:g} kg/m² ({bmi_category})" if bmi is not None else None, f"Weight {weight:g} kg" if weight is not None else None,
                       f"Height {height:g} cm" if height is not None else None, f"Waist {waist:g} cm" if waist is not None else None])
        if elective:
            options = (htn_options + (diabetes_options(ctx) if diabetic else [])
                       + lipid_options(ctx) + respiratory_options(ctx))
            for option in options:
                add(option["rule_id"], option.get("category", "treatment"), option["severity"], option["urgency"], option["title"], option["detail"],
                    *option["sources"], basis=option["basis"])
            if statin_indicated and not code_set & STATINS and cvd_state == "unknown":
                missing.append("known_cvd_for_statin_choice")
        if renal_disease or (egfr is not None and egfr < 60):
            category = None if egfr is None else g_stage(egfr)
            nephrotoxic = named(NSAID)
            add("CKD_REVIEW", "kidney", "warning", "soon", "Review kidney status and chronicity",
                (f"eGFR {egfr:g} (KDIGO category {category})" if egfr is not None else "Known chronic kidney disease with no eGFR recorded") + ("; CKD is recorded" if renal_disease and egfr is not None else "") + ". "
                + ("Repeat eGFR and check urine albumin: CKD requires abnormality for more than 3 months, so compare with previous results and look for acute causes. " if not renal_disease else "Check urine albumin and the trend against previous results. ")
                + (f"Avoid NSAIDs: {listing(nephrotoxic)} is recorded. " if nephrotoxic else "")
                + (f"Review doses of {listing(renal_review)} for this eGFR." if renal_review else ""), "KDIGO_CKD_2024",
                basis=[egfr_basis, "Known CKD" if renal_disease else None, *(["On " + listing(renal_review)] if renal_review else [])])
        if data.get("known_asthma") == "yes" or data.get("known_copd") == "yes":
            if data.get("known_copd") == "yes":
                text = ("COPD recorded" + (f", current inhalers: {listing(inhalers)}" if inhalers else ", no inhaler recorded") + ". Grade by exacerbations and breathlessness (Kenya 6.8): "
                        "group A (0-1 exacerbation a year, breathless only on strenuous exercise or hills) uses a bronchodilator; group B (breathless walking on level ground) uses LABA+LAMA; "
                        "group E (2 or more moderate exacerbations, or 1 hospital admission, a year) uses LABA+LAMA with specialist referral. "
                        + ("Smoking cessation is the most important step for this patient. " if smoker else "") + "Offer influenza, pneumococcal and COVID-19 vaccination and an exercise programme.")
                sources = ("KENYA_COPD",)
            else:
                text = ("Asthma recorded" + (f", current inhalers: {listing(inhalers)}" if inhalers else ", no inhaler recorded") + ". Review symptom frequency, night waking, reliever use and exacerbations to set the Kenya step; "
                        "check inhaler technique, adherence, triggers and a written action plan." + (" Smoking worsens control; offer cessation support." if smoker else ""))
                sources = ("KENYA_ASTHMA",)
            add("RESP_CHRONIC_REVIEW", "respiratory", "info", "soon", "Review chronic respiratory care", text, *sources,
                basis=["Known COPD" if data.get("known_copd") == "yes" else "Known asthma", "Inhalers: " + (listing(inhalers) or "none recorded"), "Current smoker" if smoker else None])
        if data.get("known_cancer") == "yes":
            add("CANCER_SCOPE", "continuity", "info", "soon", "Coordinate with the treating cancer team",
                "Known cancer is recorded. Reconcile the oncology plan, supportive care and pain needs, and referral follow-through; check interactions of " + (listing(named(test=lambda c: True)) or "current medicines") + " with cancer treatment. Cancer staging and treatment are outside this release.",
                "WHO_CANCER_DIAGNOSIS", "NCDAI_SAFETY_SPEC")
        if smoker:
            add("TOBACCO_SUPPORT", "prevention", "info", "routine", "Offer tobacco cessation support",
                "Current tobacco use" + (f" with {listing(comorbid)}, which smoking makes more dangerous" if comorbid else "") + ". Advise stopping clearly, assess readiness, and refer to a cessation programme with pharmacological support where available; record the agreed plan.",
                "KENYA_HTN_LIFESTYLE", "WHO_PEN_2020", basis=["Current smoker", *(["Known " + listing(comorbid)] if comorbid else [])])
        if data.get("adherence") == "missed":
            all_meds = named(test=lambda c: True)
            add("ADHERENCE_REVIEW", "continuity", "info", "soon", "Explore missed medicine use",
                f"Missed doses reported" + (f" across {len(all_meds)} recorded medicine{'s' if len(all_meds) != 1 else ''} ({listing(all_meds)})" if all_meds else "")
                + ". Ask which doses are missed and why (cost, side effects, stock, understanding). Simplify where possible, for example once-daily or single-pill combinations, before adding treatment.",
                "NCDAI_SAFETY_SPEC", "KENYA_HTN_STEPS", basis=["Adherence: missed doses", *(["On " + listing(all_meds)] if all_meds else [])])

    if sbp is None:
        missing.append("systolic_bp")
    if dbp is None:
        missing.append("diastolic_bp")
    if bp_at_least(140, 90) and (rsbp is None or rdbp is None):
        missing.append("repeat_blood_pressure")
    if diabetic and hba1c is None and glucose is None:
        missing.append("glycaemic_measurement")
    if glucose is not None and glucose_timing == "unknown" and not diabetic and glucose >= 5.6:
        missing.append("glucose_context")
    if (diabetic or hypertensive or renal_disease or cvd_state == "yes") and total_chol is None and ldl is None:
        missing.append("lipid_profile")
    if (diabetic or hypertensive) and bmi is None:
        missing.append("weight_and_height")
    if (diabetic or renal_disease) and egfr is None:
        missing.append("egfr")
    if symptoms & {"wheeze", "breathlessness"}:
        if spo2 is None:
            missing.append("oxygen_saturation")
        if rr is None:
            missing.append("respiratory_rate")
    if pregnancy == "unknown":
        missing.append("pregnancy_status")
    for field in ("medications_reviewed", "allergies_reviewed", "symptoms_reviewed"):
        if data.get(field) is not True:
            missing.append(field)
    for field in KNOWN_FIELDS:
        if data.get(field, "unknown") == "unknown":
            missing.append(field)
    if data.get("medicine_availability", "unknown") != "available":
        result["warnings"].append("Confirm medicine stock, cost and access; availability is unverified or limited.")
    if any(m.get("dose") is None or not m.get("unit") or not m.get("frequency") for m in meds):
        result["warnings"].append("One or more medication schedules are incomplete; dose safety has not been evaluated.")
    if calculated_egfr is not None:
        result["warnings"].append(f"eGFR {fmt(calculated_egfr)} mL/min/1.73 m² was calculated from creatinine (CKD-EPI 2021) and used by these rules; confirm the result date and trend.")
    result["warnings"].append("Medication checks are limited to selected ingredients and exact allergy matches; cross-reactivity, all interactions and dose appropriateness are not covered.")
    observed = data.get("observed_at")
    if not observed:
        missing.append("observed_at")
    else:
        try:
            stamp = observed if isinstance(observed, datetime) else datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("Observation time requires a valid timezone and cannot be in the future")
            if datetime.now(timezone.utc) - stamp > timedelta(hours=24):
                result["warnings"].append("Measurements are over 24 hours old. Verify current status; historical danger readings are not discarded.")
                missing.append("current_observations")
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid observation timestamp") from exc
    result["missing_data"] = sorted(set(missing))
    if missing:
        add("DATA_COMPLETENESS", "data_quality", "warning", "soon", "Complete essential assessment information",
            "Still needed for this patient: " + "; ".join(item.replace("_", " ") + (f" ({GAP_REASONS[item]})" if item in GAP_REASONS else "") for item in sorted(set(missing)))
            + ". Unknown, unreviewed and absent findings are distinct. Emergency assessment must not wait for routine documentation.", "NCDAI_SAFETY_SPEC")
    if not recs:
        add("CLINICIAN_REVIEW", "scope", "info", "routine", "Complete clinician review",
            "No configured high-priority rule triggered from the supplied structured fields. Review the patient and full record; this screen does not establish safety or exclude disease.", "NCDAI_SAFETY_SPEC")
    recs.sort(key=lambda rec: (SEVERITY[rec["severity"]], rec["rule_id"]))
    result["summary"] = {
        "emergency": "Immediate clinician assessment and the appropriate emergency pathway are advised.",
        "urgent": "Same-day clinician assessment is advised; act now for low glucose or evolving symptoms.",
        "soon": "Clinician review and completion of identified checks are advised; timing needs clinical confirmation.",
        "routine": "Complete the supervised NCD review and agree follow-up; this result does not provide clinical clearance.",
    }[result["urgency"]]
    from .care_plan import build as build_care_plan
    result["care_plan"] = build_care_plan({**data, "egfr": egfr, "glucose": glucose, "glucose_unit": "mmol/L"}, age, sex, [{**m, "_code": c, "_label": str(m.get("name") or c)} for m, c in zip(meds, codes)], result)
    from .dosing import attach_dosing
    from .reasoning import build as build_consultant
    result = attach_dosing(result, data, age, sex)
    # Consultant synthesis reads the final urgency; it never changes findings.
    result["consultant"] = build_consultant(data, age, sex, result)
    return result
