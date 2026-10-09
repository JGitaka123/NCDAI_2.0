"""Deterministic consultant-physician synthesis of one structured encounter.

Turns validated observations into what a consultant physician writes after a
clinic review: a patient-specific one-line summary, derived measures (eGFR by
CKD-EPI 2021, KDIGO G/A stage and risk, BMI, 10-year CVD risk, CHA2DS2-VA), a
prioritised problem list with individual targets, a stepwise guideline-linked
plan, a medication review, diagnostic considerations, monitoring and follow-up.

Boundaries: no network, no model inference and no free-text interpretation.
Plans name drug classes and guideline steps for the clinician to decide; they
never prescribe, never set doses and never lower the urgency set by the safety
rules. Blank inputs stay unknown and are reported as data gaps, never assumed
normal. frontend/mobile/engine.js is a line-for-line port held to identical
output by backend/tests/test_engine_parity.py; change both together.
"""

import math
import re

from .evidence import evidence

REASONING_VERSION = "ncdai-consultant-1.1.0-review"

ALIASES = {"glyburide": "glibenclamide", "hctz": "hydrochlorothiazide", "albuterol": "salbutamol",
           "frusemide": "furosemide", "acetylsalicylic": "aspirin", "asa": "aspirin"}
ACEI = {"lisinopril", "enalapril", "ramipril", "captopril", "perindopril"}
ARB = {"losartan", "valsartan", "candesartan", "telmisartan", "irbesartan", "olmesartan"}
DHP_CCB = {"amlodipine", "nifedipine", "felodipine"}
NONDHP_CCB = {"diltiazem", "verapamil"}
THIAZIDE = {"hydrochlorothiazide", "chlorthalidone", "indapamide", "bendroflumethiazide"}
LOOP = {"furosemide", "torasemide", "bumetanide"}
MRA = {"spironolactone", "eplerenone"}
BB_SELECTIVE = {"bisoprolol", "atenolol", "metoprolol", "nebivolol"}
BB_NONSELECTIVE = {"propranolol", "carvedilol", "labetalol"}
BB_HF = {"bisoprolol", "carvedilol", "metoprolol", "nebivolol"}
OTHER_AHT = {"methyldopa", "hydralazine", "doxazosin", "prazosin", "clonidine"}
STATIN = {"atorvastatin", "rosuvastatin", "simvastatin", "pravastatin"}
ANTIPLATELET = {"aspirin", "clopidogrel"}
ANTICOAG = {"warfarin", "rivaroxaban", "apixaban", "dabigatran", "edoxaban"}
SULFONYLUREA = {"glibenclamide", "gliclazide", "glimepiride"}
SGLT2 = {"empagliflozin", "dapagliflozin", "canagliflozin"}
GLP1 = {"liraglutide", "semaglutide", "dulaglutide", "exenatide"}
DPP4 = {"sitagliptin", "linagliptin", "saxagliptin", "vildagliptin"}
INSULIN = {"insulin", "glargine", "detemir", "degludec", "aspart", "lispro", "glulisine", "isophane", "mixtard", "actrapid"}
ICS = {"budesonide", "beclometasone", "beclomethasone", "fluticasone", "mometasone", "ciclesonide"}
LABA = {"formoterol", "salmeterol", "vilanterol", "indacaterol", "olodaterol"}
LAMA = {"tiotropium", "umeclidinium", "glycopyrronium"}
SABA = {"salbutamol", "terbutaline"}
NSAID = {"ibuprofen", "diclofenac", "naproxen", "celecoxib", "indomethacin", "meloxicam", "piroxicam", "ketoprofen"}
STATUS_ORDER = {"acute": 0, "uncontrolled": 1, "untreated": 1, "above_target": 1, "high_risk": 1, "review": 2, "unconfirmed": 2,
                "needs_confirmation": 2, "at_risk": 3, "needs_data": 3, "established": 3, "withheld": 3, "at_target": 4}
KDIGO_RISK = {"G1": ["low", "moderate", "high"], "G2": ["low", "moderate", "high"],
              "G3a": ["moderate", "high", "very high"], "G3b": ["high", "very high", "very high"],
              "G4": ["very high", "very high", "very high"], "G5": ["very high", "very high", "very high"]}
KDIGO_FREQ = {"G1": [1, 1, 2], "G2": [1, 1, 2], "G3a": [1, 2, 3], "G3b": [2, 3, 3], "G4": [3, 3, 4], "G5": [4, 4, 4]}
FRAMINGHAM = {
    "female_lipid": {"age": 2.32888, "tc": 1.20904, "hdl": -0.70833, "sbp_u": 2.76157, "sbp_t": 2.82263, "smoke": 0.52873, "dm": 0.69154, "s0": 0.95012, "mean": 26.1931},
    "male_lipid": {"age": 3.06117, "tc": 1.12370, "hdl": -0.93263, "sbp_u": 1.93303, "sbp_t": 1.99881, "smoke": 0.65451, "dm": 0.57367, "s0": 0.88936, "mean": 23.9802},
    "female_bmi": {"age": 2.72107, "bmi": 0.51125, "sbp_u": 2.81291, "sbp_t": 2.88267, "smoke": 0.61868, "dm": 0.77763, "s0": 0.94833, "mean": 26.0145},
    "male_bmi": {"age": 3.11296, "bmi": 0.79277, "sbp_u": 1.85508, "sbp_t": 1.92672, "smoke": 0.70953, "dm": 0.53160, "s0": 0.88431, "mean": 23.9388},
}


def r1(value):
    return math.floor(value * 10 + 0.5) / 10


def fmt(value):
    rounded = r1(value)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:.1f}"


def fmt0(value):
    return str(int(math.floor(value + 0.5)))


def join(items):
    items = list(items)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def cap(text):
    return text[:1].upper() + text[1:]


def normal(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def unique(values):
    out = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def ckd_epi_2021(creatinine_umol, age, sex):
    """Race-free 2021 CKD-EPI creatinine equation; None when sex is not female/male."""
    if sex not in ("female", "male") or creatinine_umol is None:
        return None
    scr = creatinine_umol / 88.4
    kappa, alpha = (0.7, -0.241) if sex == "female" else (0.9, -0.302)
    ratio = scr / kappa
    value = 142 * math.pow(min(ratio, 1), alpha) * math.pow(max(ratio, 1), -1.2) * math.pow(0.9938, age)
    return value * 1.012 if sex == "female" else value


def g_stage(egfr):
    if egfr >= 90:
        return "G1"
    if egfr >= 60:
        return "G2"
    if egfr >= 45:
        return "G3a"
    if egfr >= 30:
        return "G3b"
    if egfr >= 15:
        return "G4"
    return "G5"


def a_stage(acr):
    return "A1" if acr < 3 else "A2" if acr <= 30 else "A3"


def framingham(model, age, sbp, treated, smoker, diabetic, tc=None, hdl=None, bmi=None):
    c = FRAMINGHAM[model]
    total = c["age"] * math.log(age) + (c["sbp_t"] if treated else c["sbp_u"]) * math.log(sbp)
    total += (c["smoke"] if smoker else 0) + (c["dm"] if diabetic else 0)
    if "tc" in c:
        total += c["tc"] * math.log(tc * 38.67) + c["hdl"] * math.log(hdl * 38.67)
    else:
        total += c["bmi"] * math.log(bmi)
    return 1 - math.pow(c["s0"], math.exp(total - c["mean"]))


def build(data, age, sex, assessment):
    """Return the consultant synthesis for one assessed encounter (pure function)."""

    def num(key, low, high):
        value = data.get(key)
        if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = float(value)
        return value if math.isfinite(value) and low <= value <= high else None

    def tri(key):
        value = data.get(key, "unknown")
        return value if value in ("yes", "no", "unknown") else "unknown"

    context = data.get("dosing_context") or {}
    frail = context.get("frailty") == "yes"
    pregnant = data.get("pregnancy_status") == "yes"
    woman_childbearing = sex == "female" and age < 50 and not pregnant
    sex_word = {"female": "woman", "male": "man"}.get(sex, "adult")
    urgency = assessment.get("urgency", "routine")
    critical_titles = [rec["title"] for rec in assessment.get("recommendations", []) if rec.get("severity") == "critical"]

    # ---- medicines -------------------------------------------------------
    meds = data.get("medications") or []
    med_ingredients = []
    for med in meds:
        found = set()
        for raw in (med.get("code"), med.get("name")):
            code = normal(raw)
            if not code:
                continue
            found.add(ALIASES.get(code, code))
            for token in code.split("_"):
                found.add(ALIASES.get(token, token))
        med_ingredients.append(found)
    taking = set()
    for found in med_ingredients:
        taking |= found

    def on(group):
        return bool(taking & group)

    def dose_of(ingredient):
        for med, found in zip(meds, med_ingredients):
            dose = med.get("dose")
            if ingredient in found and isinstance(dose, (int, float)) and not isinstance(dose, bool) and normal(med.get("unit")) == "mg":
                return float(dose)
        return None

    def names(group):
        return sorted(taking & group)

    ras = on(ACEI | ARB)
    classes = []
    for label, group in (("ACE inhibitor/ARB", ACEI | ARB), ("calcium-channel blocker", DHP_CCB | NONDHP_CCB),
                         ("thiazide-like diuretic", THIAZIDE), ("beta-blocker", BB_SELECTIVE | BB_NONSELECTIVE),
                         ("mineralocorticoid antagonist", MRA), ("loop diuretic", LOOP), ("other antihypertensive", OTHER_AHT)):
        if on(group):
            classes.append(label)
    on_bp_treatment = bool(classes)
    insulin = on(INSULIN)
    sulfonylurea = on(SULFONYLUREA)

    # ---- measurements ----------------------------------------------------
    sbp, dbp = num("systolic_bp", 40, 300), num("diastolic_bp", 20, 200)
    rsbp, rdbp = num("repeat_systolic_bp", 40, 300), num("repeat_diastolic_bp", 20, 200)
    readings = [(s, d) for s, d in ((sbp, dbp), (rsbp, rdbp)) if s is not None and d is not None]
    mean_sbp = sum(s for s, _ in readings) / len(readings) if readings else None
    mean_dbp = sum(d for _, d in readings) / len(readings) if readings else None
    pulse = num("pulse", 20, 250)
    spo2 = num("oxygen_saturation", 1, 100)
    hba1c = num("hba1c", 2, 25)
    glucose = num("glucose", 0.01, 1500)
    if glucose is not None:
        glucose = glucose / 18.0 if data.get("glucose_unit") == "mg/dL" else glucose
    glucose_context = data.get("glucose_context", "unknown")
    potassium = num("potassium", 1, 10)
    creatinine = num("creatinine_umol", 10, 3000)
    entered_egfr = num("egfr", 0, 200)
    calculated_egfr = ckd_epi_2021(creatinine, age, sex)
    egfr = entered_egfr if entered_egfr is not None else calculated_egfr
    acr = num("urine_acr_mg_mmol", 0, 3000)
    weight, height, waist = num("weight_kg", 20, 350), num("height_cm", 100, 250), num("waist_cm", 40, 250)
    bmi = weight / ((height / 100) ** 2) if weight is not None and height is not None else None
    tc, hdl, ldl = num("total_cholesterol_mmol", 1, 20), num("hdl_mmol", 0.2, 5), num("ldl_mmol", 0.2, 15)
    hb = num("hemoglobin_g_dl", 3, 25)
    anaemia = hb is not None and hb < (12 if sex == "female" else 13)
    hypos = data.get("hypoglycaemia_episodes_3m")
    hypos = hypos if isinstance(hypos, int) and not isinstance(hypos, bool) else None
    exacerbations = data.get("exacerbations_past_year")
    exacerbations = exacerbations if isinstance(exacerbations, int) and not isinstance(exacerbations, bool) else None
    reliever = data.get("reliever_use_per_week")
    reliever = reliever if isinstance(reliever, int) and not isinstance(reliever, bool) else None
    symptoms = set(data.get("symptoms") or [])
    smoker = data.get("tobacco_use") == "current"

    diabetic = tri("known_diabetes") == "yes"
    hypertensive = tri("known_hypertension") == "yes"
    ascvd = tri("known_ascvd") == "yes"
    stroke = tri("prior_stroke_tia") == "yes"
    any_ascvd = ascvd or stroke
    heart_failure = tri("known_heart_failure") == "yes"
    af = tri("known_atrial_fibrillation") == "yes"
    asthma = tri("known_asthma") == "yes"
    copd = tri("known_copd") == "yes"
    ckd_markers = (egfr is not None and egfr < 60) or (acr is not None and acr >= 3)
    ckd = tri("known_ckd") == "yes" or ckd_markers
    albuminuria = acr is not None and acr >= 3

    derived, problems, med_review, considerations, monitoring, gaps = [], [], [], [], [], []
    used_sources = []

    def cite(*sources):
        for source in sources:
            if source not in used_sources:
                used_sources.append(source)
        return list(sources)

    def item(text, *sources):
        return {"text": text, "source_ids": cite(*sources)}

    def derive(did, label, value, unit, interpretation, method, *sources):
        derived.append({"id": did, "label": label, "value": value, "unit": unit,
                        "interpretation": interpretation, "method": method, "source_ids": cite(*sources)})

    def monitor(mid, test, timing, reason, *sources):
        if not any(entry["id"] == mid for entry in monitoring):
            monitoring.append({"id": mid, "test": test, "timing": timing, "reason": reason, "source_ids": cite(*sources)})

    def gap(field, why):
        if not any(entry["field"] == field for entry in gaps):
            gaps.append({"field": field, "why": why})

    def review(rid, severity, finding, action, *sources):
        med_review.append({"id": rid, "severity": severity, "finding": finding, "action": action, "source_ids": cite(*sources)})

    def consider(cid, text, *sources):
        considerations.append({"id": cid, "text": text, "source_ids": cite(*sources)})

    def add_problem(pid, title, status, facts, summary, plan, targets=()):
        sources = []
        for entry in plan:
            sources.extend(entry["source_ids"])
        problems.append({"id": pid, "title": title, "status": status, "facts": list(facts), "assessment": summary,
                         "plan": plan, "targets": list(targets), "source_ids": unique(sources)})

    pregnancy_note = ("Confirm pregnancy status and contraception first: ACE inhibitors, ARBs, statins and SGLT2 inhibitors are avoided in pregnancy."
                      if woman_childbearing else None)

    # ---- derived measures --------------------------------------------------
    if mean_sbp is not None:
        label = "Mean of 2 readings" if len(readings) == 2 else "Single reading"
        derive("bp_mean", "Office blood pressure", f"{fmt0(mean_sbp)}/{fmt0(mean_dbp)}", "mmHg", label,
               "Arithmetic mean of paired readings entered today", "ISH_HTN_2020")
    if calculated_egfr is not None:
        derive("egfr_ckd_epi", "eGFR (calculated)", fmt(calculated_egfr), "mL/min/1.73 m²",
               ("Used for this assessment" if entered_egfr is None else f"Entered eGFR {fmt(entered_egfr)} used; calculated value shown for cross-check"),
               f"CKD-EPI 2021 from creatinine {fmt(creatinine)} µmol/L, age {age}, {sex}", "CKD_EPI_2021")
    elif creatinine is not None:
        gap("sex", "CKD-EPI 2021 needs recorded female or male sex to calculate eGFR from creatinine.")
    if hba1c is not None:
        derive("hba1c_ifcc", "HbA1c (IFCC)", fmt0((hba1c - 2.15) * 10.929), "mmol/mol", f"Equivalent of {fmt(hba1c)}% (NGSP)",
               "IFCC = (NGSP − 2.15) × 10.929", "ADA_SOC_2025")
    if bmi is not None:
        category = ("underweight" if bmi < 18.5 else "healthy range" if bmi < 25 else "overweight" if bmi < 30
                    else "obesity class I" if bmi < 35 else "obesity class II" if bmi < 40 else "obesity class III")
        derive("bmi", "Body-mass index", fmt(bmi), "kg/m²", cap(category), "Weight ÷ height²", "WHO_OBESITY")
    if waist is not None and sex in ("female", "male"):
        high, very_high = (80, 88) if sex == "female" else (94, 102)
        risk = "substantially increased" if waist >= very_high else "increased" if waist >= high else "not increased"
        derive("waist", "Waist circumference", fmt(waist), "cm", f"Metabolic risk {risk}", f"WHO thresholds {high}/{very_high} cm", "WHO_OBESITY")
    if tc is not None and hdl is not None:
        derive("non_hdl", "Non-HDL cholesterol", fmt(tc - hdl), "mmol/L", "Total minus HDL cholesterol", "TC − HDL", "ESC_LIPIDS_2019")
    stage_g = g_stage(egfr) if egfr is not None else None
    stage_a = a_stage(acr) if acr is not None else None
    kidney_risk = KDIGO_RISK[stage_g][int(stage_a[1]) - 1] if stage_g and stage_a else None
    if stage_g and (ckd or stage_a):
        stage = stage_g + (stage_a or "")
        interpretation = (f"KDIGO risk: {kidney_risk}" if kidney_risk else "Albuminuria category unknown: measure urine ACR")
        derive("kdigo", "Kidney stage (KDIGO)", stage, "", interpretation,
               f"eGFR {fmt(egfr)}" + (f", ACR {fmt(acr)} mg/mmol" if acr is not None else ""), "KDIGO_CKD_2024_TX")

    # ---- cardiovascular risk -------------------------------------------------
    risk = {"category": None, "basis": "", "percent": None, "method": None, "statement": "", "source_ids": []}
    diabetes_organ_damage = diabetic and (albuminuria or (egfr is not None and egfr < 60))
    major_factors = sum([hypertensive or on_bp_treatment, smoker, bmi is not None and bmi >= 30,
                         tc is not None and tc >= 5.2, age >= 50])
    if any_ascvd:
        risk.update(category="very high", basis="established atherosclerotic cardiovascular disease",
                    source_ids=cite("ESC_LIPIDS_2019", "WHO_HEARTS_RISK_2020"))
    elif diabetes_organ_damage or (diabetic and major_factors >= 3):
        risk.update(category="very high", basis="diabetes with " + ("kidney target-organ damage" if diabetes_organ_damage else "three or more major risk factors"),
                    source_ids=cite("ESC_LIPIDS_2019"))
    elif egfr is not None and egfr < 30:
        risk.update(category="very high", basis="severe chronic kidney disease", source_ids=cite("ESC_LIPIDS_2019"))
    elif diabetic:
        risk.update(category="high", basis="diabetes", source_ids=cite("ESC_LIPIDS_2019", "WHO_HEARTS_RISK_2020"))
    elif egfr is not None and egfr < 60:
        risk.update(category="high", basis="moderate chronic kidney disease", source_ids=cite("ESC_LIPIDS_2019"))
    elif (tc is not None and tc >= 8) or (ldl is not None and ldl >= 4.9):
        risk.update(category="high", basis="markedly raised cholesterol (possible familial hypercholesterolaemia)", source_ids=cite("ESC_LIPIDS_2019"))
    if risk["category"] is None or risk["category"] != "very high":
        model = None
        if (sex in ("female", "male") and 30 <= age <= 74 and mean_sbp is not None and not any_ascvd
                and data.get("tobacco_use") in {"current", "former", "never"}):
            if tc is not None and hdl is not None:
                model = sex + "_lipid"
            elif bmi is not None:
                model = sex + "_bmi"
        if model:
            value = framingham(model, age, mean_sbp, on_bp_treatment, smoker, diabetic, tc, hdl, bmi)
            percent = r1(value * 100)
            method = "Framingham 2008 general CVD, " + ("laboratory (cholesterol)" if model.endswith("lipid") else "office (BMI)") + " model"
            risk.update(percent=percent, method=method)
            cite("FRAMINGHAM_2008", "WHO_CVD_RISK_2019")
            if risk["category"] is None:
                category = "high" if percent >= 20 else "moderate" if percent >= 10 else "low"
                risk.update(category=category, basis=f"estimated 10-year risk {fmt(percent)}%",
                            source_ids=["FRAMINGHAM_2008", "WHO_CVD_RISK_2019"])
        elif risk["category"] is None and (age >= 40 or hypertensive or diabetic or smoker or ckd or on_bp_treatment):
            if mean_sbp is None:
                gap("systolic_bp", "Blood pressure is required to estimate cardiovascular risk.")
            if not (tc is not None and hdl is not None) and bmi is None:
                gap("total_cholesterol_mmol", "Total and HDL cholesterol (or weight and height for the office model) are required to estimate cardiovascular risk.")
    if risk["category"]:
        text = f"{cap(risk['category'])} cardiovascular risk ({risk['basis']})"
        if risk["percent"] is not None and not risk["basis"].startswith("estimated"):
            text += f"; estimated 10-year risk {fmt(risk['percent'])}%"
        if risk["percent"] is not None:
            text += ". Framingham is not calibrated for Kenya; cross-check with the WHO Eastern sub-Saharan Africa chart"
        risk["statement"] = text + "."
        derive("cvd_risk", "Cardiovascular risk", cap(risk["category"]),
               "", risk["basis"] + (f"; 10-year risk {fmt(risk['percent'])}%" if risk["percent"] is not None and not risk["basis"].startswith("estimated") else ""),
               risk["method"] or "Risk category from established disease (no calculator applies)", *risk["source_ids"])
    high_risk = risk["category"] in ("high", "very high")

    # ---- pregnancy ---------------------------------------------------------
    if pregnant:
        add_problem("pregnancy", "Pregnancy: obstetric-medicine pathway", "withheld",
                    [f"Pregnancy recorded; age {age}"],
                    "Chronic-disease treatment reasoning is withheld. Blood pressure, glucose and medicine decisions in pregnancy use pregnancy-specific thresholds and a different drug list.",
                    [item("Review every current medicine for pregnancy safety today: ACE inhibitors, ARBs, statins, SGLT2 inhibitors and most oral glucose-lowering agents other than metformin are generally avoided.", "NICE_PREGNANCY"),
                     item("Arrange joint obstetric and physician care for any hypertension, diabetes or kidney disease.", "NICE_PREGNANCY")])

    # ---- hypertension ------------------------------------------------------
    if not pregnant and (mean_sbp is not None or hypertensive):
        elderly = age >= 80 or frail
        if elderly:
            target, target_text = (140, 90), "<140/90 mmHg, individualised for age 80+ or frailty; avoid orthostatic symptoms"
        elif any_ascvd or diabetic or ckd or high_risk:
            target, target_text = (130, 80), "<130/80 mmHg (WHO 2021 systolic <130 with CVD, diabetes, CKD or high risk)"
        else:
            target, target_text = (140, 90), "<140/90 mmHg (WHO 2021); aim for <130/80 if well tolerated (ISH 2020, ESC 2024)"
        hsrc = ("WHO_HTN_2021", "ISH_HTN_2020", "ESC_HTN_2024")
        if mean_sbp is None:
            add_problem("hypertension", "Hypertension", "needs_data", ["Known hypertension", "No blood pressure recorded today"],
                        "Control cannot be judged without a current reading.",
                        [item("Measure seated BP twice, 1–2 minutes apart, with a validated device and correctly sized cuff.", *hsrc)], [target_text])
            gap("systolic_bp", "Needed to judge hypertension control.")
        else:
            bp_text = f"{fmt0(mean_sbp)}/{fmt0(mean_dbp)} mmHg"
            facts = ["BP " + "; ".join(f"{fmt0(s)}/{fmt0(d)}" for s, d in readings) + " mmHg" + (f" (mean {bp_text})" if len(readings) > 1 else "")]
            facts.append("On " + (join(classes) if classes else "no antihypertensive class"))
            if data.get("adherence") == "missed":
                facts.append("Missed doses reported")
            above = mean_sbp >= target[0] or mean_dbp >= target[1]
            if not (hypertensive or on_bp_treatment):
                # Diagnosis uses the 140/90 threshold; treatment targets apply after diagnosis.
                above = mean_sbp >= 140 or mean_dbp >= 90
            severe = mean_sbp >= 180 or mean_dbp >= 110
            plan = []
            if severe:
                status = "acute"
                summary = f"Severe hypertension ({bp_text}). The safety findings govern today's action: assess for acute organ damage before any chronic plan."
                plan.append(item("Assess for hypertension-mediated organ damage now (chest pain, breathlessness, neurological signs, visual change, fundi, urine dipstick, creatinine, ECG).", "WHO_HTN_2021", "ESC_HTN_2024"))
            elif above and (hypertensive or on_bp_treatment):
                status = "uncontrolled"
                gap_s = mean_sbp - target[0]
                summary = f"Above target at {bp_text} (target {target_text.split(' (')[0].split(',')[0]}); systolic {fmt0(max(gap_s, 0))} mmHg above the systolic goal on {len(classes)} antihypertensive class{'es' if len(classes) != 1 else ''}."
            elif above:
                status = "unconfirmed"
                summary = f"Raised BP ({bp_text}) without a recorded hypertension diagnosis."
            elif hypertensive or on_bp_treatment:
                status = "at_target"
                summary = f"At target ({bp_text}) on {join(classes) if classes else 'no recorded medicine'}."
            elif mean_sbp >= 130 or mean_dbp >= 85 or (high_risk and mean_dbp >= 80):
                status = "at_risk"
                summary = f"High-normal BP ({bp_text})."
            else:
                status = None
                summary = ""
            if status == "unconfirmed":
                plan.append(item("Confirm the diagnosis: repeat readings on a separate day, or home/ambulatory BP where available, before labelling hypertension (WHO 2021 recommends confirmation on two visits).", "WHO_HTN_2021", "ISH_HTN_2020"))
                if mean_sbp >= 160 or mean_dbp >= 100 or high_risk:
                    plan.append(item("Once confirmed, start drug treatment promptly" + (" because cardiovascular risk is high" if high_risk else " because BP is ≥160/100") + "; WHO 2021 favours initial combination therapy, ideally a single-pill combination.", "WHO_HTN_2021"))
                else:
                    plan.append(item("If confirmed at ≥140/90 mmHg, start drug treatment alongside lifestyle measures (WHO 2021).", "WHO_HTN_2021"))
                plan.append(item("Baseline work-up: creatinine/eGFR, potassium, urine ACR or dipstick, glucose/HbA1c, lipids and ECG.", "WHO_HTN_2021", "KENYA_NCD_PROTOCOLS"))
            if status == "uncontrolled":
                if data.get("adherence") == "missed":
                    plan.append(item("Address adherence before escalating: explore cost, side-effects, pill burden and beliefs; a single-pill combination and once-daily dosing help.", "WHO_HTN_2021", "ISH_HTN_2020"))
                plan.append(item("Confirm with correctly measured seated readings and, where available, home or ambulatory BP to exclude a white-coat effect before escalating.", "ISH_HTN_2020", "ESC_HTN_2024"))
                has_ccb, has_thiazide = on(DHP_CCB | NONDHP_CCB), on(THIAZIDE)
                ras_reason = ("albuminuria" if albuminuria else "chronic kidney disease") if (albuminuria or ckd) and not ras and not heart_failure else None
                if heart_failure:
                    plan.append(item("In heart failure, first optimise the disease-modifying drugs (ACE inhibitor/ARB/ARNI, beta-blocker, MRA); add amlodipine if BP stays high and avoid diltiazem or verapamil.", "ESC_HF_2021", "ESC_HTN_2024"))
                elif not classes:
                    plan.append(item("Start treatment with a combination from ACE inhibitor/ARB, dihydropyridine CCB and thiazide-like diuretic classes, ideally as a single-pill combination, following the Kenya MOH step sequence.", "WHO_HTN_2021", "KENYA_NCD_PROTOCOLS"))
                elif len(classes) == 1:
                    options = [label for label, present in (("ACE inhibitor/ARB", ras), ("dihydropyridine CCB", has_ccb), ("thiazide-like diuretic", has_thiazide)) if not present]
                    if ras_reason:
                        plan.append(item(f"Add an ACE inhibitor or ARB as the second class (also indicated for {ras_reason}; see kidney plan) rather than only up-titrating monotherapy.", "ISH_HTN_2020", "KDIGO_CKD_2024_TX"))
                        ras_reason = None
                    else:
                        plan.append(item(f"Add a second class ({' or '.join(options)}) rather than only up-titrating monotherapy; preferred pairs are ACE inhibitor/ARB + CCB or CCB + thiazide-like diuretic.", "ISH_HTN_2020", "WHO_HTN_2021"))
                elif not (ras and has_ccb and has_thiazide):
                    missing = [label for label, present in (("ACE inhibitor/ARB", ras), ("dihydropyridine CCB", has_ccb), ("thiazide-like diuretic", has_thiazide)) if not present]
                    plan.append(item(f"Move to the guideline triple combination by adding {join(missing)} (ACE inhibitor/ARB + CCB + thiazide-like diuretic)" + (f"; the ACE inhibitor/ARB is also indicated for {ras_reason}." if ras_reason else "."), "ISH_HTN_2020", "ESC_HTN_2024"))
                    ras_reason = None
                else:
                    plan.append(item("This meets the definition of apparent resistant hypertension if doses are optimised: check adherence, measurement, salt/alcohol intake and interfering drugs (NSAIDs, steroids, oestrogens).", "ISH_HTN_2020", "ESC_HTN_2024"))
                    if potassium is not None and potassium <= 4.5 and (egfr is None or egfr >= 45):
                        plan.append(item(f"Fourth-line: add spironolactone (potassium {fmt(potassium)} mmol/L" + (f", eGFR {fmt(egfr)}" if egfr is not None else ", check eGFR first") + "); recheck potassium and creatinine within 2–4 weeks.", "ISH_HTN_2020", "ESC_HTN_2024"))
                    else:
                        plan.append(item("Fourth-line spironolactone needs potassium ≤4.5 mmol/L and eGFR ≥45; otherwise use a beta-blocker or alpha-blocker and seek specialist advice.", "ISH_HTN_2020", "ESC_HTN_2024"))
                    plan.append(item("Screen for secondary causes, starting with the aldosterone-renin ratio, kidney disease and sleep apnoea.", "ENDO_PA_2016", "ESC_HTN_2024"))
                if ras_reason:
                    plan.append(item(f"Include an ACE inhibitor or ARB given {ras_reason}, titrated to the maximum tolerated dose.", "KDIGO_CKD_2024_TX", "KDIGO_DM_CKD_2022", "ISH_HTN_2020"))
                if not classes:
                    plan.append(item("For patients of African ancestry, ISH 2020 advises starting with a CCB plus thiazide-like diuretic, or an ARB plus CCB; ACE-inhibitor monotherapy lowers BP less.", "ISH_HTN_2020"))
            if status in ("uncontrolled", "unconfirmed") and pregnancy_note and (not ras):
                plan.append(item(pregnancy_note, "NICE_PREGNANCY"))
            if status in ("uncontrolled", "unconfirmed", "at_risk"):
                lifestyle = "Lifestyle: salt below 5 g/day, regular physical activity, limit alcohol"
                if bmi is not None and bmi >= 25:
                    lifestyle += f", and weight reduction (BMI {fmt(bmi)})"
                plan.append(item(lifestyle + ".", "WHO_HTN_2021", "ISH_HTN_2020"))
            if status == "at_risk":
                plan.append(item("Recheck BP at least annually" + ("; with high cardiovascular risk, ESC 2024 supports drug treatment if BP stays ≥130/80 after 3 months of lifestyle change." if high_risk else "."), "ESC_HTN_2024"))
            if status == "at_target":
                plan.append(item("Continue the current regimen; review every 3–6 months with adherence and side-effect check.", "WHO_HTN_2021"))
                if mean_sbp < 110 and (age >= 65 or frail):
                    status = "review"
                    summary = f"Low treated BP ({bp_text}) in an older or frail adult."
                    plan.append(item("Ask about dizziness and falls, check standing BP, and consider reducing treatment if symptomatic.", "ESC_HTN_2024"))
            if status:
                if age < 40 and (hypertensive or above):
                    consider("secondary_htn_young", f"Hypertension at age {age}: screen for secondary causes (kidney disease, primary aldosteronism, renovascular disease, thyroid disease, drugs).", "ESC_HTN_2024", "ENDO_PA_2016")
                if potassium is not None and potassium < 3.5 and (hypertensive or above):
                    consider("primary_aldosteronism", f"Hypertension with potassium {fmt(potassium)} mmol/L" + (" (on a diuretic)" if on(THIAZIDE | LOOP) else " (no diuretic recorded)") + ": screen for primary aldosteronism with an aldosterone-renin ratio after correcting potassium.", "ENDO_PA_2016")
                if status in ("uncontrolled", "unconfirmed", "acute"):
                    monitor("bp_review", "Blood pressure", "Every 2–4 weeks after each change until at target, then every 3–6 months", "Titration to target", "WHO_HTN_2021")
                add_problem("hypertension", "Hypertension" if (hypertensive or on_bp_treatment) else "Raised blood pressure", status, facts, summary, plan, [target_text])

    # ---- diabetes ----------------------------------------------------------
    if not pregnant:
        dsrc = ("ADA_SOC_2025",)
        diag_facts = []
        if hba1c is not None:
            diag_facts.append(f"HbA1c {fmt(hba1c)}% ({fmt0((hba1c - 2.15) * 10.929)} mmol/mol)")
        if glucose is not None:
            diag_facts.append(f"{'Fasting' if glucose_context == 'fasting' else 'Random' if glucose_context == 'random' else 'Timing-unspecified'} glucose {fmt(glucose)} mmol/L")
        if diabetic:
            relaxed = frail or age >= 75 or (egfr is not None and egfr < 30) or ((hypos or 0) > 0 and (insulin or sulfonylurea))
            target = 8.0 if relaxed else 7.0
            target_text = ("HbA1c <8.0% (64 mmol/mol), individualised for " + join([reason for reason, present in (
                ("frailty", frail), (f"age {age}", age >= 75), ("advanced CKD", egfr is not None and egfr < 30),
                ("recent hypoglycaemia", (hypos or 0) > 0 and (insulin or sulfonylurea))) if present])
                if relaxed else "HbA1c <7.0% (53 mmol/mol) for most adults without hypoglycaemia")
            glucose_drugs = [name for name in names(SULFONYLUREA | SGLT2 | GLP1 | DPP4 | {"metformin", "pioglitazone"})]
            if insulin:
                glucose_drugs.append("insulin")
            facts = diag_facts + ["On " + (join(glucose_drugs) if glucose_drugs else "no glucose-lowering medicine recorded")]
            if hypos:
                facts.append(f"{hypos} hypoglycaemia episode{'s' if hypos != 1 else ''} in 3 months")
            plan = []
            if hba1c is None:
                status = "needs_data"
                summary = "Glycaemic control cannot be judged without an HbA1c."
                plan.append(item("Measure HbA1c now, then every 3 months until at target and 6-monthly once stable.", *dsrc))
                gap("hba1c", "Needed to judge diabetes control.")
            elif hba1c > target:
                status = "above_target"
                summary = f"HbA1c {fmt(hba1c)}% is {fmt(hba1c - target)} points above the individual target of <{target:.1f}%" + (f" on {join(glucose_drugs)}." if glucose_drugs else " with no glucose-lowering medicine recorded.")
            else:
                status = "at_target"
                summary = f"HbA1c {fmt(hba1c)}% is within the individual target of <{target:.1f}%."
            if hba1c is not None and hba1c > target and data.get("adherence") == "missed":
                plan.append(item("Explore missed doses (cost, supply, side-effects, beliefs) before intensifying.", *dsrc))
            cardiorenal = [reason for reason, present in (("atherosclerotic CVD", any_ascvd), ("heart failure", heart_failure),
                                                          ("chronic kidney disease", ckd_markers or tri("known_ckd") == "yes")) if present]
            sglt2_advised = False
            if cardiorenal and not on(SGLT2):
                if egfr is None:
                    plan.append(item(f"An SGLT2 inhibitor is indicated for {join(cardiorenal)} independent of HbA1c; check eGFR first (start if ≥20).", "ADA_SOC_2025", "KDIGO_CKD_2024_TX", "ESC_DM_CVD_2023"))
                elif egfr >= 20:
                    sglt2_advised = True
                    plan.append(item(f"Add an SGLT2 inhibitor for {join(cardiorenal)}, independent of HbA1c (eGFR {fmt(egfr)}); give sick-day guidance to pause it during dehydrating illness.", "ADA_SOC_2025", "KDIGO_CKD_2024_TX", "ESC_DM_CVD_2023"))
            if any_ascvd and not on(GLP1):
                plan.append(item("A GLP-1 receptor agonist with proven cardiovascular benefit is an alternative or addition for established ASCVD, where available.", "ADA_SOC_2025", "ESC_DM_CVD_2023"))
            if "metformin" in taking:
                if egfr is not None and 30 <= egfr < 45:
                    plan.append(item(f"Metformin with eGFR {fmt(egfr)}: limit to a maximum of 1000 mg/day and review renal function every 3–6 months.", "KDIGO_DM_CKD_2022", "METFORMIN_LABEL"))
                monitor("b12", "Vitamin B12", "Periodically on long-term metformin, especially with neuropathy or anaemia", "Metformin-associated deficiency", "ADA_SOC_2025")
            elif hba1c is not None and hba1c > target:
                if egfr is None:
                    plan.append(item("Metformin is first-line unless contraindicated; check eGFR before starting (not started if eGFR <45).", "KENYA_NCD_PROTOCOLS", "METFORMIN_LABEL"))
                elif egfr >= 45:
                    plan.append(item("Metformin is first-line unless contraindicated (eGFR adequate).", "KENYA_NCD_PROTOCOLS", "ADA_SOC_2025"))
            if hba1c is not None and hba1c > target:
                if hba1c >= 10 or (glucose is not None and glucose >= 16.7) or "unexplained_weight_loss" in symptoms:
                    plan.append(item("HbA1c ≥10%, glucose ≥16.7 mmol/L or weight loss suggests insulin deficiency: consider basal insulin and check ketones.", "ADA_SOC_2025"))
                elif insulin:
                    plan.append(item("Already on insulin: review doses against glucose records, injection technique and sites (lipohypertrophy), and hypoglycaemia before further titration.", "ADA_SOC_2025"))
                elif glucose_drugs:
                    choices = []
                    if bmi is not None and bmi >= 30 and not on(GLP1):
                        choices.append(f"a GLP-1 receptor agonist (weight benefit; BMI {fmt(bmi)})")
                    if not sulfonylurea and not (age >= 75 or frail):
                        choices.append("a sulfonylurea where cost limits access (gliclazide preferred; avoid glibenclamide from age 60)")
                    if not on(DPP4):
                        choices.append("a DPP-4 inhibitor (low hypoglycaemia risk)")
                    choices.append("basal insulin")
                    lead = ("If HbA1c remains above target after the SGLT2 inhibitor (expected fall about 0.5%), add an agent chosen by comorbidity, cost and hypoglycaemia risk: "
                            if sglt2_advised else "Intensify with a second agent chosen by comorbidity, cost and hypoglycaemia risk: ")
                    plan.append(item(lead + "; ".join(choices) + ".", "ADA_SOC_2025", "WHO_HEARTS_D_2020", "KENYA_NCD_PROTOCOLS"))
            if hba1c is not None and hba1c < 6.5 and (insulin or sulfonylurea) and (age >= 65 or frail):
                status = "review"
                summary = f"HbA1c {fmt(hba1c)}% on insulin or a sulfonylurea in an older or frail adult: risk of overtreatment."
                plan.append(item("De-intensify: reduce or stop the sulfonylurea or insulin dose to avoid hypoglycaemia.", "ADA_SOC_2025"))
            if (hypos or 0) > 0 and (insulin or sulfonylurea):
                plan.append(item("Review each hypoglycaemia episode (timing, meals, dose, alcohol, kidney function); consider switching sulfonylurea to a lower-risk agent and teach hypoglycaemia treatment.", "ADA_SOC_2025", "WHO_HEARTS_MEDS_2018"))
            if acr is None and not (ckd or (egfr is not None and egfr < 60)):
                plan.append(item("Measure urine ACR with eGFR at least annually to detect diabetic kidney disease.", "ADA_SOC_2025", "KDIGO_DM_CKD_2022"))
                gap("urine_acr_mg_mmol", "Annual albuminuria screening in diabetes guides ACE inhibitor/ARB and SGLT2 inhibitor use.")
            if data.get("eye_screen") != "within_12_months":
                plan.append(item("Retinal screening is " + ("overdue" if data.get("eye_screen") in ("over_12_months", "never") else "not documented") + ": arrange dilated eye examination or retinal photography.", "ADA_SOC_2025"))
            if data.get("foot_exam") != "within_12_months" and "foot_ulcer" not in symptoms:
                plan.append(item("Foot examination is " + ("overdue" if data.get("foot_exam") in ("over_12_months", "never") else "not documented") + ": check sensation (10 g monofilament), pulses and skin; educate on daily foot care.", "ADA_SOC_2025", "KENYA_NCD_PROTOCOLS"))
            if age < 35 or (bmi is not None and bmi < 25 and "unexplained_weight_loss" in symptoms):
                consider("atypical_diabetes", "Features atypical for type 2 diabetes (" + join([x for x, present in ((f"age {age}", age < 35), ("lean with weight loss", bmi is not None and bmi < 25 and "unexplained_weight_loss" in symptoms)) if present]) + "): consider autoimmune diabetes (GAD antibodies, C-peptide) and check ketones; keep a low threshold for insulin.", "ADA_SOC_2025")
            monitor("hba1c", "HbA1c", "Every 3 months until at target, then every 6 months", "Glycaemic control", "ADA_SOC_2025")
            monitor("acr_egfr", "Urine ACR and eGFR", "At least annually", "Kidney screening in diabetes", "ADA_SOC_2025", "KDIGO_DM_CKD_2022")
            add_problem("diabetes", "Diabetes", status, facts, summary, plan, [target_text])
        else:
            diagnostic = []
            if hba1c is not None and hba1c >= 6.5:
                diagnostic.append(f"HbA1c {fmt(hba1c)}%")
            if glucose is not None and glucose_context == "fasting" and glucose >= 7.0:
                diagnostic.append(f"fasting glucose {fmt(glucose)} mmol/L")
            if glucose is not None and glucose_context != "fasting" and glucose >= 11.1:
                diagnostic.append(f"random glucose {fmt(glucose)} mmol/L")
            prediabetic = (hba1c is not None and 5.7 <= hba1c < 6.5) or (glucose is not None and glucose_context == "fasting" and 6.1 <= glucose < 7.0)
            if diagnostic:
                add_problem("diabetes_possible", "Possible diabetes", "unconfirmed", diag_facts,
                            f"{cap(join(diagnostic))} is in the diabetic range without a recorded diagnosis.",
                            [item("Confirm with a repeat test on another day (or two different abnormal tests on the same sample) unless there is unequivocal hyperglycaemia with symptoms.", "ADA_SOC_2025", "KENYA_NCD_PROTOCOLS"),
                             item("If confirmed: start structured education, metformin unless contraindicated, and baseline eGFR, urine ACR, lipids, eye and foot checks.", "KENYA_NCD_PROTOCOLS", "ADA_SOC_2025")])
            elif prediabetic:
                add_problem("prediabetes", "Increased diabetes risk (prediabetes range)", "at_risk", diag_facts,
                            "Values are above normal but below the diabetic threshold.",
                            [item("Lifestyle programme: 5–7% weight loss if overweight and at least 150 minutes/week of moderate activity.", "ADA_SOC_2025"),
                             item("Repeat HbA1c or fasting glucose at least annually.", "ADA_SOC_2025")])
            if (diagnostic or prediabetic) and hba1c is not None:
                consider("hba1c_reliability_dx", "HbA1c can misclassify diabetes with anaemia, haemoglobin variants (including sickle-cell trait), recent blood loss or transfusion, advanced CKD and pregnancy; confirm with plasma glucose when any apply.", "WHO_HBA1C_2011", "ADA_SOC_2025")
        if diabetic and hba1c is not None and (anaemia or (egfr is not None and egfr < 30)):
            consider("hba1c_reliability", "HbA1c may not reflect glycaemia here (" + join([x for x, present in ((f"haemoglobin {fmt(hb)} g/dL" if hb is not None else "", anaemia), (f"eGFR {fmt(egfr)}" if egfr is not None else "", egfr is not None and egfr < 30)) if present]) + "); corroborate with glucose readings.", "WHO_HBA1C_2011", "ADA_SOC_2025")

    # ---- kidney ------------------------------------------------------------
    if not pregnant and (ckd or (egfr is not None and egfr < 60)):
        facts = []
        if egfr is not None:
            facts.append(f"eGFR {fmt(egfr)} mL/min/1.73 m²" + (" (calculated, CKD-EPI 2021)" if entered_egfr is None else ""))
        if acr is not None:
            facts.append(f"Urine ACR {fmt(acr)} mg/mmol")
        if potassium is not None:
            facts.append(f"Potassium {fmt(potassium)} mmol/L")
        stage = (stage_g or "") + (stage_a or "")
        confirmed = tri("known_ckd") == "yes"
        title = f"Chronic kidney disease {stage}".strip() if confirmed else f"Reduced kidney function or albuminuria {stage}".strip()
        summary = (f"KDIGO risk category {kidney_risk}." if kidney_risk else "Albuminuria category unknown, so KDIGO risk cannot be assigned.")
        plan = []
        if not confirmed:
            plan.append(item("Confirm chronicity: repeat eGFR and urine ACR after 3 months and exclude acute kidney injury (compare with previous results).", "KDIGO_CKD_2024"))
        if acr is None:
            plan.append(item("Measure urine ACR: albuminuria determines risk, RAS-inhibitor and SGLT2-inhibitor decisions.", "KDIGO_CKD_2024"))
            gap("urine_acr_mg_mmol", "Stages CKD risk and guides kidney-protective treatment.")
        if albuminuria and not ras and not heart_failure:
            plan.append(item(f"Start an ACE inhibitor or ARB titrated to the maximum tolerated dose for albuminuria (ACR {fmt(acr)} mg/mmol); recheck creatinine and potassium in 2–4 weeks and accept a creatinine rise of up to 30%.", "KDIGO_CKD_2024_TX", "KDIGO_DM_CKD_2022"))
            if pregnancy_note:
                plan.append(item(pregnancy_note, "NICE_PREGNANCY"))
        if egfr is not None and egfr >= 20 and not on(SGLT2) and not diabetic and ((acr is not None and acr >= 20) or heart_failure or egfr < 45):
            plan.append(item("Add an SGLT2 inhibitor for kidney protection (KDIGO 2024: eGFR ≥20 with ACR ≥20 mg/mmol or heart failure; suggested for eGFR 20–45).", "KDIGO_CKD_2024_TX"))
        if on(NSAID):
            plan.append(item("Stop NSAIDs and avoid other nephrotoxins; adjust renally cleared medicines to eGFR.", "KDIGO_CKD_2024_TX"))
        plan.append(item("Give sick-day guidance: pause metformin, SGLT2 inhibitors, ACE inhibitor/ARB and diuretics during vomiting, diarrhoea or poor intake, and restart when eating and drinking.", "KDIGO_DM_CKD_2022", "KDIGO_CKD_2024_TX"))
        if anaemia and egfr is not None and egfr < 60:
            plan.append(item(f"Haemoglobin {fmt(hb)} g/dL: evaluate anaemia (iron studies, B12/folate, blood film) before attributing it to CKD.", "KDIGO_CKD_2024"))
        refer = []
        if egfr is not None and egfr < 30:
            refer.append(f"eGFR {fmt(egfr)} (<30)")
        if acr is not None and acr >= 30:
            refer.append(f"ACR {fmt(acr)} mg/mmol (≥30)")
        if len(classes) >= 4 and mean_sbp is not None and mean_sbp >= 140:
            refer.append("uncontrolled BP on 4 or more agents")
        if potassium is not None and potassium >= 6:
            refer.append(f"potassium {fmt(potassium)} mmol/L")
        if refer:
            plan.append(item("Refer to nephrology: " + join(refer) + ".", "KDIGO_CKD_2024_TX"))
        targets = ["Systolic BP <120 mmHg with standardised measurement if tolerated (KDIGO), otherwise <130/80"]
        if stage_g and stage_a:
            freq = KDIGO_FREQ[stage_g][int(stage_a[1]) - 1]
            monitoring[:] = [entry for entry in monitoring if entry["id"] != "acr_egfr"]
            monitor("ckd_monitoring", "eGFR and urine ACR", f"{'4 or more' if freq >= 4 else freq} time{'s' if freq != 1 else ''} per year ({stage_g}{stage_a})", "KDIGO heat-map monitoring frequency", "KDIGO_CKD_2024_TX")
        status = "established" if confirmed else "needs_confirmation"
        if refer or kidney_risk == "very high":
            status = "high_risk" if confirmed else "needs_confirmation"
        add_problem("kidney", title, status, facts, summary, plan, targets)
    if (ras or on(MRA)) and not pregnant:
        monitor("renal_k", "Creatinine/eGFR and potassium", "2–4 weeks after starting or increasing ACE inhibitor/ARB, MRA or diuretic, then at least annually", "RAS-blockade safety", "KDIGO_CKD_2024_TX", "LISINOPRIL_LABEL")

    # ---- lipids and cardiovascular prevention ------------------------------
    if not pregnant:
        statin_names = names(STATIN)
        high_intensity = (dose_of("atorvastatin") or 0) >= 40 or (dose_of("rosuvastatin") or 0) >= 20
        plan, facts = [], []
        if risk["statement"]:
            facts.append(risk["statement"].rstrip("."))
        if ldl is not None:
            facts.append(f"LDL cholesterol {fmt(ldl)} mmol/L")
        if tc is not None:
            facts.append(f"Total cholesterol {fmt(tc)} mmol/L" + (f", HDL {fmt(hdl)}" if hdl is not None else ""))
        facts.append("Statin: " + (join(statin_names) + (" (high intensity)" if high_intensity else "") if statin_names else "none recorded"))
        ldl_goal = {"very high": 1.4, "high": 1.8, "moderate": 2.6}.get(risk["category"] or "")
        indication = None
        if any_ascvd:
            indication = "established ASCVD"
        elif diabetic and age >= 40:
            indication = f"diabetes at age {age}"
        elif ckd_markers and age >= 50 and egfr is not None and egfr < 60:
            indication = f"CKD at age {age}"
        elif risk["category"] in ("high", "very high"):
            indication = risk["basis"]
        status = None
        if indication and not statin_names:
            status = "untreated"
            intensity = "a high-intensity statin (atorvastatin 40–80 mg or rosuvastatin 20–40 mg class)" if risk["category"] == "very high" else "at least a moderate-intensity statin"
            plan.append(item(f"Start {intensity}: indicated for {indication}.", "WHO_HEARTS_RISK_2020", "ESC_LIPIDS_2019", "ADA_SOC_2025"))
            if pregnancy_note:
                plan.append(item(pregnancy_note, "NICE_PREGNANCY"))
        elif statin_names and ldl is not None and ldl_goal is not None and ldl > ldl_goal:
            status = "above_target"
            steps = "confirm adherence, then increase to high intensity" if not high_intensity else "confirm adherence, then add ezetimibe"
            plan.append(item(f"LDL {fmt(ldl)} mmol/L is above the goal of <{fmt(ldl_goal)} mmol/L for {risk['category']} risk: {steps}.", "ESC_LIPIDS_2019"))
        elif statin_names and ldl is None:
            status = "needs_data"
            plan.append(item("Check a lipid profile to confirm the statin response (target LDL " + (f"<{fmt(ldl_goal)} mmol/L" if ldl_goal else "per risk category") + ").", "ESC_LIPIDS_2019"))
        elif statin_names:
            status = "at_target"
            plan.append(item("Continue the statin; recheck lipids annually.", "ESC_LIPIDS_2019"))
        elif risk["category"] == "moderate":
            status = "at_risk"
            plan.append(item(f"Moderate risk: discuss a statin after lifestyle change, weighing the {fmt(risk['percent'] or 0)}% 10-year risk and patient preference.", "WHO_HEARTS_RISK_2020", "ESC_LIPIDS_2019"))
        if any_ascvd and not on(ANTIPLATELET) and not on(ANTICOAG):
            status = status or "untreated"
            plan.append(item("Secondary prevention: low-dose aspirin (or clopidogrel if aspirin is not tolerated) unless contraindicated or anticoagulated.", "WHO_HEARTS_RISK_2020"))
        if statin_names or (indication and not statin_names):
            monitor("lipids", "Lipid profile", "4–12 weeks after starting or changing a statin, then annually", "Treatment response", "ESC_LIPIDS_2019")
        if (indication or status) and not (tc is not None or ldl is not None):
            gap("total_cholesterol_mmol", "A lipid profile sets the LDL goal and treatment response.")
        if status:
            summary = (f"{cap(risk['category'])} cardiovascular risk ({risk['basis']})." if risk["category"] else "Cardiovascular risk not yet estimable.")
            if ldl_goal:
                summary += f" LDL goal <{fmt(ldl_goal)} mmol/L."
            add_problem("cv_prevention", "Cardiovascular risk and lipids", status, facts, summary, plan,
                        [f"LDL <{fmt(ldl_goal)} mmol/L" + (" and ≥50% reduction from baseline" if risk["category"] == "very high" else "")] if ldl_goal else [])

    # ---- heart failure -----------------------------------------------------
    if heart_failure and not pregnant:
        pillars = [("ACE inhibitor/ARB/ARNI", ras), ("evidence-based beta-blocker (bisoprolol, carvedilol or metoprolol succinate)", on(BB_HF)),
                   ("MRA (spironolactone)", on(MRA)), ("SGLT2 inhibitor", on(SGLT2))]
        missing = [label for label, present in pillars if not present]
        plan = [item("Confirm the phenotype with echocardiography (LVEF); the four-pillar plan below applies to HFrEF (LVEF ≤40%).", "ESC_HF_2021")]
        if missing:
            plan.append(item("Missing guideline pillars for HFrEF: " + "; ".join(missing) + ". Introduce one at a time at low dose and up-titrate every 2–4 weeks as BP, heart rate, potassium and eGFR allow.", "ESC_HF_2021"))
        if not on(MRA) and ((potassium is not None and potassium > 5.0) or (egfr is not None and egfr < 30)):
            plan.append(item("MRA is not advised while potassium >5.0 mmol/L or eGFR <30.", "ESC_HF_2021"))
        plan.append(item("Loop diuretic only for congestion, at the lowest effective dose; daily weights and a fluid/salt plan.", "ESC_HF_2021"))
        add_problem("heart_failure", "Heart failure", "uncontrolled" if missing else "established",
                    ["On " + join([label.split(" (")[0] for label, present in pillars if present]) if len(missing) < 4 else "No HFrEF disease-modifying therapy recorded"],
                    f"{4 - len(missing)} of 4 disease-modifying pillars recorded.", plan)

    # ---- atrial fibrillation -----------------------------------------------
    if af:
        points = []
        for label, value, present in (("heart failure", 1, heart_failure), ("hypertension", 1, hypertensive or on_bp_treatment),
                                      ("age ≥75", 2, age >= 75), ("diabetes", 1, diabetic), ("prior stroke/TIA", 2, stroke),
                                      ("vascular disease", 1, ascvd), ("age 65–74", 1, 65 <= age < 75)):
            if present:
                points.append((label, value))
        score = sum(value for _, value in points)
        unknown = [label for label, key in (("heart failure", "known_heart_failure"), ("diabetes", "known_diabetes"), ("stroke/TIA", "prior_stroke_tia"), ("vascular disease", "known_ascvd")) if tri(key) == "unknown"]
        derive("cha2ds2_va", "CHA2DS2-VA", str(score), "points", ("Anticoagulation recommended" if score >= 2 else "Anticoagulation to be considered" if score == 1 else "Low stroke risk") + (f"; minimum score, unknown: {join(unknown)}" if unknown else ""),
               "ESC 2024 score without sex category: " + (join(f"{label} +{value}" for label, value in points) if points else "no risk factors recorded"), "ESC_AF_2024")
        plan = []
        anticoagulated = on(ANTICOAG)
        if score >= 1 and not anticoagulated:
            plan.append(item(f"Oral anticoagulation is {'recommended' if score >= 2 else 'to be considered'} (CHA2DS2-VA {score}). A DOAC is preferred unless there is a mechanical valve or moderate–severe mitral stenosis; in Kenya, exclude rheumatic mitral stenosis by echocardiography, as warfarin is then required.", "ESC_AF_2024"))
            if on({"aspirin"}):
                plan.append(item("Aspirin alone is not effective stroke prevention in AF; it is replaced, not combined, unless there is a separate vascular indication.", "ESC_AF_2024"))
        if anticoagulated:
            plan.append(item("Review anticoagulant dose against current eGFR, weight, age and interacting drugs" + (f" (eGFR {fmt(egfr)})" if egfr is not None else " (eGFR needed)") + "; warfarin needs INR monitoring.", "ESC_AF_2024"))
        plan.append(item("Reduce modifiable bleeding risk: control BP, avoid NSAIDs and unnecessary antiplatelets, and limit alcohol.", "ESC_AF_2024"))
        if pulse is not None and pulse > 110:
            plan.append(item(f"Resting pulse {fmt0(pulse)}/min: review rate control (beta-blocker; avoid diltiazem/verapamil in reduced LVEF).", "ESC_AF_2024", "ESC_HF_2021"))
        add_problem("atrial_fibrillation", "Atrial fibrillation", "uncontrolled" if score >= 2 and not anticoagulated else "established",
                    [f"CHA2DS2-VA {score}", "Anticoagulant: " + (join(names(ANTICOAG)) if anticoagulated else "none recorded")],
                    f"Stroke-risk score {score}" + (" with no anticoagulant recorded." if score >= 2 and not anticoagulated else "."), plan)

    # ---- respiratory -------------------------------------------------------
    if asthma:
        facts = ["Inhalers: " + (join(names(ICS | LABA | LAMA | SABA | {"ipratropium"})) or "none recorded")]
        if reliever is not None:
            facts.append(f"Reliever use {reliever}×/week")
        if exacerbations is not None:
            facts.append(f"{exacerbations} exacerbation{'s' if exacerbations != 1 else ''} in 12 months")
        plan = []
        uncontrolled = (reliever is not None and reliever > 2) or (exacerbations or 0) >= 1
        if on(SABA) and not on(ICS):
            plan.append(item("SABA-only treatment is not recommended for adults: start ICS-containing treatment, preferably as-needed or maintenance-and-reliever budesonide-formoterol (GINA Track 1).", "GINA_2025"))
        if uncontrolled:
            plan.append(item("Before stepping up, check inhaler technique, adherence, triggers (smoke, occupational), rhinitis and reflux; then step up treatment.", "GINA_2025"))
        if (exacerbations or 0) >= 1:
            plan.append(item("Provide a written asthma action plan and review within 1 week of any exacerbation.", "GINA_2025"))
        if reliever is None and exacerbations is None:
            gap("reliever_use_per_week", "Reliever use and exacerbations define asthma control and future risk.")
            plan.append(item("Assess control over the last 4 weeks: daytime symptoms or reliever use >2×/week, night waking, activity limitation, and exacerbations in the past year.", "GINA_2025"))
        status = "uncontrolled" if uncontrolled or (on(SABA) and not on(ICS)) else ("needs_data" if reliever is None and exacerbations is None else "at_target")
        add_problem("asthma", "Asthma", status, facts,
                    "Not well controlled or at risk of exacerbation." if status == "uncontrolled" else "Control not assessed." if status == "needs_data" else "Well controlled on the recorded treatment.", plan)
    if copd:
        facts = ["Inhalers: " + (join(names(ICS | LABA | LAMA | SABA | {"ipratropium"})) or "none recorded")]
        if exacerbations is not None:
            facts.append(f"{exacerbations} exacerbation{'s' if exacerbations != 1 else ''} in 12 months")
        group_e = (exacerbations or 0) >= 2
        plan = [item("Confirm with post-bronchodilator spirometry (FEV1/FVC <0.7) if not already documented; in Kenya, household biomass smoke is a common cause in people who never smoked.", "GOLD_2025")]
        if not (on(LABA) and on(LAMA)):
            plan.append(item("Long-acting bronchodilator therapy: LABA + LAMA for persistent symptoms or exacerbations.", "GOLD_2025"))
        if on(ICS) and not on(LABA):
            plan.append(item("ICS without a long-acting bronchodilator is not recommended in COPD.", "GOLD_2025"))
        if group_e:
            plan.append(item("Frequent exacerbations (GOLD E): check blood eosinophils; add ICS to LABA + LAMA if ≥300 cells/µL.", "GOLD_2025"))
        if spo2 is not None and spo2 <= 88:
            plan.append(item(f"SpO2 {fmt0(spo2)}%: assess for long-term oxygen once stable (arterial blood gas).", "GOLD_2025"))
        plan.append(item("Influenza and pneumococcal vaccination, pulmonary rehabilitation and inhaler-technique review.", "GOLD_2025"))
        if exacerbations is None:
            gap("exacerbations_past_year", "Exacerbation history sets COPD group and treatment.")
        add_problem("copd", "COPD", "uncontrolled" if group_e or not (on(LABA) or on(LAMA)) else "established", facts,
                    ("Frequent exacerbator (GOLD E)." if group_e else "Exacerbation history " + ("not recorded." if exacerbations is None else "below the GOLD E threshold.")), plan)
    if spo2 is not None and 88 <= spo2 <= 96 and (asthma or copd or symptoms & {"breathlessness", "wheeze"}):
        consider("pulse_oximetry_bias", f"SpO2 {fmt0(spo2)}% may overestimate arterial oxygenation in people with darker skin; use an arterial blood gas when decisions depend on it.", "PULSE_OXIMETRY_BIAS")

    # ---- weight and tobacco ------------------------------------------------
    if bmi is not None and (bmi >= 30 or (bmi >= 27 and (hypertensive or diabetic or any_ascvd))):
        plan = [item("Agree a 5–10% weight-loss goal with diet, activity and follow-up support.", "WHO_OBESITY", "ADA_SOC_2025")]
        if diabetic and not on(GLP1):
            plan.append(item("In diabetes, a GLP-1 receptor agonist supports both glucose and weight goals where available.", "ADA_SOC_2025"))
        add_problem("weight", "Obesity" if bmi >= 30 else "Overweight with cardiometabolic disease", "at_risk", [f"BMI {fmt(bmi)} kg/m²"] + ([f"Waist {fmt(waist)} cm"] if waist is not None else []),
                    "Weight contributes to BP, glucose and cardiovascular risk.", plan)
    if bmi is not None and bmi < 18.5:
        consider("underweight", f"BMI {fmt(bmi)} kg/m²: evaluate undernutrition, TB, HIV, uncontrolled diabetes, malignancy and food insecurity.", "WHO_OBESITY", "WHO_TB_SCREENING_2021")
    if smoker:
        add_problem("tobacco", "Current tobacco use", "at_risk", ["Current tobacco use"],
                    "Stopping is the single most effective intervention for cardiovascular and lung risk.",
                    [item("Give brief advice to quit today and offer behavioural support with pharmacotherapy (varenicline, nicotine replacement, bupropion or cytisine) where available; follow up within 2 weeks.", "WHO_TOBACCO_2024")])
    elif data.get("tobacco_use") not in {"former", "never"}:
        gap("tobacco_use", "Record tobacco status before calculating numeric cardiovascular risk; unknown status is not scored as non-smoking.")

    # ---- diagnostic considerations -----------------------------------------
    if symptoms & {"persistent_cough", "hemoptysis", "unexplained_weight_loss"}:
        consider("tb_screen", "Cough, haemoptysis or weight loss: test for tuberculosis (rapid molecular test on sputum) before attributing symptoms to cancer or chronic lung disease" + (", especially with diabetes, which raises TB risk" if diabetic else "") + ".", "WHO_TB_SCREENING_2021")

    # ---- medication review -------------------------------------------------
    nsaid_reasons = []
    if on(NSAID):
        if ras and on(THIAZIDE | LOOP | MRA):
            review("triple_whammy", "high", f"NSAID ({join(names(NSAID))}) with an ACE inhibitor/ARB and a diuretic", "This combination causes acute kidney injury; stop the NSAID and use paracetamol or topical options.", "KDIGO_CKD_2024_TX", "LISINOPRIL_LABEL")
        if ckd:
            nsaid_reasons.append("kidney disease")
        if heart_failure:
            nsaid_reasons.append("heart failure (fluid retention)")
        if on(ANTICOAG):
            nsaid_reasons.append("anticoagulation (bleeding)")
        if mean_sbp is not None and mean_sbp >= 140:
            nsaid_reasons.append("raised BP")
        if nsaid_reasons:
            review("nsaid", "high" if heart_failure or on(ANTICOAG) else "moderate", f"NSAID ({join(names(NSAID))}) with {join(nsaid_reasons)}", "Avoid NSAIDs; use paracetamol or topical agents and review over-the-counter use.", "ESC_HF_2021", "KDIGO_CKD_2024_TX")
    if asthma and on(BB_NONSELECTIVE):
        review("bb_asthma", "high", f"Non-selective beta-blocker ({join(names(BB_NONSELECTIVE))}) with asthma", "Can trigger severe bronchospasm: switch to a cardioselective agent or an alternative class.", "GINA_2025")
    elif asthma and on(BB_SELECTIVE):
        review("bb_asthma_selective", "low", f"Cardioselective beta-blocker ({join(names(BB_SELECTIVE))}) with asthma", "Usually tolerated when clearly indicated; monitor for worsening symptoms.", "GINA_2025")
    if heart_failure and "pioglitazone" in taking:
        review("tzd_hf", "high", "Pioglitazone with heart failure", "Causes fluid retention and worsens heart failure: stop and choose another agent.", "ESC_HF_2021")
    if heart_failure and on(NONDHP_CCB):
        review("nondhp_hf", "high", f"{cap(join(names(NONDHP_CCB)))} with heart failure", "Negatively inotropic in reduced LVEF: avoid.", "ESC_HF_2021")
    if on(ANTICOAG) and on(ANTIPLATELET):
        review("anticoag_antiplatelet", "moderate", f"Anticoagulant ({join(names(ANTICOAG))}) with antiplatelet ({join(names(ANTIPLATELET))})", "Confirm a current indication and planned duration for dual therapy; bleeding risk is substantially higher.", "ESC_AF_2024")
    if "aspirin" in taking and not any_ascvd and not af:
        review("aspirin_primary", "low", "Aspirin without recorded atherosclerotic disease", "Not routinely recommended for primary prevention; review the indication and bleeding risk.", "WHO_HEARTS_RISK_2020", "ADA_SOC_2025")
    if on(ACEI) and any("angioedema" in normal(allergy) for allergy in data.get("allergies") or []):
        review("acei_angioedema", "high", "ACE inhibitor with a recorded angioedema history", "ACE inhibitors are contraindicated after angioedema: stop and seek specialist advice before any ARB.", "LISINOPRIL_LABEL")
    if (insulin or sulfonylurea) and ((hypos or 0) > 0 or (egfr is not None and egfr < 30) or age >= 75):
        review("hypoglycaemia_risk", "moderate", "Insulin or sulfonylurea with " + join([x for x, present in (("recent hypoglycaemia", (hypos or 0) > 0), (f"eGFR {fmt(egfr) if egfr is not None else ''}", egfr is not None and egfr < 30), (f"age {age}", age >= 75)) if present]),
               "High hypoglycaemia risk: review the need, dose and agent (gliclazide or a DPP-4 inhibitor carry lower risk than glibenclamide).", "ADA_SOC_2025", "WHO_HEARTS_MEDS_2018")
    if on(MRA) and ((potassium is not None and potassium > 5.0) or (egfr is not None and egfr < 30)):
        review("mra_k", "high", f"{cap(join(names(MRA)))} with " + join([x for x, present in ((f"potassium {fmt(potassium) if potassium is not None else ''}", potassium is not None and potassium > 5.0), (f"eGFR {fmt(egfr) if egfr is not None else ''}", egfr is not None and egfr < 30)) if present]),
               "Hyperkalaemia risk: hold or reduce and recheck potassium and creatinine.", "ESC_HF_2021")
    if "digoxin" in taking and ((potassium is not None and potassium < 3.5) or (egfr is not None and egfr < 30)):
        review("digoxin", "high", "Digoxin with hypokalaemia or reduced kidney function", "Toxicity risk: check a digoxin level, correct potassium and review the dose.", "ESC_AF_2024")
    if diabetic and "prednisolone" in taking:
        review("steroid_dm", "moderate", "Prednisolone in diabetes", "Expect afternoon/evening hyperglycaemia: increase glucose monitoring and plan for treatment adjustment.", "ADA_SOC_2025")
    if on(THIAZIDE | LOOP) and potassium is not None and potassium < 3.5:
        review("diuretic_hypok", "moderate", f"Diuretic with potassium {fmt(potassium)} mmol/L", "Likely contributory: review dose, consider an ACE inhibitor/ARB or potassium-sparing agent, and check magnesium.", "NHS_LOW_POTASSIUM")
    for label, group in (("statins", STATIN), ("sulfonylureas", SULFONYLUREA), ("calcium-channel blockers", DHP_CCB), ("beta-blockers", BB_SELECTIVE | BB_NONSELECTIVE), ("NSAIDs", NSAID), ("anticoagulants", ANTICOAG), ("ACE inhibitors", ACEI), ("ARBs", ARB)):
        if len(taking & group) > 1:
            review("class_duplicate_" + normal(label), "moderate", f"Two {label} recorded ({join(names(group))})", "Therapeutic duplication: confirm which is intended and stop the other.", "NCDAI_SAFETY_SPEC")

    # ---- assemble ----------------------------------------------------------
    for entry in problems:
        entry["priority"] = STATUS_ORDER[entry["status"]]
    problems.sort(key=lambda entry: entry["priority"])
    for index, entry in enumerate(problems):
        entry["rank"] = index + 1
    for entry in problems:
        del entry["priority"]

    conditions = [label for label, present in (
        ("hypertension", hypertensive), ("diabetes", diabetic),
        ("chronic kidney disease" + (f" {stage_g}{stage_a or ''}" if stage_g and tri("known_ckd") == "yes" else ""), tri("known_ckd") == "yes"),
        ("coronary or peripheral arterial disease", ascvd), ("previous stroke/TIA", stroke), ("heart failure", heart_failure),
        ("atrial fibrillation", af), ("asthma", asthma), ("COPD", copd), ("cancer", tri("known_cancer") == "yes")) if present]
    one_liner = f"{age}-year-old {sex_word}" + (" with " + join(conditions) if conditions else " with no chronic NCD diagnosis recorded")
    if pregnant:
        one_liner += ", currently pregnant"
    if smoker:
        one_liner += ", current smoker"
    one_liner += "."
    today = []
    if mean_sbp is not None:
        today.append(f"BP {fmt0(mean_sbp)}/{fmt0(mean_dbp)} mmHg")
    if hba1c is not None:
        today.append(f"HbA1c {fmt(hba1c)}%")
    if egfr is not None:
        today.append(f"eGFR {fmt(egfr)}")
    if acr is not None:
        today.append(f"ACR {fmt(acr)} mg/mmol")
    if ldl is not None:
        today.append(f"LDL {fmt(ldl)} mmol/L")
    if bmi is not None:
        today.append(f"BMI {fmt(bmi)}")
    if today:
        one_liner += " Today: " + ", ".join(today) + "."
    if meds:
        one_liner += f" {len(meds)} current medicine{'s' if len(meds) != 1 else ''}."

    active = [entry for entry in problems if entry["status"] not in ("at_target", "established")]
    if urgency in ("emergency", "urgent"):
        impression = ("Acute findings take priority: " + join(critical_titles) + ". " if critical_titles else "Same-day assessment is required. ") + "Stabilise first; the chronic plan below applies once acute issues are addressed."
    elif active:
        impression = "Priorities: " + "; ".join(f"{entry['rank']}) {entry['title']} ({entry['status'].replace('_', ' ')})" for entry in active[:4]) + "."
    elif problems:
        impression = "Recorded conditions are at target on current information; continue the plan and routine monitoring."
    else:
        impression = "No chronic-disease problem was identified from the structured data; this does not exclude disease."

    if urgency in ("emergency", "urgent"):
        follow_up = "Same day, per the acute findings; chronic review within 2 weeks of stabilisation."
    elif any(entry["status"] in ("acute", "uncontrolled", "untreated", "above_target", "high_risk", "review", "unconfirmed", "needs_confirmation") for entry in problems) or med_review:
        follow_up = "2–4 weeks: confirm readings, review changes and blood results."
    elif problems:
        follow_up = "3–6 months, with monitoring as listed."
    else:
        follow_up = "Routine screening interval; re-assess if new symptoms."

    lines = [one_liner, "", "Impression: " + impression]
    for entry in problems:
        lines.append("")
        lines.append(f"{entry['rank']}. {entry['title']} [{entry['status'].replace('_', ' ')}]")
        if entry["assessment"]:
            lines.append("   " + entry["assessment"])
        for target in entry["targets"]:
            lines.append("   Target: " + target)
        for step in entry["plan"]:
            lines.append("   - " + step["text"])
    if med_review:
        lines.append("")
        lines.append("Medication review:")
        for entry in med_review:
            lines.append(f"   - {entry['finding']}: {entry['action']}")
    if considerations:
        lines.append("")
        lines.append("Consider:")
        for entry in considerations:
            lines.append("   - " + entry["text"])
    if monitoring:
        lines.append("")
        lines.append("Monitoring:")
        for entry in monitoring:
            lines.append(f"   - {entry['test']}: {entry['timing']}")
    lines.append("")
    lines.append("Follow-up: " + follow_up)
    lines.append("Decision support for clinician review; not a prescription.")

    return {
        "version": REASONING_VERSION,
        "one_liner": one_liner,
        "impression": impression,
        "acute_first": urgency in ("emergency", "urgent"),
        "derived": derived,
        "cardiovascular_risk": risk if risk["category"] else None,
        "problems": problems,
        "medication_review": med_review,
        "considerations": considerations,
        "monitoring": monitoring,
        "data_gaps": gaps,
        "follow_up": follow_up,
        "summary_text": "\n".join(lines),
        "sources": evidence(*used_sources),
        "boundary": "Deterministic synthesis from structured fields for clinician review. It names options and guideline steps; it does not diagnose, prescribe or set doses. Verify against the full clinical picture.",
    }
