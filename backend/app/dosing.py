"""Bounded, deterministic Kenyan starting-dose references, never prescriptions.

No network, model inference, unit guessing, renal interpolation or free-text
parsing participates. A reference is withheld outside the documented population.
See docs/dosing-engine.md for source conflicts and conservative scope policies.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import hashlib
import json

from .dosing_schemas import DosingInput
from .evidence import evidence

DOSING_VERSION = "ncdai-dose-reference-0.2.0"
KENYA_PDF_SHA256 = "e836eef61b8739db399e5af9ce75754b7836bf84693130f41bfa3107c27f78e8"
SCOPE_NOTE = (
    "Kenya MOH starting and maximum doses for selected single-ingredient oral medicines, not prescriptions. "
    "No automatic titration, renal adjustment, insulin, oncology or paediatric dosing. "
    "The initial scope excludes age 65+, frailty, pregnancy, breastfeeding, organ impairment, "
    "acute illness, recorded allergies and medicines outside this small interaction catalogue. "
    "A clinician must select the medicine and review its complete product information."
)

# Numeric facts transcribed from visually inspected MOH PDF pages25/44.
# Product labels qualify eligibility; they do not silently replace Kenya doses.
_MEDICINES = {
    "amlodipine_tablet": dict(name="Amlodipine", ingredient="amlodipine", indication="hypertension", formulation="Single-ingredient tablet", initial=5, maximum=10, per_dose_max=10, frequencies=[1], label="AMLODIPINE_LABEL", page=16,
        checks="Review small body size, frailty, hepatic disease, severe aortic stenosis, hypotension and interacting medicines.",
        monitoring="Review blood pressure, dizziness and oedema; clinician determines follow-up and any titration."),
    "losartan_tablet": dict(name="Losartan", ingredient="losartan", indication="hypertension", formulation="Single-ingredient potassium-salt tablet", initial=50, maximum=100, per_dose_max=100, frequencies=[1], label="LOSARTAN_LABEL", page=16,
        checks="Review pregnancy/plans for pregnancy, volume depletion, renal artery disease, angioedema, potassium supplements/salt substitutes and renin-angiotensin-system medicines.",
        monitoring="Arrange blood pressure, creatinine/eGFR and potassium follow-up after initiation or changes under the local protocol."),
    "lisinopril_tablet": dict(name="Lisinopril", ingredient="lisinopril", indication="hypertension", formulation="Single-ingredient tablet", initial=10, maximum=40, per_dose_max=40, frequencies=[1], label="LISINOPRIL_LABEL", page=16,
        checks="Review pregnancy/plans for pregnancy, prior/hereditary angioedema, renal artery disease, volume depletion, potassium supplements and sacubitril/valsartan exposure within 36 hours.",
        monitoring="Arrange blood pressure, creatinine/eGFR and potassium follow-up; urgent assessment is required for swelling suggesting angioedema."),
    "metformin_ir_tablet": dict(name="Metformin (immediate release)", ingredient="metformin", indication="type_2_diabetes", formulation="Single-ingredient immediate-release tablet only", initial=500, maximum=2000, per_dose_max=1000, frequencies=[1, 2], label="METFORMIN_LABEL", page=35,
        checks="Review metabolic acidosis, hypoxia, alcohol excess, liver disease, acute illness, surgery/fasting and recent or planned iodinated contrast. Extended-release and combination products are excluded.",
        monitoring="Take with food; clinician directs gradual titration according to tolerance, glucose, renal function and vitamin B12 monitoring needs."),
}
# Further Table 4 rows with an unambiguous once-daily start and maximum (PDF page 25,
# verified 2026-09-17 against the same SHA256). Kenya values only; no product label
# is substituted. Enalapril (range/divided), captopril (divided), perindopril (salt
# ambiguity) and nifedipine (no maximum) remain excluded.
_CCB = dict(indication="hypertension", page=16, label=None,
            checks="Review small body size, frailty, hepatic disease, severe aortic stenosis, hypotension and interacting medicines (including strong CYP3A4 inhibitors and grapefruit juice).",
            monitoring="Review blood pressure, dizziness, oedema, headache and palpitations; clinician determines follow-up and any titration.")
_DIURETIC = dict(indication="hypertension", page=16, label=None,
                 checks="Review gout, previous hyponatraemia or hypokalaemia, diabetes control, lithium and NSAID use, and pregnancy or plans for pregnancy.",
                 monitoring="Check sodium, potassium, creatinine and glucose after starting and at follow-up; Table 4 lists hypokalaemia, hyponatraemia, hyperuricaemia and hyperglycaemia.")
_ACE = dict(indication="hypertension", page=16, label=None,
            checks="Review pregnancy/plans for pregnancy, prior/hereditary angioedema, renal artery disease, volume depletion, potassium supplements/salt substitutes and sacubitril/valsartan exposure within 36 hours.",
            monitoring="Arrange blood pressure, creatinine/eGFR and potassium follow-up; cough is common and swelling suggesting angioedema needs urgent assessment.")
_ARB = dict(indication="hypertension", page=16, label=None,
            checks="Review pregnancy/plans for pregnancy, volume depletion, renal artery disease, angioedema history, potassium supplements/salt substitutes and other renin-angiotensin-system medicines.",
            monitoring="Arrange blood pressure, creatinine/eGFR and potassium follow-up after initiation or changes under the local protocol.")
for _key, _name, _ingredient, _form, _initial, _maximum, _group in [
    ("felodipine_pr_tablet", "Felodipine (prolonged release)", "felodipine", "Single-ingredient prolonged-release tablet", 5, 10, _CCB),
    ("hydrochlorothiazide_tablet", "Hydrochlorothiazide", "hydrochlorothiazide", "Single-ingredient tablet", 12.5, 25, _DIURETIC),
    ("chlorthalidone_tablet", "Chlorthalidone", "chlorthalidone", "Single-ingredient tablet", 25, 50, _DIURETIC),
    ("indapamide_ir_tablet", "Indapamide (2.5 mg immediate release)", "indapamide", "Single-ingredient 2.5 mg immediate-release tablet only (not 1.5 mg modified release)", 2.5, 5, _DIURETIC),
    ("ramipril_capsule", "Ramipril", "ramipril", "Single-ingredient capsule or tablet", 2.5, 10, _ACE),
    ("candesartan_tablet", "Candesartan", "candesartan", "Single-ingredient candesartan cilexetil tablet", 8, 32, _ARB),
    ("irbesartan_tablet", "Irbesartan", "irbesartan", "Single-ingredient tablet", 150, 300, _ARB),
    ("telmisartan_tablet", "Telmisartan", "telmisartan", "Single-ingredient tablet", 40, 80, _ARB),
    ("valsartan_tablet", "Valsartan", "valsartan", "Single-ingredient tablet", 80, 160, _ARB),
]:
    _MEDICINES[_key] = dict(name=_name, ingredient=_ingredient, formulation=_form, initial=_initial, maximum=_maximum,
                            per_dose_max=_maximum, frequencies=[1], **_group)
RAS_INGREDIENTS = {"losartan", "lisinopril", "ramipril", "candesartan", "irbesartan", "telmisartan", "valsartan"}
POTASSIUM_GATED = RAS_INGREDIENTS | {"hydrochlorothiazide", "chlorthalidone", "indapamide"}
MANIFEST_SHA256 = hashlib.sha256(json.dumps(_MEDICINES, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def catalogue():
    return {"version": DOSING_VERSION, "manifest_sha256": MANIFEST_SHA256, "scope_note": SCOPE_NOTE,
            "medicines": [{"medicine_id": key, "name": m["name"], "indication": m["indication"],
                           "formulation": m["formulation"], "route": "oral", "unit": "mg",
                           "clinical_checks": m["checks"]} for key, m in _MEDICINES.items()]}


def _recent(value, now, period):
    if not value:
        return False
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.tzinfo is not None and -timedelta(minutes=5) <= now - stamp <= period
    except (ValueError, TypeError):
        return False


def evaluate_dosing(data: dict, age: int, sex: str, urgency: str, *, now=None):
    inputs = DosingInput.model_validate({k: data[k] for k in ("dosing_requests", "dosing_context") if k in data})
    now = now or datetime.now(timezone.utc)
    ctx = inputs.dosing_context
    results = []
    all_requested = {r.medicine_id for r in inputs.dosing_requests}
    current = {str(m.get("code", "")) for m in data.get("medications", [])}
    allowed_ingredients = {m["ingredient"] for m in _MEDICINES.values()}
    for request in inputs.dosing_requests:
        codes, reasons = [], []

        def block(code, reason):
            if code not in codes:
                codes.append(code)
                reasons.append(reason)

        item = _MEDICINES.get(request.medicine_id)
        proposed = None if request.proposed_dose_mg is None else Decimal(str(request.proposed_dose_mg)) * request.frequency_per_day
        result = {"medicine_id": request.medicine_id, "name": item["name"] if item else request.medicine_id,
                  "status": "blocked", "reasons": reasons, "reason_codes": codes, "reference": None,
                  "proposed_daily_mg": float(proposed) if proposed is not None else None,
                  "evidence": [], "source_pdf_sha256": KENYA_PDF_SHA256}
        results.append(result)
        if item is None:
            block("unsupported_medicine", "This medicine/formulation has no configured dose reference. Obtain a verified formulary review.")
            continue
        sources = evidence("KENYA_DOSES_HTN" if item["page"] == 16 else "KENYA_DOSES_DM", *([item["label"]] if item["label"] else []))
        result["evidence"] = sources
        if request.indication != item["indication"]:
            block("indication_mismatch", "Selected indication does not match this medicine reference.")
        history = "known_hypertension" if item["indication"] == "hypertension" else "known_diabetes"
        if data.get(history) != "yes":
            block("unconfirmed_indication", "Confirm the relevant diagnosis; this module does not diagnose or choose treatment.")
        if isinstance(age, bool) or not isinstance(age, int) or not 18 <= age < 65:
            block("age_outside_scope", "This initial reference scope is age 18–64; individualized dosing review is required outside it.")
        if urgency in {"urgent", "emergency"} or data.get("symptoms"):
            block("acute_assessment", "Resolve symptoms or urgent clinical assessment before elective starting-dose support.")
        for field in ("medications_reviewed", "allergies_reviewed", "symptoms_reviewed"):
            if data.get(field) is not True:
                block(field, "Complete " + field.replace("_", " ") + " before requesting a dose reference.")
        for field in ("acutely_unwell", "acute_kidney_injury"):
            if data.get(field) != "no":
                block(field, "Confirm absence of " + field.replace("_", " ") + "; otherwise use individualized dosing review.")
        if data.get("allergies"):
            block("allergy_history", "Recorded allergy history requires individual medicine/excipient and cross-reactivity review; no dose is cleared here.")
        if data.get("pregnancy_status") not in {"no", "not_applicable"}:
            block("pregnancy", "Pregnancy or uncertain pregnancy status is outside this dosing scope.")
        if ctx.breastfeeding not in {"no", "not_applicable"}:
            block("breastfeeding", "Breastfeeding or uncertain breastfeeding status requires individualized review.")
        for field in ("hepatic_impairment", "acute_illness", "dialysis", "frailty"):
            if getattr(ctx, field) != "no":
                block(field, "Confirm absence of " + field.replace("_", " ") + "; otherwise use individualized dosing review.")
        if not ctx.contraindications_reviewed:
            block("contraindications_reviewed", "Review the medicine-specific contraindication checklist and complete product information.")
        if not ctx.interactions_reviewed:
            block("interactions_reviewed", "Review prescribed, over-the-counter, traditional medicines and supplements for interactions.")
        if data.get("known_ckd") != "no" or data.get("egfr") is None or data["egfr"] < 60:
            block("renal_scope", "This starting-dose module requires no known CKD and eGFR at least 60 mL/min/1.73 m². It does not calculate renal adjustments.")
        if not _recent(ctx.renal_observed_at, now, timedelta(days=7)):
            block("renal_result_time", "Verify the renal result date; this initial implementation requires a result within seven days.")
        if not _recent(data.get("observed_at"), now, timedelta(hours=24)):
            block("observation_time", "Current clinical observations within 24 hours are required for this reference check.")
        if data.get("systolic_bp") is None or data.get("diastolic_bp") is None:
            block("blood_pressure_missing", "Record current blood pressure before using starting-dose support.")
        elif min(data["systolic_bp"], data.get("repeat_systolic_bp") or data["systolic_bp"]) < 100 or min(data["diastolic_bp"], data.get("repeat_diastolic_bp") or data["diastolic_bp"]) < 60:
            block("low_blood_pressure", "Low recorded blood pressure requires individual review; the dose reference is withheld.")
        if data.get("medicine_availability") != "available":
            block("availability", "Confirm availability of the exact single-ingredient formulation.")
        if data.get("known_cancer") == "yes":
            block("complex_care", "Coordinate medicine initiation with the treating cancer team.")
        if current - allowed_ingredients:
            block("unmapped_interaction", "One or more current medicines are outside this dose interaction catalogue; pharmacist review is required.")
        if len(current) != len(data.get("medications", [])):
            block("duplicate_medication", "Reconcile duplicate current-medicine entries before a dose reference is supplied.")
        if any(m.get("dose") is None or not m.get("unit") or not m.get("frequency") for m in data.get("medications", [])):
            block("incomplete_medication", "Complete all current medication schedules before dose support.")
        if any(str(m.get("name", "")).strip().lower() != m.get("code") for m in data.get("medications", [])):
            block("ambiguous_medication", "Current medicine names must match the catalogue ingredient codes; resolve brand, combination or formulation ambiguity.")
        if item["ingredient"] in current:
            block("existing_therapy", "This medicine is already recorded. Regimen changes and duplicate initiation are outside this starting-dose scope.")
        if item["ingredient"] in POTASSIUM_GATED:
            kind = "RAS-medicine" if item["ingredient"] in RAS_INGREDIENTS else "diuretic"
            if not _recent(ctx.potassium_observed_at, now, timedelta(days=7)):
                block("potassium_result_time", "Verify the potassium result date separately; this initial implementation requires it within seven days.")
            if data.get("potassium") is None or not 3.5 <= data["potassium"] <= 5.0:
                block("potassium", f"A verified potassium result from 3.5 to 5.0 mmol/L is required for this bounded {kind} reference.")
        if item["ingredient"] in RAS_INGREDIENTS:
            requested_ras = {_MEDICINES[r]["ingredient"] for r in all_requested if r in _MEDICINES} & RAS_INGREDIENTS
            if (RAS_INGREDIENTS & current) or len(requested_ras) > 1:
                block("dual_ras", "ACE inhibitor/ARB combination or duplicate RAS therapy requires prescriber review; no starting dose is supplied.")
        if request.medicine_id == "metformin_ir_tablet" and data.get("hba1c") is None and data.get("glucose") is None:
            block("glycaemic_measurement", "Record a glycaemic measurement and individualized treatment goal.")
        if reasons:
            continue
        outside = proposed is not None and (
            request.frequency_per_day not in item["frequencies"] or
            Decimal(str(request.proposed_dose_mg)) < item["initial"] or
            Decimal(str(request.proposed_dose_mg)) > item["per_dose_max"] or proposed > item["maximum"])
        if outside:
            result["status"] = "outside_reference"
            block("outside_reference", "The proposed dose or frequency is outside the configured Kenya reference. Verify it with the prescriber; do not administer on the strength of this check.")
        else:
            result["status"] = "reference"
            result["reference"] = {"initial_dose_mg": item["initial"], "frequency_per_day": 1, "max_daily_mg": item["maximum"]}
        result["clinical_checks"] = item["checks"]
        result["monitoring"] = item["monitoring"]
    return {"version": DOSING_VERSION, "manifest_sha256": MANIFEST_SHA256,
            "scope_note": SCOPE_NOTE, "results": deepcopy(results)}


def attach_dosing(assessment, data, age, sex):
    dosing = evaluate_dosing(data, age, sex, assessment["urgency"])
    assessment["dosing"] = dosing
    for item in dosing["results"]:
        rule_id = "DOSE_" + item["medicine_id"].upper()
        ref = item["reference"]
        detail = " ".join(item["reasons"])
        if ref:
            detail = (f"Kenya starting reference: {ref['initial_dose_mg']} mg orally once daily; "
                      f"configured daily ceiling {ref['max_daily_mg']} mg. This is not an instruction to start or increase treatment. "
                      + item["clinical_checks"] + " " + item["monitoring"])
        if item["proposed_daily_mg"] is not None:
            detail += f" Proposed schedule totals {item['proposed_daily_mg']:g} mg/day; a range check does not establish dose appropriateness."
        assessment["recommendations"].append({"id": rule_id, "rule_id": rule_id, "category": "dosing",
            "severity": "info" if ref else "warning", "title": f"{item['name']}: " + ("dose reference for clinician review" if ref else "dose reference withheld"),
            "detail": detail, "evidence": item["evidence"] or evidence("KENYA_NCD_PROTOCOLS")})
    return assessment
