// NCDAI offline clinical engine: a line-for-line port of backend/app/clinical.py
// (safety rules, without the dose-reference module), backend/app/treatment.py
// (guideline treatment options), backend/app/care_plan.py (patient summary) and
// backend/app/reasoning.py (consultant synthesis). backend/tests/test_engine_parity.py
// runs both engines on the same cases and requires identical output; change them together.
// Plain browser script: needs evidence.js loaded first; exposes self.NCDAIEngine.
(function (root) {
  'use strict'
  var REGISTRY = root.NCDAI_EVIDENCE
  if (!REGISTRY) throw new Error('Load evidence.js before engine.js')
  var RULESET_VERSION = 'ncdai-2-rules-0.4.0'
  var REASONING_VERSION = 'ncdai-consultant-1.1.0-review'
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
  // Python str.capitalize(): first character upper case, the rest lower case.
  function pyCapitalize(text) { return text.slice(0, 1).toUpperCase() + text.slice(1).toLowerCase() }
  // Python ", ".join(names[:-1]) + " and " + names[-1] (the clinical.py listing helper).
  function join(items) {
    if (!items.length) return ''
    if (items.length === 1) return items[0]
    return items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1]
  }
  function normal(value) { return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') }
  function unique(values) { var out = []; values.forEach(function (v) { if (out.indexOf(v) < 0) out.push(v) }); return out }
  function isNum(value) { return typeof value === 'number' }
  function isInt(value) { return typeof value === 'number' && Number.isInteger(value) }
  // Python isinstance(x, (int, float)): bool is an int subclass.
  function isPyNumber(value) { return typeof value === 'number' || typeof value === 'boolean' }
  // Python truthiness: None, False, 0, '' and empty containers are false; NaN is true.
  function truthy(value) {
    if (value == null || value === false || value === 0 || value === '') return false
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'object') return Object.keys(value).length > 0
    return true
  }
  // Python str() for the scalar values these rules print.
  function pyStr(value) { return value === true ? 'True' : value === false ? 'False' : value == null ? 'None' : String(value) }
  // Python float() for a recorded dose.
  function pyFloat(value) {
    if (typeof value === 'boolean') return value ? 1 : 0
    if (typeof value === 'number') return value
    if (typeof value === 'string' && /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$/.test(value)) return Number(value.trim())
    throw new Error('could not convert dose to float')
  }
  // Exact decimal expansion of a finite double: |x| = digits x 10^-scale.
  function exactDecimal(x) {
    var view = new DataView(new ArrayBuffer(8))
    view.setFloat64(0, Math.abs(x))
    var hi = view.getUint32(0), lo = view.getUint32(4), exponent = (hi >>> 20) & 0x7ff
    var mantissa = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo)
    if (exponent === 0) exponent = 1; else mantissa |= 1n << 52n
    var shift = exponent - 1075
    if (shift >= 0) return { digits: (mantissa << BigInt(shift)).toString(), scale: 0 }
    return { digits: (mantissa * 5n ** BigInt(-shift)).toString(), scale: -shift }
  }
  // Python f"{x:.Nf}" and "%.Nf": exact binary value, round half to even.
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
  // Python round(x, digits) on a float: correctly rounded, ties to even.
  function pyRound(x, digits) { return Number(pyFixed(x, digits)) }
  // Python f"{x:g}": 6 significant digits rounded half to even on the exact binary
  // value, trailing zeros stripped, exponent form outside 1e-4 <= |x| < 1e6.
  function pyG(x) {
    if (typeof x === 'boolean') x = x ? 1 : 0
    var negative = x < 0 || Object.is(x, -0)
    if (Number.isNaN(x)) return 'nan'
    if (!Number.isFinite(x)) return negative ? '-inf' : 'inf'
    if (x === 0) return negative ? '-0' : '0'
    var precision = 6, exact = exactDecimal(x), digits = exact.digits
    var exp10 = digits.length - 1 - exact.scale, keep
    if (digits.length > precision) {
      keep = digits.slice(0, precision)
      var rest = digits.slice(precision), first = rest.charCodeAt(0) - 48
      var up = first > 5 || (first === 5 && (/[1-9]/.test(rest.slice(1)) || (keep.charCodeAt(precision - 1) - 48) % 2 === 1))
      if (up) {
        keep = (BigInt(keep) + 1n).toString()
        if (keep.length > precision) { keep = keep.slice(0, precision); exp10 += 1 }
      }
    } else keep = digits + '0'.repeat(precision - digits.length)
    var text
    if (exp10 >= -4 && exp10 < precision) {
      var whole = exp10 >= 0 ? keep.slice(0, exp10 + 1) : '0'
      var frac = (exp10 >= 0 ? keep.slice(exp10 + 1) : '0'.repeat(-exp10 - 1) + keep).replace(/0+$/, '')
      text = frac ? whole + '.' + frac : whole
    } else {
      var tail = keep.slice(1).replace(/0+$/, '')
      text = keep.charAt(0) + (tail ? '.' + tail : '') + 'e' + (exp10 < 0 ? '-' : '+') + String(Math.abs(exp10)).padStart(2, '0')
    }
    return (negative ? '-' : '') + text
  }
  // (x / 100) ** 2 in clinical.py. Python delegates float ** to the platform pow(), which
  // equals x * x for heights recorded to 0.1 cm (checked for 100.0-250.0 cm).
  function sq(value) { return value * value }
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
  // Why each gap matters, shown with the gap so the request is specific to this patient.
  var GAP_REASONS = {
    repeat_blood_pressure: 'a raised reading must be confirmed before diagnosis or treatment changes',
    egfr: 'kidney function decides metformin, sulfonylurea and statin choices',
    egfr_for_metformin_review: 'metformin is recorded and depends on kidney function',
    egfr_for_RAS_medication_review: 'an ACE inhibitor/ARB is recorded',
    potassium_for_RAS_medication_review: 'an ACE inhibitor/ARB is recorded',
    pregnancy_status_for_RAS_medication_review: 'ACE inhibitors/ARBs are harmful in pregnancy',
    pregnancy_status: 'several NCD medicines are unsafe in pregnancy',
    glycaemic_measurement: 'an HbA1c or fasting glucose is needed to judge diabetes control',
    glucose_context: 'fasting (>=7.0) and random (>=11.1) diagnostic thresholds differ',
    lipid_profile: 'needed to choose and monitor statin treatment',
    weight_and_height: 'BMI guides weight targets and treatment',
    known_cvd_for_statin_choice: 'established cardiovascular disease changes the statin dose to atorvastatin 80 mg',
    current_observations: 'the recorded measurements are more than 24 hours old',
    observed_at: 'measurement time is needed to judge whether results are current',
  }
  var KNOWN_FIELDS = ['known_hypertension', 'known_diabetes', 'known_asthma', 'known_copd', 'known_ckd', 'known_cancer']
  var INHALER_NAMES = ['salbutamol', 'formoterol', 'salmeterol', 'ipratropium', 'tiotropium', 'beclometasone', 'beclomethasone', 'budesonide', 'fluticasone']
  function ingredient(value) { var n = normal(value); return has(C_ALIASES, n) ? C_ALIASES[n] : n }
  function underscoresToSpaces(text) { return text.replace(/_/g, ' ') }
  function anyCode() { return true }

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
    // sources: evidence IDs; basis lists the recorded values that triggered the
    // rule, so the clinician sees why it applies to this patient (falsy items dropped).
    function add(ruleId, category, severity, urgency, title, detail, sources, basis) {
      if (recs.some(function (r) { return r.rule_id === ruleId })) throw new Error('Duplicate rule identifier')
      recs.push({ id: ruleId, rule_id: ruleId, category: category, severity: severity, title: title, detail: detail,
        basis: (basis || []).filter(truthy), evidence: evidence.apply(null, sources) })
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
    // An entered laboratory eGFR always wins; a calculated value never hides it.
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
    var glucoseTiming = get(data, 'glucose_context', 'unknown')
    if (['fasting', 'random', 'unknown'].indexOf(glucoseTiming) < 0) throw new Error('Unrecognized glucose sample timing')
    var weight = num('weight_kg', 20, 350), height = num('height_cm', 100, 250), waist = num('waist_cm', 40, 250)
    var totalChol = num('total_cholesterol_mmol', 1, 20), ldl = num('ldl_mmol', 0.2, 15)
    var hdl = num('hdl_mmol', 0.2, 5), triglycerides = num('triglycerides_mmol', 0.1, 60)
    var bmi = weight != null && height != null ? pyRound(weight / sq(height / 100), 1) : null
    var bmiCategory = bmi == null ? null : bmi < 18.5 ? 'underweight' : bmi < 25 ? 'healthy' : bmi < 30 ? 'overweight' : 'obesity'
    result.derived = { bmi: bmi, bmi_category: bmiCategory }
    var symptoms = set(get(data, 'symptoms') || [])
    var meds = get(data, 'medications') || []
    var codes = meds.map(function (m) { return ingredient(get(m, 'code')) })
    var codeSet = set(codes)
    var allergies = set((get(data, 'allergies') || []).map(ingredient))
    var pregnancy = get(data, 'pregnancy_status', 'unknown')
    if (['yes', 'no', 'unknown', 'not_applicable'].indexOf(pregnancy) < 0) throw new Error('Unrecognized pregnancy status')
    KNOWN_FIELDS.concat(['known_ascvd', 'prior_stroke_tia', 'acutely_unwell', 'acute_kidney_injury']).forEach(function (field) {
      if (['yes', 'no', 'unknown'].indexOf(get(data, field, 'unknown')) < 0) throw new Error('Unrecognized ' + field + ' status')
    })
    var pregnant = pregnancy === 'yes'
    var diabetic = get(data, 'known_diabetes') === 'yes'
    var hypertensive = get(data, 'known_hypertension') === 'yes'
    var renalDisease = get(data, 'known_ckd') === 'yes'
    var cvdState = cvdStatus(data)
    // Use all readings independently. Do not silently average away a danger sign.
    var highs = [sbp, rsbp].filter(function (v) { return v != null }), highd = [dbp, rdbp].filter(function (v) { return v != null })
    var highestSbp = highs.length ? Math.max.apply(null, highs) : null, highestDbp = highd.length ? Math.max.apply(null, highd) : null
    function bpAtLeast(s, d) { return (highestSbp != null && highestSbp >= s) || (highestDbp != null && highestDbp >= d) }
    function reading(s, d) {
      return s != null && d != null ? pyG(s) + '/' + pyG(d) : s != null ? pyG(s) + '/–' : d != null ? '–/' + pyG(d) : null
    }
    function found(group) { return sortedStrings(intersection(symptoms, group).map(underscoresToSpaces)) }

    var bpBasis = [reading(sbp, dbp) ? 'BP ' + reading(sbp, dbp) + ' mmHg' : null,
      reading(rsbp, rdbp) ? 'Repeat BP ' + reading(rsbp, rdbp) + ' mmHg' : null]
    var timingLabel = has({ fasting: 1, random: 1 }, glucoseTiming) ? { fasting: 'Fasting', random: 'Random' }[glucoseTiming] : 'Unspecified-timing'
    var glucoseBasis = glucose != null ? timingLabel + ' glucose ' + pyFixed(glucose, 1) + ' mmol/L'
      + (unit === 'mg/dL' ? ' (entered ' + pyG(get(data, 'glucose')) + ' mg/dL)' : '') : null
    var hba1cBasis = hba1c != null ? 'HbA1c ' + pyG(hba1c) + '%' : null
    var egfrBasis = egfr != null ? 'eGFR ' + pyG(egfr) + ' mL/min/1.73 m²' : null
    var potassiumBasis = potassium != null ? 'Potassium ' + pyG(potassium) + ' mmol/L' : null
    var symptomBasis = symptoms.size ? 'Symptoms: ' + sortedStrings(Array.from(symptoms).map(underscoresToSpaces)).join(', ') : null
    var medNames = new Map()
    meds.forEach(function (m, i) { medNames.set(codes[i], truthy(get(m, 'name')) ? pyStr(get(m, 'name')) : codes[i]) })

    // Recorded names for a class, so guidance refers to this patient's own medicines.
    function named(members, test) {
      return unique(codes).filter(function (c) { return (members != null && members.has(c)) || (test != null && test(c)) })
        .map(function (c) { return medNames.get(c) })
    }

    var bpLowering = named(union(C_ACE, C_ARB, T_CCB, T_THIAZIDE, T_BETA_BLOCKER, T_OTHER_BP, set(['furosemide'])))
    var glucoseLowering = named(C_SULFONYLUREA, isInsulin)
    var comorbid = [['known_hypertension', 'hypertension'], ['known_diabetes', 'diabetes'], ['known_ckd', 'chronic kidney disease'],
      ['known_ascvd', 'coronary or peripheral arterial disease'], ['prior_stroke_tia', 'previous stroke or TIA'], ['known_copd', 'COPD'], ['known_asthma', 'asthma']]
      .filter(function (p) { return get(data, p[0]) === 'yes' }).map(function (p) { return p[1] })

    var acuteFound = found(ACUTE_SYMPTOMS)
    if (acuteFound.length) add('EMERGENCY_SYMPTOMS', 'acute_safety', 'critical', 'emergency', 'Immediate acute assessment',
      'Recorded now: ' + join(acuteFound) + '. These need immediate clinician assessment and the local emergency pathway'
      + (comorbid.length ? '; with ' + join(comorbid) + ' on record, consider acute coronary syndrome, stroke and metabolic causes' : '')
      + '. Normal BP or glucose cannot rule out an emergency.',
      ['WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC'], [symptomBasis].concat(bpBasis, [glucoseBasis]))
    var systolics = [sbp, rsbp].filter(function (v) { return v != null })
    if (systolics.some(function (v) { return v <= 90 })) add('LOW_BP', 'acute_safety', 'warning', 'urgent', 'Low systolic BP needs assessment',
      'Lowest systolic reading ' + pyG(Math.min.apply(null, systolics)) + ' mmHg. Assess perfusion, symptoms, hydration and change from baseline now, and verify the measurement. '
      + (bpLowering.length ? 'BP-lowering medicines recorded: ' + join(bpLowering) + '; review whether they contribute before the next doses. ' : 'No BP-lowering medicine is recorded, so look for other causes. ')
      + 'This is an isolated vital-sign flag, not a shock diagnosis or NEWS2 score.', ['RCP_NEWS2', 'NCDAI_SAFETY_SPEC'],
      bpBasis.concat(['BP-lowering medicines: ' + (join(bpLowering) || 'none recorded')]))
    if (pulse != null && (pulse <= 40 || pulse >= 131)) {
      var slow = pulse <= 40, blockers = named(T_BETA_BLOCKER)
      add('PULSE_EXTREME', 'acute_safety', 'warning', 'urgent', 'Marked pulse abnormality',
        'Pulse ' + pyG(pulse) + '/min (' + (slow ? 'bradycardia' : 'tachycardia') + '). Confirm manually, check rhythm with an ECG and assess symptoms now. '
        + (slow ? (blockers.length ? join(blockers) + ' is recorded and can slow the heart; review it urgently. ' : '')
          : 'Look for fever, dehydration, hypoxaemia, pain, bleeding and arrhythmia. ')
        + 'The complete early-warning assessment is outside this screen.', ['RCP_NEWS2', 'NCDAI_SAFETY_SPEC'],
        ['Pulse ' + pyG(pulse) + '/min'].concat(slow && blockers.length ? ['On ' + join(blockers)] : []))
    }
    if (rr != null && rr <= 8) add('RESP_SLOW', 'acute_safety', 'critical', 'emergency', 'Very low respiratory rate',
      'Respiratory rate ' + pyG(rr) + '/min. Obtain immediate clinical assessment of airway, breathing and consciousness'
      + (glucose != null && glucose <= 3.9 + 1e-9 ? '; with glucose ' + pyFixed(glucose, 1) + ' mmol/L recorded, exclude hypoglycaemia' : '')
      + '. This flag does not determine the cause or treatment.', ['RCP_NEWS2', 'NCDAI_SAFETY_SPEC'], ['Respiratory rate ' + pyG(rr) + '/min'])
    var dangerFound = found(BP_DANGER_SYMPTOMS)
    if (bpAtLeast(180, 110) && dangerFound.length) add('BP_CRISIS', 'acute_safety', 'critical', 'emergency', 'Severe BP with warning symptoms',
      'Highest BP ' + reading(highestSbp, highestDbp) + ' mmHg with ' + join(dangerFound) + '. Assess for hypertension-mediated organ damage now '
      + '(fundoscopy, neurological and cardiac examination, ECG, creatinine and urine). The Kenya protocol manages hypertensive emergencies at level 4 and above: stabilise and refer. '
      + 'Repeat BP when feasible without delaying care; this alert does not diagnose a hypertensive emergency.',
      ['KENYA_HTN_STEPS', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC'], bpBasis.concat([symptomBasis]))
    else if (bpAtLeast(180, 110)) add('BP_SEVERE', 'hypertension', 'critical', 'urgent', 'Severe blood pressure reading',
      'Highest BP ' + reading(highestSbp, highestDbp) + ' mmHg is grade 3 (≥180/110). Without organ damage the Kenya protocol treats this as a hypertensive urgency: rest in a quiet room for at least 30 minutes, '
      + (bpLowering.length ? 'optimise the current oral medicines (' + join(bpLowering) + ')' : 'initiate oral treatment')
      + ', recheck BP after 1 hour, review baseline investigations and review again in 48-72 hours, aiming for 140/90 or less within 24 hours. '
      + 'Examine for organ damage today; symptoms not documented cannot be assumed absent.',
      ['KENYA_HTN_STEPS', 'WHO_HTN_2021', 'NCDAI_SAFETY_SPEC'], bpBasis.concat(['BP-lowering medicines: ' + (join(bpLowering) || 'none recorded')]))
    if (pregnant) {
      var teratogens = named(union(C_ACE, C_ARB, T_STATINS))
      add('PREGNANCY_SCOPE', 'scope', 'warning', 'urgent', 'Use the pregnancy care pathway',
        'Pregnancy is recorded. Obtain obstetric review; adult non-pregnancy NCD treatment options are withheld.'
        + (teratogens.length ? ' Medicines needing review in pregnancy: ' + join(teratogens) + '.' : ''),
        ['NICE_PREGNANCY', 'WHO_HTN_2021'], ['Pregnant'].concat(teratogens.length ? ['On ' + join(teratogens)] : []))
      if (bpAtLeast(160, 110)) add('PREGNANCY_SEVERE_BP', 'acute_safety', 'critical', 'emergency', 'Severe BP in pregnancy',
        'BP ' + reading(highestSbp, highestDbp) + ' mmHg in pregnancy. Activate immediate obstetric assessment for this severe reading and repeat promptly without delaying escalation.', ['NICE_PREGNANCY'], bpBasis)
      else if (dangerFound.length) add('PREGNANCY_WARNING', 'acute_safety', 'critical', 'emergency', 'Pregnancy warning symptoms',
        pyCapitalize(join(dangerFound)) + ' in pregnancy. Promptly assess possible pre-eclampsia using the obstetric emergency pathway, even when BP is unavailable or below the severe threshold.',
        ['NICE_PREGNANCY', 'NCDAI_SAFETY_SPEC'], [symptomBasis].concat(bpBasis))
    }
    if (glucose != null && glucose <= 3.9 + 1e-9) {
      var danger = glucose < 3 || symptoms.has('confusion') || symptoms.has('seizure')
      var cause = '', sulfonylureas = named(C_SULFONYLUREA), insulins = named(null, isInsulin)
      if (sulfonylureas.length) cause += ' ' + join(sulfonylureas) + ' is recorded: sulfonylurea hypoglycaemia can recur, so observe longer; the Kenya flowchart advises stopping a sulfonylurea after recurrent hypoglycaemia.'
      if (insulins.length) cause += ' ' + join(insulins) + ' is recorded: find the cause, then reduce the insulin dose by 10-20%.'
      add('HYPOGLYCEMIA', 'acute_safety', 'critical', danger ? 'emergency' : 'urgent', 'Low glucose requires action now',
        'Glucose ' + pyFixed(glucose, 2) + ' mmol/L (hypoglycaemia is 3.9 or below). Treat now (Kenya 4.8): if responsive and able to swallow, give 15-20 g oral carbohydrate and recheck capillary glucose in 15 minutes, '
        + 'repeating until above 3.9, then a meal or snack within 30 minutes. If responsive but nil by mouth, give 15-20 g (30-40 ml) of 50% dextrose IV. If not responsive, give 25 g (50 ml) of 50% dextrose IV, '
        + 'or glucagon 1 mg IM if there is no IV access, inform the consultant and recheck every 15 minutes; if glucose stays low, refer on a 10% dextrose 500 ml infusion.'
        + cause + ' Then evaluate the cause and teach the patient how to prevent further episodes.',
        ['KENYA_HYPOGLYCAEMIA', 'KENYA_DM_TREATMENT'], [glucoseBasis, symptomBasis].concat(glucoseLowering.length ? ['On ' + join(glucoseLowering)] : []))
    } else if (symptoms.has('hypoglycemia_symptoms')) {
      add('SUSPECTED_HYPOGLYCEMIA', 'acute_safety', 'warning', 'urgent', 'Assess reported hypoglycaemia symptoms now',
        'Hypoglycaemia symptoms are recorded' + (glucoseLowering.length ? ' in a patient on ' + join(glucoseLowering) : '')
        + '. Check a capillary glucose now; if it is 3.9 mmol/L or below, give 15-20 g oral carbohydrate and recheck in 15 minutes (Kenya 4.8). A missing or older normal result does not resolve these symptoms.',
        ['KENYA_HYPOGLYCAEMIA'], [symptomBasis].concat(glucoseLowering.length ? ['On ' + join(glucoseLowering)] : []))
      missing.push('current_glucose_for_symptoms')
    }
    if (glucose != null && glucose >= 18) {
      var crisisFound = sortedStrings(intersection(symptoms, set(['vomiting', 'dehydration', 'confusion'])))
      var crisis = crisisFound.length > 0, sglt2 = named(C_SGLT2)
      add(crisis ? 'HYPERGLYCEMIC_CRISIS' : 'GLUCOSE_HIGH', 'acute_safety', 'critical', crisis ? 'emergency' : 'urgent',
        crisis ? 'Assess possible hyperglycaemic crisis' : 'Markedly elevated glucose',
        'Glucose ' + pyFixed(glucose, 1) + ' mmol/L' + (crisis ? ' with ' + join(crisisFound) : '')
        + (!diabetic ? ' in a patient without a recorded diabetes diagnosis' : '') + '. Assess hydration and conscious level and check urine or blood ketones now'
        + (sglt2.length ? '; ' + join(sglt2) + ' is recorded, so ketoacidosis is possible even at lower glucose' : '')
        + '. The Kenya protocol manages DKA and HHS at level 4 facilities and above: stabilise and refer. No insulin or fluid dose is generated here.',
        ['KENYA_HYPOGLYCAEMIA', 'WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC'], [glucoseBasis, symptomBasis])
    }
    var sickFound = sortedStrings(intersection(symptoms, set(['vomiting', 'dehydration'])))
    if (intersects(codeSet, C_SGLT2) && sickFound.length) add('SGLT2_ACUTE_ILLNESS', 'medication_safety', 'critical', 'urgent', 'Acute illness with an SGLT2 inhibitor',
      join(named(C_SGLT2)) + ' with ' + join(sickFound) + '. Assess for ketoacidosis, including when glucose is not markedly high; '
      + 'pause the SGLT2 inhibitor during the illness (sick-day rule) and check ketones. A normal glucose cannot provide clearance.', ['SGLT2_LABEL', 'NCDAI_SAFETY_SPEC'], [symptomBasis])
    if (spo2 != null && spo2 < 95) {
      var copd = get(data, 'known_copd') === 'yes'
      add('RESP_HYPOXEMIA', 'respiratory', spo2 < 92 ? 'critical' : 'warning', spo2 < 92 ? 'emergency' : 'urgent',
        'Low oxygen saturation needs assessment',
        'SpO2 ' + pyG(spo2) + '%' + (rr != null ? ' with respiratory rate ' + pyG(rr) + '/min' : '') + '. Check the probe and signal, then assess immediately if below 92%. '
        + (copd ? "COPD is recorded: compare with the patient's usual saturation; long-term oxygen is considered only when SaO2 is 88% or below on two occasions three weeks apart. " : 'Confirm baseline, oxygen use and clinical state. ')
        + 'This tool does not set an oxygen dose or target.', [copd ? 'KENYA_COPD' : 'WHO_PEN_2020', 'NCDAI_SAFETY_SPEC'], ['SpO2 ' + pyG(spo2) + '%', copd ? 'Known COPD' : null])
    }
    if (rr != null && rr > 25) add('RESP_TACHYPNEA', 'respiratory', 'warning', 'urgent', 'Raised respiratory rate',
      'Respiratory rate ' + pyG(rr) + '/min' + (spo2 != null ? ', SpO2 ' + pyG(spo2) + '%' : '') + '. Assess respiratory effort and acute causes now (infection, asthma or COPD exacerbation, heart failure, acidosis); '
      + 'a chronic respiratory diagnosis must not obscure other causes of rapid breathing.', ['WHO_PEN_2020', 'NCDAI_SAFETY_SPEC'], ['Respiratory rate ' + pyG(rr) + '/min'])
    var inhalers = named(null, function (c) { return INHALER_NAMES.some(function (n) { return c.indexOf(n) >= 0 }) })
    if (symptoms.has('wheeze')) {
      var context = get(data, 'known_asthma') === 'yes' ? 'asthma' : get(data, 'known_copd') === 'yes' ? 'COPD' : null
      add('RESP_WHEEZE', 'respiratory', 'warning', 'urgent', 'Assess current wheeze',
        'Wheeze today' + (context ? ' in known ' + context : ' without a recorded asthma or COPD diagnosis') + '. Assess severity (ability to speak, respiratory rate, SpO2), give the acute reliever per the local pathway and review response. '
        + (inhalers.length ? 'Current inhalers: ' + join(inhalers) + '; check technique and adherence. ' : 'No inhaler is recorded. ')
        + (!context ? 'Consider heart failure and other causes of wheeze. ' : ''), [context === 'asthma' ? 'KENYA_ASTHMA' : context ? 'KENYA_COPD' : 'WHO_PEN_2020'],
        [symptomBasis, spo2 != null ? 'SpO2 ' + pyG(spo2) + '%' : null, 'Inhalers: ' + (join(inhalers) || 'none recorded')])
    }
    var smoker = get(data, 'tobacco_use') === 'current'
    if (symptoms.has('hemoptysis')) add('HEMOPTYSIS', 'referral', 'warning', 'urgent', 'Assess coughing blood today',
      'Coughing blood is recorded' + (smoker ? ' in a current smoker' : '') + (spo2 != null ? ', with SpO2 ' + pyG(spo2) + '%' : '')
      + '. Establish the amount, haemodynamic stability and respiratory status; test sputum for TB and arrange a chest X-ray. Escalate immediately if unstable. No cancer diagnosis is inferred.',
      ['NCI_CANCER_SYMPTOMS', 'NCDAI_SAFETY_SPEC'], [symptomBasis, smoker ? 'Current smoker' : null])
    var warningSigns = set(intersection(symptoms, set(['unexplained_weight_loss', 'persistent_cough', 'breast_lump', 'abnormal_bleeding'])))
    if (warningSigns.size) {
      var actions = []
      if (warningSigns.has('breast_lump')) actions.push('breast lump: examine both breasts and axillae and refer to a surgeon, who arranges imaging and biopsy with a radiologist')
      if (warningSigns.has('abnormal_bleeding')) actions.push((sex === 'female' ? 'abnormal bleeding: identify the site; for vaginal bleeding do a speculum examination and biopsy and refer to a gynaecologic oncologist; ' : 'abnormal bleeding: identify the site; ')
        + 'blood in the stool needs referral for colonoscopy, and blood in the urine referral to a urologist')
      if (warningSigns.has('unexplained_weight_loss')) actions.push('unexplained weight loss' + (weight != null ? ' (current weight ' + pyG(weight) + ' kg; compare with previous records)' : '')
        + ': with changed bowel habit, anaemia or blood in the stool refer for colonoscopy; with upper abdominal pain or new indigestion refer urgently for endoscopy (OGD); also consider TB, HIV and uncontrolled diabetes')
      if (warningSigns.has('persistent_cough')) actions.push('persistent cough' + (smoker ? ' in a current smoker' : '') + ': test sputum for TB and arrange a chest X-ray; persistent hoarseness needs ENT referral')
      add('CANCER_WARNING', 'referral', 'warning', symptoms.has('abnormal_bleeding') ? 'urgent' : 'soon', 'Arrange diagnostic assessment of warning symptoms',
        'Kenya Table 9 actions for this patient: ' + actions.join('; ') + '. Record symptom duration and set a tracked referral. These symptoms can have non-cancer causes, including infection.',
        ['KENYA_CANCER_SIGNS', 'WHO_CANCER_DIAGNOSIS'], [symptomBasis, smoker ? 'Current smoker' : null])
    }
    var renalReview = named(union(set(['metformin']), C_SULFONYLUREA, C_SGLT2, C_NSAID, C_ACE, C_ARB, set(['spironolactone'])))
    if (egfr != null && egfr < 30) add('RENAL_SEVERE', 'kidney', 'critical', 'urgent', 'Severely reduced kidney function',
      'eGFR ' + pyG(egfr) + ' (KDIGO category ' + (egfr < 15 ? 'G5' : 'G4') + '). Arrange prompt clinical assessment and referral planning; assess acute deterioration, hydration, urine output and previous results. '
      + (renalReview.length ? 'Review these recorded medicines against this eGFR today: ' + join(renalReview) + '. ' : '')
      + 'A single result cannot establish chronicity.', ['WHO_HEARTS_D_2020', 'KDIGO_CKD_2024'], [egfrBasis].concat(renalReview.length ? ['On ' + join(renalReview)] : []))
    if (potassium != null && potassium >= 5.5) {
      // A negative dosing-context entry cannot cancel a positive acute finding.
      var acuteK = get(data, 'acutely_unwell') === 'yes' || get(data, 'acute_kidney_injury') === 'yes' || get(get(data, 'dosing_context') || {}, 'acute_illness') === 'yes'
      ;['acutely_unwell', 'acute_kidney_injury'].forEach(function (field) { if (get(data, field, 'unknown') === 'unknown') missing.push(field) })
      var detail
      if (potassium >= 6.5) detail = 'Arrange immediate hospital assessment and treatment. Do not delay transfer for a community repeat sample.'
      else if (acuteK) detail = 'Arrange same-day hospital assessment because acute illness or acute kidney injury is recorded. Escalate immediately if unstable; do not wait for routine repeat testing.'
      else if (potassium >= 6) detail = 'Arrange same-day clinical review and repeat potassium within one day. Assess whether hospital care is needed.'
      else detail = 'For an unexpected result, repeat potassium within three days, or sooner as clinically indicated. Confirm clinical stability and previous results before setting follow-up.'
      var raising = named(union(C_ACE, C_ARB, set(['spironolactone']), C_NSAID))
      detail = 'Potassium ' + pyG(potassium) + ' mmol/L' + (egfr != null ? ', eGFR ' + pyG(egfr) : '') + '. ' + detail
      detail += raising.length ? ' Potassium-raising medicines recorded: ' + join(raising) + '; review them now.' : ''
      detail += ' Assess clinical state, ECG, sample validity (haemolysis) and diet. Unknown acute illness or kidney injury must be assessed now; if present, consider hospital assessment today. No potassium-lowering dose is generated.'
      add('POTASSIUM_HIGH', 'acute_safety', potassium >= 6 || acuteK ? 'critical' : 'warning',
        potassium >= 6.5 ? 'emergency' : potassium >= 6 || acuteK ? 'urgent' : 'soon', 'Elevated potassium', detail, ['UKKA_POTASSIUM_2026'],
        [potassiumBasis, 'Acutely unwell: ' + pyStr(get(data, 'acutely_unwell', 'unknown')), 'Acute kidney injury: ' + pyStr(get(data, 'acute_kidney_injury', 'unknown'))]
          .concat(raising.length ? ['On ' + join(raising)] : []))
    }
    if (potassium != null && potassium < 3.5) {
      var wasting = named(union(T_THIAZIDE, set(['furosemide'])))
      add('POTASSIUM_LOW', 'acute_safety', potassium < 3 ? 'critical' : 'warning',
        potassium < 2.5 ? 'emergency' : potassium < 3 ? 'urgent' : 'soon', 'Reduced potassium',
        'Potassium ' + pyG(potassium) + ' mmol/L. ' + (wasting.length ? 'Potassium-lowering diuretics recorded: ' + join(wasting) + '; review the dose and need. ' : '')
        + 'Review symptoms, ECG, vomiting or diarrhoea, and magnesium. Below 2.5 mmol/L requires immediate supervised assessment; no electrolyte replacement dose is generated.', ['NHS_LOW_POTASSIUM'],
        [potassiumBasis].concat(wasting.length ? ['On ' + join(wasting)] : []))
    }
    if (symptoms.has('foot_ulcer')) add('FOOT_ULCER', 'referral', 'warning', 'urgent', 'Assess foot ulcer and limb risk',
      'Foot ulcer recorded' + (diabetic ? ' in a patient with diabetes (' + (hba1cBasis || glucoseBasis || 'no current glycaemic result') + ')' : '')
      + '. Today assess infection (spreading redness, pus, fever), foot pulses and perfusion, and systemic illness; offload the foot. Infection, gangrene or critical ischaemia warrants urgent referral; absence of these findings has not been established.',
      ['WHO_HEARTS_D_2020', 'NCDAI_SAFETY_SPEC'], [symptomBasis, diabetic ? hba1cBasis : null])
    if (codeSet.has('metformin')) {
      if (egfr == null) missing.push('egfr_for_metformin_review')
      else if (egfr < 30) add('METFORMIN_RENAL', 'medication_safety', 'critical', 'urgent', 'Metformin renal contraindication flag',
        medNames.get('metformin') + ' is recorded with eGFR ' + pyG(egfr) + ", below the label's renal limit of 30. Obtain urgent prescriber review to stop it; the system does not issue a prescription change.", ['METFORMIN_LABEL'], [egfrBasis, 'On metformin'])
      else if (egfr < 45) add('METFORMIN_REVIEW', 'medication_safety', 'warning', 'soon', 'Review metformin with reduced eGFR',
        medNames.get('metformin') + ' is recorded with eGFR ' + pyG(egfr) + ' (30-44). Review benefit, risk and the current dose, and monitor kidney function more often. Starting metformin is not recommended in this range.', ['METFORMIN_LABEL'], [egfrBasis, 'On metformin'])
    }
    if (codeSet.has('glibenclamide') && age >= 60) add('GLIBENCLAMIDE_OLDER_ADULT', 'medication_safety', 'warning', 'soon', 'Review glibenclamide in an older adult',
      'Age ' + age + ' on ' + medNames.get('glibenclamide') + ". The WHO protocol advises avoiding glibenclamide from age 60 because of hypoglycaemia; the Kenya flowchart's sulfonylurea options are gliclazide 40-160 mg or glimepiride 1-4 mg. "
      + 'Review hypoglycaemia history with the prescriber.', ['WHO_HEARTS_MEDS_2018', 'KENYA_DM_TREATMENT'], ['Age ' + age, 'On glibenclamide'])
    if (intersects(codeSet, C_SULFONYLUREA) && egfr != null && egfr < 60) add('SULFONYLUREA_RENAL', 'medication_safety', 'warning', 'soon', 'Review sulfonylurea with impaired kidney function',
      join(named(C_SULFONYLUREA)) + ' with eGFR ' + pyG(egfr) + '. Reduced kidney function increases hypoglycaemia risk. Ask about hypoglycaemic episodes, meal pattern and monitoring; do not infer a safe dose from this screen.',
      ['NICE_DIABETES_2026', 'NCDAI_SAFETY_SPEC'], [egfrBasis, 'On ' + join(named(C_SULFONYLUREA))])
    var rasClass = union(C_ACE, C_ARB)
    if (intersects(codeSet, rasClass)) {
      if (pregnant) add('RAS_PREGNANCY', 'medication_safety', 'critical', 'urgent', 'ACE inhibitor/ARB in pregnancy',
        join(named(rasClass)) + ' is recorded in pregnancy. Arrange urgent prescriber and obstetric review because of fetal risk. No replacement drug is selected automatically.',
        ['NICE_PREGNANCY', 'LISINOPRIL_LABEL'], ['Pregnant', 'On ' + join(named(rasClass))])
      if (pregnancy === 'unknown') missing.push('pregnancy_status_for_RAS_medication_review')
      if (egfr == null) missing.push('egfr_for_RAS_medication_review')
      if (potassium == null) missing.push('potassium_for_RAS_medication_review')
    }
    if (pregnant && intersects(codeSet, T_STATINS)) add('STATIN_PREGNANCY', 'medication_safety', 'critical', 'urgent', 'Statin recorded in pregnancy',
      join(named(T_STATINS)) + ' is recorded and statins are contraindicated in pregnancy (NICE 1.5.9). Arrange prescriber review to stop it; do not restart until breastfeeding has finished.',
      ['NICE_LIPIDS_NG238'], ['Pregnant', 'On ' + join(named(T_STATINS))])
    if (intersects(codeSet, C_ACE) && intersects(codeSet, C_ARB)) add('DUAL_RAS', 'medication_safety', 'warning', 'soon', 'Combined ACE inhibitor and ARB recorded',
      join(named(C_ACE)) + ' and ' + join(named(C_ARB)) + ' are both recorded. Combining an ACE inhibitor with an ARB raises renal, potassium and hypotension risk; reconcile and seek prescriber review to stop one.',
      ['LISINOPRIL_LABEL'], ['On ' + join(named(rasClass)), potassiumBasis, egfrBasis])
    if (intersects(codeSet, rasClass) && codeSet.has('spironolactone')) add('POTASSIUM_MEDICATION_RISK', 'medication_safety', 'warning', 'soon', 'Potassium-raising combination',
      join(named(rasClass)) + ' with ' + medNames.get('spironolactone') + (potassium != null ? '; latest potassium ' + pyG(potassium) + ' mmol/L' : '; no potassium is recorded') + (egfr != null ? ', eGFR ' + pyG(egfr) : '')
      + '. Verify the indication and arrange regular potassium and kidney-function monitoring; no dose change is inferred.', ['LISINOPRIL_LABEL'], [potassiumBasis, egfrBasis])
    if (intersects(codeSet, C_NSAID) && intersects(codeSet, rasClass)) {
      var diuretics = named(union(T_THIAZIDE, set(['furosemide', 'spironolactone'])))
      add('NSAID_RENAL', 'medication_safety', 'warning', 'soon', 'NSAID with ACE inhibitor/ARB',
        join(named(C_NSAID)) + ' with ' + join(named(rasClass)) + (diuretics.length ? ' and ' + join(diuretics) + " (the 'triple whammy' for acute kidney injury)" : '') + (egfr != null ? '; eGFR ' + pyG(egfr) : '')
        + '. Review the need for the NSAID, check over-the-counter use and hydration, and arrange supervised medication reconciliation.', ['LISINOPRIL_LABEL'],
        ['On ' + join(named(union(C_NSAID, rasClass))), egfrBasis])
    }
    var conflicts = sortedStrings(intersection(codeSet, allergies))
    var extra = new Set()
    meds.forEach(function (m, i) { if (allergies.has(ingredient(get(m, 'name')))) extra.add(codes[i]) })
    conflicts = conflicts.concat(sortedStrings(Array.from(extra).filter(function (c) { return conflicts.indexOf(c) < 0 })))
    if (conflicts.length) add('ALLERGY_CONFLICT', 'medication_safety', 'critical', 'urgent', 'Medicine overlaps a recorded allergy',
      'Potential exact-match conflict: ' + conflicts.join(', ') + '. Confirm the substance, reaction and severity with a clinician before administration decisions.', ['NCDAI_SAFETY_SPEC'])
    var counts = new Map()
    codes.forEach(function (c) { counts.set(c, (counts.get(c) || 0) + 1) })
    var duplicate = sortedStrings(Array.from(counts.keys()).filter(function (c) { return counts.get(c) > 1 }))
    if (duplicate.length) add('DUPLICATE_MEDICATION', 'medication_safety', 'warning', 'soon', 'Possible duplicate medicine entries',
      'Reconcile duplicate ingredient codes: ' + duplicate.join(', ') + '. Separate schedules may be intentional; never combine doses automatically.', ['NCDAI_SAFETY_SPEC'])
    var unsupported = sortedStrings(Array.from(codeSet).filter(function (c) { return !C_SUPPORTED.has(c) }))
    if (unsupported.length) add('MEDICATION_UNSUPPORTED', 'medication_safety', 'warning', 'soon', 'Medicines outside the rule dictionary',
      'Manual pharmacist/prescriber review required for: ' + unsupported.map(function (c) { return medNames.get(c) }).join(', ') + '. Absence of an interaction alert does not establish compatibility.', ['NCDAI_SAFETY_SPEC'])

    // Routine disease review is not allowed to compete with an emergency banner.
    var acute = PRIORITY[result.urgency] >= PRIORITY.urgent
    var cvd = cvdState === 'yes'
    // Elective medicine options are withheld whenever the encounter is acute.
    var elective = get(data, 'acutely_unwell') !== 'yes'
    if (!pregnant && !acute) {
      var useRepeat = rsbp != null && rdbp != null
      var ctx = { age: age, sex: sex, pregnancy: pregnancy,
        meds: meds.map(function (m, i) { return Object.assign({}, m, { _code: codes[i], _label: medNames.get(codes[i]) }) }), codes: codeSet,
        control_bp: useRepeat ? [rsbp, rdbp] : sbp != null && dbp != null ? [sbp, dbp] : null,
        control_is_repeat: useRepeat, diabetic: diabetic, renal_disease: renalDisease, cvd: cvd, cvd_status: cvdState,
        asthma: get(data, 'known_asthma') === 'yes',
        tobacco: get(data, 'tobacco_use', 'unknown'), adherence: get(data, 'adherence', 'unknown'),
        egfr: egfr, hba1c: hba1c, glucose: glucose, glucose_timing: glucoseTiming, weight: weight,
        total_cholesterol: totalChol, ldl: ldl, hdl: hdl, triglycerides: triglycerides }
      var htnOptions = hypertensive && elective ? hypertensionOptions(ctx) : []
      var grade = bpAtLeast(160, 100) ? 'grade 2' : 'grade 1'
      var risk = comorbid.filter(function (c) {
        return c === 'diabetes' || c === 'chronic kidney disease' || c === 'coronary or peripheral arterial disease' || c === 'previous stroke or TIA'
      })
      var nextStep = (htnOptions.length ? ' Treatment options for this patient are listed as a separate recommendation.' : hypertensive ? ''
        : ' If hypertension is not yet diagnosed, confirm persistent elevation (SBP ≥140 and/or DBP ≥90 mmHg on repeat readings, the Kenya protocol confirms in the second month) before diagnosing and treating.')
        + (risk.length ? ' With ' + join(risk) + ' on record, cardiovascular risk is high.' : '')
      if (bpAtLeast(160, 100)) add('BP_HIGH', 'hypertension', 'warning', 'soon', 'Prompt BP treatment review',
        'Highest reading ' + reading(highestSbp, highestDbp) + ' mmHg is in the ' + grade + ' hypertension range (≥160/100). Confirm the measurement and review adherence and contraindications without delay; '
        + 'the Kenya protocol starts medicine for grade 2 hypertension alongside lifestyle changes.' + nextStep, ['KENYA_HTN_STEPS', 'WHO_HTN_2021'], bpBasis)
      else if (bpAtLeast(140, 90)) add('BP_REVIEW', 'hypertension', 'warning', 'soon', 'Raised BP needs confirmation and review',
        'Highest reading ' + reading(highestSbp, highestDbp) + ' mmHg is in the grade 1 hypertension range (140-159/90-99). Confirm the reading with correct technique and review medicines and adherence.' + nextStep,
        ['KENYA_HTN_STEPS', 'WHO_HTN_2021'], bpBasis)
      else if (hypertensive) add('HTN_FOLLOWUP', 'hypertension', 'info', 'routine', 'Continue an individualized BP review plan',
        (highestSbp != null ? 'BP ' + reading(highestSbp, highestDbp) + ' mmHg is at the Kenya target (<140/90)' : 'No BP is recorded at this visit')
        + (bpLowering.length ? ' on ' + join(bpLowering) : '') + '. Continue the current plan; once at target the protocol reviews every 4-6 months, sooner for symptoms such as headache or a persistent cough (ACE inhibitor). '
        + 'Incomplete data cannot establish control.', ['KENYA_HTN_STEPS'], bpBasis.concat(['Medicines: ' + (join(bpLowering) || 'none recorded')]))
      var fastingGlucose = glucoseTiming === 'fasting' ? glucose : null
      if (hba1c != null && hba1c >= 6.5 && !diabetic) add('DIABETES_CONFIRM', 'diabetes', 'warning', 'soon', 'Confirm possible diabetes',
        'HbA1c ' + pyG(hba1c) + '% meets the diagnostic threshold (≥6.5%). Without classic symptoms, arrange a confirmatory test on a different day (HbA1c or fasting blood sugar) before diagnosing; '
        + 'HbA1c can be unreliable with anaemia or haemoglobin variants.', ['KENYA_DM_DIAGNOSIS'], [hba1cBasis, glucoseBasis])
      else if (fastingGlucose != null && fastingGlucose >= 7.0 && !diabetic) add('DIABETES_CONFIRM', 'diabetes', 'warning', 'soon', 'Confirm possible diabetes (fasting glucose)',
        'Fasting glucose ' + pyFixed(fastingGlucose, 1) + ' mmol/L meets the diagnostic threshold (≥7.0). Without classic symptoms, arrange a confirmatory fasting blood sugar or HbA1c on a different day before diagnosing.',
        ['KENYA_DM_DIAGNOSIS'], [glucoseBasis])
      else if (glucose != null && glucoseTiming !== 'fasting' && glucose >= 11.1 && !diabetic) add('DIABETES_CONFIRM', 'diabetes', 'warning', 'soon', 'Clarify elevated glucose and diagnosis',
        (glucoseTiming === 'random' ? 'Random' : 'Unspecified-timing') + ' glucose ' + pyFixed(glucose, 1) + ' mmol/L is ≥11.1. With polyuria, polydipsia or weight loss this supports diabetes; '
        + 'without symptoms, a confirmatory fasting blood sugar (≥7.0 mmol/L) or HbA1c (≥6.5%) on another day is needed; record it in Laboratory results.', ['KENYA_DM_DIAGNOSIS'], [glucoseBasis])
      else if (!diabetic && ((hba1c != null && 5.7 <= hba1c && hba1c < 6.5) || (fastingGlucose != null && 5.6 <= fastingGlucose && fastingGlucose < 7.0))) {
        var loss = weight != null && bmi != null && bmi >= 25 ? ' For this patient (' + pyG(weight) + ' kg) that is ' + pyFixed(weight * 0.05, 0) + '-' + pyFixed(weight * 0.1, 0) + ' kg.' : ''
        add('PREDIABETES', 'prevention', 'info', 'routine', 'Prediabetes range: lifestyle intervention',
          (hba1c != null && 5.7 <= hba1c && hba1c < 6.5 ? hba1cBasis : glucoseBasis) + ' is in the prediabetes range (HbA1c 5.7-6.4% or fasting glucose 5.6-6.9 mmol/L). Advise diet, 30 minutes of physical activity 5 times weekly and sleep hygiene; '
          + 'if overweight aim to lose 5-10% of body weight in 12 months.' + loss + ' Repeat HbA1c every 3-6 months. Metformin is considered if BMI is above 35 or there was gestational diabetes'
          + (bmi != null ? ' (BMI ' + pyG(bmi) + ').' : '.'),
          ['KENYA_PREDIABETES'], [hba1cBasis, glucoseBasis, bmi != null ? 'BMI ' + pyG(bmi) + ' kg/m²' : null])
      }
      if (diabetic) {
        var aboveTarget = (hba1c != null && hba1c >= 7) || (hba1c == null && fastingGlucose != null && fastingGlucose > 7.2)
        var status
        if (hba1c != null) status = 'HbA1c ' + pyG(hba1c) + '% is ' + (hba1c >= 7 ? pyFixed(hba1c - 7, 1) + ' points above' : 'within') + ' the Kenya target (<7.0%). '
        else if (fastingGlucose != null) status = 'Fasting glucose ' + pyFixed(fastingGlucose, 1) + ' mmol/L is ' + (fastingGlucose > 7.2 ? 'above' : 'within') + ' the Kenya fasting target (4.4-7.2). '
        else status = 'No HbA1c or fasting glucose is recorded to judge control against the Kenya target (HbA1c <7.0%). '
        add('DIABETES_REVIEW', 'diabetes', hba1c != null && hba1c >= 9 ? 'warning' : 'info',
          hba1c != null && hba1c >= 9 ? 'soon' : 'routine', 'Review diabetes control and complication screening',
          status + (aboveTarget && elective ? 'Treatment options are listed separately. ' : '')
          + (glucoseLowering.length ? 'Ask about hypoglycaemia on ' + join(glucoseLowering) + '. ' : '')
          + 'Complication screening: kidney function (eGFR' + (egfr != null ? ', last ' + pyG(egfr) : ', not recorded') + ') and urine albumin, eyes, and feet (pulses, sensation, ulcers).',
          ['KENYA_DM_TREATMENT', 'NCDAI_SAFETY_SPEC'],
          [hba1cBasis, glucoseBasis, egfrBasis, 'Glucose-lowering medicines: ' + (join(named(union(set(['metformin']), C_SULFONYLUREA, C_SGLT2), isInsulin)) || 'none recorded')])
      }
      var statinIndicated = diabetic || cvd || renalDisease || (totalChol != null && totalChol >= 8)
      if (!statinIndicated && ((hdl != null && hdl < 0.9) || (triglycerides != null && triglycerides > 2.82))) add('LIPID_RISK_FACTOR', 'prevention', 'info', 'routine', 'Abnormal lipids: estimate cardiovascular risk',
        [hdl != null && hdl < 0.9 ? 'HDL ' + pyG(hdl) + ' mmol/L (below 0.90)' : null,
          triglycerides != null && triglycerides > 2.82 ? 'Triglycerides ' + pyG(triglycerides) + ' mmol/L (above 2.82)' : null].filter(truthy).join('; ')
        + '. These are cardiovascular and diabetes risk factors. Estimate 10-year CVD risk with the WHO chart (age, sex, smoking, systolic BP and cholesterol); a statin is advised above 20%. '
        + 'Screen for diabetes if not done and advise diet, activity and weight management.',
        ['KENYA_DM_SCREENING', 'KENYA_CVD_RISK'], [hdl != null ? 'HDL ' + pyG(hdl) + ' mmol/L' : null, triglycerides != null ? 'Triglycerides ' + pyG(triglycerides) + ' mmol/L' : null])
      var central = waist != null && ((sex === 'female' && waist >= 90) || (sex === 'male' && waist >= 100))
      if ((bmi != null && bmi >= 25) || central) {
        var goal = ''
        if (weight != null) {
          goal = ' A 5-10% loss for this patient is ' + pyFixed(weight * 0.05, 0) + '-' + pyFixed(weight * 0.1, 0) + ' kg over 12 months'
          if (height != null) goal += '; a BMI below 25 corresponds to under ' + pyFixed(25 * sq(height / 100), 0) + ' kg at ' + pyG(height) + ' cm'
          goal += '.'
        }
        add('WEIGHT_MANAGEMENT', 'prevention', 'info', 'routine',
          (bmi != null && bmi >= 30 ? 'Obesity' : bmi != null && bmi >= 25 ? 'Overweight' : 'Raised waist circumference') + ': agree a weight plan',
          (bmi != null ? 'BMI ' + pyG(bmi) + ' kg/m² (' + bmiCategory + ')' : 'BMI not calculable')
          + (waist != null ? ', waist ' + pyG(waist) + ' cm' + (central ? ' (above the Kenya cut-off of ' + (sex === 'female' ? '90' : '100') + ' cm)' : '') : '') + '. '
          + (hypertensive || diabetic ? 'Weight loss will help lower ' + join([hypertensive ? 'blood pressure' : '', diabetic ? 'glucose' : ''].filter(truthy)) + ' and cardiovascular risk. '
            : 'Overweight is a diabetes and cardiovascular risk factor; screen for diabetes and estimate CVD risk. ')
          + 'Advise reduced salt, sugar and saturated fat and moderate aerobic activity 30 minutes on 5-7 days weekly.' + goal + ' Record weight at each visit.',
          ['KENYA_HTN_LIFESTYLE', 'KENYA_DM_SCREENING'],
          [bmi != null ? 'BMI ' + pyG(bmi) + ' kg/m² (' + bmiCategory + ')' : null, weight != null ? 'Weight ' + pyG(weight) + ' kg' : null,
            height != null ? 'Height ' + pyG(height) + ' cm' : null, waist != null ? 'Waist ' + pyG(waist) + ' cm' : null])
      }
      if (elective) {
        var treatmentOptions = htnOptions.concat(diabetic ? diabetesOptions(ctx) : [],
          lipidOptions(ctx), respiratoryOptions(ctx))
        treatmentOptions.forEach(function (option) {
          add(option.rule_id, has(option, 'category') ? option.category : 'treatment', option.severity, option.urgency, option.title, option.detail,
            option.sources, option.basis)
        })
        if (statinIndicated && !intersects(codeSet, T_STATINS) && cvdState === 'unknown') missing.push('known_cvd_for_statin_choice')
      }
      if (renalDisease || (egfr != null && egfr < 60)) {
        var category = egfr == null ? null : gStage(egfr)
        var nephrotoxic = named(C_NSAID)
        add('CKD_REVIEW', 'kidney', 'warning', 'soon', 'Review kidney status and chronicity',
          (egfr != null ? 'eGFR ' + pyG(egfr) + ' (KDIGO category ' + category + ')' : 'Known chronic kidney disease with no eGFR recorded') + (renalDisease && egfr != null ? '; CKD is recorded' : '') + '. '
          + (!renalDisease ? 'Repeat eGFR and check urine albumin: CKD requires abnormality for more than 3 months, so compare with previous results and look for acute causes. ' : 'Check urine albumin and the trend against previous results. ')
          + (nephrotoxic.length ? 'Avoid NSAIDs: ' + join(nephrotoxic) + ' is recorded. ' : '')
          + (renalReview.length ? 'Review doses of ' + join(renalReview) + ' for this eGFR.' : ''), ['KDIGO_CKD_2024'],
          [egfrBasis, renalDisease ? 'Known CKD' : null].concat(renalReview.length ? ['On ' + join(renalReview)] : []))
      }
      if (get(data, 'known_asthma') === 'yes' || get(data, 'known_copd') === 'yes') {
        var text, respSources
        if (get(data, 'known_copd') === 'yes') {
          text = 'COPD recorded' + (inhalers.length ? ', current inhalers: ' + join(inhalers) : ', no inhaler recorded') + '. Grade by exacerbations and breathlessness (Kenya 6.8): '
            + 'group A (0-1 exacerbation a year, breathless only on strenuous exercise or hills) uses a bronchodilator; group B (breathless walking on level ground) uses LABA+LAMA; '
            + 'group E (2 or more moderate exacerbations, or 1 hospital admission, a year) uses LABA+LAMA with specialist referral. '
            + (smoker ? 'Smoking cessation is the most important step for this patient. ' : '') + 'Offer influenza, pneumococcal and COVID-19 vaccination and an exercise programme.'
          respSources = ['KENYA_COPD']
        } else {
          text = 'Asthma recorded' + (inhalers.length ? ', current inhalers: ' + join(inhalers) : ', no inhaler recorded') + '. Review symptom frequency, night waking, reliever use and exacerbations to set the Kenya step; '
            + 'check inhaler technique, adherence, triggers and a written action plan.' + (smoker ? ' Smoking worsens control; offer cessation support.' : '')
          respSources = ['KENYA_ASTHMA']
        }
        add('RESP_CHRONIC_REVIEW', 'respiratory', 'info', 'soon', 'Review chronic respiratory care', text, respSources,
          [get(data, 'known_copd') === 'yes' ? 'Known COPD' : 'Known asthma', 'Inhalers: ' + (join(inhalers) || 'none recorded'), smoker ? 'Current smoker' : null])
      }
      if (get(data, 'known_cancer') === 'yes') add('CANCER_SCOPE', 'continuity', 'info', 'soon', 'Coordinate with the treating cancer team',
        'Known cancer is recorded. Reconcile the oncology plan, supportive care and pain needs, and referral follow-through; check interactions of ' + (join(named(null, anyCode)) || 'current medicines') + ' with cancer treatment. Cancer staging and treatment are outside this release.',
        ['WHO_CANCER_DIAGNOSIS', 'NCDAI_SAFETY_SPEC'])
      if (smoker) add('TOBACCO_SUPPORT', 'prevention', 'info', 'routine', 'Offer tobacco cessation support',
        'Current tobacco use' + (comorbid.length ? ' with ' + join(comorbid) + ', which smoking makes more dangerous' : '') + '. Advise stopping clearly, assess readiness, and refer to a cessation programme with pharmacological support where available; record the agreed plan.',
        ['KENYA_HTN_LIFESTYLE', 'WHO_PEN_2020'], ['Current smoker'].concat(comorbid.length ? ['Known ' + join(comorbid)] : []))
      if (get(data, 'adherence') === 'missed') {
        var allMeds = named(null, anyCode)
        add('ADHERENCE_REVIEW', 'continuity', 'info', 'soon', 'Explore missed medicine use',
          'Missed doses reported' + (allMeds.length ? ' across ' + allMeds.length + ' recorded medicine' + (allMeds.length !== 1 ? 's' : '') + ' (' + join(allMeds) + ')' : '')
          + '. Ask which doses are missed and why (cost, side effects, stock, understanding). Simplify where possible, for example once-daily or single-pill combinations, before adding treatment.',
          ['NCDAI_SAFETY_SPEC', 'KENYA_HTN_STEPS'], ['Adherence: missed doses'].concat(allMeds.length ? ['On ' + join(allMeds)] : []))
      }
    }

    if (sbp == null) missing.push('systolic_bp')
    if (dbp == null) missing.push('diastolic_bp')
    if (bpAtLeast(140, 90) && (rsbp == null || rdbp == null)) missing.push('repeat_blood_pressure')
    if (diabetic && hba1c == null && glucose == null) missing.push('glycaemic_measurement')
    if (glucose != null && glucoseTiming === 'unknown' && !diabetic && glucose >= 5.6) missing.push('glucose_context')
    if ((diabetic || hypertensive || renalDisease || cvdState === 'yes') && totalChol == null && ldl == null) missing.push('lipid_profile')
    if ((diabetic || hypertensive) && bmi == null) missing.push('weight_and_height')
    if ((diabetic || renalDisease) && egfr == null) missing.push('egfr')
    if (symptoms.has('wheeze') || symptoms.has('breathlessness')) {
      if (spo2 == null) missing.push('oxygen_saturation')
      if (rr == null) missing.push('respiratory_rate')
    }
    if (pregnancy === 'unknown') missing.push('pregnancy_status')
    ;['medications_reviewed', 'allergies_reviewed', 'symptoms_reviewed'].forEach(function (field) { if (get(data, field) !== true) missing.push(field) })
    KNOWN_FIELDS.forEach(function (field) { if (get(data, field, 'unknown') === 'unknown') missing.push(field) })
    if (get(data, 'medicine_availability', 'unknown') !== 'available') result.warnings.push('Confirm medicine stock, cost and access; availability is unverified or limited.')
    if (meds.some(function (m) { return get(m, 'dose') == null || !truthy(get(m, 'unit')) || !truthy(get(m, 'frequency')) })) result.warnings.push('One or more medication schedules are incomplete; dose safety has not been evaluated.')
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
      'Still needed for this patient: ' + result.missing_data.map(function (item) { return underscoresToSpaces(item) + (has(GAP_REASONS, item) ? ' (' + GAP_REASONS[item] + ')' : '') }).join('; ')
      + '. Unknown, unreviewed and absent findings are distinct. Emergency assessment must not wait for routine documentation.', ['NCDAI_SAFETY_SPEC'])
    if (!recs.length) add('CLINICIAN_REVIEW', 'scope', 'info', 'routine', 'Complete clinician review',
      'No configured high-priority rule triggered from the supplied structured fields. Review the patient and full record; this screen does not establish safety or exclude disease.', ['NCDAI_SAFETY_SPEC'])
    recs.sort(function (a, b) { return SEVERITY[a.severity] - SEVERITY[b.severity] || (a.rule_id < b.rule_id ? -1 : a.rule_id > b.rule_id ? 1 : 0) })
    result.summary = {
      emergency: 'Immediate clinician assessment and the appropriate emergency pathway are advised.',
      urgent: 'Same-day clinician assessment is advised; act now for low glucose or evolving symptoms.',
      soon: 'Clinician review and completion of identified checks are advised; timing needs clinical confirmation.',
      routine: 'Complete the supervised NCD review and agree follow-up; this result does not provide clinical clearance.',
    }[result.urgency]
    result.care_plan = buildCarePlan(Object.assign({}, data, { egfr: egfr, glucose: glucose, glucose_unit: 'mmol/L' }), age, sex, meds.map(function (m, i) {
      return Object.assign({}, m, { _code: codes[i], _label: truthy(get(m, 'name')) ? pyStr(get(m, 'name')) : codes[i] })
    }), result)
    // The backend attaches its dose-reference module here; it is not ported (excluded from parity).
    // Consultant synthesis reads the final urgency; it never changes findings.
    result.consultant = build(data, age, sex, result)
    return result
  }

  // ---- treatment options (treatment.py) -----------------------------------
  // Guideline treatment options for confirmed hypertension and type 2 diabetes,
  // statins, aspirin and asthma. Deterministic and advisory; the caller (assess)
  // withholds them in acute, urgent or pregnancy contexts. Mirrors treatment.py
  // function by function: change both together.
  var T_CCB = set(['amlodipine', 'felodipine', 'nifedipine'])
  var T_THIAZIDE = set(['hydrochlorothiazide', 'chlorthalidone', 'indapamide'])
  var T_ACE = set(['lisinopril', 'enalapril', 'ramipril', 'captopril', 'perindopril'])
  var T_ARB = set(['losartan', 'valsartan', 'candesartan', 'telmisartan', 'irbesartan'])
  var T_RAS = union(T_ACE, T_ARB)
  var T_BETA_BLOCKER = set(['atenolol', 'bisoprolol', 'carvedilol', 'metoprolol', 'propranolol', 'labetalol', 'nebivolol'])
  var T_OTHER_BP = set(['spironolactone', 'methyldopa', 'hydralazine', 'clonidine', 'prazosin', 'minoxidil', 'furosemide'])
  var T_STATINS = set(['atorvastatin', 'simvastatin', 'rosuvastatin', 'pravastatin', 'lovastatin'])
  var T_SULFONYLUREA = set(['glibenclamide', 'gliclazide', 'glimepiride', 'glipizide'])
  var T_DPP4 = set(['sitagliptin', 'vildagliptin', 'linagliptin', 'saxagliptin'])
  var T_SGLT2 = set(['empagliflozin', 'dapagliflozin', 'canagliflozin'])
  var T_TZD = set(['pioglitazone'])
  var T_BP_ANY = union(T_CCB, T_THIAZIDE, T_RAS, T_BETA_BLOCKER, T_OTHER_BP)
  var T_GLUCOSE_ORAL = union(set(['metformin']), T_SULFONYLUREA, T_DPP4, T_SGLT2, T_TZD)
  var T_INSULIN_NAMES = set(['glargine', 'detemir', 'degludec', 'mixtard', 'insulatard', 'actrapid', 'humulin', 'novomix'])

  // Kenya MOH Table 4 (printed page 16, PDF page 25): once-daily start and maximum, mg.
  // Enalapril, captopril, perindopril and nifedipine have ranges, salts or divided
  // schedules and are deliberately not compared.
  var HTN_TABLE4 = {
    amlodipine: [5, 10], felodipine: [5, 10], chlorthalidone: [25, 50],
    hydrochlorothiazide: [12.5, 25], indapamide: [2.5, 5], lisinopril: [10, 40],
    ramipril: [2.5, 10], candesartan: [8, 32], irbesartan: [150, 300],
    losartan: [50, 100], telmisartan: [40, 80], valsartan: [80, 160],
  }
  var CLASS_LABEL = { ccb: 'calcium channel blocker', thiazide: 'thiazide/thiazide-like diuretic', ras: 'ACE inhibitor/ARB' }
  var START_EXAMPLE = {
    ccb: 'amlodipine 5 mg once daily (maximum 10 mg)',
    thiazide: 'hydrochlorothiazide 12.5 mg once daily (maximum 25 mg) or chlorthalidone 25 mg once daily (maximum 50 mg)',
    ras: 'losartan 50 mg once daily (maximum 100 mg) or lisinopril 10 mg once daily (maximum 40 mg)',
  }
  var STEP_NOTE = 'Kenya protocol: stay on each step for at least 3 months before escalating; first exclude non-adherence, '
    + 'white-coat hypertension and incorrect measurement technique. Target <140/90 mmHg; review monthly until at target.'
  var RAS_CHECK = 'Before an ACE inhibitor/ARB: confirm the patient is not pregnant or planning pregnancy, '
    + 'and check potassium and eGFR at baseline and after starting.'

  // Established cardiovascular disease from the recorded history: coronary or
  // peripheral arterial disease, or a previous stroke/TIA. 'unknown' unless both
  // are recorded, so an incomplete history is never read as absence.
  function cvdStatus(data) {
    var ascvd = get(data, 'known_ascvd', 'unknown'), stroke = get(data, 'prior_stroke_tia', 'unknown')
    if (ascvd === 'yes' || stroke === 'yes') return 'yes'
    return ascvd === 'no' && stroke === 'no' ? 'no' : 'unknown'
  }
  function isInsulin(code) { return code.indexOf('insulin') >= 0 || T_INSULIN_NAMES.has(code) }
  // Free-text frequencies are only compared when they unambiguously mean once daily.
  function onceDaily(frequency) {
    var text = pyStr(truthy(frequency) ? frequency : '').trim().toLowerCase()
    return /^(?:od|o\.d\.?|once( a)? daily|once( a)? day|daily|1 ?x ?daily|every morning|nocte|once)$/.test(text)
  }
  function unitText(med) { var u = get(med, 'unit'); return pyStr(truthy(u) ? u : '').trim().toLowerCase() }
  // [current_mg, maximum_mg] only when the schedule is unambiguous, else null.
  function dosePosition(med) {
    var code = med._code, dose = get(med, 'dose')
    if (!has(HTN_TABLE4, code) || dose == null || unitText(med) !== 'mg' || !onceDaily(get(med, 'frequency'))) return null
    return [pyFloat(dose), HTN_TABLE4[code][1]]
  }
  // Recorded name, dose and schedule, e.g. 'Amlodipine 5 mg once daily'.
  function regimen(med) {
    var dose = get(med, 'dose')
    return [med._label, isPyNumber(dose) ? pyG(dose) : null, get(med, 'unit'), get(med, 'frequency')].filter(truthy).map(pyStr).join(' ')
  }
  function mg(value) { return pyG(value) + ' mg' }
  function label(med) { return med._label }

  function hypertensionOptions(ctx) {
    var meds = ctx.meds, codes = ctx.codes
    var readings = ctx.control_bp
    if (readings == null) return []
    var sbp = readings[0], dbp = readings[1]
    var thresholdSbp = ctx.age >= 80 && !(ctx.diabetic || ctx.renal_disease) ? 150 : 140
    if (sbp < thresholdSbp && dbp < 90) return []
    var classes = set([['ccb', T_CCB], ['thiazide', T_THIAZIDE], ['ras', T_RAS]].filter(function (p) { return intersects(codes, p[1]) }).map(function (p) { return p[0] }))
    var onAny = intersects(codes, T_BP_ANY)
    var current = sortedStrings(meds.filter(function (m) { return T_BP_ANY.has(m._code) }).map(regimen))
    var basis = ['BP used for control: ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg' + (ctx.control_is_repeat ? ' (repeat reading)' : ''),
      'Current antihypertensives: ' + (current.length ? current.join(', ') : 'none recorded'),
      'Target: <' + thresholdSbp + '/90 mmHg', 'Adherence: ' + underscoresToSpaces(ctx.adherence)]
    var sources = ['KENYA_HTN_STEPS', 'KENYA_DOSES_HTN']
    if (onAny && ctx.adherence === 'missed') {
      return [{ rule_id: 'TX_HTN_ADHERENCE', severity: 'warning', urgency: 'soon',
        title: 'BP above target with missed doses: address adherence before escalating',
        detail: 'BP ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg is above target while missed doses are reported. The Kenya protocol requires '
          + 'non-adherence to be excluded before up-titration. Agree a plan for barriers, cost and side effects, '
          + 'consider a once-daily or single-pill combination, and recheck BP in about 4 weeks before adding medicines.',
        sources: sources, basis: basis }]
    }
    if (!onAny) {
      var grade = sbp < 160 && dbp < 100 ? 1 : 2
      var highRisk = ctx.diabetic || ctx.renal_disease || ctx.cvd || ctx.tobacco === 'current'
      var lead = 'Grade ' + (grade === 1 ? grade : '2 or higher') + ' hypertension (BP ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg) with no antihypertensive recorded. '
      if (grade === 1 && !highRisk && ctx.age < 80) {
        lead += 'Without other cardiovascular risk factors the protocol allows lifestyle management for up to 3 months first; '
          + 'if BP remains at or above 140/90 mmHg, start medicine. '
      }
      var startDetail = lead + 'Step 1 options: a low-dose two-drug combination, for example amlodipine 5 mg + losartan 50 mg once daily, '
        + 'amlodipine 5 mg + lisinopril 10 mg once daily, or amlodipine 5 mg + hydrochlorothiazide 12.5 mg once daily. '
        + 'Monotherapy (for example amlodipine 5 mg once daily) is reserved for low-risk grade 1 hypertension (the protocol notes systolic at or above 150 mmHg), adults aged 80 or over, or frail patients. '
        + 'Use a single-pill combination where available. ' + RAS_CHECK + ' ' + STEP_NOTE
      return [{ rule_id: 'TX_HTN_START', severity: 'warning', urgency: 'soon',
        title: 'Consider starting antihypertensive treatment (Kenya step 1)', detail: startDetail, sources: sources, basis: basis }]
    }
    if (classes.has('ccb') && classes.has('thiazide') && classes.has('ras')) {
      return [{ rule_id: 'TX_HTN_SPECIALIST', severity: 'warning', urgency: 'soon',
        title: 'BP above target on triple therapy: step 4 needs a physician',
        detail: 'BP ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg despite triple therapy (' + current.join(', ') + '). '
          + 'Confirm full doses and adherence and exclude secondary causes. Step 4 adds spironolactone or another diuretic, '
          + 'a beta blocker or a centrally acting agent, and must be started with a physician. Refer: patients not at target '
          + 'after 3 months of treatment are a referral indication.',
        sources: sources.concat(['KENYA_HTN_LIFESTYLE']), basis: basis }]
    }
    var belowMax = []
    meds.forEach(function (med) {
      var position = dosePosition(med)
      if (position && position[0] < position[1]) belowMax.push(med._label + ' ' + mg(position[0]) + ' once daily to up to ' + mg(position[1]))
    })
    var unclear = meds.filter(function (m) { return has(HTN_TABLE4, m._code) && dosePosition(m) == null }).map(label)
    var missingClasses = ['ccb', 'ras', 'thiazide'].filter(function (c) { return !classes.has(c) })
    var detail, title
    if (classes.size <= 1) {
      var addition = missingClasses.slice(0, 2).map(function (c) { return START_EXAMPLE[c] }).join(' or ')
      detail = 'BP ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg on ' + current.join(', ') + ' (' + (classes.size ? 'one first-line medicine class' : 'no first-line medicine class') + '). Move to a two-drug combination: add ' + addition + '. '
        + (belowMax.length ? 'Increasing the current medicine (' + belowMax.join('; ') + ') is an alternative if a single agent is preferred. ' : '')
        + (intersects(codes, T_BETA_BLOCKER) && !classes.size
          ? 'A beta blocker alone is not a first-line step unless it has a specific indication (heart failure, angina, atrial fibrillation). ' : '')
        + (missingClasses.indexOf('ras') >= 0 ? RAS_CHECK + ' ' : '') + STEP_NOTE
      return [{ rule_id: 'TX_HTN_STEP_UP', severity: 'warning', urgency: 'soon',
        title: 'BP above target: add a second medicine class (Kenya step 1-2)', detail: detail, sources: sources, basis: basis }]
    }
    if (belowMax.length) {
      detail = 'BP ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg on ' + current.join(', ') + '. Step 2 is full-dose dual therapy: increase '
        + belowMax.join('; ') + '. ' + STEP_NOTE
      title = 'BP above target: increase to full-dose dual therapy (Kenya step 2)'
    } else {
      detail = 'BP ' + pyG(sbp) + '/' + pyG(dbp) + ' mmHg on ' + current.join(', ')
        + (unclear.length ? ' (doses not compared because the schedule is unclear for: ' + unclear.join(', ') + '; confirm they are at the maximum first)' : ' at the maximum Table 4 doses')
        + '. Step 3 is triple therapy: add the missing ' + CLASS_LABEL[missingClasses[0]] + ', for example ' + START_EXAMPLE[missingClasses[0]] + '. '
        + (missingClasses[0] === 'ras' ? RAS_CHECK + ' ' : '') + STEP_NOTE
      title = 'BP above target: add a ' + CLASS_LABEL[missingClasses[0]] + ' (Kenya step 3)'
    }
    return [{ rule_id: 'TX_HTN_STEP_UP', severity: 'warning', urgency: 'soon', title: title, detail: detail, sources: sources, basis: basis }]
  }

  function diabetesOptions(ctx) {
    var codes = ctx.codes, egfr = ctx.egfr, hba1c = ctx.hba1c
    var fasting = ctx.glucose_timing === 'fasting' ? ctx.glucose : null
    var metformin = codes.has('metformin')
    var insulin = Array.from(codes).some(isInsulin)
    var oral = [['metformin', set(['metformin'])], ['sulfonylurea', T_SULFONYLUREA], ['DPP-4 inhibitor', T_DPP4],
      ['SGLT2 inhibitor', T_SGLT2], ['pioglitazone', T_TZD]].filter(function (p) { return intersects(codes, p[1]) }).map(function (p) { return p[0] })
    var current = sortedStrings(ctx.meds.filter(function (m) { return T_GLUCOSE_ORAL.has(m._code) || isInsulin(m._code) }).map(regimen))
    var above, measure
    if (hba1c != null) { above = hba1c >= 7.0; measure = 'HbA1c ' + pyG(hba1c) + '%' }
    else if (fasting != null) { above = fasting > 7.2; measure = 'fasting glucose ' + pyFixed(fasting, 1) + ' mmol/L' }
    else { above = null; measure = 'no HbA1c or fasting glucose recorded' }
    var basis = ['Glycaemic control: ' + measure, 'Target: HbA1c <7.0%; fasting glucose 4.4-7.2 mmol/L',
      'Current glucose-lowering medicines: ' + (current.length ? current.join(', ') : 'none recorded'),
      'eGFR: ' + (egfr != null ? pyG(egfr) + ' mL/min/1.73 m²' : 'not recorded')]
    if (ctx.weight != null) basis.push('Weight: ' + pyG(ctx.weight) + ' kg')
    var sources = ['KENYA_DM_TREATMENT']
    var options = []
    var cardiorenal = ctx.cvd || ctx.renal_disease || (egfr != null && egfr < 60)
    var detail, title, rule
    if (!metformin && !oral.length && !insulin) {
      if (egfr == null) {
        detail = 'Metformin is first-line treatment for type 2 diabetes: start 500 mg once daily with food and titrate to 1 g twice daily as tolerated. '
          + 'Record an eGFR before starting, because kidney function decides whether metformin can be used.'
      } else if (egfr > 45) {
        detail = 'eGFR ' + pyG(egfr) + '. Start metformin 500 mg once daily with food and titrate upwards to 1 g twice daily as tolerated. '
          + 'Review GI tolerance, kidney function and vitamin B12 over time.'
      } else if (egfr > 30) {
        detail = 'eGFR ' + pyG(egfr) + '. The Kenya flowchart permits metformin above 30, but the product label advises against starting it at eGFR 30-45. '
          + 'Individualize with the prescriber; if started, keep the dose low and monitor kidney function.'
      } else {
        detail = 'eGFR ' + pyG(egfr) + ': metformin is contraindicated. For GFR ≤30 the Kenya flowchart lists an SGLT2 inhibitor, a DPP-4 inhibitor '
          + 'or pioglitazone. Seek physician review for medicine choice and dosing in advanced kidney disease.'
      }
      if (cardiorenal && (egfr == null || egfr > 30)) {
        detail += ' With cardiovascular or kidney disease, the protocol advises adding an SGLT2 inhibitor alongside metformin even if HbA1c is at target.'
      }
      options.push({ rule_id: 'TX_DM_METFORMIN', severity: 'warning', urgency: 'soon',
        title: egfr == null || egfr > 30 ? 'No glucose-lowering medicine recorded: consider metformin (Kenya first line)' : 'Metformin contraindicated: physician choice of alternative',
        detail: detail, sources: sources.concat(['METFORMIN_LABEL']), basis: basis })
      return options
    }
    if (above) {
      if (insulin) {
        detail = cap(measure) + ' is above target on ' + current.join(', ') + '. Basal or NPH insulin: titrate by 2-4 units every 3 days to a fasting glucose of 4-7 mmol/L; '
          + 'for hypoglycaemia, find the cause and reduce by 10-20%. If HbA1c stays above target with a normal fasting glucose, '
          + 'add prandial insulin 4 units with the largest meal (or 10% of the basal dose), increasing by 1-2 units twice weekly. '
          + 'Insulin changes are made at level 4 facilities and above.'
        title = 'Glycaemia above target on insulin: titrate per Kenya insulin protocol'
        rule = 'TX_DM_INSULIN'
      } else if (!metformin && (egfr == null || egfr > 30)) {
        detail = cap(measure) + ' on ' + oral.join(', ') + ' without metformin, the first-line medicine. Unless it was stopped for '
          + 'intolerance or a contraindication, add metformin 500 mg once daily with food, titrating to 1 g twice daily as tolerated. '
          + (egfr == null ? 'Record an eGFR before starting. ' : egfr <= 45 ? 'Avoid starting it at eGFR 30-45 (product label). ' : '')
        title = 'Glycaemia above target without metformin: consider adding metformin'
        rule = 'TX_DM_INTENSIFY'
      } else if (oral.length <= 1) {
        detail = cap(measure) + ' on ' + (current.join(', ') || 'current therapy') + '. Add a second medicine: a sulfonylurea '
          + '(gliclazide 40-160 mg or glimepiride 1-4 mg; watch for hypoglycaemia and stop if recurrent) where cost matters, '
          + 'or a DPP-4 inhibitor or SGLT2 inhibitor where hypoglycaemia risk matters. '
          + (cardiorenal && (egfr || 0) > 30 ? 'With cardiovascular or kidney disease and eGFR above 30, an SGLT2 inhibitor is preferred. ' : '')
          + (ctx.age >= 60 ? 'Avoid glibenclamide at age 60 or over. ' : '')
          + 'Confirm adherence and reassess HbA1c in about 3 months.'
        title = 'Glycaemia above target: add a second glucose-lowering medicine (Kenya 4.5)'
        rule = 'TX_DM_INTENSIFY'
      } else {
        var dose = ''
        if (ctx.weight != null) dose = ' (for ' + pyG(ctx.weight) + ' kg, 0.1-0.2 IU/kg is ' + pyFixed(ctx.weight * 0.1, 0) + '-' + pyFixed(ctx.weight * 0.2, 0) + ' units)'
        detail = cap(measure) + ' on ' + oral.length + ' oral medicines (' + current.join(', ') + '). '
          + (oral.length === 2 && !intersects(codes, T_TZD) ? 'Options: add pioglitazone 15-30 mg (avoid in heart failure), or ' : 'Consider: ')
          + 'start basal or NPH insulin at bedtime, 10 units a day or 0.1-0.2 IU/kg/day' + dose + ', titrated by 2-4 units every 3 days '
          + 'to a fasting glucose of 4-7 mmol/L. Insulin is started at level 4 facilities and above; refer if not available here.'
        title = 'Glycaemia above target on combination therapy: consider a third agent or basal insulin'
        rule = 'TX_DM_INTENSIFY'
      }
      options.push({ rule_id: rule, severity: 'warning', urgency: 'soon', title: title, detail: detail, sources: sources, basis: basis })
    }
    if (!options.length && metformin && !intersects(codes, T_SGLT2) && (ctx.cvd || ctx.renal_disease) && egfr != null && egfr > 30 && !insulin) {
      options.push({ rule_id: 'TX_DM_CARDIORENAL', severity: 'info', urgency: 'routine',
        title: 'Cardiovascular or kidney disease with diabetes: consider an SGLT2 inhibitor',
        detail: 'eGFR ' + pyG(egfr) + '. The Kenya protocol advises starting an SGLT2 inhibitor with metformin in people with high cardiovascular risk '
          + 'or CKD and GFR above 30, even when HbA1c is within target. Counsel on genital hygiene and sick-day rules '
          + '(pause during vomiting or dehydration).',
        sources: sources.concat(['SGLT2_LABEL']), basis: basis })
    }
    return options
  }

  // NICE NG238 "Terms used": statin intensity by daily dose (mg).
  var STATIN_INTENSITY = {
    atorvastatin: [[20, 80, 'high'], [10, 10, 'medium']],
    rosuvastatin: [[10, 40, 'high'], [5, 5, 'medium']],
    simvastatin: [[20, 40, 'medium'], [10, 10, 'low']],
    fluvastatin: [[80, 80, 'medium'], [20, 40, 'low']],
    pravastatin: [[5, 40, 'low']],
  }
  var STATIN_MONITORING = 'Check a full lipid profile and liver transaminase (ALT or AST) 2-3 months after starting or changing the dose, '
    + 'transaminase again at 12 months, and a lipid profile annually (NICE 1.11).'

  // [daily mg or null, intensity or null]; dose is read only when unambiguous.
  function statinPosition(med) {
    var dose = get(med, 'dose')
    if (dose == null || unitText(med) !== 'mg' || !onceDaily(get(med, 'frequency'))) return [null, null]
    var bands = has(STATIN_INTENSITY, med._code) ? STATIN_INTENSITY[med._code] : []
    for (var i = 0; i < bands.length; i++) {
      if (!isPyNumber(dose)) throw new TypeError('statin dose must be a number')
      if (bands[i][0] <= +dose && +dose <= bands[i][1]) return [pyFloat(dose), bands[i][2]]
    }
    return [pyFloat(dose), null]
  }
  function nonHdlOf(tc, hdl) { return tc != null && hdl != null ? pyRound(tc - hdl, 1) : null }

  function lipidOptions(ctx) {
    var meds = ctx.meds
    var tc = ctx.total_cholesterol, ldl = ctx.ldl, hdl = ctx.hdl, tg = ctx.triglycerides
    var nonHdl = nonHdlOf(tc, hdl)
    var egfr = ctx.egfr, cvd = ctx.cvd
    var ckd = ctx.renal_disease || (egfr != null && egfr < 60)
    var lipidBasis = [tc != null ? 'Total cholesterol ' + pyG(tc) + ' mmol/L' : null, ldl != null ? 'LDL ' + pyG(ldl) + ' mmol/L' : null,
      hdl != null ? 'HDL ' + pyG(hdl) + ' mmol/L' : null, nonHdl != null ? 'Non-HDL ' + pyG(nonHdl) + ' mmol/L (total minus HDL)' : null,
      tg != null ? 'Triglycerides ' + pyG(tg) + ' mmol/L' : null].filter(truthy)
    var options = []
    // Specialist thresholds apply whatever else is decided (NICE 1.4.5-1.4.7).
    var referral = []
    if (tg != null && tg > 20) referral.push('triglycerides ' + pyG(tg) + ' mmol/L are above 20: arrange urgent specialist review unless explained by alcohol or poor glycaemic control')
    else if (tg != null && tg >= 10) referral.push('triglycerides ' + pyG(tg) + ' mmol/L (10-20): repeat a fasting sample after 5 days and within 2 weeks, look for secondary causes, and seek specialist advice if still above 10')
    if ((tc != null && tc > 9.0) || (nonHdl != null && nonHdl > 7.5)) {
      referral.push('total cholesterol above 9.0 or non-HDL above 7.5 mmol/L: arrange specialist assessment for a familial lipid disorder, even without a family history')
    }
    if (referral.length) {
      options.push({ rule_id: 'LIPID_SPECIALIST', severity: 'warning', urgency: 'soon', category: 'referral',
        title: 'Lipid result meets a specialist-referral threshold',
        detail: 'For this patient: ' + referral.join('; ') + '. First exclude secondary causes (excess alcohol, uncontrolled diabetes, hypothyroidism, liver disease, nephrotic syndrome).',
        sources: ['NICE_LIPIDS_NG238'], basis: lipidBasis })
    }
    var statins = meds.filter(function (m) { return T_STATINS.has(m._code) })
    var reasons = [[cvd, 'established cardiovascular disease'], [ctx.diabetic, 'diabetes'], [ctx.renal_disease, 'chronic kidney disease'],
      [tc != null && tc >= 8, tc != null ? 'total cholesterol ' + pyG(tc) + ' mmol/L (at least 8)' : '']]
      .filter(function (p) { return p[0] }).map(function (p) { return p[1] })
    var pregnancyNote = ''
    if (ctx.sex === 'female' && ctx.age < 55) {
      pregnancyNote = ' Statins are contraindicated in pregnancy: ' + (ctx.pregnancy !== 'no' && ctx.pregnancy !== 'not_applicable' ? 'confirm pregnancy status before prescribing. ' : '')
        + 'Advise stopping if pregnancy is possible, stopping 3 months before trying to conceive, and not taking it while breastfeeding.'
    }
    if (!statins.length && reasons.length) {
      var dose, why, target
      if (ckd) {
        dose = 'atorvastatin 20 mg once daily'
        why = 'NICE 1.8.1 offers atorvastatin 20 mg for primary or secondary prevention in chronic kidney disease'
          + (egfr != null ? ' (eGFR ' + pyG(egfr) + ').' : '.')
          + ' If the lipid target is not met, the dose may be increased while eGFR is 30 or above; below 30, agree higher doses with a renal specialist.'
        target = 'Target: LDL 2.0 mmol/L or less (non-HDL 2.6 or less) with cardiovascular disease; otherwise a reduction in non-HDL cholesterol of more than 40%.'
      } else if (cvd) {
        dose = 'atorvastatin 80 mg once daily'
        why = 'NICE 1.7.2 offers atorvastatin 80 mg for established cardiovascular disease whatever the cholesterol level. Use a lower dose if it could '
          + 'interact with other medicines, adverse effects are likely, or the patient prefers it (1.7.3).'
        target = 'Target: LDL 2.0 mmol/L or less, or non-HDL 2.6 mmol/L or less (NICE 1.7.1).'
      } else {
        dose = 'atorvastatin 20 mg once daily'
        why = 'NICE 1.6.7 recommends atorvastatin 20 mg for primary prevention. The Kenya protocol counts established diabetes or kidney disease '
          + 'as more than 20% 10-year CVD risk, for which it advises a statin.'
        target = 'Target: more than 40% reduction in non-HDL cholesterol (NICE 1.6.1)'
          + (nonHdl != null ? '; from the current ' + pyG(nonHdl) + ' mmol/L that means below ' + pyFixed(nonHdl * 0.6, 1) + ' mmol/L.' : '; record a baseline full lipid profile first.')
      }
      var ageNote = ctx.age >= 85 && !cvd ? ' At 85 or older, consider rather than offer, weighing frailty and life expectancy (NICE 1.6.9).' : ''
      var startDetail = 'Recorded ' + reasons.join(' and ') + ', with no statin on the medicine list. Suggested: ' + dose + '. ' + why + ' ' + target + ' '
        + 'Before starting: full lipid profile, ALT or AST, renal function and HbA1c; ask about unexplained muscle symptoms (check creatine kinase if present). '
        + 'A transaminase below 3 times the upper limit of normal does not rule out a statin. ' + STATIN_MONITORING + pregnancyNote + ageNote
      options.push({ rule_id: 'TX_STATIN_START', severity: 'warning', urgency: 'soon', category: 'treatment',
        title: 'Start a statin: ' + dose, detail: startDetail, sources: ['NICE_LIPIDS_NG238', 'KENYA_CVD_RISK'],
        basis: reasons.map(function (r) { return r.slice(0, 5) !== 'total' ? 'Known ' + r : null })
          .concat(lipidBasis, [egfr != null ? 'eGFR ' + pyG(egfr) + ' mL/min/1.73 m²' : null, 'No statin recorded']) })
    } else if (statins.length) {
      var med = statins[0]
      var position = statinPosition(med), daily = position[0], level = position[1]
      var current = daily != null ? med._label + ' ' + pyG(daily) + ' mg daily' : med._label + ' (dose or schedule unclear)'
      var intensity = level ? ' (' + level + ' intensity)' : ''
      var above = (ldl != null && ldl > 2.0) || (nonHdl != null && nonHdl > 2.6)
      var steps = null, title = null
      if (cvd && above) {
        if (ckd && egfr != null && egfr < 30) {
          steps = 'eGFR is below 30: agree any dose increase with a renal specialist (NICE 1.8.3).'
        } else if (daily != null && ((med._code === 'atorvastatin' && daily >= 80) || (med._code === 'rosuvastatin' && daily >= 40))) {
          steps = 'Already on the maximum dose of a high-intensity statin: confirm adherence, then consider adding ezetimibe (NICE 1.7.9, TA385).'
        } else {
          steps = 'Confirm adherence and timing, then move to a high-intensity statin at the maximum tolerated dose, for example atorvastatin 80 mg once daily'
            + (ckd ? ' (with CKD and eGFR 30 or above, increase atorvastatin stepwise from 20 mg)' : '') + ' (NICE 1.9.1).'
        }
        title = 'Lipids above the secondary-prevention target: intensify statin'
      } else if (cvd && (level === 'low' || level === 'medium')) {
        steps = 'Discuss switching to a high-intensity statin such as atorvastatin 80 mg once daily (NICE 1.11.12)'
          + (ldl == null && nonHdl == null ? '; check a lipid profile to judge control.' : '.')
        title = 'Cardiovascular disease on a lower-intensity statin'
      } else if (cvd && ldl == null && nonHdl == null) {
        steps = 'No LDL or non-HDL is recorded: check a full lipid profile against the target of LDL 2.0 or less / non-HDL 2.6 or less (NICE 1.7.1).'
        title = 'Check lipid control on statin'
      }
      if (steps) {
        options.push({ rule_id: 'TX_STATIN_OPTIMISE', severity: above ? 'warning' : 'info', urgency: 'soon', category: 'treatment',
          title: title, detail: 'Currently on ' + current + intensity + '. ' + steps + ' ' + STATIN_MONITORING,
          sources: ['NICE_LIPIDS_NG238'], basis: ['Current statin: ' + current + intensity].concat(lipidBasis, ['Known cardiovascular disease']) })
      }
    }
    var aspirin = meds.filter(function (m) { return m._code === 'aspirin' })
    if (aspirin.length && ctx.cvd_status !== 'yes') {
      options.push({ rule_id: 'TX_ASPIRIN_REVIEW', severity: 'info', urgency: 'routine', category: 'treatment',
        title: 'Review aspirin without recorded cardiovascular disease',
        detail: aspirin[0]._label + ' is recorded but cardiovascular disease is '
          + (ctx.cvd_status === 'no' ? 'recorded as absent' : 'not documented')
          + '. NICE 1.2.1 advises not routinely offering aspirin for primary prevention. Confirm the indication (for example a previous heart attack, stroke or stent); '
          + 'if there is none, discuss stopping it, particularly with a history of bleeding or dyspepsia.',
        sources: ['NICE_LIPIDS_NG238'], basis: ['On ' + aspirin[0]._label, 'Cardiovascular disease: ' + ctx.cvd_status] })
    }
    return options
  }

  var T_RESPIRATORY = ['salbutamol', 'formoterol', 'salmeterol', 'ipratropium', 'tiotropium', 'montelukast', 'beclometasone', 'beclomethasone', 'budesonide', 'fluticasone']
  var T_ICS = ['beclometasone', 'beclomethasone', 'budesonide', 'fluticasone', 'ciclesonide', 'mometasone']
  function contains(code, names) { return names.some(function (name) { return code.indexOf(name) >= 0 }) }
  function hasIcs(code) { return contains(code, T_ICS) }

  // Kenya 6.7: SABA or LABA monotherapy is not recommended; every step includes ICS.
  function respiratoryOptions(ctx) {
    if (!ctx.asthma) return []
    var meds = ctx.meds
    if (meds.some(function (m) { return hasIcs(m._code) })) return []
    var labels = meds.filter(function (m) { return contains(m._code, T_RESPIRATORY) }).map(label)
    var saba = meds.filter(function (m) { return m._code.indexOf('salbutamol') >= 0 }).map(label)
    var laba = meds.filter(function (m) { return m._code.indexOf('formoterol') >= 0 || m._code.indexOf('salmeterol') >= 0 }).map(label)
    var problem
    if (laba.length) problem = laba.join(', ') + ' (a long-acting beta agonist) is recorded without an inhaled corticosteroid; LABA monotherapy is not recommended in asthma.'
    else if (saba.length) problem = saba.join(', ') + ' is recorded without an inhaled corticosteroid; SABA monotherapy is not recommended.'
    else problem = 'No asthma inhaler is recorded.'
    var detail = problem + ' Every step of the Kenya protocol includes an inhaled corticosteroid. Choose the step from the symptom pattern: '
      + 'symptoms less than twice a month, as-needed low-dose budesonide-formoterol (or salbutamol-beclometasone); twice a month or more but not most days, '
      + 'add regular low-dose ICS (beclometasone or budesonide) or use as-needed budesonide-formoterol; most days or night waking weekly, regular low-dose '
      + 'ICS-formoterol or ICS-LABA; with low lung function as well, medium-dose ICS-formoterol and specialist consultation. '
      + 'Check inhaler technique (add a spacer if needed), adherence and triggers, and rinse the mouth after ICS.'
    return [{ rule_id: 'TX_ASTHMA_ICS', severity: 'warning', urgency: 'soon', category: 'treatment',
      title: 'Asthma without an inhaled corticosteroid: add ICS (Kenya step chart)', detail: detail,
      sources: ['KENYA_ASTHMA'], basis: ['Known asthma', 'Inhalers recorded: ' + (labels.length ? labels.join(', ') : 'none')] }]
  }

  // ---- patient summary (care_plan.py) --------------------------------------
  // Display-only: restates this patient's values against their targets and
  // collects the monitoring the cited sources specify. assess() passes the rules' eGFR
  // (including CKD-EPI) and mmol/L glucose; other values are read as recorded.
  var CARE_CLASSES = [
    [T_CCB, 'Calcium channel blocker'], [T_THIAZIDE, 'Thiazide-type diuretic'], [T_ACE, 'ACE inhibitor'], [T_ARB, 'ARB'],
    [T_BETA_BLOCKER, 'Beta blocker'], [T_OTHER_BP, 'Other BP-lowering'], [set(['metformin']), 'Biguanide'], [T_SULFONYLUREA, 'Sulfonylurea'],
    [T_DPP4, 'DPP-4 inhibitor'], [T_SGLT2, 'SGLT2 inhibitor'], [T_TZD, 'Thiazolidinedione'], [T_STATINS, 'Statin'], [set(['aspirin']), 'Antiplatelet'],
  ]
  var CARE_INHALERS = ['salbutamol', 'formoterol', 'salmeterol', 'ipratropium', 'tiotropium', 'beclometasone', 'beclomethasone', 'budesonide', 'fluticasone']

  function classOf(code) {
    if (isInsulin(code)) return 'Insulin'
    for (var i = 0; i < CARE_CLASSES.length; i++) if (CARE_CLASSES[i][0].has(code)) return CARE_CLASSES[i][1]
    if (contains(code, CARE_INHALERS)) return 'Inhaler'
    return 'Other'
  }

  function buildCarePlan(data, age, sex, meds, assessment) {
    var rules = set(assessment.recommendations.map(function (rec) { return rec.rule_id }))
    var derived = truthy(assessment.derived) ? assessment.derived : {}
    function yes(field) { return (field === 'known_cvd' ? cvdStatus(data) : get(data, field)) === 'yes' }
    var sbp = get(data, 'systolic_bp', null), dbp = get(data, 'diastolic_bp', null)
    var rsbp = get(data, 'repeat_systolic_bp', null), rdbp = get(data, 'repeat_diastolic_bp', null)
    var isRepeat = rsbp != null && rdbp != null
    var control = isRepeat ? [rsbp, rdbp] : sbp != null && dbp != null ? [sbp, dbp] : null
    var hba1c = get(data, 'hba1c', null), egfr = get(data, 'egfr', null)
    var fasting = get(data, 'glucose_context') === 'fasting' && get(data, 'glucose_unit') === 'mmol/L' ? get(data, 'glucose', null) : null
    var codes = set(meds.map(function (m) { return m._code }))
    var problems = []
    function problem(name, status, tone) { problems.push({ name: name, status: status, tone: tone }) }

    var critical = assessment.recommendations.filter(function (rec) { return rec.severity === 'critical' }).map(function (rec) { return rec.title })
    if (critical.length) {
      problem('Acute findings', assessment.urgency === 'urgent' || assessment.urgency === 'emergency'
        ? critical.join('; ') + '. Routine treatment options are withheld until these are addressed.' : critical.join('; '), 'urgent')
    }
    if (yes('pregnancy_status')) problem('Pregnancy', 'Recorded; obstetric pathway applies', 'urgent')
    if (yes('known_hypertension')) {
      var target = age >= 80 && !(yes('known_diabetes') || yes('known_ckd')) ? 150 : 140
      if (control) {
        var bpAbove = control[0] >= target || control[1] >= 90
        problem('Hypertension', 'BP ' + pyG(control[0]) + '/' + pyG(control[1]) + ' mmHg' + (isRepeat ? ' (repeat)' : '') + ': ' + (bpAbove ? 'above' : 'at') + ' target (<' + target + '/90)', bpAbove ? 'attention' : 'ok')
      } else problem('Hypertension', 'No BP recorded at this visit', 'unknown')
    } else if (control && (control[0] >= 140 || control[1] >= 90)) {
      problem('Raised blood pressure', 'BP ' + pyG(control[0]) + '/' + pyG(control[1]) + ' mmHg without a recorded diagnosis: confirm on repeat readings', 'attention')
    }
    if (yes('known_diabetes')) {
      if (hba1c != null) problem('Type 2 diabetes', 'HbA1c ' + pyG(hba1c) + '%: ' + (hba1c >= 7 ? pyFixed(hba1c - 7, 1) + ' above' : 'within') + ' target (<7.0%)', hba1c >= 7 ? 'attention' : 'ok')
      else if (fasting != null) problem('Type 2 diabetes', 'Fasting glucose ' + pyG(fasting) + ' mmol/L: ' + (fasting > 7.2 ? 'above' : 'within') + ' target (4.4-7.2)', fasting > 7.2 ? 'attention' : 'ok')
      else problem('Type 2 diabetes', 'No HbA1c or fasting glucose recorded', 'unknown')
    } else if (rules.has('DIABETES_CONFIRM')) problem('Possible diabetes', 'Diagnostic threshold met once: confirmatory test needed', 'attention')
    else if (rules.has('PREDIABETES')) problem('Prediabetes', 'In the prediabetes range: lifestyle intervention', 'attention')
    var statins = meds.filter(function (m) { return T_STATINS.has(m._code) })
    var highRisk = [['known_cvd', 'cardiovascular disease'], ['known_diabetes', 'diabetes'], ['known_ckd', 'kidney disease']]
      .filter(function (p) { return yes(p[0]) }).map(function (p) { return p[1] })
    var tc = get(data, 'total_cholesterol_mmol', null), hdl = get(data, 'hdl_mmol', null), ldl = get(data, 'ldl_mmol', null)
    var nonHdl = nonHdlOf(tc, hdl)
    var lipids = [ldl != null ? 'LDL ' + pyG(ldl) : null, nonHdl != null ? 'non-HDL ' + pyG(nonHdl) : null,
      tc != null && nonHdl == null ? 'total ' + pyG(tc) : null].filter(truthy).join(', ')
    if (highRisk.length || statins.length || (tc != null && tc >= 8)) {
      var therapy
      if (statins.length) {
        var position = statinPosition(statins[0])
        therapy = 'on ' + statins[0]._label + (position[0] != null ? ' ' + pyG(position[0]) + ' mg (' + (position[1] || 'unclassified') + ' intensity)' : '')
      } else therapy = 'no statin recorded'
      var lipidTarget = yes('known_cvd') ? ' (target LDL ≤2.0 or non-HDL ≤2.6)' : ''
      var lipidAbove = yes('known_cvd') && ((ldl != null && ldl > 2.0) || (nonHdl != null && nonHdl > 2.6))
      problem('Cardiovascular risk', (highRisk.length ? 'High, from ' + highRisk.join(' and ') + '; ' : '') + therapy
        + (lipids ? '; lipids ' + lipids + ' mmol/L' + lipidTarget : '; no lipid profile recorded'),
        !statins.length || lipidAbove || !lipids ? 'attention' : 'ok')
    }
    if ((egfr != null && egfr < 60) || yes('known_ckd')) {
      var category = egfr == null ? null : gStage(egfr)
      problem('Kidney function', (egfr != null ? 'eGFR ' + pyG(egfr) + ' (KDIGO ' + category + ')' : 'Known CKD; no eGFR recorded')
        + (yes('known_ckd') ? '' : ': chronicity not yet established'), egfr != null && egfr < 30 ? 'urgent' : 'attention')
    }
    if (get(derived, 'bmi') != null) {
      var bmi = derived.bmi
      problem('Weight', 'BMI ' + pyG(bmi) + ' kg/m² (' + derived.bmi_category + ')' + (get(data, 'weight_kg') != null ? ', ' + pyG(data.weight_kg) + ' kg' : ''),
        bmi >= 18.5 && bmi < 25 ? 'ok' : 'attention')
    }
    var inhalers = meds.filter(function (m) { return classOf(m._code) === 'Inhaler' }).map(label)
    if (yes('known_asthma')) {
      problem('Asthma', 'Inhalers: ' + (inhalers.length ? inhalers.join(', ') : 'none recorded') + (rules.has('TX_ASTHMA_ICS') ? '; no inhaled corticosteroid' : ''),
        rules.has('TX_ASTHMA_ICS') ? 'attention' : 'ok')
    }
    if (yes('known_copd')) problem('COPD', 'Inhalers: ' + (inhalers.length ? inhalers.join(', ') : 'none recorded'), inhalers.length ? 'ok' : 'attention')
    if (get(data, 'tobacco_use') === 'current') problem('Tobacco', 'Current smoker', 'attention')
    if (get(data, 'adherence') === 'missed') problem('Adherence', 'Missed doses reported', 'attention')

    var medicines = meds.map(function (m) {
      var doseValue = get(m, 'dose')
      var dose = [isPyNumber(doseValue) ? pyG(doseValue) : null, get(m, 'unit'), get(m, 'frequency')].filter(truthy).map(pyStr).join(' ') || 'dose not recorded'
      var note = null
      var position = dosePosition(m)
      if (position) note = position[0] >= position[1] ? 'at the Table 4 maximum' : 'below the Table 4 maximum of ' + pyG(position[1]) + ' mg'
      else if (T_STATINS.has(m._code)) {
        var level = statinPosition(m)[1]
        note = level ? level + ' intensity (NICE)' : null
      }
      return { name: m._label, dose: dose, class: classOf(m._code), note: note }
    })

    var monitoring = []
    function monitor(item, when, source) { monitoring.push({ item: item, when: when, source_id: source }) }
    if (yes('known_hypertension')) monitor('Blood pressure', 'Monthly until below 140/90 mmHg, then every 4-6 months', 'KENYA_HTN_STEPS')
    if (intersects(codes, union(T_ACE, T_ARB)) || rules.has('TX_HTN_START') || rules.has('TX_HTN_STEP_UP')) {
      monitor('Potassium and creatinine/eGFR', 'After starting or changing an ACE inhibitor or ARB', 'LOSARTAN_LABEL')
    }
    if (statins.length || rules.has('TX_STATIN_START')) {
      monitor('Full lipid profile and ALT/AST', '2-3 months after starting or changing a statin', 'NICE_LIPIDS_NG238')
      monitor('ALT/AST', 'At 12 months, then only if clinically indicated', 'NICE_LIPIDS_NG238')
      monitor('Full lipid profile', 'Annually, at the medication review', 'NICE_LIPIDS_NG238')
    }
    if (highRisk.length) monitor('Cardiovascular risk review', 'Every 3 months; refer if risk has not fallen after 6 months', 'KENYA_CVD_RISK')
    if (Array.from(codes).some(isInsulin) || rules.has('TX_DM_INSULIN')) monitor('Fasting glucose', 'Titrate basal insulin by 2-4 units every 3 days to 4-7 mmol/L', 'KENYA_DM_TREATMENT')
    if (rules.has('PREDIABETES')) monitor('HbA1c', 'Every 3-6 months while in the prediabetes range', 'KENYA_PREDIABETES')
    if (egfr != null && egfr < 60 && !yes('known_ckd')) monitor('eGFR and urine albumin', 'Repeat to confirm: CKD needs abnormality for more than 3 months', 'KDIGO_CKD_2024')
    if (codes.has('metformin') || rules.has('TX_DM_METFORMIN')) monitor('Kidney function and vitamin B12', 'During long-term metformin treatment', 'METFORMIN_LABEL')

    var conditions = [['known_hypertension', 'hypertension'], ['known_diabetes', 'type 2 diabetes'], ['known_ckd', 'chronic kidney disease'],
      ['known_cvd', 'cardiovascular disease'], ['known_asthma', 'asthma'], ['known_copd', 'COPD'], ['known_cancer', 'cancer']]
      .filter(function (p) { return yes(p[0]) }).map(function (p) { return p[1] })
    var person = sex === 'female' ? 'woman' : sex === 'male' ? 'man' : 'adult'
    var headline = age + '-year-old ' + person + (conditions.length ? ' with ' + join(conditions) : ' with no recorded NCD diagnosis')
      + (meds.length ? ' on ' + meds.length + ' recorded medicine' + (meds.length !== 1 ? 's' : '') : ', no medicines recorded') + '. Clinical priority: ' + assessment.urgency + '.'
    return { headline: headline, problems: problems, medicines: medicines, monitoring: monitoring }
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
      if ((sex === 'female' || sex === 'male') && age >= 30 && age <= 74 && meanSbp != null && !anyAscvd && ['current', 'former', 'never'].includes(get(data, 'tobacco_use'))) {
        if (tc != null && hdl != null) model = sex + '_lipid'
        else if (bmi != null) model = sex + '_bmi'
      }
      if (model) {
        var percent = r1(framingham(model, age, meanSbp, onBpTreatment, smoker, diabetic, tc, hdl, bmi) * 100)
        var method = 'Framingham 2008 general CVD, ' + (model.slice(-5) === 'lipid' ? 'laboratory (cholesterol)' : 'office (BMI)') + ' model'
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
    var bpTargetPending = false
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
        } else if ((hypertensive || onBpTreatment) && age < 80 && !frail && !(anyAscvd || diabetic || ckd) && risk.category == null && !['current', 'former', 'never'].includes(get(data, 'tobacco_use')) && (meanSbp >= 130 || meanDbp >= 80)) {
          bpTargetPending = true
          status = 'needs_data'
          targetText = 'Individual BP target pending cardiovascular risk assessment'
          summary = 'BP ' + bpText + ': control is provisional because cardiovascular risk is not estimable; this reading lies between the existing general and high-risk targets.'
          plan.push(item('Record tobacco status and complete cardiovascular risk assessment before judging BP control or assigning a routine review interval; confirm correctly measured readings.', 'WHO_HTN_2021', 'ISH_HTN_2020', 'ESC_HTN_2024'))
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
      } else if (statinNames.length && ldlGoal == null) {
        status = 'needs_data'
        plan.push(item('Confirm cardiovascular risk and an individual LDL goal before judging statin response; no target is established from the recorded data.', 'ESC_LIPIDS_2019'))
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
    else if (!['former', 'never'].includes(get(data, 'tobacco_use'))) gap('tobacco_use', 'Record tobacco status before calculating numeric cardiovascular risk; unknown status is not scored as non-smoking.')

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
    else if (bpTargetPending) followUp = 'Complete cardiovascular risk inputs and confirm the blood pressure target before assigning routine follow-up.'
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
    if (risk.category == null && !['current', 'former', 'never'].includes(get(data, 'tobacco_use'))) lines.push('Risk not estimated: tobacco status missing. Record tobacco status before calculating numeric cardiovascular risk; unknown status is not scored as non-smoking.')
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
