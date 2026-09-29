// NCDAI offline clinical engine: a line-for-line port of backend/app/clinical.py
// (safety rules, without the dose-reference module) and backend/app/reasoning.py
// (consultant synthesis). backend/tests/test_engine_parity.py runs both engines on
// the same cases and requires identical output; change them together.
// Plain browser script: needs evidence.js loaded first; exposes self.NCDAIEngine.
(function (root) {
  'use strict'
  var REGISTRY = root.NCDAI_EVIDENCE
  if (!REGISTRY) throw new Error('Load evidence.js before engine.js')
  var RULESET_VERSION = 'ncdai-2-rules-0.2.0'
  var REASONING_VERSION = 'ncdai-consultant-1.0.0'
  var SOURCES = {}
  REGISTRY.sources.forEach(function (source) { SOURCES[source.source_id] = source })

  // ---- Python-compatible helpers ------------------------------------------
  function has(obj, key) { return obj != null && Object.prototype.hasOwnProperty.call(obj, key) }
  function get(obj, key, fallback) { return has(obj, key) ? obj[key] : fallback }
  function evidence() {
    return Array.prototype.map.call(arguments, function (id) {
      if (!SOURCES[id]) throw new Error('Unknown evidence source ' + id)
      return JSON.parse(JSON.stringify(SOURCES[id]))
    })
  }
  function set(values) { return new Set(values) }
  function union() { var out = new Set(); for (var i = 0; i < arguments.length; i++) arguments[i].forEach(function (v) { out.add(v) }); return out }
  function intersects(a, b) { var found = false; b.forEach(function (v) { if (a.has(v)) found = true }); return found }
  function intersection(a, b) { var out = []; a.forEach(function (v) { if (b.has(v)) out.push(v) }); return out }
  function sortedStrings(values) { return values.slice().sort(function (x, y) { return x < y ? -1 : x > y ? 1 : 0 }) }
  function r1(value) { return Math.floor(value * 10 + 0.5) / 10 }
  function fmt(value) { var r = r1(value); return Number.isInteger(r) ? String(r) : r.toFixed(1) }
  function fmt0(value) { return String(Math.floor(value + 0.5)) }
  function cap(text) { return text.slice(0, 1).toUpperCase() + text.slice(1) }
  function join(items) {
    if (!items.length) return ''
    if (items.length === 1) return items[0]
    return items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1]
  }
  function normal(value) { return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') }
  function unique(values) { var out = []; values.forEach(function (v) { if (out.indexOf(v) < 0) out.push(v) }); return out }
  function isNum(value) { return typeof value === 'number' }
  function isInt(value) { return typeof value === 'number' && Number.isInteger(value) }
  // Python f"{x:.Nf}": exact binary value, round half to even.
  function pyFixed(x, digits) {
    var negative = x < 0 || Object.is(x, -0), view = new DataView(new ArrayBuffer(8))
    view.setFloat64(0, Math.abs(x))
    var hi = view.getUint32(0), lo = view.getUint32(4), exponent = (hi >>> 20) & 0x7ff
    var mantissa = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo)
    if (exponent === 0) exponent = 1; else mantissa |= 1n << 52n
    var shift = exponent - 1075, scaled = mantissa * 10n ** BigInt(digits), q
    if (shift >= 0) q = scaled << BigInt(shift)
    else {
      var denominator = 1n << BigInt(-shift), remainder = scaled % denominator
      q = scaled / denominator
      if (2n * remainder > denominator || (2n * remainder === denominator && q % 2n === 1n)) q += 1n
    }
    var text = q.toString().padStart(digits + 1, '0')
    return (negative ? '-' : '') + (digits ? text.slice(0, -digits) + '.' + text.slice(-digits) : text)
  }
  // Python f"{x:g}" for values in clinical ranges.
  function pyG(x) {
    var text = x.toPrecision(6)
    if (text.indexOf('e') >= 0) return text
    return text.indexOf('.') >= 0 ? text.replace(/0+$/, '').replace(/\.$/, '') : text
  }
  function parseInstant(value) {
    var text = String(value)
    if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([zZ]|[+-]\d{2}:?\d{2})$/.test(text)) throw new Error('Invalid observation timestamp')
    var stamp = Date.parse(text.replace(' ', 'T'))
    if (!Number.isFinite(stamp)) throw new Error('Invalid observation timestamp')
    return stamp
  }

  // ---- safety rules (clinical.py) ----------------------------------------
  var C_ACE = set(['lisinopril', 'enalapril', 'ramipril', 'captopril', 'perindopril'])
  var C_ARB = set(['losartan', 'valsartan', 'candesartan', 'telmisartan', 'irbesartan'])
  var C_DIURETIC = set(['hydrochlorothiazide', 'chlorthalidone', 'indapamide', 'furosemide', 'spironolactone'])
  var C_NSAID = set(['ibuprofen', 'diclofenac', 'naproxen', 'celecoxib'])
  var C_SULFONYLUREA = set(['glibenclamide', 'gliclazide', 'glimepiride'])
  var C_SGLT2 = set(['empagliflozin', 'dapagliflozin', 'canagliflozin'])
  var C_SUPPORTED = union(C_ACE, C_ARB, C_DIURETIC, C_NSAID, C_SULFONYLUREA, C_SGLT2, set([
    'metformin', 'insulin', 'amlodipine', 'nifedipine', 'aspirin', 'atorvastatin',
    'salbutamol', 'budesonide', 'beclometasone', 'formoterol', 'salmeterol',
    'ipratropium', 'tiotropium', 'prednisolone']))
  var C_ALIASES = { glyburide: 'glibenclamide', hctz: 'hydrochlorothiazide' }
  var PRIORITY = { routine: 0, soon: 1, urgent: 2, emergency: 3 }
  var SEVERITY = { critical: 0, warning: 1, info: 2 }
  var ACUTE_SYMPTOMS = set(['chest_pain', 'breathlessness', 'neurological_deficit', 'confusion', 'seizure'])
  var BP_DANGER_SYMPTOMS = set(['severe_headache', 'visual_disturbance', 'vomiting'])
  var KNOWN_FIELDS = ['known_hypertension', 'known_diabetes', 'known_asthma', 'known_copd', 'known_ckd', 'known_cancer']
  function ingredient(value) { var n = normal(value); return has(C_ALIASES, n) ? C_ALIASES[n] : n }

  function assess(data, age, sex, options) {
    options = options || {}
    var nowMs = options.now != null ? options.now : Date.now()
    if (data === null || typeof data !== 'object' || Array.isArray(data)) throw new Error('Clinical data must be an object')
    if (!isInt(age) || age < 18 || age > 120) throw new Error('The adult NCD pathway supports ages 18 through 120 only')
    var result = {
      id: options.id || ('offline-' + nowMs), urgency: 'routine', summary: '', recommendations: [], missing_data: [],
      warnings: [
        'Clinician verification is required; clinical evaluation of this limited implementation is ongoing.',
        'This is a limited advisory screen, not diagnosis, prescribing, or clearance for discharge.',
        'Unstructured notes are not interpreted by these safety rules; enter critical findings in structured fields.',
      ],
      model_info: { mode: 'deterministic_rules', status: REGISTRY.review_status },
      evidence_version: REGISTRY.version, rules_version: RULESET_VERSION,
      generated_at: new Date(nowMs).toISOString(),
    }
    var recs = result.recommendations, missing = []
    function add(ruleId, category, severity, urgency, title, detail) {
      if (recs.some(function (r) { return r.rule_id === ruleId })) throw new Error('Duplicate rule identifier')
      recs.push({ id: ruleId, rule_id: ruleId, category: category, severity: severity, title: title, detail: detail,
        evidence: evidence.apply(null, Array.prototype.slice.call(arguments, 6)) })
      if (PRIORITY[urgency] > PRIORITY[result.urgency]) result.urgency = urgency
    }
    function num(key, minimum, maximum) {
      var value = get(data, key)
      if (value == null) return null
      if (!isNum(value)) throw new Error(key + ' must be a finite number or null')
      if (!Number.isFinite(value) || !(minimum <= value && value <= maximum)) throw new Error(key + ' is outside the supported measurement range')
      return value
    }
    var sbp = num('systolic_bp', 40, 300), dbp = num('diastolic_bp', 20, 200)
    var rsbp = num('repeat_systolic_bp', 40, 300), rdbp = num('repeat_diastolic_bp', 20, 200)
    ;[[sbp, dbp], [rsbp, rdbp]].forEach(function (pair) {
      if (pair[0] != null && pair[1] != null && pair[0] <= pair[1]) throw new Error('Systolic pressure must exceed diastolic pressure')
    })
    var egfr = num('egfr', 0, 200), potassium = num('potassium', 1, 10)
    var creatinine = num('creatinine_umol', 10, 3000), calculatedEgfr = null
    if (egfr == null && creatinine != null) { calculatedEgfr = ckdEpi2021(creatinine, age, sex); egfr = calculatedEgfr }
    var pulse = num('pulse', 20, 250)
    var hba1c = num('hba1c', 2, 25)
    var spo2 = num('oxygen_saturation', 1, 100), rr = num('respiratory_rate', 1, 80)
    var glucose = num('glucose', 0.01, 1500)
    var unit = get(data, 'glucose_unit')
    if (glucose != null) {
      if (unit !== 'mg/dL' && unit !== 'mmol/L') throw new Error('A measured glucose requires an explicit supported unit')
      glucose = unit === 'mg/dL' ? glucose / 18.0 : glucose
      if (glucose > 83.34) throw new Error('Glucose outside supported range; verify its units')
    }
    var symptoms = set(get(data, 'symptoms') || [])
    var meds = get(data, 'medications') || []
    var codes = meds.map(function (m) { return ingredient(get(m, 'code')) })
    var codeSet = set(codes)
    var allergies = set((get(data, 'allergies') || []).map(ingredient))
    var pregnancy = get(data, 'pregnancy_status', 'unknown')
    if (['yes', 'no', 'unknown', 'not_applicable'].indexOf(pregnancy) < 0) throw new Error('Unrecognized pregnancy status')
    KNOWN_FIELDS.concat(['acutely_unwell', 'acute_kidney_injury']).forEach(function (field) {
      if (['yes', 'no', 'unknown'].indexOf(get(data, field, 'unknown')) < 0) throw new Error('Unrecognized ' + field + ' status')
    })
    var pregnant = pregnancy === 'yes'
    var diabetic = get(data, 'known_diabetes') === 'yes'
    var hypertensive = get(data, 'known_hypertension') === 'yes'
    var renalDisease = get(data, 'known_ckd') === 'yes'
    var highs = [sbp, rsbp].filter(function (v) { return v != null }), highd = [dbp, rdbp].filter(function (v) { return v != null })
    var highestSbp = highs.length ? Math.max.apply(null, highs) : null, highestDbp = highd.length ? Math.max.apply(null, highd) : null
    function bpAtLeast(s, d) { return (highestSbp != null && highestSbp >= s) || (highestDbp != null && highestDbp >= d) }
    function anyIn(values, group) { return values.some(function (v) { return group.has(v) }) }
    var sym = Array.from(symptoms)

    if (anyIn(sym, ACUTE_SYMPTOMS)) add('EMERGENCY_SYMPTOMS', 'acute_safety', 'critical', 'emergency', 'Immediate acute assessment',
      'Recorded acute warning symptoms need immediate clinician assessment and the local emergency pathway. Normal BP or glucose cannot rule out an emergency.', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC')
    if ([sbp, rsbp].some(function (v) { return v != null && v <= 90 })) add('LOW_BP', 'acute_safety', 'warning', 'urgent', 'Low systolic BP needs assessment',
      'Assess perfusion, symptoms, medicines and change from baseline now; verify the measurement. This is an isolated vital-sign flag, not a shock diagnosis or NEWS2 score.', 'RCP_NEWS2', 'NCDAI_SAFETY_SPEC')
    if (pulse != null && (pulse <= 40 || pulse >= 131)) add('PULSE_EXTREME', 'acute_safety', 'warning', 'urgent', 'Marked pulse abnormality',
      'Confirm pulse, assess symptoms and rhythm, and obtain prompt clinical review. The complete early-warning assessment is outside this screen.', 'RCP_NEWS2', 'NCDAI_SAFETY_SPEC')
    if (rr != null && rr <= 8) add('RESP_SLOW', 'acute_safety', 'critical', 'emergency', 'Very low respiratory rate',
      'Obtain immediate clinical assessment of airway, breathing and consciousness. This flag does not determine the cause or treatment.', 'RCP_NEWS2', 'NCDAI_SAFETY_SPEC')
    if (bpAtLeast(180, 110) && anyIn(sym, BP_DANGER_SYMPTOMS)) add('BP_CRISIS', 'acute_safety', 'critical', 'emergency', 'Severe BP with warning symptoms',
      'Assess possible acute organ injury immediately. Repeat BP when feasible without delaying urgent care; this alert does not diagnose a hypertensive emergency.', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC')
    else if (bpAtLeast(180, 110)) add('BP_SEVERE', 'hypertension', 'critical', 'urgent', 'Severe blood pressure reading',
      'Arrange same-day clinical assessment for organ injury, repeat measurement and a supervised management plan. Symptoms not documented cannot be assumed absent.', 'WHO_HTN_2021', 'NCDAI_SAFETY_SPEC')
    if (pregnant) {
      add('PREGNANCY_SCOPE', 'scope', 'warning', 'urgent', 'Use the pregnancy care pathway',
        'Obtain obstetric review. Adult non-pregnancy NCD treatment logic is withheld; maternal and fetal assessment require a separate approved pathway.', 'NICE_PREGNANCY', 'WHO_HTN_2021')
      if (bpAtLeast(160, 110)) add('PREGNANCY_SEVERE_BP', 'acute_safety', 'critical', 'emergency', 'Severe BP in pregnancy',
        'Activate immediate obstetric assessment for this severe reading. Repeat promptly without delaying escalation.', 'NICE_PREGNANCY')
      else if (anyIn(sym, BP_DANGER_SYMPTOMS)) add('PREGNANCY_WARNING', 'acute_safety', 'critical', 'emergency', 'Pregnancy warning symptoms',
        'Promptly assess possible pregnancy complications using the obstetric emergency pathway, even when BP is unavailable or below the severe threshold.', 'NICE_PREGNANCY', 'NCDAI_SAFETY_SPEC')
    }
    if (glucose != null && glucose <= 3.9 + 1e-9) {
      var danger = glucose < 3 || symptoms.has('confusion') || symptoms.has('seizure')
      add('HYPOGLYCEMIA', 'acute_safety', 'critical', danger ? 'emergency' : 'urgent', 'Low glucose requires action now',
        'Glucose is ' + pyFixed(glucose, 2) + ' mmol/L. Assess consciousness and treat immediately through the local hypoglycaemia protocol; recheck and investigate the cause. No automatic dose or route is generated.',
        'KENYA_NCD_PROTOCOLS', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC')
    } else if (symptoms.has('hypoglycemia_symptoms')) {
      add('SUSPECTED_HYPOGLYCEMIA', 'acute_safety', 'warning', 'urgent', 'Assess reported hypoglycaemia symptoms now',
        'Check a current glucose and clinical state. A missing or older normal result does not resolve these symptoms; follow the local acute assessment protocol.', 'KENYA_NCD_PROTOCOLS')
      missing.push('current_glucose_for_symptoms')
    }
    if (glucose != null && glucose >= 18) {
      var crisis = symptoms.has('vomiting') || symptoms.has('dehydration') || symptoms.has('confusion')
      add(crisis ? 'HYPERGLYCEMIC_CRISIS' : 'GLUCOSE_HIGH', 'acute_safety', 'critical', crisis ? 'emergency' : 'urgent',
        crisis ? 'Assess possible hyperglycaemic crisis' : 'Markedly elevated glucose',
        'Obtain acute clinical assessment, hydration status and ketones where available. Laboratory and clinical assessment must establish the cause; no insulin or fluid dose is generated.', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC')
    }
    if (intersects(codeSet, C_SGLT2) && (symptoms.has('vomiting') || symptoms.has('dehydration'))) add('SGLT2_ACUTE_ILLNESS', 'medication_safety', 'critical', 'urgent', 'Acute illness with an SGLT2 inhibitor',
      'Assess for ketoacidosis, including when glucose is not markedly high. Obtain urgent clinician medication review and ketone assessment; a normal glucose cannot provide clearance.', 'SGLT2_LABEL', 'NCDAI_SAFETY_SPEC')
    if (spo2 != null && spo2 < 95) add('RESP_HYPOXEMIA', 'respiratory', spo2 < 92 ? 'critical' : 'warning', spo2 < 92 ? 'emergency' : 'urgent', 'Low oxygen saturation needs assessment',
      'Recorded SpO2 is ' + pyG(spo2) + '%. Check signal quality and assess immediately if below 92%. Confirm baseline, oxygen use and clinical state; this tool does not set an oxygen dose or target.', 'WHO_PEN_2020', 'NCDAI_SAFETY_SPEC')
    if (rr != null && rr > 25) add('RESP_TACHYPNEA', 'respiratory', 'warning', 'urgent', 'Raised respiratory rate',
      'Assess respiratory effort and acute causes now; a chronic respiratory diagnosis must not obscure other causes of rapid breathing.', 'WHO_PEN_2020', 'NCDAI_SAFETY_SPEC')
    if (symptoms.has('wheeze')) add('RESP_WHEEZE', 'respiratory', 'warning', 'urgent', 'Assess current wheeze',
      'Evaluate exacerbation severity, oxygenation and the existing action plan. Review alternative diagnoses and arrange supervised acute management.', 'WHO_PEN_2020')
    if (symptoms.has('hemoptysis')) add('HEMOPTYSIS', 'referral', 'warning', 'urgent', 'Assess coughing blood today',
      'Establish bleeding amount, stability and respiratory status, and investigate infection including TB and other causes. Escalate immediately if unstable; no cancer diagnosis is inferred.', 'NCI_CANCER_SYMPTOMS', 'NCDAI_SAFETY_SPEC')
    if (anyIn(sym, set(['unexplained_weight_loss', 'persistent_cough', 'breast_lump', 'abnormal_bleeding']))) add('CANCER_WARNING', 'referral', 'warning', symptoms.has('abnormal_bleeding') ? 'urgent' : 'soon', 'Arrange diagnostic assessment of warning symptoms',
      'Confirm symptom duration, bleeding severity, examination findings and relevant risk history; establish a tracked diagnostic/referral plan. These symptoms can have non-cancer causes, including infection.', 'NCI_CANCER_SYMPTOMS', 'WHO_CANCER_DIAGNOSIS')
    if (egfr != null && egfr < 30) add('RENAL_SEVERE', 'kidney', 'critical', 'urgent', 'Severely reduced kidney function',
      'Arrange prompt clinical assessment and referral planning; assess acute deterioration, urine output and previous results. A single result cannot establish chronicity.', 'WHO_HEARTS_D_2020', 'KDIGO_CKD_2024')
    if (potassium != null && potassium >= 5.5) {
      var acuteK = get(data, 'acutely_unwell') === 'yes' || get(data, 'acute_kidney_injury') === 'yes' || get(get(data, 'dosing_context') || {}, 'acute_illness') === 'yes'
      ;['acutely_unwell', 'acute_kidney_injury'].forEach(function (field) { if (get(data, field, 'unknown') === 'unknown') missing.push(field) })
      var detail
      if (potassium >= 6.5) detail = 'Arrange immediate hospital assessment and treatment. Do not delay transfer for a community repeat sample.'
      else if (acuteK) detail = 'Arrange same-day hospital assessment because acute illness or acute kidney injury is recorded. Escalate immediately if unstable; do not wait for routine repeat testing.'
      else if (potassium >= 6) detail = 'Arrange same-day clinical review and repeat potassium within one day. Assess whether hospital care is needed.'
      else detail = 'For an unexpected result, repeat potassium within three days, or sooner as clinically indicated. Confirm clinical stability and previous results before setting follow-up.'
      detail += ' Assess clinical state, ECG needs, sample validity and medicines. Unknown acute illness or kidney injury must be assessed now; if present, consider hospital assessment today. No potassium-lowering dose is generated.'
      add('POTASSIUM_HIGH', 'acute_safety', potassium >= 6 || acuteK ? 'critical' : 'warning',
        potassium >= 6.5 ? 'emergency' : potassium >= 6 || acuteK ? 'urgent' : 'soon', 'Elevated potassium', detail, 'UKKA_POTASSIUM_2026')
    }
    if (potassium != null && potassium < 3.5) add('POTASSIUM_LOW', 'acute_safety', potassium < 3 ? 'critical' : 'warning',
      potassium < 2.5 ? 'emergency' : potassium < 3 ? 'urgent' : 'soon', 'Reduced potassium',
      'Review symptoms, ECG, medicines and magnesium. Below 2.5 mmol/L requires immediate supervised assessment; no electrolyte replacement dose is generated.', 'NHS_LOW_POTASSIUM')
    if (symptoms.has('foot_ulcer')) add('FOOT_ULCER', 'referral', 'warning', 'urgent', 'Assess foot ulcer and limb risk',
      'Assess infection, perfusion and systemic illness today. Infection, gangrene or critical ischaemia warrants urgent referral; absence of these findings has not been established.', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC')
    if (codeSet.has('metformin')) {
      if (egfr == null) missing.push('egfr_for_metformin_review')
      else if (egfr < 30) add('METFORMIN_RENAL', 'medication_safety', 'critical', 'urgent', 'Metformin renal contraindication flag',
        "Recorded eGFR is below the metformin label's renal limit. Obtain urgent prescriber review of current therapy; the system does not issue a prescription change.", 'METFORMIN_LABEL')
      else if (egfr < 45) add('METFORMIN_REVIEW', 'medication_safety', 'warning', 'soon', 'Review metformin with reduced eGFR',
        "Review benefit, risk and monitoring of existing metformin therapy. Initiation is not recommended in this renal range by the referenced label.", 'METFORMIN_LABEL')
    }
    if (codeSet.has('glibenclamide') && age >= 60) add('GLIBENCLAMIDE_OLDER_ADULT', 'medication_safety', 'warning', 'soon', 'Review glibenclamide in an older adult',
      'The referenced WHO protocol advises avoiding glibenclamide from age 60. Review the current regimen and hypoglycaemia risk with the prescriber.', 'WHO_HEARTS_MEDS_2018')
    if (intersects(codeSet, C_SULFONYLUREA) && egfr != null && egfr < 60) add('SULFONYLUREA_RENAL', 'medication_safety', 'warning', 'soon', 'Review sulfonylurea with impaired kidney function',
      'Renal impairment can increase hypoglycaemia risk. Review the exact medicine, prior episodes, eating pattern and monitoring; do not infer a safe dose from this screen.', 'NICE_DIABETES_2026', 'NCDAI_SAFETY_SPEC')
    if (intersects(codeSet, union(C_ACE, C_ARB))) {
      if (pregnant) add('RAS_PREGNANCY', 'medication_safety', 'critical', 'urgent', 'ACE inhibitor/ARB in pregnancy',
        'Arrange urgent prescriber and obstetric review of the recorded renin-angiotensin-system medicine because of fetal risk. No replacement drug is selected automatically.', 'NICE_PREGNANCY', 'LISINOPRIL_LABEL')
      if (pregnancy === 'unknown') missing.push('pregnancy_status_for_RAS_medication_review')
      if (egfr == null) missing.push('egfr_for_RAS_medication_review')
      if (potassium == null) missing.push('potassium_for_RAS_medication_review')
    }
    if (intersects(codeSet, C_ACE) && intersects(codeSet, C_ARB)) add('DUAL_RAS', 'medication_safety', 'warning', 'soon', 'Combined ACE inhibitor and ARB recorded',
      'Reconcile both medicines and seek prescriber review for renal, potassium and hypotension risk.', 'LISINOPRIL_LABEL')
    if (intersects(codeSet, union(C_ACE, C_ARB)) && codeSet.has('spironolactone')) add('POTASSIUM_MEDICATION_RISK', 'medication_safety', 'warning', 'soon', 'Potassium-raising combination',
      'Verify indication, kidney function and potassium monitoring for this combination; no dose change is inferred.', 'LISINOPRIL_LABEL')
    if (intersects(codeSet, C_NSAID) && intersects(codeSet, union(C_ACE, C_ARB))) add('NSAID_RENAL', 'medication_safety', 'warning', 'soon', 'NSAID with ACE inhibitor/ARB',
      'Review renal risk, hydration and non-prescription medicines. Concurrent diuretic use adds concern; arrange supervised medication reconciliation.', 'LISINOPRIL_LABEL')
    var conflicts = sortedStrings(intersection(codeSet, allergies))
    var extra = new Set()
    meds.forEach(function (m, i) { if (allergies.has(ingredient(get(m, 'name')))) extra.add(codes[i]) })
    conflicts = conflicts.concat(sortedStrings(Array.from(extra).filter(function (c) { return conflicts.indexOf(c) < 0 })))
    if (conflicts.length) add('ALLERGY_CONFLICT', 'medication_safety', 'critical', 'urgent', 'Medicine overlaps a recorded allergy',
      'Potential exact-match conflict: ' + conflicts.join(', ') + '. Confirm the substance, reaction and severity with a clinician before administration decisions.', 'NCDAI_SAFETY_SPEC')
    var counts = {}
    codes.forEach(function (c) { counts[c] = (counts[c] || 0) + 1 })
    var duplicate = sortedStrings(Object.keys(counts).filter(function (c) { return counts[c] > 1 }))
    if (duplicate.length) add('DUPLICATE_MEDICATION', 'medication_safety', 'warning', 'soon', 'Possible duplicate medicine entries',
      'Reconcile duplicate ingredient codes: ' + duplicate.join(', ') + '. Separate schedules may be intentional; never combine doses automatically.', 'NCDAI_SAFETY_SPEC')
    var unsupported = sortedStrings(Array.from(codeSet).filter(function (c) { return !C_SUPPORTED.has(c) }))
    if (unsupported.length) add('MEDICATION_UNSUPPORTED', 'medication_safety', 'warning', 'soon', 'Medicines outside the rule dictionary',
      'Manual pharmacist/prescriber review required for: ' + unsupported.join(', ') + '. Absence of an interaction alert does not establish compatibility.', 'NCDAI_SAFETY_SPEC')

    var acute = PRIORITY[result.urgency] >= PRIORITY.urgent
    if (!pregnant && !acute) {
      if (bpAtLeast(160, 100)) add('BP_HIGH', 'hypertension', 'warning', 'soon', 'Prompt BP treatment review',
        'Confirm measurement and arrange clinician review without delay, including adherence and contraindications. Do not derive a new prescription from this reading alone.', 'WHO_HTN_2021')
      else if (bpAtLeast(140, 90)) add('BP_REVIEW', 'hypertension', 'warning', 'soon', 'Raised BP needs confirmation and review',
        'Confirm the reading and previous diagnosis; review the care plan, medicines and adherence with the clinician.', 'WHO_HTN_2021')
      else if (hypertensive) add('HTN_FOLLOWUP', 'hypertension', 'info', 'routine', 'Continue an individualized BP review plan',
        'Review the agreed target, tolerability and follow-up timing. Diabetes or kidney/CV disease may change targets; incomplete data cannot establish control.', 'WHO_HTN_2021')
      if (hba1c != null && hba1c >= 6.5 && !diabetic) add('DIABETES_CONFIRM', 'diabetes', 'warning', 'soon', 'Confirm possible diabetes',
        'Review diagnostic context and confirmatory testing; do not diagnose from this value alone, particularly where HbA1c reliability is uncertain.', 'KENYA_NCD_PROTOCOLS')
      else if (glucose != null && glucose >= 11.1 && !diabetic) add('DIABETES_CONFIRM', 'diabetes', 'warning', 'soon', 'Clarify elevated glucose and diagnosis',
        'Establish fasting/random status, symptoms and confirmatory testing. A single unspecified glucose measurement is not a diagnosis.', 'KENYA_NCD_PROTOCOLS')
      if (diabetic) add('DIABETES_REVIEW', 'diabetes', hba1c != null && hba1c >= 9 ? 'warning' : 'info',
        hba1c != null && hba1c >= 9 ? 'soon' : 'routine', 'Review diabetes control and complication screening',
        'Review the individualized glycaemic goal, hypoglycaemia, adherence, kidney/eye/foot checks and follow-up. A high HbA1c prompts review, not automatic intensification.', 'KENYA_NCD_PROTOCOLS', 'NCDAI_SAFETY_SPEC')
      if (renalDisease || (egfr != null && egfr < 60)) add('CKD_REVIEW', 'kidney', 'warning', 'soon', 'Review kidney status and chronicity',
        'Check prior eGFR, urine albumin and possible acute causes; confirm persistent abnormality rather than labeling one low result as CKD.', 'KDIGO_CKD_2024')
      if (get(data, 'known_asthma') === 'yes' || get(data, 'known_copd') === 'yes') add('RESP_CHRONIC_REVIEW', 'respiratory', 'info', 'soon', 'Review chronic respiratory care',
        'Confirm diagnosis with appropriate testing, inhaler technique, adherence, triggers, exacerbation history and a written action plan.', 'WHO_PEN_2020')
      if (get(data, 'known_cancer') === 'yes') add('CANCER_SCOPE', 'continuity', 'info', 'soon', 'Coordinate with the treating cancer team',
        'Reconcile the oncology plan, supportive care needs and referral follow-through. Cancer staging and treatment are outside this release.', 'WHO_CANCER_DIAGNOSIS', 'NCDAI_SAFETY_SPEC')
      if (get(data, 'tobacco_use') === 'current') add('TOBACCO_SUPPORT', 'prevention', 'info', 'routine', 'Offer tobacco cessation support',
        'Discuss readiness and access to a locally approved cessation service and document the agreed support plan.', 'WHO_PEN_2020')
      if (get(data, 'adherence') === 'missed') add('ADHERENCE_REVIEW', 'continuity', 'info', 'soon', 'Explore missed medicine use',
        'Discuss barriers, affordability, adverse effects and understanding before treatment changes; agree a feasible plan with the patient.', 'NCDAI_SAFETY_SPEC', 'WHO_HTN_2021')
    }
    if (sbp == null) missing.push('systolic_bp')
    if (dbp == null) missing.push('diastolic_bp')
    if (bpAtLeast(140, 90) && (rsbp == null || rdbp == null)) missing.push('repeat_blood_pressure')
    if (diabetic && hba1c == null && glucose == null) missing.push('glycaemic_measurement')
    if ((diabetic || renalDisease) && egfr == null) missing.push('egfr')
    if (symptoms.has('wheeze') || symptoms.has('breathlessness')) {
      if (spo2 == null) missing.push('oxygen_saturation')
      if (rr == null) missing.push('respiratory_rate')
    }
    if (pregnancy === 'unknown') missing.push('pregnancy_status')
    ;['medications_reviewed', 'allergies_reviewed', 'symptoms_reviewed'].forEach(function (field) { if (get(data, field) !== true) missing.push(field) })
    KNOWN_FIELDS.forEach(function (field) { if (get(data, field, 'unknown') === 'unknown') missing.push(field) })
    if (get(data, 'medicine_availability', 'unknown') !== 'available') result.warnings.push('Confirm medicine stock, cost and access; availability is unverified or limited.')
    if (meds.some(function (m) { return get(m, 'dose') == null || !get(m, 'unit') || !get(m, 'frequency') })) result.warnings.push('One or more medication schedules are incomplete; dose safety has not been evaluated.')
    if (calculatedEgfr != null) result.warnings.push('eGFR ' + fmt(calculatedEgfr) + ' mL/min/1.73 m² was calculated from creatinine (CKD-EPI 2021) and used by these rules; confirm the result date and trend.')
    result.warnings.push('Medication checks are limited to selected ingredients and exact allergy matches; cross-reactivity, all interactions and dose appropriateness are not covered.')
    var observed = get(data, 'observed_at')
    if (!observed) missing.push('observed_at')
    else {
      var stamp = parseInstant(observed)
      if (stamp > nowMs + 5 * 60000) throw new Error('Invalid observation timestamp')
      if (nowMs - stamp > 24 * 3600000) {
        result.warnings.push('Measurements are over 24 hours old. Verify current status; historical danger readings are not discarded.')
        missing.push('current_observations')
      }
    }
    result.missing_data = sortedStrings(unique(missing))
    if (missing.length) add('DATA_COMPLETENESS', 'data_quality', 'warning', 'soon', 'Complete essential assessment information',
      'Review the missing-data list. Unknown, unreviewed and absent findings are distinct. Emergency assessment must not wait for routine documentation.', 'NCDAI_SAFETY_SPEC')
    if (!recs.length) add('CLINICIAN_REVIEW', 'scope', 'info', 'routine', 'Complete clinician review',
      'No configured high-priority rule triggered from the supplied structured fields. Review the patient and full record; this screen does not establish safety or exclude disease.', 'NCDAI_SAFETY_SPEC')
    recs.sort(function (a, b) { return SEVERITY[a.severity] - SEVERITY[b.severity] || (a.rule_id < b.rule_id ? -1 : a.rule_id > b.rule_id ? 1 : 0) })
    result.summary = {
      emergency: 'Immediate clinician assessment and the appropriate emergency pathway are advised.',
      urgent: 'Same-day clinician assessment is advised; act now for low glucose or evolving symptoms.',
      soon: 'Clinician review and completion of identified checks are advised; timing needs clinical confirmation.',
      routine: 'Complete the supervised NCD review and agree follow-up; this result does not provide clinical clearance.',
    }[result.urgency]
    result.consultant = build(data, age, sex, result)
    return result
  }

  // ---- consultant synthesis (reasoning.py) --------------------------------
  var ALIASES = { glyburide: 'glibenclamide', hctz: 'hydrochlorothiazide', albuterol: 'salbutamol', frusemide: 'furosemide', acetylsalicylic: 'aspirin', asa: 'aspirin' }
  var ACEI = set(['lisinopril', 'enalapril', 'ramipril', 'captopril', 'perindopril'])
  var ARB = set(['losartan', 'valsartan', 'candesartan', 'telmisartan', 'irbesartan', 'olmesartan'])
  var DHP_CCB = set(['amlodipine', 'nifedipine', 'felodipine'])
  var NONDHP_CCB = set(['diltiazem', 'verapamil'])
  var THIAZIDE = set(['hydrochlorothiazide', 'chlorthalidone', 'indapamide', 'bendroflumethiazide'])
  var LOOP = set(['furosemide', 'torasemide', 'bumetanide'])
  var MRA = set(['spironolactone', 'eplerenone'])
  var BB_SELECTIVE = set(['bisoprolol', 'atenolol', 'metoprolol', 'nebivolol'])
  var BB_NONSELECTIVE = set(['propranolol', 'carvedilol', 'labetalol'])
  var BB_HF = set(['bisoprolol', 'carvedilol', 'metoprolol', 'nebivolol'])
  var OTHER_AHT = set(['methyldopa', 'hydralazine', 'doxazosin', 'prazosin', 'clonidine'])
  var STATIN = set(['atorvastatin', 'rosuvastatin', 'simvastatin', 'pravastatin'])
  var ANTIPLATELET = set(['aspirin', 'clopidogrel'])
  var ANTICOAG = set(['warfarin', 'rivaroxaban', 'apixaban', 'dabigatran', 'edoxaban'])
  var SULFONYLUREA = set(['glibenclamide', 'gliclazide', 'glimepiride'])
  var SGLT2 = set(['empagliflozin', 'dapagliflozin', 'canagliflozin'])
  var GLP1 = set(['liraglutide', 'semaglutide', 'dulaglutide', 'exenatide'])
  var DPP4 = set(['sitagliptin', 'linagliptin', 'saxagliptin', 'vildagliptin'])
  var INSULIN = set(['insulin', 'glargine', 'detemir', 'degludec', 'aspart', 'lispro', 'glulisine', 'isophane', 'mixtard', 'actrapid'])
  var ICS = set(['budesonide', 'beclometasone', 'beclomethasone', 'fluticasone', 'mometasone', 'ciclesonide'])
  var LABA = set(['formoterol', 'salmeterol', 'vilanterol', 'indacaterol', 'olodaterol'])
  var LAMA = set(['tiotropium', 'umeclidinium', 'glycopyrronium'])
  var SABA = set(['salbutamol', 'terbutaline'])
  var NSAID = set(['ibuprofen', 'diclofenac', 'naproxen', 'celecoxib', 'indomethacin', 'meloxicam', 'piroxicam', 'ketoprofen'])
  var STATUS_ORDER = { acute: 0, uncontrolled: 1, untreated: 1, above_target: 1, high_risk: 1, review: 2, unconfirmed: 2,
    needs_confirmation: 2, at_risk: 3, needs_data: 3, established: 3, withheld: 3, at_target: 4 }
  var KDIGO_RISK = { G1: ['low', 'moderate', 'high'], G2: ['low', 'moderate', 'high'], G3a: ['moderate', 'high', 'very high'],
    G3b: ['high', 'very high', 'very high'], G4: ['very high', 'very high', 'very high'], G5: ['very high', 'very high', 'very high'] }
  var KDIGO_FREQ = { G1: [1, 1, 2], G2: [1, 1, 2], G3a: [1, 2, 3], G3b: [2, 3, 3], G4: [3, 3, 4], G5: [4, 4, 4] }
  var FRAMINGHAM = {
    female_lipid: { age: 2.32888, tc: 1.20904, hdl: -0.70833, sbp_u: 2.76157, sbp_t: 2.82263, smoke: 0.52873, dm: 0.69154, s0: 0.95012, mean: 26.1931 },
    male_lipid: { age: 3.06117, tc: 1.12370, hdl: -0.93263, sbp_u: 1.93303, sbp_t: 1.99881, smoke: 0.65451, dm: 0.57367, s0: 0.88936, mean: 23.9802 },
    female_bmi: { age: 2.72107, bmi: 0.51125, sbp_u: 2.81291, sbp_t: 2.88267, smoke: 0.61868, dm: 0.77763, s0: 0.94833, mean: 26.0145 },
    male_bmi: { age: 3.11296, bmi: 0.79277, sbp_u: 1.85508, sbp_t: 1.92672, smoke: 0.70953, dm: 0.53160, s0: 0.88431, mean: 23.9388 },
  }

  function ckdEpi2021(creatinineUmol, age, sex) {
    if ((sex !== 'female' && sex !== 'male') || creatinineUmol == null) return null
    var scr = creatinineUmol / 88.4
    var kappa = sex === 'female' ? 0.7 : 0.9, alpha = sex === 'female' ? -0.241 : -0.302
    var ratio = scr / kappa
    var value = 142 * Math.pow(Math.min(ratio, 1), alpha) * Math.pow(Math.max(ratio, 1), -1.2) * Math.pow(0.9938, age)
    return sex === 'female' ? value * 1.012 : value
  }
  function gStage(egfr) { return egfr >= 90 ? 'G1' : egfr >= 60 ? 'G2' : egfr >= 45 ? 'G3a' : egfr >= 30 ? 'G3b' : egfr >= 15 ? 'G4' : 'G5' }
  function aStage(acr) { return acr < 3 ? 'A1' : acr <= 30 ? 'A2' : 'A3' }
  function framingham(model, age, sbp, treated, smoker, diabetic, tc, hdl, bmi) {
    var c = FRAMINGHAM[model]
    var total = c.age * Math.log(age) + (treated ? c.sbp_t : c.sbp_u) * Math.log(sbp)
    total += (smoker ? c.smoke : 0) + (diabetic ? c.dm : 0)
    if (has(c, 'tc')) total += c.tc * Math.log(tc * 38.67) + c.hdl * Math.log(hdl * 38.67)
    else total += c.bmi * Math.log(bmi)
    return 1 - Math.pow(c.s0, Math.exp(total - c.mean))
  }

  function build(data, age, sex, assessment) {
    function num(key, low, high) {
      var value = get(data, key)
      if (value == null || !isNum(value)) return null
      return Number.isFinite(value) && low <= value && value <= high ? value : null
    }
    function tri(key) { var value = get(data, key, 'unknown'); return value === 'yes' || value === 'no' || value === 'unknown' ? value : 'unknown' }
    function sel(pairs) { return pairs.filter(function (p) { return p[1] }).map(function (p) { return p[0] }) }

    var context = get(data, 'dosing_context') || {}
    var frail = get(context, 'frailty') === 'yes'
    var pregnant = get(data, 'pregnancy_status') === 'yes'
    var womanChildbearing = sex === 'female' && age < 50 && !pregnant
    var sexWord = sex === 'female' ? 'woman' : sex === 'male' ? 'man' : 'adult'
    var urgency = get(assessment, 'urgency', 'routine')
    var criticalTitles = get(assessment, 'recommendations', []).filter(function (r) { return get(r, 'severity') === 'critical' }).map(function (r) { return r.title })

    // ---- medicines
    var meds = get(data, 'medications') || []
    var medIngredients = meds.map(function (med) {
      var found = new Set()
      ;[get(med, 'code'), get(med, 'name')].forEach(function (raw) {
        var code = normal(raw)
        if (!code) return
        found.add(has(ALIASES, code) ? ALIASES[code] : code)
        code.split('_').forEach(function (token) { found.add(has(ALIASES, token) ? ALIASES[token] : token) })
      })
      return found
    })
    var taking = new Set()
    medIngredients.forEach(function (found) { found.forEach(function (v) { taking.add(v) }) })
    function on(group) { return intersects(taking, group) }
    function doseOf(name) {
      for (var i = 0; i < meds.length; i++) {
        var dose = get(meds[i], 'dose')
        if (medIngredients[i].has(name) && isNum(dose) && normal(get(meds[i], 'unit')) === 'mg') return dose
      }
      return null
    }
    function names(group) { return sortedStrings(intersection(taking, group)) }

    var ras = on(union(ACEI, ARB))
    var classes = sel([['ACE inhibitor/ARB', on(union(ACEI, ARB))], ['calcium-channel blocker', on(union(DHP_CCB, NONDHP_CCB))],
      ['thiazide-like diuretic', on(THIAZIDE)], ['beta-blocker', on(union(BB_SELECTIVE, BB_NONSELECTIVE))],
      ['mineralocorticoid antagonist', on(MRA)], ['loop diuretic', on(LOOP)], ['other antihypertensive', on(OTHER_AHT)]])
    var onBpTreatment = classes.length > 0
    var insulin = on(INSULIN), sulfonylurea = on(SULFONYLUREA)

    // ---- measurements
    var sbp = num('systolic_bp', 40, 300), dbp = num('diastolic_bp', 20, 200)
    var rsbp = num('repeat_systolic_bp', 40, 300), rdbp = num('repeat_diastolic_bp', 20, 200)
    var readings = [[sbp, dbp], [rsbp, rdbp]].filter(function (p) { return p[0] != null && p[1] != null })
    var meanSbp = readings.length ? readings.reduce(function (t, p) { return t + p[0] }, 0) / readings.length : null
    var meanDbp = readings.length ? readings.reduce(function (t, p) { return t + p[1] }, 0) / readings.length : null
    var pulse = num('pulse', 20, 250)
    var spo2 = num('oxygen_saturation', 1, 100)
    var hba1c = num('hba1c', 2, 25)
    var glucose = num('glucose', 0.01, 1500)
    if (glucose != null) glucose = get(data, 'glucose_unit') === 'mg/dL' ? glucose / 18.0 : glucose
    var glucoseContext = get(data, 'glucose_context', 'unknown')
    var potassium = num('potassium', 1, 10)
    var creatinine = num('creatinine_umol', 10, 3000)
    var enteredEgfr = num('egfr', 0, 200)
    var calculatedEgfr = ckdEpi2021(creatinine, age, sex)
    var egfr = enteredEgfr != null ? enteredEgfr : calculatedEgfr
    var acr = num('urine_acr_mg_mmol', 0, 3000)
    var weight = num('weight_kg', 20, 350), height = num('height_cm', 100, 250), waist = num('waist_cm', 40, 250)
    var bmi = weight != null && height != null ? weight / Math.pow(height / 100, 2) : null
    var tc = num('total_cholesterol_mmol', 1, 20), hdl = num('hdl_mmol', 0.2, 5), ldl = num('ldl_mmol', 0.2, 15)
    var hb = num('hemoglobin_g_dl', 3, 25)
    var anaemia = hb != null && hb < (sex === 'female' ? 12 : 13)
    var hypos = get(data, 'hypoglycaemia_episodes_3m'); hypos = isInt(hypos) ? hypos : null
    var exacerbations = get(data, 'exacerbations_past_year'); exacerbations = isInt(exacerbations) ? exacerbations : null
    var reliever = get(data, 'reliever_use_per_week'); reliever = isInt(reliever) ? reliever : null
    var symptoms = new Set(get(data, 'symptoms') || [])
    var smoker = get(data, 'tobacco_use') === 'current'

    var diabetic = tri('known_diabetes') === 'yes', hypertensive = tri('known_hypertension') === 'yes'
    var ascvd = tri('known_ascvd') === 'yes', stroke = tri('prior_stroke_tia') === 'yes', anyAscvd = ascvd || stroke
    var heartFailure = tri('known_heart_failure') === 'yes', af = tri('known_atrial_fibrillation') === 'yes'
    var asthma = tri('known_asthma') === 'yes', copd = tri('known_copd') === 'yes'
    var ckdMarkers = (egfr != null && egfr < 60) || (acr != null && acr >= 3)
    var ckd = tri('known_ckd') === 'yes' || ckdMarkers
    var albuminuria = acr != null && acr >= 3

    var derived = [], problems = [], medReview = [], considerations = [], monitoring = [], gaps = [], usedSources = []
    function cite() { var ids = Array.prototype.slice.call(arguments); ids.forEach(function (id) { if (usedSources.indexOf(id) < 0) usedSources.push(id) }); return ids }
    function item(text) { return { text: text, source_ids: cite.apply(null, Array.prototype.slice.call(arguments, 1)) } }
    function derive(id, label, value, unit, interpretation, method) {
      derived.push({ id: id, label: label, value: value, unit: unit, interpretation: interpretation, method: method, source_ids: cite.apply(null, Array.prototype.slice.call(arguments, 6)) })
    }
    function monitor(id, test, timing, reason) {
      var ids = Array.prototype.slice.call(arguments, 4)
      if (!monitoring.some(function (e) { return e.id === id })) monitoring.push({ id: id, test: test, timing: timing, reason: reason, source_ids: cite.apply(null, ids) })
    }
    function gap(field, why) { if (!gaps.some(function (e) { return e.field === field })) gaps.push({ field: field, why: why }) }
    function review(id, severity, finding, action) { medReview.push({ id: id, severity: severity, finding: finding, action: action, source_ids: cite.apply(null, Array.prototype.slice.call(arguments, 4)) }) }
    function consider(id, text) { considerations.push({ id: id, text: text, source_ids: cite.apply(null, Array.prototype.slice.call(arguments, 2)) }) }
    function addProblem(id, title, status, facts, summary, plan, targets) {
      var sources = []
      plan.forEach(function (e) { sources = sources.concat(e.source_ids) })
      problems.push({ id: id, title: title, status: status, facts: facts.slice(), assessment: summary, plan: plan, targets: (targets || []).slice(), source_ids: unique(sources) })
    }
    var pregnancyNote = womanChildbearing ? 'Confirm pregnancy status and contraception first: ACE inhibitors, ARBs, statins and SGLT2 inhibitors are avoided in pregnancy.' : null

    // ---- derived measures
    if (meanSbp != null) derive('bp_mean', 'Office blood pressure', fmt0(meanSbp) + '/' + fmt0(meanDbp), 'mmHg', readings.length === 2 ? 'Mean of 2 readings' : 'Single reading',
      'Arithmetic mean of paired readings entered today', 'ISH_HTN_2020')
    if (calculatedEgfr != null) derive('egfr_ckd_epi', 'eGFR (calculated)', fmt(calculatedEgfr), 'mL/min/1.73 m²',
      enteredEgfr == null ? 'Used for this assessment' : 'Entered eGFR ' + fmt(enteredEgfr) + ' used; calculated value shown for cross-check',
      'CKD-EPI 2021 from creatinine ' + fmt(creatinine) + ' µmol/L, age ' + age + ', ' + sex, 'CKD_EPI_2021')
    else if (creatinine != null) gap('sex', 'CKD-EPI 2021 needs recorded female or male sex to calculate eGFR from creatinine.')
    if (hba1c != null) derive('hba1c_ifcc', 'HbA1c (IFCC)', fmt0((hba1c - 2.15) * 10.929), 'mmol/mol', 'Equivalent of ' + fmt(hba1c) + '% (NGSP)', 'IFCC = (NGSP − 2.15) × 10.929', 'ADA_SOC_2025')
    if (bmi != null) {
      var category = bmi < 18.5 ? 'underweight' : bmi < 25 ? 'healthy range' : bmi < 30 ? 'overweight' : bmi < 35 ? 'obesity class I' : bmi < 40 ? 'obesity class II' : 'obesity class III'
      derive('bmi', 'Body-mass index', fmt(bmi), 'kg/m²', cap(category), 'Weight ÷ height²', 'WHO_OBESITY')
    }
    if (waist != null && (sex === 'female' || sex === 'male')) {
      var wHigh = sex === 'female' ? 80 : 94, wVery = sex === 'female' ? 88 : 102
      var wRisk = waist >= wVery ? 'substantially increased' : waist >= wHigh ? 'increased' : 'not increased'
      derive('waist', 'Waist circumference', fmt(waist), 'cm', 'Metabolic risk ' + wRisk, 'WHO thresholds ' + wHigh + '/' + wVery + ' cm', 'WHO_OBESITY')
    }
    if (tc != null && hdl != null) derive('non_hdl', 'Non-HDL cholesterol', fmt(tc - hdl), 'mmol/L', 'Total minus HDL cholesterol', 'TC − HDL', 'ESC_LIPIDS_2019')
    var stageG = egfr != null ? gStage(egfr) : null, stageA = acr != null ? aStage(acr) : null
    var kidneyRisk = stageG && stageA ? KDIGO_RISK[stageG][Number(stageA[1]) - 1] : null
    if (stageG && (ckd || stageA)) derive('kdigo', 'Kidney stage (KDIGO)', stageG + (stageA || ''), '',
      kidneyRisk ? 'KDIGO risk: ' + kidneyRisk : 'Albuminuria category unknown: measure urine ACR',
      'eGFR ' + fmt(egfr) + (acr != null ? ', ACR ' + fmt(acr) + ' mg/mmol' : ''), 'KDIGO_CKD_2024_TX')

    // ---- cardiovascular risk
    var risk = { category: null, basis: '', percent: null, method: null, statement: '', source_ids: [] }
    var diabetesOrganDamage = diabetic && (albuminuria || (egfr != null && egfr < 60))
    var majorFactors = [hypertensive || onBpTreatment, smoker, bmi != null && bmi >= 30, tc != null && tc >= 5.2, age >= 50].filter(Boolean).length
    function setRisk(category, basis, ids) { risk.category = category; risk.basis = basis; risk.source_ids = ids }
    if (anyAscvd) setRisk('very high', 'established atherosclerotic cardiovascular disease', cite('ESC_LIPIDS_2019', 'WHO_HEARTS_RISK_2020'))
    else if (diabetesOrganDamage || (diabetic && majorFactors >= 3)) setRisk('very high', 'diabetes with ' + (diabetesOrganDamage ? 'kidney target-organ damage' : 'three or more major risk factors'), cite('ESC_LIPIDS_2019'))
    else if (egfr != null && egfr < 30) setRisk('very high', 'severe chronic kidney disease', cite('ESC_LIPIDS_2019'))
    else if (diabetic) setRisk('high', 'diabetes', cite('ESC_LIPIDS_2019', 'WHO_HEARTS_RISK_2020'))
    else if (egfr != null && egfr < 60) setRisk('high', 'moderate chronic kidney disease', cite('ESC_LIPIDS_2019'))
    else if ((tc != null && tc >= 8) || (ldl != null && ldl >= 4.9)) setRisk('high', 'markedly raised cholesterol (possible familial hypercholesterolaemia)', cite('ESC_LIPIDS_2019'))
    if (risk.category == null || risk.category !== 'very high') {
      var model = null
      if ((sex === 'female' || sex === 'male') && age >= 30 && age <= 74 && meanSbp != null && !anyAscvd) {
        if (tc != null && hdl != null) model = sex + '_lipid'
        else if (bmi != null) model = sex + '_bmi'
      }
      if (model) {
        var percent = r1(framingham(model, age, meanSbp, onBpTreatment, smoker, diabetic, tc, hdl, bmi) * 100)
        var method = 'Framingham 2008 general CVD, ' + (model.slice(-5) === 'lipid' ? 'laboratory (cholesterol)' : 'office (BMI)') + ' model'
        var tobacco = get(data, 'tobacco_use')
        if (tobacco == null || tobacco === 'unknown') method += '; tobacco status unknown, scored as non-smoker'
        risk.percent = percent; risk.method = method
        cite('FRAMINGHAM_2008', 'WHO_CVD_RISK_2019')
        if (risk.category == null) setRisk(percent >= 20 ? 'high' : percent >= 10 ? 'moderate' : 'low', 'estimated 10-year risk ' + fmt(percent) + '%', ['FRAMINGHAM_2008', 'WHO_CVD_RISK_2019'])
      } else if (risk.category == null && (age >= 40 || hypertensive || diabetic || smoker || ckd || onBpTreatment)) {
        if (meanSbp == null) gap('systolic_bp', 'Blood pressure is required to estimate cardiovascular risk.')
        if (!(tc != null && hdl != null) && bmi == null) gap('total_cholesterol_mmol', 'Total and HDL cholesterol (or weight and height for the office model) are required to estimate cardiovascular risk.')
      }
    }
    if (risk.category) {
      var estimated = risk.basis.indexOf('estimated') === 0
      var riskText = cap(risk.category) + ' cardiovascular risk (' + risk.basis + ')'
      if (risk.percent != null && !estimated) riskText += '; estimated 10-year risk ' + fmt(risk.percent) + '%'
      if (risk.percent != null) riskText += '. Framingham is not calibrated for Kenya; cross-check with the WHO Eastern sub-Saharan Africa chart'
      risk.statement = riskText + '.'
      derive.apply(null, ['cvd_risk', 'Cardiovascular risk', cap(risk.category), '', risk.basis + (risk.percent != null && !estimated ? '; 10-year risk ' + fmt(risk.percent) + '%' : ''),
        risk.method || 'Risk category from established disease (no calculator applies)'].concat(risk.source_ids))
    }
    var highRisk = risk.category === 'high' || risk.category === 'very high'

    // ---- pregnancy
    if (pregnant) addProblem('pregnancy', 'Pregnancy: obstetric-medicine pathway', 'withheld', ['Pregnancy recorded; age ' + age],
      'Chronic-disease treatment reasoning is withheld. Blood pressure, glucose and medicine decisions in pregnancy use pregnancy-specific thresholds and a different drug list.',
      [item('Review every current medicine for pregnancy safety today: ACE inhibitors, ARBs, statins, SGLT2 inhibitors and most oral glucose-lowering agents other than metformin are generally avoided.', 'NICE_PREGNANCY'),
        item('Arrange joint obstetric and physician care for any hypertension, diabetes or kidney disease.', 'NICE_PREGNANCY')])

    // ---- hypertension
    var plan, facts, status, summary
    if (!pregnant && (meanSbp != null || hypertensive)) {
      var target, targetText
      if (age >= 80 || frail) { target = [140, 90]; targetText = '<140/90 mmHg, individualised for age 80+ or frailty; avoid orthostatic symptoms' }
      else if (anyAscvd || diabetic || ckd || highRisk) { target = [130, 80]; targetText = '<130/80 mmHg (WHO 2021 systolic <130 with CVD, diabetes, CKD or high risk)' }
      else { target = [140, 90]; targetText = '<140/90 mmHg (WHO 2021); aim for <130/80 if well tolerated (ISH 2020, ESC 2024)' }
      if (meanSbp == null) {
        addProblem('hypertension', 'Hypertension', 'needs_data', ['Known hypertension', 'No blood pressure recorded today'], 'Control cannot be judged without a current reading.',
          [item('Measure seated BP twice, 1–2 minutes apart, with a validated device and correctly sized cuff.', 'WHO_HTN_2021', 'ISH_HTN_2020', 'ESC_HTN_2024')], [targetText])
        gap('systolic_bp', 'Needed to judge hypertension control.')
      } else {
        var bpText = fmt0(meanSbp) + '/' + fmt0(meanDbp) + ' mmHg'
        facts = ['BP ' + readings.map(function (p) { return fmt0(p[0]) + '/' + fmt0(p[1]) }).join('; ') + ' mmHg' + (readings.length > 1 ? ' (mean ' + bpText + ')' : '')]
        facts.push('On ' + (classes.length ? join(classes) : 'no antihypertensive class'))
        if (get(data, 'adherence') === 'missed') facts.push('Missed doses reported')
        var above = meanSbp >= target[0] || meanDbp >= target[1]
        if (!(hypertensive || onBpTreatment)) above = meanSbp >= 140 || meanDbp >= 90
        var severe = meanSbp >= 180 || meanDbp >= 110
        plan = []
        if (severe) {
          status = 'acute'
          summary = 'Severe hypertension (' + bpText + "). The safety findings govern today's action: assess for acute organ damage before any chronic plan."
          plan.push(item('Assess for hypertension-mediated organ damage now (chest pain, breathlessness, neurological signs, visual change, fundi, urine dipstick, creatinine, ECG).', 'WHO_HTN_2021', 'ESC_HTN_2024'))
        } else if (above && (hypertensive || onBpTreatment)) {
          status = 'uncontrolled'
          summary = 'Above target at ' + bpText + ' (target ' + targetText.split(' (')[0].split(',')[0] + '); systolic ' + fmt0(Math.max(meanSbp - target[0], 0)) + ' mmHg above the systolic goal on ' + classes.length + ' antihypertensive class' + (classes.length !== 1 ? 'es' : '') + '.'
        } else if (above) {
          status = 'unconfirmed'; summary = 'Raised BP (' + bpText + ') without a recorded hypertension diagnosis.'
        } else if (hypertensive || onBpTreatment) {
          status = 'at_target'; summary = 'At target (' + bpText + ') on ' + (classes.length ? join(classes) : 'no recorded medicine') + '.'
        } else if (meanSbp >= 130 || meanDbp >= 85 || (highRisk && meanDbp >= 80)) {
          status = 'at_risk'; summary = 'High-normal BP (' + bpText + ').'
        } else { status = null; summary = '' }
        if (status === 'unconfirmed') {
          plan.push(item('Confirm the diagnosis: repeat readings on a separate day, or home/ambulatory BP where available, before labelling hypertension (WHO 2021 recommends confirmation on two visits).', 'WHO_HTN_2021', 'ISH_HTN_2020'))
          if (meanSbp >= 160 || meanDbp >= 100 || highRisk) plan.push(item('Once confirmed, start drug treatment promptly' + (highRisk ? ' because cardiovascular risk is high' : ' because BP is ≥160/100') + '; WHO 2021 favours initial combination therapy, ideally a single-pill combination.', 'WHO_HTN_2021'))
          else plan.push(item('If confirmed at ≥140/90 mmHg, start drug treatment alongside lifestyle measures (WHO 2021).', 'WHO_HTN_2021'))
          plan.push(item('Baseline work-up: creatinine/eGFR, potassium, urine ACR or dipstick, glucose/HbA1c, lipids and ECG.', 'WHO_HTN_2021', 'KENYA_NCD_PROTOCOLS'))
        }
        if (status === 'uncontrolled') {
          if (get(data, 'adherence') === 'missed') plan.push(item('Address adherence before escalating: explore cost, side-effects, pill burden and beliefs; a single-pill combination and once-daily dosing help.', 'WHO_HTN_2021', 'ISH_HTN_2020'))
          plan.push(item('Confirm with correctly measured seated readings and, where available, home or ambulatory BP to exclude a white-coat effect before escalating.', 'ISH_HTN_2020', 'ESC_HTN_2024'))
          var hasCcb = on(union(DHP_CCB, NONDHP_CCB)), hasThiazide = on(THIAZIDE)
          var rasReason = (albuminuria || ckd) && !ras && !heartFailure ? (albuminuria ? 'albuminuria' : 'chronic kidney disease') : null
          var triple = [['ACE inhibitor/ARB', ras], ['dihydropyridine CCB', hasCcb], ['thiazide-like diuretic', hasThiazide]].filter(function (p) { return !p[1] }).map(function (p) { return p[0] })
          if (heartFailure) plan.push(item('In heart failure, first optimise the disease-modifying drugs (ACE inhibitor/ARB/ARNI, beta-blocker, MRA); add amlodipine if BP stays high and avoid diltiazem or verapamil.', 'ESC_HF_2021', 'ESC_HTN_2024'))
          else if (!classes.length) plan.push(item('Start treatment with a combination from ACE inhibitor/ARB, dihydropyridine CCB and thiazide-like diuretic classes, ideally as a single-pill combination, following the Kenya MOH step sequence.', 'WHO_HTN_2021', 'KENYA_NCD_PROTOCOLS'))
          else if (classes.length === 1) {
            if (rasReason) { plan.push(item('Add an ACE inhibitor or ARB as the second class (also indicated for ' + rasReason + '; see kidney plan) rather than only up-titrating monotherapy.', 'ISH_HTN_2020', 'KDIGO_CKD_2024_TX')); rasReason = null }
            else plan.push(item('Add a second class (' + triple.join(' or ') + ') rather than only up-titrating monotherapy; preferred pairs are ACE inhibitor/ARB + CCB or CCB + thiazide-like diuretic.', 'ISH_HTN_2020', 'WHO_HTN_2021'))
          } else if (!(ras && hasCcb && hasThiazide)) {
            plan.push(item('Move to the guideline triple combination by adding ' + join(triple) + ' (ACE inhibitor/ARB + CCB + thiazide-like diuretic)' + (rasReason ? '; the ACE inhibitor/ARB is also indicated for ' + rasReason + '.' : '.'), 'ISH_HTN_2020', 'ESC_HTN_2024'))
            rasReason = null
          } else {
            plan.push(item('This meets the definition of apparent resistant hypertension if doses are optimised: check adherence, measurement, salt/alcohol intake and interfering drugs (NSAIDs, steroids, oestrogens).', 'ISH_HTN_2020', 'ESC_HTN_2024'))
            if (potassium != null && potassium <= 4.5 && (egfr == null || egfr >= 45)) plan.push(item('Fourth-line: add spironolactone (potassium ' + fmt(potassium) + ' mmol/L' + (egfr != null ? ', eGFR ' + fmt(egfr) : ', check eGFR first') + '); recheck potassium and creatinine within 2–4 weeks.', 'ISH_HTN_2020', 'ESC_HTN_2024'))
            else plan.push(item('Fourth-line spironolactone needs potassium ≤4.5 mmol/L and eGFR ≥45; otherwise use a beta-blocker or alpha-blocker and seek specialist advice.', 'ISH_HTN_2020', 'ESC_HTN_2024'))
            plan.push(item('Screen for secondary causes, starting with the aldosterone-renin ratio, kidney disease and sleep apnoea.', 'ENDO_PA_2016', 'ESC_HTN_2024'))
          }
          if (rasReason) plan.push(item('Include an ACE inhibitor or ARB given ' + rasReason + ', titrated to the maximum tolerated dose.', 'KDIGO_CKD_2024_TX', 'KDIGO_DM_CKD_2022', 'ISH_HTN_2020'))
          if (!classes.length) plan.push(item('For patients of African ancestry, ISH 2020 advises starting with a CCB plus thiazide-like diuretic, or an ARB plus CCB; ACE-inhibitor monotherapy lowers BP less.', 'ISH_HTN_2020'))
        }
        if ((status === 'uncontrolled' || status === 'unconfirmed') && pregnancyNote && !ras) plan.push(item(pregnancyNote, 'NICE_PREGNANCY'))
        if (status === 'uncontrolled' || status === 'unconfirmed' || status === 'at_risk') {
          var lifestyle = 'Lifestyle: salt below 5 g/day, regular physical activity, limit alcohol'
          if (bmi != null && bmi >= 25) lifestyle += ', and weight reduction (BMI ' + fmt(bmi) + ')'
          plan.push(item(lifestyle + '.', 'WHO_HTN_2021', 'ISH_HTN_2020'))
        }
        if (status === 'at_risk') plan.push(item('Recheck BP at least annually' + (highRisk ? '; with high cardiovascular risk, ESC 2024 supports drug treatment if BP stays ≥130/80 after 3 months of lifestyle change.' : '.'), 'ESC_HTN_2024'))
        if (status === 'at_target') {
          plan.push(item('Continue the current regimen; review every 3–6 months with adherence and side-effect check.', 'WHO_HTN_2021'))
          if (meanSbp < 110 && (age >= 65 || frail)) {
            status = 'review'; summary = 'Low treated BP (' + bpText + ') in an older or frail adult.'
            plan.push(item('Ask about dizziness and falls, check standing BP, and consider reducing treatment if symptomatic.', 'ESC_HTN_2024'))
          }
        }
        if (status) {
          if (age < 40 && (hypertensive || above)) consider('secondary_htn_young', 'Hypertension at age ' + age + ': screen for secondary causes (kidney disease, primary aldosteronism, renovascular disease, thyroid disease, drugs).', 'ESC_HTN_2024', 'ENDO_PA_2016')
          if (potassium != null && potassium < 3.5 && (hypertensive || above)) consider('primary_aldosteronism', 'Hypertension with potassium ' + fmt(potassium) + ' mmol/L' + (on(union(THIAZIDE, LOOP)) ? ' (on a diuretic)' : ' (no diuretic recorded)') + ': screen for primary aldosteronism with an aldosterone-renin ratio after correcting potassium.', 'ENDO_PA_2016')
          if (status === 'uncontrolled' || status === 'unconfirmed' || status === 'acute') monitor('bp_review', 'Blood pressure', 'Every 2–4 weeks after each change until at target, then every 3–6 months', 'Titration to target', 'WHO_HTN_2021')
          addProblem('hypertension', hypertensive || onBpTreatment ? 'Hypertension' : 'Raised blood pressure', status, facts, summary, plan, [targetText])
        }
      }
    }

    // ---- diabetes
    if (!pregnant) {
      var diagFacts = []
      if (hba1c != null) diagFacts.push('HbA1c ' + fmt(hba1c) + '% (' + fmt0((hba1c - 2.15) * 10.929) + ' mmol/mol)')
      if (glucose != null) diagFacts.push((glucoseContext === 'fasting' ? 'Fasting' : glucoseContext === 'random' ? 'Random' : 'Timing-unspecified') + ' glucose ' + fmt(glucose) + ' mmol/L')
      if (diabetic) {
        var recentHypo = (hypos || 0) > 0 && (insulin || sulfonylurea)
        var relaxed = frail || age >= 75 || (egfr != null && egfr < 30) || recentHypo
        var dmTarget = relaxed ? 8.0 : 7.0
        var dmTargetText = relaxed ? 'HbA1c <8.0% (64 mmol/mol), individualised for ' + join(sel([['frailty', frail], ['age ' + age, age >= 75], ['advanced CKD', egfr != null && egfr < 30], ['recent hypoglycaemia', recentHypo]]))
          : 'HbA1c <7.0% (53 mmol/mol) for most adults without hypoglycaemia'
        var glucoseDrugs = names(union(SULFONYLUREA, SGLT2, GLP1, DPP4, set(['metformin', 'pioglitazone'])))
        if (insulin) glucoseDrugs.push('insulin')
        facts = diagFacts.concat(['On ' + (glucoseDrugs.length ? join(glucoseDrugs) : 'no glucose-lowering medicine recorded')])
        if (hypos) facts.push(hypos + ' hypoglycaemia episode' + (hypos !== 1 ? 's' : '') + ' in 3 months')
        plan = []
        if (hba1c == null) {
          status = 'needs_data'; summary = 'Glycaemic control cannot be judged without an HbA1c.'
          plan.push(item('Measure HbA1c now, then every 3 months until at target and 6-monthly once stable.', 'ADA_SOC_2025'))
          gap('hba1c', 'Needed to judge diabetes control.')
        } else if (hba1c > dmTarget) {
          status = 'above_target'
          summary = 'HbA1c ' + fmt(hba1c) + '% is ' + fmt(hba1c - dmTarget) + ' points above the individual target of <' + dmTarget.toFixed(1) + '%' + (glucoseDrugs.length ? ' on ' + join(glucoseDrugs) + '.' : ' with no glucose-lowering medicine recorded.')
        } else {
          status = 'at_target'; summary = 'HbA1c ' + fmt(hba1c) + '% is within the individual target of <' + dmTarget.toFixed(1) + '%.'
        }
        var aboveDm = hba1c != null && hba1c > dmTarget
        if (aboveDm && get(data, 'adherence') === 'missed') plan.push(item('Explore missed doses (cost, supply, side-effects, beliefs) before intensifying.', 'ADA_SOC_2025'))
        var cardiorenal = sel([['atherosclerotic CVD', anyAscvd], ['heart failure', heartFailure], ['chronic kidney disease', ckdMarkers || tri('known_ckd') === 'yes']])
        var sglt2Advised = false
        if (cardiorenal.length && !on(SGLT2)) {
          if (egfr == null) plan.push(item('An SGLT2 inhibitor is indicated for ' + join(cardiorenal) + ' independent of HbA1c; check eGFR first (start if ≥20).', 'ADA_SOC_2025', 'KDIGO_CKD_2024_TX', 'ESC_DM_CVD_2023'))
          else if (egfr >= 20) {
            sglt2Advised = true
            plan.push(item('Add an SGLT2 inhibitor for ' + join(cardiorenal) + ', independent of HbA1c (eGFR ' + fmt(egfr) + '); give sick-day guidance to pause it during dehydrating illness.', 'ADA_SOC_2025', 'KDIGO_CKD_2024_TX', 'ESC_DM_CVD_2023'))
          }
        }
        if (anyAscvd && !on(GLP1)) plan.push(item('A GLP-1 receptor agonist with proven cardiovascular benefit is an alternative or addition for established ASCVD, where available.', 'ADA_SOC_2025', 'ESC_DM_CVD_2023'))
        if (taking.has('metformin')) {
          if (egfr != null && egfr >= 30 && egfr < 45) plan.push(item('Metformin with eGFR ' + fmt(egfr) + ': limit to a maximum of 1000 mg/day and review renal function every 3–6 months.', 'KDIGO_DM_CKD_2022', 'METFORMIN_LABEL'))
          monitor('b12', 'Vitamin B12', 'Periodically on long-term metformin, especially with neuropathy or anaemia', 'Metformin-associated deficiency', 'ADA_SOC_2025')
        } else if (aboveDm) {
          if (egfr == null) plan.push(item('Metformin is first-line unless contraindicated; check eGFR before starting (not started if eGFR <45).', 'KENYA_NCD_PROTOCOLS', 'METFORMIN_LABEL'))
          else if (egfr >= 45) plan.push(item('Metformin is first-line unless contraindicated (eGFR adequate).', 'KENYA_NCD_PROTOCOLS', 'ADA_SOC_2025'))
        }
        if (aboveDm) {
          if (hba1c >= 10 || (glucose != null && glucose >= 16.7) || symptoms.has('unexplained_weight_loss')) plan.push(item('HbA1c ≥10%, glucose ≥16.7 mmol/L or weight loss suggests insulin deficiency: consider basal insulin and check ketones.', 'ADA_SOC_2025'))
          else if (insulin) plan.push(item('Already on insulin: review doses against glucose records, injection technique and sites (lipohypertrophy), and hypoglycaemia before further titration.', 'ADA_SOC_2025'))
          else if (glucoseDrugs.length) {
            var choices = []
            if (bmi != null && bmi >= 30 && !on(GLP1)) choices.push('a GLP-1 receptor agonist (weight benefit; BMI ' + fmt(bmi) + ')')
            if (!sulfonylurea && !(age >= 75 || frail)) choices.push('a sulfonylurea where cost limits access (gliclazide preferred; avoid glibenclamide from age 60)')
            if (!on(DPP4)) choices.push('a DPP-4 inhibitor (low hypoglycaemia risk)')
            choices.push('basal insulin')
            var lead = sglt2Advised ? 'If HbA1c remains above target after the SGLT2 inhibitor (expected fall about 0.5%), add an agent chosen by comorbidity, cost and hypoglycaemia risk: '
              : 'Intensify with a second agent chosen by comorbidity, cost and hypoglycaemia risk: '
            plan.push(item(lead + choices.join('; ') + '.', 'ADA_SOC_2025', 'WHO_HEARTS_D_2020', 'KENYA_NCD_PROTOCOLS'))
          }
        }
        if (hba1c != null && hba1c < 6.5 && (insulin || sulfonylurea) && (age >= 65 || frail)) {
          status = 'review'; summary = 'HbA1c ' + fmt(hba1c) + '% on insulin or a sulfonylurea in an older or frail adult: risk of overtreatment.'
          plan.push(item('De-intensify: reduce or stop the sulfonylurea or insulin dose to avoid hypoglycaemia.', 'ADA_SOC_2025'))
        }
        if (recentHypo) plan.push(item('Review each hypoglycaemia episode (timing, meals, dose, alcohol, kidney function); consider switching sulfonylurea to a lower-risk agent and teach hypoglycaemia treatment.', 'ADA_SOC_2025', 'WHO_HEARTS_MEDS_2018'))
        if (acr == null && !(ckd || (egfr != null && egfr < 60))) {
          plan.push(item('Measure urine ACR with eGFR at least annually to detect diabetic kidney disease.', 'ADA_SOC_2025', 'KDIGO_DM_CKD_2022'))
          gap('urine_acr_mg_mmol', 'Annual albuminuria screening in diabetes guides ACE inhibitor/ARB and SGLT2 inhibitor use.')
        }
        var eye = get(data, 'eye_screen'), foot = get(data, 'foot_exam')
        if (eye !== 'within_12_months') plan.push(item('Retinal screening is ' + (eye === 'over_12_months' || eye === 'never' ? 'overdue' : 'not documented') + ': arrange dilated eye examination or retinal photography.', 'ADA_SOC_2025'))
        if (foot !== 'within_12_months' && !symptoms.has('foot_ulcer')) plan.push(item('Foot examination is ' + (foot === 'over_12_months' || foot === 'never' ? 'overdue' : 'not documented') + ': check sensation (10 g monofilament), pulses and skin; educate on daily foot care.', 'ADA_SOC_2025', 'KENYA_NCD_PROTOCOLS'))
        var leanLoss = bmi != null && bmi < 25 && symptoms.has('unexplained_weight_loss')
        if (age < 35 || leanLoss) consider('atypical_diabetes', 'Features atypical for type 2 diabetes (' + join(sel([['age ' + age, age < 35], ['lean with weight loss', leanLoss]])) + '): consider autoimmune diabetes (GAD antibodies, C-peptide) and check ketones; keep a low threshold for insulin.', 'ADA_SOC_2025')
        monitor('hba1c', 'HbA1c', 'Every 3 months until at target, then every 6 months', 'Glycaemic control', 'ADA_SOC_2025')
        monitor('acr_egfr', 'Urine ACR and eGFR', 'At least annually', 'Kidney screening in diabetes', 'ADA_SOC_2025', 'KDIGO_DM_CKD_2022')
        addProblem('diabetes', 'Diabetes', status, facts, summary, plan, [dmTargetText])
      } else {
        var diagnostic = []
        if (hba1c != null && hba1c >= 6.5) diagnostic.push('HbA1c ' + fmt(hba1c) + '%')
        if (glucose != null && glucoseContext === 'fasting' && glucose >= 7.0) diagnostic.push('fasting glucose ' + fmt(glucose) + ' mmol/L')
        if (glucose != null && glucoseContext !== 'fasting' && glucose >= 11.1) diagnostic.push('random glucose ' + fmt(glucose) + ' mmol/L')
        var prediabetic = (hba1c != null && hba1c >= 5.7 && hba1c < 6.5) || (glucose != null && glucoseContext === 'fasting' && glucose >= 6.1 && glucose < 7.0)
        if (diagnostic.length) addProblem('diabetes_possible', 'Possible diabetes', 'unconfirmed', diagFacts, cap(join(diagnostic)) + ' is in the diabetic range without a recorded diagnosis.',
          [item('Confirm with a repeat test on another day (or two different abnormal tests on the same sample) unless there is unequivocal hyperglycaemia with symptoms.', 'ADA_SOC_2025', 'KENYA_NCD_PROTOCOLS'),
            item('If confirmed: start structured education, metformin unless contraindicated, and baseline eGFR, urine ACR, lipids, eye and foot checks.', 'KENYA_NCD_PROTOCOLS', 'ADA_SOC_2025')])
        else if (prediabetic) addProblem('prediabetes', 'Increased diabetes risk (prediabetes range)', 'at_risk', diagFacts, 'Values are above normal but below the diabetic threshold.',
          [item('Lifestyle programme: 5–7% weight loss if overweight and at least 150 minutes/week of moderate activity.', 'ADA_SOC_2025'),
            item('Repeat HbA1c or fasting glucose at least annually.', 'ADA_SOC_2025')])
        if ((diagnostic.length || prediabetic) && hba1c != null) consider('hba1c_reliability_dx', 'HbA1c can misclassify diabetes with anaemia, haemoglobin variants (including sickle-cell trait), recent blood loss or transfusion, advanced CKD and pregnancy; confirm with plasma glucose when any apply.', 'WHO_HBA1C_2011', 'ADA_SOC_2025')
      }
      if (diabetic && hba1c != null && (anaemia || (egfr != null && egfr < 30))) consider('hba1c_reliability', 'HbA1c may not reflect glycaemia here (' + join(sel([[hb != null ? 'haemoglobin ' + fmt(hb) + ' g/dL' : '', anaemia], [egfr != null ? 'eGFR ' + fmt(egfr) : '', egfr != null && egfr < 30]])) + '); corroborate with glucose readings.', 'WHO_HBA1C_2011', 'ADA_SOC_2025')
    }

    // ---- kidney
    if (!pregnant && (ckd || (egfr != null && egfr < 60))) {
      facts = []
      if (egfr != null) facts.push('eGFR ' + fmt(egfr) + ' mL/min/1.73 m²' + (enteredEgfr == null ? ' (calculated, CKD-EPI 2021)' : ''))
      if (acr != null) facts.push('Urine ACR ' + fmt(acr) + ' mg/mmol')
      if (potassium != null) facts.push('Potassium ' + fmt(potassium) + ' mmol/L')
      var stage = (stageG || '') + (stageA || '')
      var confirmed = tri('known_ckd') === 'yes'
      var title = (confirmed ? 'Chronic kidney disease ' + stage : 'Reduced kidney function or albuminuria ' + stage).trim()
      summary = kidneyRisk ? 'KDIGO risk category ' + kidneyRisk + '.' : 'Albuminuria category unknown, so KDIGO risk cannot be assigned.'
      plan = []
      if (!confirmed) plan.push(item('Confirm chronicity: repeat eGFR and urine ACR after 3 months and exclude acute kidney injury (compare with previous results).', 'KDIGO_CKD_2024'))
      if (acr == null) {
        plan.push(item('Measure urine ACR: albuminuria determines risk, RAS-inhibitor and SGLT2-inhibitor decisions.', 'KDIGO_CKD_2024'))
        gap('urine_acr_mg_mmol', 'Stages CKD risk and guides kidney-protective treatment.')
      }
      if (albuminuria && !ras && !heartFailure) {
        plan.push(item('Start an ACE inhibitor or ARB titrated to the maximum tolerated dose for albuminuria (ACR ' + fmt(acr) + ' mg/mmol); recheck creatinine and potassium in 2–4 weeks and accept a creatinine rise of up to 30%.', 'KDIGO_CKD_2024_TX', 'KDIGO_DM_CKD_2022'))
        if (pregnancyNote) plan.push(item(pregnancyNote, 'NICE_PREGNANCY'))
      }
      if (egfr != null && egfr >= 20 && !on(SGLT2) && !diabetic && ((acr != null && acr >= 20) || heartFailure || egfr < 45)) plan.push(item('Add an SGLT2 inhibitor for kidney protection (KDIGO 2024: eGFR ≥20 with ACR ≥20 mg/mmol or heart failure; suggested for eGFR 20–45).', 'KDIGO_CKD_2024_TX'))
      if (on(NSAID)) plan.push(item('Stop NSAIDs and avoid other nephrotoxins; adjust renally cleared medicines to eGFR.', 'KDIGO_CKD_2024_TX'))
      plan.push(item('Give sick-day guidance: pause metformin, SGLT2 inhibitors, ACE inhibitor/ARB and diuretics during vomiting, diarrhoea or poor intake, and restart when eating and drinking.', 'KDIGO_DM_CKD_2022', 'KDIGO_CKD_2024_TX'))
      if (anaemia && egfr != null && egfr < 60) plan.push(item('Haemoglobin ' + fmt(hb) + ' g/dL: evaluate anaemia (iron studies, B12/folate, blood film) before attributing it to CKD.', 'KDIGO_CKD_2024'))
      var refer = []
      if (egfr != null && egfr < 30) refer.push('eGFR ' + fmt(egfr) + ' (<30)')
      if (acr != null && acr >= 30) refer.push('ACR ' + fmt(acr) + ' mg/mmol (≥30)')
      if (classes.length >= 4 && meanSbp != null && meanSbp >= 140) refer.push('uncontrolled BP on 4 or more agents')
      if (potassium != null && potassium >= 6) refer.push('potassium ' + fmt(potassium) + ' mmol/L')
      if (refer.length) plan.push(item('Refer to nephrology: ' + join(refer) + '.', 'KDIGO_CKD_2024_TX'))
      if (stageG && stageA) {
        var freq = KDIGO_FREQ[stageG][Number(stageA[1]) - 1]
        for (var mi = monitoring.length - 1; mi >= 0; mi--) if (monitoring[mi].id === 'acr_egfr') monitoring.splice(mi, 1)
        monitor('ckd_monitoring', 'eGFR and urine ACR', (freq >= 4 ? '4 or more' : String(freq)) + ' time' + (freq !== 1 ? 's' : '') + ' per year (' + stageG + stageA + ')', 'KDIGO heat-map monitoring frequency', 'KDIGO_CKD_2024_TX')
      }
      status = confirmed ? 'established' : 'needs_confirmation'
      if (refer.length || kidneyRisk === 'very high') status = confirmed ? 'high_risk' : 'needs_confirmation'
      addProblem('kidney', title, status, facts, summary, plan, ['Systolic BP <120 mmHg with standardised measurement if tolerated (KDIGO), otherwise <130/80'])
    }
    if ((ras || on(MRA)) && !pregnant) monitor('renal_k', 'Creatinine/eGFR and potassium', '2–4 weeks after starting or increasing ACE inhibitor/ARB, MRA or diuretic, then at least annually', 'RAS-blockade safety', 'KDIGO_CKD_2024_TX', 'LISINOPRIL_LABEL')

    // ---- lipids and cardiovascular prevention
    if (!pregnant) {
      var statinNames = names(STATIN)
      var highIntensity = (doseOf('atorvastatin') || 0) >= 40 || (doseOf('rosuvastatin') || 0) >= 20
      plan = []; facts = []
      if (risk.statement) facts.push(risk.statement.replace(/\.+$/, ''))
      if (ldl != null) facts.push('LDL cholesterol ' + fmt(ldl) + ' mmol/L')
      if (tc != null) facts.push('Total cholesterol ' + fmt(tc) + ' mmol/L' + (hdl != null ? ', HDL ' + fmt(hdl) : ''))
      facts.push('Statin: ' + (statinNames.length ? join(statinNames) + (highIntensity ? ' (high intensity)' : '') : 'none recorded'))
      var ldlGoal = { 'very high': 1.4, high: 1.8, moderate: 2.6 }[risk.category || '']
      if (ldlGoal === undefined) ldlGoal = null
      var indication = null
      if (anyAscvd) indication = 'established ASCVD'
      else if (diabetic && age >= 40) indication = 'diabetes at age ' + age
      else if (ckdMarkers && age >= 50 && egfr != null && egfr < 60) indication = 'CKD at age ' + age
      else if (highRisk) indication = risk.basis
      status = null
      if (indication && !statinNames.length) {
        status = 'untreated'
        var intensity = risk.category === 'very high' ? 'a high-intensity statin (atorvastatin 40–80 mg or rosuvastatin 20–40 mg class)' : 'at least a moderate-intensity statin'
        plan.push(item('Start ' + intensity + ': indicated for ' + indication + '.', 'WHO_HEARTS_RISK_2020', 'ESC_LIPIDS_2019', 'ADA_SOC_2025'))
        if (pregnancyNote) plan.push(item(pregnancyNote, 'NICE_PREGNANCY'))
      } else if (statinNames.length && ldl != null && ldlGoal != null && ldl > ldlGoal) {
        status = 'above_target'
        plan.push(item('LDL ' + fmt(ldl) + ' mmol/L is above the goal of <' + fmt(ldlGoal) + ' mmol/L for ' + risk.category + ' risk: ' + (highIntensity ? 'confirm adherence, then add ezetimibe' : 'confirm adherence, then increase to high intensity') + '.', 'ESC_LIPIDS_2019'))
      } else if (statinNames.length && ldl == null) {
        status = 'needs_data'
        plan.push(item('Check a lipid profile to confirm the statin response (target LDL ' + (ldlGoal ? '<' + fmt(ldlGoal) + ' mmol/L' : 'per risk category') + ').', 'ESC_LIPIDS_2019'))
      } else if (statinNames.length) {
        status = 'at_target'
        plan.push(item('Continue the statin; recheck lipids annually.', 'ESC_LIPIDS_2019'))
      } else if (risk.category === 'moderate') {
        status = 'at_risk'
        plan.push(item('Moderate risk: discuss a statin after lifestyle change, weighing the ' + fmt(risk.percent || 0) + '% 10-year risk and patient preference.', 'WHO_HEARTS_RISK_2020', 'ESC_LIPIDS_2019'))
      }
      if (anyAscvd && !on(ANTIPLATELET) && !on(ANTICOAG)) {
        status = status || 'untreated'
        plan.push(item('Secondary prevention: low-dose aspirin (or clopidogrel if aspirin is not tolerated) unless contraindicated or anticoagulated.', 'WHO_HEARTS_RISK_2020'))
      }
      if (statinNames.length || (indication && !statinNames.length)) monitor('lipids', 'Lipid profile', '4–12 weeks after starting or changing a statin, then annually', 'Treatment response', 'ESC_LIPIDS_2019')
      if ((indication || status) && !(tc != null || ldl != null)) gap('total_cholesterol_mmol', 'A lipid profile sets the LDL goal and treatment response.')
      if (status) {
        summary = risk.category ? cap(risk.category) + ' cardiovascular risk (' + risk.basis + ').' : 'Cardiovascular risk not yet estimable.'
        if (ldlGoal) summary += ' LDL goal <' + fmt(ldlGoal) + ' mmol/L.'
        addProblem('cv_prevention', 'Cardiovascular risk and lipids', status, facts, summary, plan,
          ldlGoal ? ['LDL <' + fmt(ldlGoal) + ' mmol/L' + (risk.category === 'very high' ? ' and ≥50% reduction from baseline' : '')] : [])
      }
    }

    // ---- heart failure
    if (heartFailure && !pregnant) {
      var pillars = [['ACE inhibitor/ARB/ARNI', ras], ['evidence-based beta-blocker (bisoprolol, carvedilol or metoprolol succinate)', on(BB_HF)], ['MRA (spironolactone)', on(MRA)], ['SGLT2 inhibitor', on(SGLT2)]]
      var missingPillars = pillars.filter(function (p) { return !p[1] }).map(function (p) { return p[0] })
      plan = [item('Confirm the phenotype with echocardiography (LVEF); the four-pillar plan below applies to HFrEF (LVEF ≤40%).', 'ESC_HF_2021')]
      if (missingPillars.length) plan.push(item('Missing guideline pillars for HFrEF: ' + missingPillars.join('; ') + '. Introduce one at a time at low dose and up-titrate every 2–4 weeks as BP, heart rate, potassium and eGFR allow.', 'ESC_HF_2021'))
      if (!on(MRA) && ((potassium != null && potassium > 5.0) || (egfr != null && egfr < 30))) plan.push(item('MRA is not advised while potassium >5.0 mmol/L or eGFR <30.', 'ESC_HF_2021'))
      plan.push(item('Loop diuretic only for congestion, at the lowest effective dose; daily weights and a fluid/salt plan.', 'ESC_HF_2021'))
      addProblem('heart_failure', 'Heart failure', missingPillars.length ? 'uncontrolled' : 'established',
        [missingPillars.length < 4 ? 'On ' + join(pillars.filter(function (p) { return p[1] }).map(function (p) { return p[0].split(' (')[0] })) : 'No HFrEF disease-modifying therapy recorded'],
        (4 - missingPillars.length) + ' of 4 disease-modifying pillars recorded.', plan)
    }

    // ---- atrial fibrillation
    if (af) {
      var points = [['heart failure', 1, heartFailure], ['hypertension', 1, hypertensive || onBpTreatment], ['age ≥75', 2, age >= 75], ['diabetes', 1, diabetic],
        ['prior stroke/TIA', 2, stroke], ['vascular disease', 1, ascvd], ['age 65–74', 1, age >= 65 && age < 75]].filter(function (p) { return p[2] })
      var score = points.reduce(function (t, p) { return t + p[1] }, 0)
      var unknownFactors = [['heart failure', 'known_heart_failure'], ['diabetes', 'known_diabetes'], ['stroke/TIA', 'prior_stroke_tia'], ['vascular disease', 'known_ascvd']]
        .filter(function (p) { return tri(p[1]) === 'unknown' }).map(function (p) { return p[0] })
      derive('cha2ds2_va', 'CHA2DS2-VA', String(score), 'points', (score >= 2 ? 'Anticoagulation recommended' : score === 1 ? 'Anticoagulation to be considered' : 'Low stroke risk') + (unknownFactors.length ? '; minimum score, unknown: ' + join(unknownFactors) : ''),
        'ESC 2024 score without sex category: ' + (points.length ? join(points.map(function (p) { return p[0] + ' +' + p[1] })) : 'no risk factors recorded'), 'ESC_AF_2024')
      plan = []
      var anticoagulated = on(ANTICOAG)
      if (score >= 1 && !anticoagulated) {
        plan.push(item('Oral anticoagulation is ' + (score >= 2 ? 'recommended' : 'to be considered') + ' (CHA2DS2-VA ' + score + '). A DOAC is preferred unless there is a mechanical valve or moderate–severe mitral stenosis; in Kenya, exclude rheumatic mitral stenosis by echocardiography, as warfarin is then required.', 'ESC_AF_2024'))
        if (taking.has('aspirin')) plan.push(item('Aspirin alone is not effective stroke prevention in AF; it is replaced, not combined, unless there is a separate vascular indication.', 'ESC_AF_2024'))
      }
      if (anticoagulated) plan.push(item('Review anticoagulant dose against current eGFR, weight, age and interacting drugs' + (egfr != null ? ' (eGFR ' + fmt(egfr) + ')' : ' (eGFR needed)') + '; warfarin needs INR monitoring.', 'ESC_AF_2024'))
      plan.push(item('Reduce modifiable bleeding risk: control BP, avoid NSAIDs and unnecessary antiplatelets, and limit alcohol.', 'ESC_AF_2024'))
      if (pulse != null && pulse > 110) plan.push(item('Resting pulse ' + fmt0(pulse) + '/min: review rate control (beta-blocker; avoid diltiazem/verapamil in reduced LVEF).', 'ESC_AF_2024', 'ESC_HF_2021'))
      var untreatedAf = score >= 2 && !anticoagulated
      addProblem('atrial_fibrillation', 'Atrial fibrillation', untreatedAf ? 'uncontrolled' : 'established',
        ['CHA2DS2-VA ' + score, 'Anticoagulant: ' + (anticoagulated ? join(names(ANTICOAG)) : 'none recorded')],
        'Stroke-risk score ' + score + (untreatedAf ? ' with no anticoagulant recorded.' : '.'), plan)
    }

    // ---- respiratory
    var inhalers = union(ICS, LABA, LAMA, SABA, set(['ipratropium']))
    if (asthma) {
      facts = ['Inhalers: ' + (join(names(inhalers)) || 'none recorded')]
      if (reliever != null) facts.push('Reliever use ' + reliever + '×/week')
      if (exacerbations != null) facts.push(exacerbations + ' exacerbation' + (exacerbations !== 1 ? 's' : '') + ' in 12 months')
      plan = []
      var poorControl = (reliever != null && reliever > 2) || (exacerbations || 0) >= 1
      var sabaOnly = on(SABA) && !on(ICS)
      if (sabaOnly) plan.push(item('SABA-only treatment is not recommended for adults: start ICS-containing treatment, preferably as-needed or maintenance-and-reliever budesonide-formoterol (GINA Track 1).', 'GINA_2025'))
      if (poorControl) plan.push(item('Before stepping up, check inhaler technique, adherence, triggers (smoke, occupational), rhinitis and reflux; then step up treatment.', 'GINA_2025'))
      if ((exacerbations || 0) >= 1) plan.push(item('Provide a written asthma action plan and review within 1 week of any exacerbation.', 'GINA_2025'))
      if (reliever == null && exacerbations == null) {
        gap('reliever_use_per_week', 'Reliever use and exacerbations define asthma control and future risk.')
        plan.push(item('Assess control over the last 4 weeks: daytime symptoms or reliever use >2×/week, night waking, activity limitation, and exacerbations in the past year.', 'GINA_2025'))
      }
      status = poorControl || sabaOnly ? 'uncontrolled' : reliever == null && exacerbations == null ? 'needs_data' : 'at_target'
      addProblem('asthma', 'Asthma', status, facts,
        status === 'uncontrolled' ? 'Not well controlled or at risk of exacerbation.' : status === 'needs_data' ? 'Control not assessed.' : 'Well controlled on the recorded treatment.', plan)
    }
    if (copd) {
      facts = ['Inhalers: ' + (join(names(inhalers)) || 'none recorded')]
      if (exacerbations != null) facts.push(exacerbations + ' exacerbation' + (exacerbations !== 1 ? 's' : '') + ' in 12 months')
      var groupE = (exacerbations || 0) >= 2
      plan = [item('Confirm with post-bronchodilator spirometry (FEV1/FVC <0.7) if not already documented; in Kenya, household biomass smoke is a common cause in people who never smoked.', 'GOLD_2025')]
      if (!(on(LABA) && on(LAMA))) plan.push(item('Long-acting bronchodilator therapy: LABA + LAMA for persistent symptoms or exacerbations.', 'GOLD_2025'))
      if (on(ICS) && !on(LABA)) plan.push(item('ICS without a long-acting bronchodilator is not recommended in COPD.', 'GOLD_2025'))
      if (groupE) plan.push(item('Frequent exacerbations (GOLD E): check blood eosinophils; add ICS to LABA + LAMA if ≥300 cells/µL.', 'GOLD_2025'))
      if (spo2 != null && spo2 <= 88) plan.push(item('SpO2 ' + fmt0(spo2) + '%: assess for long-term oxygen once stable (arterial blood gas).', 'GOLD_2025'))
      plan.push(item('Influenza and pneumococcal vaccination, pulmonary rehabilitation and inhaler-technique review.', 'GOLD_2025'))
      if (exacerbations == null) gap('exacerbations_past_year', 'Exacerbation history sets COPD group and treatment.')
      addProblem('copd', 'COPD', groupE || !(on(LABA) || on(LAMA)) ? 'uncontrolled' : 'established', facts,
        groupE ? 'Frequent exacerbator (GOLD E).' : 'Exacerbation history ' + (exacerbations == null ? 'not recorded.' : 'below the GOLD E threshold.'), plan)
    }
    if (spo2 != null && spo2 >= 88 && spo2 <= 96 && (asthma || copd || symptoms.has('breathlessness') || symptoms.has('wheeze')))
      consider('pulse_oximetry_bias', 'SpO2 ' + fmt0(spo2) + '% may overestimate arterial oxygenation in people with darker skin; use an arterial blood gas when decisions depend on it.', 'PULSE_OXIMETRY_BIAS')

    // ---- weight and tobacco
    if (bmi != null && (bmi >= 30 || (bmi >= 27 && (hypertensive || diabetic || anyAscvd)))) {
      plan = [item('Agree a 5–10% weight-loss goal with diet, activity and follow-up support.', 'WHO_OBESITY', 'ADA_SOC_2025')]
      if (diabetic && !on(GLP1)) plan.push(item('In diabetes, a GLP-1 receptor agonist supports both glucose and weight goals where available.', 'ADA_SOC_2025'))
      addProblem('weight', bmi >= 30 ? 'Obesity' : 'Overweight with cardiometabolic disease', 'at_risk', ['BMI ' + fmt(bmi) + ' kg/m²'].concat(waist != null ? ['Waist ' + fmt(waist) + ' cm'] : []),
        'Weight contributes to BP, glucose and cardiovascular risk.', plan)
    }
    if (bmi != null && bmi < 18.5) consider('underweight', 'BMI ' + fmt(bmi) + ' kg/m²: evaluate undernutrition, TB, HIV, uncontrolled diabetes, malignancy and food insecurity.', 'WHO_OBESITY', 'WHO_TB_SCREENING_2021')
    if (smoker) addProblem('tobacco', 'Current tobacco use', 'at_risk', ['Current tobacco use'], 'Stopping is the single most effective intervention for cardiovascular and lung risk.',
      [item('Give brief advice to quit today and offer behavioural support with pharmacotherapy (varenicline, nicotine replacement, bupropion or cytisine) where available; follow up within 2 weeks.', 'WHO_TOBACCO_2024')])
    else if (get(data, 'tobacco_use', 'unknown') === 'unknown') gap('tobacco_use', 'Tobacco status changes cardiovascular risk and respiratory plans.')

    // ---- diagnostic considerations
    if (symptoms.has('persistent_cough') || symptoms.has('hemoptysis') || symptoms.has('unexplained_weight_loss'))
      consider('tb_screen', 'Cough, haemoptysis or weight loss: test for tuberculosis (rapid molecular test on sputum) before attributing symptoms to cancer or chronic lung disease' + (diabetic ? ', especially with diabetes, which raises TB risk' : '') + '.', 'WHO_TB_SCREENING_2021')

    // ---- medication review
    if (on(NSAID)) {
      if (ras && on(union(THIAZIDE, LOOP, MRA))) review('triple_whammy', 'high', 'NSAID (' + join(names(NSAID)) + ') with an ACE inhibitor/ARB and a diuretic', 'This combination causes acute kidney injury; stop the NSAID and use paracetamol or topical options.', 'KDIGO_CKD_2024_TX', 'LISINOPRIL_LABEL')
      var nsaidReasons = sel([['kidney disease', ckd], ['heart failure (fluid retention)', heartFailure], ['anticoagulation (bleeding)', on(ANTICOAG)], ['raised BP', meanSbp != null && meanSbp >= 140]])
      if (nsaidReasons.length) review('nsaid', heartFailure || on(ANTICOAG) ? 'high' : 'moderate', 'NSAID (' + join(names(NSAID)) + ') with ' + join(nsaidReasons), 'Avoid NSAIDs; use paracetamol or topical agents and review over-the-counter use.', 'ESC_HF_2021', 'KDIGO_CKD_2024_TX')
    }
    if (asthma && on(BB_NONSELECTIVE)) review('bb_asthma', 'high', 'Non-selective beta-blocker (' + join(names(BB_NONSELECTIVE)) + ') with asthma', 'Can trigger severe bronchospasm: switch to a cardioselective agent or an alternative class.', 'GINA_2025')
    else if (asthma && on(BB_SELECTIVE)) review('bb_asthma_selective', 'low', 'Cardioselective beta-blocker (' + join(names(BB_SELECTIVE)) + ') with asthma', 'Usually tolerated when clearly indicated; monitor for worsening symptoms.', 'GINA_2025')
    if (heartFailure && taking.has('pioglitazone')) review('tzd_hf', 'high', 'Pioglitazone with heart failure', 'Causes fluid retention and worsens heart failure: stop and choose another agent.', 'ESC_HF_2021')
    if (heartFailure && on(NONDHP_CCB)) review('nondhp_hf', 'high', cap(join(names(NONDHP_CCB))) + ' with heart failure', 'Negatively inotropic in reduced LVEF: avoid.', 'ESC_HF_2021')
    if (on(ANTICOAG) && on(ANTIPLATELET)) review('anticoag_antiplatelet', 'moderate', 'Anticoagulant (' + join(names(ANTICOAG)) + ') with antiplatelet (' + join(names(ANTIPLATELET)) + ')', 'Confirm a current indication and planned duration for dual therapy; bleeding risk is substantially higher.', 'ESC_AF_2024')
    if (taking.has('aspirin') && !anyAscvd && !af) review('aspirin_primary', 'low', 'Aspirin without recorded atherosclerotic disease', 'Not routinely recommended for primary prevention; review the indication and bleeding risk.', 'WHO_HEARTS_RISK_2020', 'ADA_SOC_2025')
    if (on(ACEI) && (get(data, 'allergies') || []).some(function (a) { return normal(a).indexOf('angioedema') >= 0 })) review('acei_angioedema', 'high', 'ACE inhibitor with a recorded angioedema history', 'ACE inhibitors are contraindicated after angioedema: stop and seek specialist advice before any ARB.', 'LISINOPRIL_LABEL')
    if ((insulin || sulfonylurea) && ((hypos || 0) > 0 || (egfr != null && egfr < 30) || age >= 75))
      review('hypoglycaemia_risk', 'moderate', 'Insulin or sulfonylurea with ' + join(sel([['recent hypoglycaemia', (hypos || 0) > 0], ['eGFR ' + (egfr != null ? fmt(egfr) : ''), egfr != null && egfr < 30], ['age ' + age, age >= 75]])),
        'High hypoglycaemia risk: review the need, dose and agent (gliclazide or a DPP-4 inhibitor carry lower risk than glibenclamide).', 'ADA_SOC_2025', 'WHO_HEARTS_MEDS_2018')
    if (on(MRA) && ((potassium != null && potassium > 5.0) || (egfr != null && egfr < 30)))
      review('mra_k', 'high', cap(join(names(MRA))) + ' with ' + join(sel([['potassium ' + (potassium != null ? fmt(potassium) : ''), potassium != null && potassium > 5.0], ['eGFR ' + (egfr != null ? fmt(egfr) : ''), egfr != null && egfr < 30]])),
        'Hyperkalaemia risk: hold or reduce and recheck potassium and creatinine.', 'ESC_HF_2021')
    if (taking.has('digoxin') && ((potassium != null && potassium < 3.5) || (egfr != null && egfr < 30))) review('digoxin', 'high', 'Digoxin with hypokalaemia or reduced kidney function', 'Toxicity risk: check a digoxin level, correct potassium and review the dose.', 'ESC_AF_2024')
    if (diabetic && taking.has('prednisolone')) review('steroid_dm', 'moderate', 'Prednisolone in diabetes', 'Expect afternoon/evening hyperglycaemia: increase glucose monitoring and plan for treatment adjustment.', 'ADA_SOC_2025')
    if (on(union(THIAZIDE, LOOP)) && potassium != null && potassium < 3.5) review('diuretic_hypok', 'moderate', 'Diuretic with potassium ' + fmt(potassium) + ' mmol/L', 'Likely contributory: review dose, consider an ACE inhibitor/ARB or potassium-sparing agent, and check magnesium.', 'NHS_LOW_POTASSIUM')
    ;[['statins', STATIN], ['sulfonylureas', SULFONYLUREA], ['calcium-channel blockers', DHP_CCB], ['beta-blockers', union(BB_SELECTIVE, BB_NONSELECTIVE)], ['NSAIDs', NSAID], ['anticoagulants', ANTICOAG], ['ACE inhibitors', ACEI], ['ARBs', ARB]].forEach(function (pair) {
      if (intersection(taking, pair[1]).length > 1) review('class_duplicate_' + normal(pair[0]), 'moderate', 'Two ' + pair[0] + ' recorded (' + join(names(pair[1])) + ')', 'Therapeutic duplication: confirm which is intended and stop the other.', 'NCDAI_SAFETY_SPEC')
    })

    // ---- assemble
    problems.sort(function (a, b) { return STATUS_ORDER[a.status] - STATUS_ORDER[b.status] })
    problems.forEach(function (entry, index) { entry.rank = index + 1 })
    var knownCkd = tri('known_ckd') === 'yes'
    var conditions = sel([['hypertension', hypertensive], ['diabetes', diabetic],
      ['chronic kidney disease' + (stageG && knownCkd ? ' ' + stageG + (stageA || '') : ''), knownCkd],
      ['coronary or peripheral arterial disease', ascvd], ['previous stroke/TIA', stroke], ['heart failure', heartFailure],
      ['atrial fibrillation', af], ['asthma', asthma], ['COPD', copd], ['cancer', tri('known_cancer') === 'yes']])
    var oneLiner = age + '-year-old ' + sexWord + (conditions.length ? ' with ' + join(conditions) : ' with no chronic NCD diagnosis recorded')
    if (pregnant) oneLiner += ', currently pregnant'
    if (smoker) oneLiner += ', current smoker'
    oneLiner += '.'
    var today = []
    if (meanSbp != null) today.push('BP ' + fmt0(meanSbp) + '/' + fmt0(meanDbp) + ' mmHg')
    if (hba1c != null) today.push('HbA1c ' + fmt(hba1c) + '%')
    if (egfr != null) today.push('eGFR ' + fmt(egfr))
    if (acr != null) today.push('ACR ' + fmt(acr) + ' mg/mmol')
    if (ldl != null) today.push('LDL ' + fmt(ldl) + ' mmol/L')
    if (bmi != null) today.push('BMI ' + fmt(bmi))
    if (today.length) oneLiner += ' Today: ' + today.join(', ') + '.'
    if (meds.length) oneLiner += ' ' + meds.length + ' current medicine' + (meds.length !== 1 ? 's' : '') + '.'

    var activeProblems = problems.filter(function (e) { return e.status !== 'at_target' && e.status !== 'established' })
    var acuteFirst = urgency === 'emergency' || urgency === 'urgent'
    var impression
    if (acuteFirst) impression = (criticalTitles.length ? 'Acute findings take priority: ' + join(criticalTitles) + '. ' : 'Same-day assessment is required. ') + 'Stabilise first; the chronic plan below applies once acute issues are addressed.'
    else if (activeProblems.length) impression = 'Priorities: ' + activeProblems.slice(0, 4).map(function (e) { return e.rank + ') ' + e.title + ' (' + e.status.replace(/_/g, ' ') + ')' }).join('; ') + '.'
    else if (problems.length) impression = 'Recorded conditions are at target on current information; continue the plan and routine monitoring.'
    else impression = 'No chronic-disease problem was identified from the structured data; this does not exclude disease.'
    var shortInterval = ['acute', 'uncontrolled', 'untreated', 'above_target', 'high_risk', 'review', 'unconfirmed', 'needs_confirmation']
    var followUp
    if (acuteFirst) followUp = 'Same day, per the acute findings; chronic review within 2 weeks of stabilisation.'
    else if (problems.some(function (e) { return shortInterval.indexOf(e.status) >= 0 }) || medReview.length) followUp = '2–4 weeks: confirm readings, review changes and blood results.'
    else if (problems.length) followUp = '3–6 months, with monitoring as listed.'
    else followUp = 'Routine screening interval; re-assess if new symptoms.'

    var lines = [oneLiner, '', 'Impression: ' + impression]
    problems.forEach(function (entry) {
      lines.push('')
      lines.push(entry.rank + '. ' + entry.title + ' [' + entry.status.replace(/_/g, ' ') + ']')
      if (entry.assessment) lines.push('   ' + entry.assessment)
      entry.targets.forEach(function (t) { lines.push('   Target: ' + t) })
      entry.plan.forEach(function (step) { lines.push('   - ' + step.text) })
    })
    if (medReview.length) { lines.push(''); lines.push('Medication review:'); medReview.forEach(function (e) { lines.push('   - ' + e.finding + ': ' + e.action) }) }
    if (considerations.length) { lines.push(''); lines.push('Consider:'); considerations.forEach(function (e) { lines.push('   - ' + e.text) }) }
    if (monitoring.length) { lines.push(''); lines.push('Monitoring:'); monitoring.forEach(function (e) { lines.push('   - ' + e.test + ': ' + e.timing) }) }
    lines.push('')
    lines.push('Follow-up: ' + followUp)
    lines.push('Decision support for clinician review; not a prescription.')

    return {
      version: REASONING_VERSION, one_liner: oneLiner, impression: impression, acute_first: acuteFirst,
      derived: derived, cardiovascular_risk: risk.category ? risk : null, problems: problems,
      medication_review: medReview, considerations: considerations, monitoring: monitoring, data_gaps: gaps,
      follow_up: followUp, summary_text: lines.join('\n'), sources: evidence.apply(null, usedSources),
      boundary: 'Deterministic synthesis from structured fields for clinician review. It names options and guideline steps; it does not diagnose, prescribe or set doses. Verify against the full clinical picture.',
    }
  }

  root.NCDAIEngine = { assess: assess, build: build, ckdEpi2021: ckdEpi2021, framingham: framingham,
    RULESET_VERSION: RULESET_VERSION, REASONING_VERSION: REASONING_VERSION, EVIDENCE_VERSION: REGISTRY.version }
})(typeof self !== 'undefined' ? self : this)
