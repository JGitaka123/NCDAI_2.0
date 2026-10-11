"""Guideline treatment options for confirmed hypertension and type 2 diabetes.

Deterministic and advisory: each option names the Kenya MOH protocol step and
the transcribed Table 4 / section 4.5 doses (PDF SHA256 recorded in dosing.py),
for a clinician to accept, modify or reject. Nothing here writes a prescription
or changes the medication list. Options are withheld in acute, urgent or
pregnancy contexts; the caller enforces those gates before invoking this module.
Free-text frequencies are only compared when they unambiguously mean once daily.
"""
import re

CCB = {"amlodipine", "felodipine", "nifedipine"}
THIAZIDE = {"hydrochlorothiazide", "chlorthalidone", "indapamide"}
ACE = {"lisinopril", "enalapril", "ramipril", "captopril", "perindopril"}
ARB = {"losartan", "valsartan", "candesartan", "telmisartan", "irbesartan"}
RAS = ACE | ARB
BETA_BLOCKER = {"atenolol", "bisoprolol", "carvedilol", "metoprolol", "propranolol", "labetalol", "nebivolol"}
OTHER_BP = {"spironolactone", "methyldopa", "hydralazine", "clonidine", "prazosin", "minoxidil", "furosemide"}
STATINS = {"atorvastatin", "simvastatin", "rosuvastatin", "pravastatin", "lovastatin"}
SULFONYLUREA = {"glibenclamide", "gliclazide", "glimepiride", "glipizide"}
DPP4 = {"sitagliptin", "vildagliptin", "linagliptin", "saxagliptin"}
SGLT2 = {"empagliflozin", "dapagliflozin", "canagliflozin"}
TZD = {"pioglitazone"}

# Kenya MOH Table 4 (printed page 16, PDF page 25): once-daily start and maximum, mg.
# Enalapril, captopril, perindopril and nifedipine have ranges, salts or divided
# schedules and are deliberately not compared.
HTN_TABLE4 = {
    "amlodipine": (5, 10), "felodipine": (5, 10), "chlorthalidone": (25, 50),
    "hydrochlorothiazide": (12.5, 25), "indapamide": (2.5, 5), "lisinopril": (10, 40),
    "ramipril": (2.5, 10), "candesartan": (8, 32), "irbesartan": (150, 300),
    "losartan": (50, 100), "telmisartan": (40, 80), "valsartan": (80, 160),
}
CLASS_LABEL = {"ccb": "calcium channel blocker", "thiazide": "thiazide/thiazide-like diuretic", "ras": "ACE inhibitor/ARB"}
START_EXAMPLE = {
    "ccb": "amlodipine 5 mg once daily (maximum 10 mg)",
    "thiazide": "hydrochlorothiazide 12.5 mg once daily (maximum 25 mg) or chlorthalidone 25 mg once daily (maximum 50 mg)",
    "ras": "losartan 50 mg once daily (maximum 100 mg) or lisinopril 10 mg once daily (maximum 40 mg)",
}
STEP_NOTE = ("Kenya protocol: stay on each step for at least 3 months before escalating; first exclude non-adherence, "
             "white-coat hypertension and incorrect measurement technique. Target <140/90 mmHg; review monthly until at target.")
RAS_CHECK = ("Before an ACE inhibitor/ARB: confirm the patient is not pregnant or planning pregnancy, "
             "and check potassium and eGFR at baseline and after starting.")


def is_insulin(code: str) -> bool:
    return "insulin" in code or code in {"glargine", "detemir", "degludec", "mixtard", "insulatard", "actrapid", "humulin", "novomix"}


def _once_daily(frequency) -> bool:
    text = str(frequency or "").strip().lower()
    return bool(re.fullmatch(r"(od|o\.d\.?|once( a)? daily|once( a)? day|daily|1 ?x ?daily|every morning|nocte|once)", text))


def _dose_position(med: dict):
    """Returns (current_mg, maximum_mg) only when the schedule is unambiguous."""
    code, dose = med["_code"], med.get("dose")
    if code not in HTN_TABLE4 or dose is None or str(med.get("unit") or "").strip().lower() != "mg" or not _once_daily(med.get("frequency")):
        return None
    return float(dose), HTN_TABLE4[code][1]


def regimen(med: dict) -> str:
    """Recorded name, dose and schedule, e.g. 'Amlodipine 5 mg once daily'."""
    dose = med.get("dose")
    parts = [med["_label"], f"{dose:g}" if isinstance(dose, (int, float)) else None, med.get("unit"), med.get("frequency")]
    return " ".join(str(part) for part in parts if part)


def _mg(value: float) -> str:
    return f"{value:g} mg"


def hypertension_options(ctx: dict) -> list[dict]:
    meds, codes = ctx["meds"], ctx["codes"]
    readings = ctx["control_bp"]
    if readings is None:
        return []
    sbp, dbp = readings
    threshold_sbp = 150 if ctx["age"] >= 80 and not (ctx["diabetic"] or ctx["renal_disease"]) else 140
    if sbp < threshold_sbp and dbp < 90:
        return []
    classes = {name for name, members in (("ccb", CCB), ("thiazide", THIAZIDE), ("ras", RAS)) if codes & members}
    on_any = bool(codes & (CCB | THIAZIDE | RAS | BETA_BLOCKER | OTHER_BP))
    current = sorted(regimen(m) for m in meds if m["_code"] in CCB | THIAZIDE | RAS | BETA_BLOCKER | OTHER_BP)
    basis = [f"BP used for control: {sbp:g}/{dbp:g} mmHg" + (" (repeat reading)" if ctx["control_is_repeat"] else ""),
             "Current antihypertensives: " + (", ".join(current) if current else "none recorded"),
             f"Target: <{threshold_sbp}/90 mmHg", "Adherence: " + ctx["adherence"].replace("_", " ")]
    sources = ("KENYA_HTN_STEPS", "KENYA_DOSES_HTN")
    if on_any and ctx["adherence"] == "missed":
        return [dict(rule_id="TX_HTN_ADHERENCE", severity="warning", urgency="soon",
                     title="BP above target with missed doses: address adherence before escalating",
                     detail=(f"BP {sbp:g}/{dbp:g} mmHg is above target while missed doses are reported. The Kenya protocol requires "
                             "non-adherence to be excluded before up-titration. Agree a plan for barriers, cost and side effects, "
                             "consider a once-daily or single-pill combination, and recheck BP in about 4 weeks before adding medicines."),
                     sources=sources, basis=basis)]
    if not on_any:
        grade = 1 if sbp < 160 and dbp < 100 else 2
        high_risk = ctx["diabetic"] or ctx["renal_disease"] or ctx["cvd"] or ctx["tobacco"] == "current"
        lead = (f"Grade {grade if grade == 1 else '2 or higher'} hypertension (BP {sbp:g}/{dbp:g} mmHg) with no antihypertensive recorded. ")
        if grade == 1 and not high_risk and ctx["age"] < 80:
            lead += ("Without other cardiovascular risk factors the protocol allows lifestyle management for up to 3 months first; "
                     "if BP remains at or above 140/90 mmHg, start medicine. ")
        detail = (lead + "Step 1 options: a low-dose two-drug combination, for example amlodipine 5 mg + losartan 50 mg once daily, "
                  "amlodipine 5 mg + lisinopril 10 mg once daily, or amlodipine 5 mg + hydrochlorothiazide 12.5 mg once daily. "
                  "Monotherapy (for example amlodipine 5 mg once daily) is reserved for low-risk grade 1 hypertension (the protocol notes systolic at or above 150 mmHg), adults aged 80 or over, or frail patients. "
                  "Use a single-pill combination where available. " + RAS_CHECK + " " + STEP_NOTE)
        return [dict(rule_id="TX_HTN_START", severity="warning", urgency="soon",
                     title="Consider starting antihypertensive treatment (Kenya step 1)", detail=detail, sources=sources, basis=basis)]
    if classes >= {"ccb", "thiazide", "ras"}:
        return [dict(rule_id="TX_HTN_SPECIALIST", severity="warning", urgency="soon",
                     title="BP above target on triple therapy: step 4 needs a physician",
                     detail=(f"BP {sbp:g}/{dbp:g} mmHg despite triple therapy ({', '.join(current)}). "
                             "Confirm full doses and adherence and exclude secondary causes. Step 4 adds spironolactone or another diuretic, "
                             "a beta blocker or a centrally acting agent, and must be started with a physician. Refer: patients not at target "
                             "after 3 months of treatment are a referral indication."),
                     sources=(*sources, "KENYA_HTN_LIFESTYLE"), basis=basis)]
    below_max = []
    for med in meds:
        position = _dose_position(med)
        if position and position[0] < position[1]:
            below_max.append(f"{med['_label']} {_mg(position[0])} once daily to up to {_mg(position[1])}")
    unclear = [m["_label"] for m in meds if m["_code"] in HTN_TABLE4 and _dose_position(m) is None]
    missing = [c for c in ("ccb", "ras", "thiazide") if c not in classes]
    if len(classes) <= 1:
        add = " or ".join(START_EXAMPLE[c] for c in missing[:2])
        detail = (f"BP {sbp:g}/{dbp:g} mmHg on {', '.join(current)} (one medicine class). Move to a two-drug combination: add {add}. "
                  + (f"Increasing the current medicine ({'; '.join(below_max)}) is an alternative if a single agent is preferred. " if below_max else "")
                  + ("A beta blocker alone is not a first-line step unless it has a specific indication (heart failure, angina, atrial fibrillation). "
                     if codes & BETA_BLOCKER and not classes else "")
                  + (RAS_CHECK + " " if "ras" in missing else "") + STEP_NOTE)
        return [dict(rule_id="TX_HTN_STEP_UP", severity="warning", urgency="soon",
                     title="BP above target: add a second medicine class (Kenya step 1-2)", detail=detail, sources=sources, basis=basis)]
    if below_max:
        detail = (f"BP {sbp:g}/{dbp:g} mmHg on {', '.join(current)}. Step 2 is full-dose dual therapy: increase "
                  + "; ".join(below_max) + ". " + STEP_NOTE)
        title = "BP above target: increase to full-dose dual therapy (Kenya step 2)"
    else:
        detail = (f"BP {sbp:g}/{dbp:g} mmHg on {', '.join(current)}"
                  + (f" (doses not compared because the schedule is unclear for: {', '.join(unclear)}; confirm they are at the maximum first)" if unclear else " at the maximum Table 4 doses")
                  + f". Step 3 is triple therapy: add the missing {CLASS_LABEL[missing[0]]}, for example {START_EXAMPLE[missing[0]]}. "
                  + (RAS_CHECK + " " if missing[0] == "ras" else "") + STEP_NOTE)
        title = f"BP above target: add a {CLASS_LABEL[missing[0]]} (Kenya step 3)"
    return [dict(rule_id="TX_HTN_STEP_UP", severity="warning", urgency="soon", title=title, detail=detail, sources=sources, basis=basis)]


def diabetes_options(ctx: dict) -> list[dict]:
    codes, egfr, hba1c = ctx["codes"], ctx["egfr"], ctx["hba1c"]
    fasting = ctx["glucose"] if ctx["glucose_timing"] == "fasting" else None
    metformin = "metformin" in codes
    insulin = any(is_insulin(c) for c in codes)
    oral = [name for name, members in (("metformin", {"metformin"}), ("sulfonylurea", SULFONYLUREA), ("DPP-4 inhibitor", DPP4),
                                       ("SGLT2 inhibitor", SGLT2), ("pioglitazone", TZD)) if codes & members]
    current = sorted(regimen(m) for m in ctx["meds"] if m["_code"] in {"metformin"} | SULFONYLUREA | DPP4 | SGLT2 | TZD or is_insulin(m["_code"]))
    if hba1c is not None:
        above, measure = hba1c >= 7.0, f"HbA1c {hba1c:g}%"
    elif fasting is not None:
        above, measure = fasting > 7.2, f"fasting glucose {fasting:.1f} mmol/L"
    else:
        above, measure = None, "no HbA1c or fasting glucose recorded"
    basis = ["Glycaemic control: " + measure, "Target: HbA1c <7.0%; fasting glucose 4.4-7.2 mmol/L",
             "Current glucose-lowering medicines: " + (", ".join(current) if current else "none recorded"),
             "eGFR: " + (f"{egfr:g} mL/min/1.73 m²" if egfr is not None else "not recorded")]
    if ctx["weight"] is not None:
        basis.append(f"Weight: {ctx['weight']:g} kg")
    sources = ("KENYA_DM_TREATMENT",)
    options = []
    cardiorenal = ctx["cvd"] or ctx["renal_disease"] or (egfr is not None and egfr < 60)
    if not metformin and not oral and not insulin:
        if egfr is None:
            detail = ("Metformin is first-line treatment for type 2 diabetes: start 500 mg once daily with food and titrate to 1 g twice daily as tolerated. "
                      "Record an eGFR before starting, because kidney function decides whether metformin can be used.")
        elif egfr > 45:
            detail = (f"eGFR {egfr:g}. Start metformin 500 mg once daily with food and titrate upwards to 1 g twice daily as tolerated. "
                      "Review GI tolerance, kidney function and vitamin B12 over time.")
        elif egfr > 30:
            detail = (f"eGFR {egfr:g}. The Kenya flowchart permits metformin above 30, but the product label advises against starting it at eGFR 30-45. "
                      "Individualize with the prescriber; if started, keep the dose low and monitor kidney function.")
        else:
            detail = (f"eGFR {egfr:g}: metformin is contraindicated. For GFR ≤30 the Kenya flowchart lists an SGLT2 inhibitor, a DPP-4 inhibitor "
                      "or pioglitazone. Seek physician review for medicine choice and dosing in advanced kidney disease.")
        if cardiorenal and (egfr is None or egfr > 30):
            detail += " With cardiovascular or kidney disease, the protocol advises adding an SGLT2 inhibitor alongside metformin even if HbA1c is at target."
        options.append(dict(rule_id="TX_DM_METFORMIN", severity="warning", urgency="soon",
                            title="No glucose-lowering medicine recorded: consider metformin (Kenya first line)" if egfr is None or egfr > 30 else "Metformin contraindicated: physician choice of alternative",
                            detail=detail, sources=(*sources, "METFORMIN_LABEL"), basis=basis))
        return options
    if above:
        if insulin:
            detail = (f"{measure[0].upper() + measure[1:]} is above target on {', '.join(current)}. Basal or NPH insulin: titrate by 2-4 units every 3 days to a fasting glucose of 4-7 mmol/L; "
                      "for hypoglycaemia, find the cause and reduce by 10-20%. If HbA1c stays above target with a normal fasting glucose, "
                      "add prandial insulin 4 units with the largest meal (or 10% of the basal dose), increasing by 1-2 units twice weekly. "
                      "Insulin changes are made at level 4 facilities and above.")
            title = "Glycaemia above target on insulin: titrate per Kenya insulin protocol"
            rule = "TX_DM_INSULIN"
        elif not metformin and (egfr is None or egfr > 30):
            detail = (f"{measure[0].upper() + measure[1:]} on {', '.join(oral)} without metformin, the first-line medicine. Unless it was stopped for "
                      "intolerance or a contraindication, add metformin 500 mg once daily with food, titrating to 1 g twice daily as tolerated. "
                      + ("Record an eGFR before starting. " if egfr is None else "Avoid starting it at eGFR 30-45 (product label). " if egfr <= 45 else ""))
            title, rule = "Glycaemia above target without metformin: consider adding metformin", "TX_DM_INTENSIFY"
        elif len(oral) <= 1:
            detail = (f"{measure[0].upper() + measure[1:]} on {', '.join(current) or 'current therapy'}. Add a second medicine: a sulfonylurea "
                      "(gliclazide 40-160 mg or glimepiride 1-4 mg; watch for hypoglycaemia and stop if recurrent) where cost matters, "
                      "or a DPP-4 inhibitor or SGLT2 inhibitor where hypoglycaemia risk matters. "
                      + ("With cardiovascular or kidney disease and eGFR above 30, an SGLT2 inhibitor is preferred. " if cardiorenal and (egfr or 0) > 30 else "")
                      + ("Avoid glibenclamide at age 60 or over. " if ctx["age"] >= 60 else "")
                      + "Confirm adherence and reassess HbA1c in about 3 months.")
            title, rule = "Glycaemia above target: add a second glucose-lowering medicine (Kenya 4.5)", "TX_DM_INTENSIFY"
        else:
            dose = ""
            if ctx["weight"] is not None:
                dose = f" (for {ctx['weight']:g} kg, 0.1-0.2 IU/kg is {ctx['weight'] * 0.1:.0f}-{ctx['weight'] * 0.2:.0f} units)"
            detail = (f"{measure[0].upper() + measure[1:]} on {len(oral)} oral medicines ({', '.join(current)}). "
                      + ("Options: add pioglitazone 15-30 mg (avoid in heart failure), or " if len(oral) == 2 and not codes & TZD else "Consider: ")
                      + f"start basal or NPH insulin at bedtime, 10 units a day or 0.1-0.2 IU/kg/day{dose}, titrated by 2-4 units every 3 days "
                      "to a fasting glucose of 4-7 mmol/L. Insulin is started at level 4 facilities and above; refer if not available here.")
            title, rule = "Glycaemia above target on combination therapy: consider a third agent or basal insulin", "TX_DM_INTENSIFY"
        options.append(dict(rule_id=rule, severity="warning", urgency="soon", title=title, detail=detail, sources=sources, basis=basis))
    if not options and metformin and not codes & SGLT2 and (ctx["cvd"] or ctx["renal_disease"]) and egfr is not None and egfr > 30 and not insulin:
        options.append(dict(rule_id="TX_DM_CARDIORENAL", severity="info", urgency="routine",
                            title="Cardiovascular or kidney disease with diabetes: consider an SGLT2 inhibitor",
                            detail=(f"eGFR {egfr:g}. The Kenya protocol advises starting an SGLT2 inhibitor with metformin in people with high cardiovascular risk "
                                    "or CKD and GFR above 30, even when HbA1c is within target. Counsel on genital hygiene and sick-day rules "
                                    "(pause during vomiting or dehydration)."),
                            sources=(*sources, "SGLT2_LABEL"), basis=basis))
    return options


# NICE NG238 "Terms used": statin intensity by daily dose (mg).
STATIN_INTENSITY = {
    "atorvastatin": [(20, 80, "high"), (10, 10, "medium")],
    "rosuvastatin": [(10, 40, "high"), (5, 5, "medium")],
    "simvastatin": [(20, 40, "medium"), (10, 10, "low")],
    "fluvastatin": [(80, 80, "medium"), (20, 40, "low")],
    "pravastatin": [(5, 40, "low")],
}
STATIN_MONITORING = ("Check a full lipid profile and liver transaminase (ALT or AST) 2-3 months after starting or changing the dose, "
                     "transaminase again at 12 months, and a lipid profile annually (NICE 1.11).")


def _statin_position(med: dict):
    """(daily mg or None, intensity or None); dose is read only when unambiguous."""
    dose, unit = med.get("dose"), str(med.get("unit") or "").strip().lower()
    if dose is None or unit != "mg" or not _once_daily(med.get("frequency")):
        return None, None
    for low, high, level in STATIN_INTENSITY.get(med["_code"], []):
        if low <= dose <= high:
            return float(dose), level
    return float(dose), None


def _non_hdl(ctx):
    tc, hdl = ctx.get("total_cholesterol"), ctx.get("hdl")
    return round(tc - hdl, 1) if tc is not None and hdl is not None else None


def lipid_options(ctx: dict) -> list[dict]:
    meds = ctx["meds"]
    tc, ldl, hdl, tg = ctx.get("total_cholesterol"), ctx.get("ldl"), ctx.get("hdl"), ctx.get("triglycerides")
    non_hdl = _non_hdl(ctx)
    egfr, cvd = ctx["egfr"], ctx["cvd"]
    ckd = ctx["renal_disease"] or (egfr is not None and egfr < 60)
    lipid_basis = [f"Total cholesterol {tc:g} mmol/L" if tc is not None else None, f"LDL {ldl:g} mmol/L" if ldl is not None else None,
                   f"HDL {hdl:g} mmol/L" if hdl is not None else None, f"Non-HDL {non_hdl:g} mmol/L (total minus HDL)" if non_hdl is not None else None,
                   f"Triglycerides {tg:g} mmol/L" if tg is not None else None]
    lipid_basis = [item for item in lipid_basis if item]
    options = []
    # Specialist thresholds apply whatever else is decided (NICE 1.4.5-1.4.7).
    referral = []
    if tg is not None and tg > 20:
        referral.append(f"triglycerides {tg:g} mmol/L are above 20: arrange urgent specialist review unless explained by alcohol or poor glycaemic control")
    elif tg is not None and tg >= 10:
        referral.append(f"triglycerides {tg:g} mmol/L (10-20): repeat a fasting sample after 5 days and within 2 weeks, look for secondary causes, and seek specialist advice if still above 10")
    if (tc is not None and tc > 9.0) or (non_hdl is not None and non_hdl > 7.5):
        referral.append("total cholesterol above 9.0 or non-HDL above 7.5 mmol/L: arrange specialist assessment for a familial lipid disorder, even without a family history")
    if referral:
        options.append(dict(rule_id="LIPID_SPECIALIST", severity="warning", urgency="soon", category="referral",
                            title="Lipid result meets a specialist-referral threshold",
                            detail="For this patient: " + "; ".join(referral) + ". First exclude secondary causes (excess alcohol, uncontrolled diabetes, hypothyroidism, liver disease, nephrotic syndrome).",
                            sources=("NICE_LIPIDS_NG238",), basis=lipid_basis))
    statins = [m for m in meds if m["_code"] in STATINS]
    reasons = [label for flag, label in ((cvd, "established cardiovascular disease"), (ctx["diabetic"], "diabetes"),
                                         (ctx["renal_disease"], "chronic kidney disease"),
                                         (tc is not None and tc >= 8, f"total cholesterol {tc:g} mmol/L (at least 8)" if tc is not None else "")) if flag]
    pregnancy_note = ""
    if ctx["sex"] == "female" and ctx["age"] < 55:
        pregnancy_note = (" Statins are contraindicated in pregnancy: " + ("confirm pregnancy status before prescribing. " if ctx["pregnancy"] not in {"no", "not_applicable"} else "")
                          + "Advise stopping if pregnancy is possible, stopping 3 months before trying to conceive, and not taking it while breastfeeding.")
    if not statins and reasons:
        if ckd:
            dose = "atorvastatin 20 mg once daily"
            why = ("NICE 1.8.1 offers atorvastatin 20 mg for primary or secondary prevention in chronic kidney disease"
                   + (f" (eGFR {egfr:g})." if egfr is not None else ".")
                   + " If the lipid target is not met, the dose may be increased while eGFR is 30 or above; below 30, agree higher doses with a renal specialist.")
            target = "Target: LDL 2.0 mmol/L or less (non-HDL 2.6 or less) with cardiovascular disease; otherwise a reduction in non-HDL cholesterol of more than 40%."
        elif cvd:
            dose = "atorvastatin 80 mg once daily"
            why = ("NICE 1.7.2 offers atorvastatin 80 mg for established cardiovascular disease whatever the cholesterol level. Use a lower dose if it could "
                   "interact with other medicines, adverse effects are likely, or the patient prefers it (1.7.3).")
            target = "Target: LDL 2.0 mmol/L or less, or non-HDL 2.6 mmol/L or less (NICE 1.7.1)."
        else:
            dose = "atorvastatin 20 mg once daily"
            why = ("NICE 1.6.7 recommends atorvastatin 20 mg for primary prevention. The Kenya protocol counts established diabetes or kidney disease "
                   "as more than 20% 10-year CVD risk, for which it advises a statin.")
            target = ("Target: more than 40% reduction in non-HDL cholesterol (NICE 1.6.1)"
                      + (f"; from the current {non_hdl:g} mmol/L that means below {non_hdl * 0.6:.1f} mmol/L." if non_hdl is not None else "; record a baseline full lipid profile first."))
        age_note = " At 85 or older, consider rather than offer, weighing frailty and life expectancy (NICE 1.6.9)." if ctx["age"] >= 85 and not cvd else ""
        detail = (f"Recorded {' and '.join(reasons)}, with no statin on the medicine list. Suggested: {dose}. {why} {target} "
                  "Before starting: full lipid profile, ALT or AST, renal function and HbA1c; ask about unexplained muscle symptoms (check creatine kinase if present). "
                  "A transaminase below 3 times the upper limit of normal does not rule out a statin. " + STATIN_MONITORING + pregnancy_note + age_note)
        options.append(dict(rule_id="TX_STATIN_START", severity="warning", urgency="soon", category="treatment",
                            title=f"Start a statin: {dose}", detail=detail, sources=("NICE_LIPIDS_NG238", "KENYA_CVD_RISK"),
                            basis=[*("Known " + r if not r.startswith("total") else None for r in reasons), *lipid_basis,
                                   f"eGFR {egfr:g} mL/min/1.73 m²" if egfr is not None else None, "No statin recorded"]))
    elif statins:
        med = statins[0]
        daily, level = _statin_position(med)
        current = f"{med['_label']} {daily:g} mg daily" if daily is not None else f"{med['_label']} (dose or schedule unclear)"
        intensity = f" ({level} intensity)" if level else ""
        above = (ldl is not None and ldl > 2.0) or (non_hdl is not None and non_hdl > 2.6)
        steps = title = None
        if cvd and above:
            if ckd and egfr is not None and egfr < 30:
                steps = "eGFR is below 30: agree any dose increase with a renal specialist (NICE 1.8.3)."
            elif daily is not None and ((med["_code"] == "atorvastatin" and daily >= 80) or (med["_code"] == "rosuvastatin" and daily >= 40)):
                steps = "Already on the maximum dose of a high-intensity statin: confirm adherence, then consider adding ezetimibe (NICE 1.7.9, TA385)."
            else:
                steps = ("Confirm adherence and timing, then move to a high-intensity statin at the maximum tolerated dose, for example atorvastatin 80 mg once daily"
                         + (" (with CKD and eGFR 30 or above, increase atorvastatin stepwise from 20 mg)" if ckd else "") + " (NICE 1.9.1).")
            title = "Lipids above the secondary-prevention target: intensify statin"
        elif cvd and level in {"low", "medium"}:
            steps = ("Discuss switching to a high-intensity statin such as atorvastatin 80 mg once daily (NICE 1.11.12)"
                     + ("; check a lipid profile to judge control." if ldl is None and non_hdl is None else "."))
            title = "Cardiovascular disease on a lower-intensity statin"
        elif cvd and ldl is None and non_hdl is None:
            steps = "No LDL or non-HDL is recorded: check a full lipid profile against the target of LDL 2.0 or less / non-HDL 2.6 or less (NICE 1.7.1)."
            title = "Check lipid control on statin"
        if steps:
            options.append(dict(rule_id="TX_STATIN_OPTIMISE", severity="warning" if above else "info", urgency="soon", category="treatment",
                                title=title, detail=f"Currently on {current}{intensity}. {steps} " + STATIN_MONITORING,
                                sources=("NICE_LIPIDS_NG238",), basis=[f"Current statin: {current}{intensity}", *lipid_basis, "Known cardiovascular disease"]))
    aspirin = [m for m in meds if m["_code"] == "aspirin"]
    if aspirin and ctx["cvd_status"] != "yes":
        options.append(dict(rule_id="TX_ASPIRIN_REVIEW", severity="info", urgency="routine", category="treatment",
                            title="Review aspirin without recorded cardiovascular disease",
                            detail=(f"{aspirin[0]['_label']} is recorded but cardiovascular disease is "
                                    + ("recorded as absent" if ctx["cvd_status"] == "no" else "not documented")
                                    + ". NICE 1.2.1 advises not routinely offering aspirin for primary prevention. Confirm the indication (for example a previous heart attack, stroke or stent); "
                                      "if there is none, discuss stopping it, particularly with a history of bleeding or dyspepsia."),
                            sources=("NICE_LIPIDS_NG238",), basis=[f"On {aspirin[0]['_label']}", "Cardiovascular disease: " + ctx["cvd_status"]]))
    return options


RESPIRATORY = ("salbutamol", "formoterol", "salmeterol", "ipratropium", "tiotropium", "montelukast", "beclometasone", "beclomethasone", "budesonide", "fluticasone")
ICS = ("beclometasone", "beclomethasone", "budesonide", "fluticasone", "ciclesonide", "mometasone")


def _has_ics(code):
    return any(name in code for name in ICS)


def respiratory_options(ctx: dict) -> list[dict]:
    """Kenya 6.7: SABA or LABA monotherapy is not recommended; every step includes ICS."""
    if not ctx["asthma"]:
        return []
    meds = ctx["meds"]
    if any(_has_ics(m["_code"]) for m in meds):
        return []
    labels = [m["_label"] for m in meds if any(name in m["_code"] for name in RESPIRATORY)]
    saba = [m["_label"] for m in meds if "salbutamol" in m["_code"]]
    laba = [m["_label"] for m in meds if "formoterol" in m["_code"] or "salmeterol" in m["_code"]]
    if laba:
        problem = f"{', '.join(laba)} (a long-acting beta agonist) is recorded without an inhaled corticosteroid; LABA monotherapy is not recommended in asthma."
    elif saba:
        problem = f"{', '.join(saba)} is the only asthma inhaler recorded; SABA monotherapy is not recommended."
    else:
        problem = "No asthma inhaler is recorded."
    detail = (problem + " Every step of the Kenya protocol includes an inhaled corticosteroid. Choose the step from the symptom pattern: "
              "symptoms less than twice a month, as-needed low-dose budesonide-formoterol (or salbutamol-beclometasone); twice a month or more but not most days, "
              "add regular low-dose ICS (beclometasone or budesonide) or use as-needed budesonide-formoterol; most days or night waking weekly, regular low-dose "
              "ICS-formoterol or ICS-LABA; with low lung function as well, medium-dose ICS-formoterol and specialist consultation. "
              "Check inhaler technique (add a spacer if needed), adherence and triggers, and rinse the mouth after ICS.")
    return [dict(rule_id="TX_ASTHMA_ICS", severity="warning", urgency="soon", category="treatment",
                 title="Asthma without an inhaled corticosteroid: add ICS (Kenya step chart)", detail=detail,
                 sources=("KENYA_ASTHMA",), basis=["Known asthma", "Inhalers recorded: " + (", ".join(labels) if labels else "none")])]
