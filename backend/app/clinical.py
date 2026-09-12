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

RULESET_VERSION = "ncdai-2-rules-0.1.2"

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
            "Proposed rules require independent clinician signoff. Synthetic development use only.",
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

    def add(rule_id, category, severity, urgency, title, detail, *sources):
        if any(r["rule_id"] == rule_id for r in recs):
            raise RuntimeError("Duplicate rule identifier")
        recs.append({"id": rule_id, "rule_id": rule_id, "category": category,
                     "severity": severity, "title": title, "detail": detail,
                     "evidence": evidence(*sources)})
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
    symptoms = set(data.get("symptoms") or [])
    meds = data.get("medications") or []
    codes = [_ingredient(m.get("code")) for m in meds]
    code_set = set(codes)
    allergies = {_ingredient(a) for a in data.get("allergies") or []}
    pregnancy = data.get("pregnancy_status", "unknown")
    if pregnancy not in {"yes", "no", "unknown", "not_applicable"}:
        raise ValueError("Unrecognized pregnancy status")
    for field in (*KNOWN_FIELDS, "acutely_unwell", "acute_kidney_injury"):
        if data.get(field, "unknown") not in {"yes", "no", "unknown"}:
            raise ValueError(f"Unrecognized {field} status")
    pregnant = pregnancy == "yes"
    diabetic = data.get("known_diabetes") == "yes"
    hypertensive = data.get("known_hypertension") == "yes"
    renal_disease = data.get("known_ckd") == "yes"
    # Use all readings independently. Do not silently average away a danger sign.
    highest_sbp = max((v for v in (sbp, rsbp) if v is not None), default=None)
    highest_dbp = max((v for v in (dbp, rdbp) if v is not None), default=None)

    def bp_at_least(s, d):
        return (highest_sbp is not None and highest_sbp >= s) or (highest_dbp is not None and highest_dbp >= d)

    if symptoms & ACUTE_SYMPTOMS:
        add("EMERGENCY_SYMPTOMS", "acute_safety", "critical", "emergency", "Immediate acute assessment",
            "Recorded acute warning symptoms need immediate clinician assessment and the local emergency pathway. Normal BP or glucose cannot rule out an emergency.",
            "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC")
    if any(v is not None and v <= 90 for v in (sbp, rsbp)):
        add("LOW_BP", "acute_safety", "warning", "urgent", "Low systolic BP needs assessment",
            "Assess perfusion, symptoms, medicines and change from baseline now; verify the measurement. This is an isolated vital-sign flag, not a shock diagnosis or NEWS2 score.", "RCP_NEWS2", "NCDAI_SAFETY_SPEC")
    if pulse is not None and (pulse <= 40 or pulse >= 131):
        add("PULSE_EXTREME", "acute_safety", "warning", "urgent", "Marked pulse abnormality",
            "Confirm pulse, assess symptoms and rhythm, and obtain prompt clinical review. The complete early-warning assessment is outside this screen.", "RCP_NEWS2", "NCDAI_SAFETY_SPEC")
    if rr is not None and rr <= 8:
        add("RESP_SLOW", "acute_safety", "critical", "emergency", "Very low respiratory rate",
            "Obtain immediate clinical assessment of airway, breathing and consciousness. This flag does not determine the cause or treatment.", "RCP_NEWS2", "NCDAI_SAFETY_SPEC")
    if bp_at_least(180, 110) and symptoms & BP_DANGER_SYMPTOMS:
        add("BP_CRISIS", "acute_safety", "critical", "emergency", "Severe BP with warning symptoms",
            "Assess possible acute organ injury immediately. Repeat BP when feasible without delaying urgent care; this alert does not diagnose a hypertensive emergency.",
            "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC")
    elif bp_at_least(180, 110):
        add("BP_SEVERE", "hypertension", "critical", "urgent", "Severe blood pressure reading",
            "Arrange same-day clinical assessment for organ injury, repeat measurement and a supervised management plan. Symptoms not documented cannot be assumed absent.",
            "WHO_HTN_2021", "NCDAI_SAFETY_SPEC")
    if pregnant:
        add("PREGNANCY_SCOPE", "scope", "warning", "urgent", "Use the pregnancy care pathway",
            "Obtain obstetric review. Adult non-pregnancy NCD treatment logic is withheld; maternal and fetal assessment require a separate approved pathway.",
            "NICE_PREGNANCY", "WHO_HTN_2021")
        if bp_at_least(160, 110):
            add("PREGNANCY_SEVERE_BP", "acute_safety", "critical", "emergency", "Severe BP in pregnancy",
                "Activate immediate obstetric assessment for this severe reading. Repeat promptly without delaying escalation.", "NICE_PREGNANCY")
        elif symptoms & BP_DANGER_SYMPTOMS:
            add("PREGNANCY_WARNING", "acute_safety", "critical", "emergency", "Pregnancy warning symptoms",
                "Promptly assess possible pregnancy complications using the obstetric emergency pathway, even when BP is unavailable or below the severe threshold.",
                "NICE_PREGNANCY", "NCDAI_SAFETY_SPEC")
    if glucose is not None and glucose <= 3.9 + 1e-9:
        danger = glucose < 3 or bool(symptoms & {"confusion", "seizure"})
        add("HYPOGLYCEMIA", "acute_safety", "critical", "emergency" if danger else "urgent", "Low glucose requires action now",
            f"Glucose is {glucose:.2f} mmol/L. Assess consciousness and treat immediately through the local hypoglycaemia protocol; recheck and investigate the cause. No automatic dose or route is generated.",
            "KENYA_NCD_PROTOCOLS", "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC")
    elif "hypoglycemia_symptoms" in symptoms:
        add("SUSPECTED_HYPOGLYCEMIA", "acute_safety", "warning", "urgent", "Assess reported hypoglycaemia symptoms now",
            "Check a current glucose and clinical state. A missing or older normal result does not resolve these symptoms; follow the local acute assessment protocol.", "KENYA_NCD_PROTOCOLS")
        missing.append("current_glucose_for_symptoms")
    if glucose is not None and glucose >= 18:
        crisis = bool(symptoms & {"vomiting", "dehydration", "confusion"})
        add("HYPERGLYCEMIC_CRISIS" if crisis else "GLUCOSE_HIGH", "acute_safety", "critical", "emergency" if crisis else "urgent",
            "Assess possible hyperglycaemic crisis" if crisis else "Markedly elevated glucose",
            "Obtain acute clinical assessment, hydration status and ketones where available. Laboratory and clinical assessment must establish the cause; no insulin or fluid dose is generated.",
            "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC")
    if code_set & SGLT2 and symptoms & {"vomiting", "dehydration"}:
        add("SGLT2_ACUTE_ILLNESS", "medication_safety", "critical", "urgent", "Acute illness with an SGLT2 inhibitor",
            "Assess for ketoacidosis, including when glucose is not markedly high. Obtain urgent clinician medication review and ketone assessment; a normal glucose cannot provide clearance.", "SGLT2_LABEL", "NCDAI_SAFETY_SPEC")
    if spo2 is not None and spo2 < 95:
        add("RESP_HYPOXEMIA", "respiratory", "critical" if spo2 < 92 else "warning", "emergency" if spo2 < 92 else "urgent",
            "Low oxygen saturation needs assessment",
            f"Recorded SpO2 is {spo2:g}%. Check signal quality and assess immediately if below 92%. Confirm baseline, oxygen use and clinical state; this tool does not set an oxygen dose or target.",
            "WHO_PEN_2020", "NCDAI_SAFETY_SPEC")
    if rr is not None and rr > 25:
        add("RESP_TACHYPNEA", "respiratory", "warning", "urgent", "Raised respiratory rate",
            "Assess respiratory effort and acute causes now; a chronic respiratory diagnosis must not obscure other causes of rapid breathing.", "WHO_PEN_2020", "NCDAI_SAFETY_SPEC")
    if "wheeze" in symptoms:
        add("RESP_WHEEZE", "respiratory", "warning", "urgent", "Assess current wheeze",
            "Evaluate exacerbation severity, oxygenation and the existing action plan. Review alternative diagnoses and arrange supervised acute management.", "WHO_PEN_2020")
    if "hemoptysis" in symptoms:
        add("HEMOPTYSIS", "referral", "warning", "urgent", "Assess coughing blood today",
            "Establish bleeding amount, stability and respiratory status, and investigate infection including TB and other causes. Escalate immediately if unstable; no cancer diagnosis is inferred.", "NCI_CANCER_SYMPTOMS", "NCDAI_SAFETY_SPEC")
    if symptoms & {"unexplained_weight_loss", "persistent_cough", "breast_lump", "abnormal_bleeding"}:
        add("CANCER_WARNING", "referral", "warning", "urgent" if "abnormal_bleeding" in symptoms else "soon", "Arrange diagnostic assessment of warning symptoms",
            "Confirm symptom duration, bleeding severity, examination findings and relevant risk history; establish a tracked diagnostic/referral plan. These symptoms can have non-cancer causes, including infection.", "NCI_CANCER_SYMPTOMS", "WHO_CANCER_DIAGNOSIS")
    if egfr is not None and egfr < 30:
        add("RENAL_SEVERE", "kidney", "critical", "urgent", "Severely reduced kidney function",
            "Arrange prompt clinical assessment and referral planning; assess acute deterioration, urine output and previous results. A single result cannot establish chronicity.", "WHO_HEARTS_D_2020", "KDIGO_CKD_2024")
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
        detail += " Assess clinical state, ECG needs, sample validity and medicines. Unknown acute illness or kidney injury must be assessed now; if present, consider hospital assessment today. No potassium-lowering dose is generated."
        add("POTASSIUM_HIGH", "acute_safety", "critical" if potassium >= 6 or acute else "warning",
            "emergency" if potassium >= 6.5 else "urgent" if potassium >= 6 or acute else "soon",
            "Elevated potassium", detail, "UKKA_POTASSIUM_2026")
    if potassium is not None and potassium < 3.5:
        add("POTASSIUM_LOW", "acute_safety", "critical" if potassium < 3 else "warning",
            "emergency" if potassium < 2.5 else "urgent" if potassium < 3 else "soon", "Reduced potassium",
            "Review symptoms, ECG, medicines and magnesium. Below 2.5 mmol/L requires immediate supervised assessment; no electrolyte replacement dose is generated.", "NHS_LOW_POTASSIUM")
    if "foot_ulcer" in symptoms:
        add("FOOT_ULCER", "referral", "warning", "urgent", "Assess foot ulcer and limb risk",
            "Assess infection, perfusion and systemic illness today. Infection, gangrene or critical ischaemia warrants urgent referral; absence of these findings has not been established.", "WHO_HEARTS_D_2020", "NCDAI_SAFETY_SPEC")
    if "metformin" in code_set:
        if egfr is None:
            missing.append("egfr_for_metformin_review")
        elif egfr < 30:
            add("METFORMIN_RENAL", "medication_safety", "critical", "urgent", "Metformin renal contraindication flag",
                "Recorded eGFR is below the metformin label's renal limit. Obtain urgent prescriber review of current therapy; the system does not issue a prescription change.", "METFORMIN_LABEL")
        elif egfr < 45:
            add("METFORMIN_REVIEW", "medication_safety", "warning", "soon", "Review metformin with reduced eGFR",
                "Review benefit, risk and monitoring of existing metformin therapy. Initiation is not recommended in this renal range by the referenced label.", "METFORMIN_LABEL")
    if "glibenclamide" in code_set and age >= 60:
        add("GLIBENCLAMIDE_OLDER_ADULT", "medication_safety", "warning", "soon", "Review glibenclamide in an older adult",
            "The referenced WHO protocol advises avoiding glibenclamide from age 60. Review the current regimen and hypoglycaemia risk with the prescriber.", "WHO_HEARTS_MEDS_2018")
    if code_set & SULFONYLUREA and egfr is not None and egfr < 60:
        add("SULFONYLUREA_RENAL", "medication_safety", "warning", "soon", "Review sulfonylurea with impaired kidney function",
            "Renal impairment can increase hypoglycaemia risk. Review the exact medicine, prior episodes, eating pattern and monitoring; do not infer a safe dose from this screen.", "NICE_DIABETES_2026", "NCDAI_SAFETY_SPEC")
    if code_set & (ACE | ARB):
        if pregnant:
            add("RAS_PREGNANCY", "medication_safety", "critical", "urgent", "ACE inhibitor/ARB in pregnancy",
                "Arrange urgent prescriber and obstetric review of the recorded renin-angiotensin-system medicine because of fetal risk. No replacement drug is selected automatically.", "NICE_PREGNANCY", "LISINOPRIL_LABEL")
        if pregnancy == "unknown":
            missing.append("pregnancy_status_for_RAS_medication_review")
        if egfr is None:
            missing.append("egfr_for_RAS_medication_review")
        if potassium is None:
            missing.append("potassium_for_RAS_medication_review")
    if code_set & ACE and code_set & ARB:
        add("DUAL_RAS", "medication_safety", "warning", "soon", "Combined ACE inhibitor and ARB recorded",
            "Reconcile both medicines and seek prescriber review for renal, potassium and hypotension risk.", "LISINOPRIL_LABEL")
    if code_set & (ACE | ARB) and "spironolactone" in code_set:
        add("POTASSIUM_MEDICATION_RISK", "medication_safety", "warning", "soon", "Potassium-raising combination",
            "Verify indication, kidney function and potassium monitoring for this combination; no dose change is inferred.", "LISINOPRIL_LABEL")
    if code_set & NSAID and code_set & (ACE | ARB):
        add("NSAID_RENAL", "medication_safety", "warning", "soon", "NSAID with ACE inhibitor/ARB",
            "Review renal risk, hydration and non-prescription medicines. Concurrent diuretic use adds concern; arrange supervised medication reconciliation.", "LISINOPRIL_LABEL")
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
            "Manual pharmacist/prescriber review required for: " + ", ".join(unsupported) + ". Absence of an interaction alert does not establish compatibility.", "NCDAI_SAFETY_SPEC")

    # Routine disease review is not allowed to compete with an emergency banner.
    acute = PRIORITY[result["urgency"]] >= PRIORITY["urgent"]
    if not pregnant and not acute:
        if bp_at_least(160, 100):
            add("BP_HIGH", "hypertension", "warning", "soon", "Prompt BP treatment review",
                "Confirm measurement and arrange clinician review without delay, including adherence and contraindications. Do not derive a new prescription from this reading alone.", "WHO_HTN_2021")
        elif bp_at_least(140, 90):
            add("BP_REVIEW", "hypertension", "warning", "soon", "Raised BP needs confirmation and review",
                "Confirm the reading and previous diagnosis; review the care plan, medicines and adherence with the clinician.", "WHO_HTN_2021")
        elif hypertensive:
            add("HTN_FOLLOWUP", "hypertension", "info", "routine", "Continue an individualized BP review plan",
                "Review the agreed target, tolerability and follow-up timing. Diabetes or kidney/CV disease may change targets; incomplete data cannot establish control.", "WHO_HTN_2021")
        if hba1c is not None and hba1c >= 6.5 and not diabetic:
            add("DIABETES_CONFIRM", "diabetes", "warning", "soon", "Confirm possible diabetes",
                "Review diagnostic context and confirmatory testing; do not diagnose from this value alone, particularly where HbA1c reliability is uncertain.", "KENYA_NCD_PROTOCOLS")
        elif glucose is not None and glucose >= 11.1 and not diabetic:
            add("DIABETES_CONFIRM", "diabetes", "warning", "soon", "Clarify elevated glucose and diagnosis",
                "Establish fasting/random status, symptoms and confirmatory testing. A single unspecified glucose measurement is not a diagnosis.", "KENYA_NCD_PROTOCOLS")
        if diabetic:
            add("DIABETES_REVIEW", "diabetes", "warning" if hba1c is not None and hba1c >= 9 else "info",
                "soon" if hba1c is not None and hba1c >= 9 else "routine", "Review diabetes control and complication screening",
                "Review the individualized glycaemic goal, hypoglycaemia, adherence, kidney/eye/foot checks and follow-up. A high HbA1c prompts review, not automatic intensification.", "KENYA_NCD_PROTOCOLS", "NCDAI_SAFETY_SPEC")
        if renal_disease or (egfr is not None and egfr < 60):
            add("CKD_REVIEW", "kidney", "warning", "soon", "Review kidney status and chronicity",
                "Check prior eGFR, urine albumin and possible acute causes; confirm persistent abnormality rather than labeling one low result as CKD.", "KDIGO_CKD_2024")
        if data.get("known_asthma") == "yes" or data.get("known_copd") == "yes":
            add("RESP_CHRONIC_REVIEW", "respiratory", "info", "soon", "Review chronic respiratory care",
                "Confirm diagnosis with appropriate testing, inhaler technique, adherence, triggers, exacerbation history and a written action plan.", "WHO_PEN_2020")
        if data.get("known_cancer") == "yes":
            add("CANCER_SCOPE", "continuity", "info", "soon", "Coordinate with the treating cancer team",
                "Reconcile the oncology plan, supportive care needs and referral follow-through. Cancer staging and treatment are outside this release.", "WHO_CANCER_DIAGNOSIS", "NCDAI_SAFETY_SPEC")
        if data.get("tobacco_use") == "current":
            add("TOBACCO_SUPPORT", "prevention", "info", "routine", "Offer tobacco cessation support",
                "Discuss readiness and access to a locally approved cessation service and document the agreed support plan.", "WHO_PEN_2020")
        if data.get("adherence") == "missed":
            add("ADHERENCE_REVIEW", "continuity", "info", "soon", "Explore missed medicine use",
                "Discuss barriers, affordability, adverse effects and understanding before treatment changes; agree a feasible plan with the patient.", "NCDAI_SAFETY_SPEC", "WHO_HTN_2021")

    if sbp is None:
        missing.append("systolic_bp")
    if dbp is None:
        missing.append("diastolic_bp")
    if bp_at_least(140, 90) and (rsbp is None or rdbp is None):
        missing.append("repeat_blood_pressure")
    if diabetic and hba1c is None and glucose is None:
        missing.append("glycaemic_measurement")
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
            "Review the missing-data list. Unknown, unreviewed and absent findings are distinct. Emergency assessment must not wait for routine documentation.", "NCDAI_SAFETY_SPEC")
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
    from .dosing import attach_dosing
    return attach_dosing(result, data, age, sex)
