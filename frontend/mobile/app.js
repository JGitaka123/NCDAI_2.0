// NCDAI Consult: offline mobile front end for engine.js. No network, no storage.
(function () {
  'use strict'
  var Engine = self.NCDAIEngine
  var form = document.getElementById('patient-view')
  var consultView = document.getElementById('consult-view')
  var examplesBar = document.getElementById('examples')
  var tabs = { consult: document.getElementById('tab-consult'), patient: document.getElementById('tab-patient') }
  var activeExample = null, lastResult = null

  // ---- DOM helper ---------------------------------------------------------
  function h(tag, attrs) {
    var el = document.createElement(tag)
    for (var key in attrs || {}) {
      var value = attrs[key]
      if (value == null || value === false) continue
      if (key === 'class') el.className = value
      else if (key === 'text') el.textContent = value
      else if (key.slice(0, 2) === 'on') el.addEventListener(key.slice(2), value)
      else el.setAttribute(key, value === true ? '' : value)
    }
    for (var i = 2; i < arguments.length; i++) {
      var child = arguments[i]
      if (child == null || child === false) continue
      if (Array.isArray(child)) child.forEach(function (c) { if (c != null && c !== false) el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c) })
      else el.appendChild(typeof child === 'string' ? document.createTextNode(child) : child)
    }
    return el
  }
  function words(value) { return String(value).replace(/_/g, ' ') }

  // ---- form definition ----------------------------------------------------
  var SYMPTOMS = [['chest_pain', 'Chest pain'], ['breathlessness', 'Breathlessness'], ['neurological_deficit', 'New neurological deficit'], ['confusion', 'Confusion'],
    ['seizure', 'Seizure'], ['severe_headache', 'Severe headache'], ['visual_disturbance', 'Visual disturbance'], ['vomiting', 'Vomiting'], ['dehydration', 'Dehydration'],
    ['foot_ulcer', 'Foot ulcer'], ['hypoglycemia_symptoms', 'Hypoglycaemia symptoms'], ['wheeze', 'Wheeze'], ['hemoptysis', 'Coughing blood'],
    ['unexplained_weight_loss', 'Unexplained weight loss'], ['persistent_cough', 'Persistent cough'], ['breast_lump', 'Breast lump'], ['abnormal_bleeding', 'Abnormal bleeding']]
  var HISTORY = [['known_hypertension', 'Hypertension'], ['known_diabetes', 'Diabetes'], ['known_ckd', 'Chronic kidney disease'], ['known_ascvd', 'Coronary / peripheral arterial disease'],
    ['prior_stroke_tia', 'Previous stroke or TIA'], ['known_heart_failure', 'Heart failure'], ['known_atrial_fibrillation', 'Atrial fibrillation'], ['known_asthma', 'Asthma'],
    ['known_copd', 'COPD'], ['known_cancer', 'Cancer'], ['acutely_unwell', 'Acutely unwell now'], ['acute_kidney_injury', 'Acute kidney injury suspected']]
  var MEDICINES = ['Metformin', 'Gliclazide', 'Glibenclamide', 'Insulin', 'Empagliflozin', 'Dapagliflozin', 'Sitagliptin', 'Liraglutide', 'Pioglitazone', 'Amlodipine', 'Nifedipine', 'Losartan',
    'Valsartan', 'Lisinopril', 'Enalapril', 'Hydrochlorothiazide', 'Indapamide', 'Furosemide', 'Spironolactone', 'Bisoprolol', 'Carvedilol', 'Atenolol', 'Propranolol', 'Methyldopa',
    'Atorvastatin', 'Rosuvastatin', 'Simvastatin', 'Aspirin', 'Clopidogrel', 'Warfarin', 'Rivaroxaban', 'Apixaban', 'Digoxin', 'Salbutamol', 'Budesonide', 'Beclometasone',
    'Budesonide/formoterol', 'Tiotropium', 'Prednisolone', 'Ibuprofen', 'Diclofenac']
  function num(name, label, unit, min, max, step) { return { kind: 'number', name: name, label: label + (unit ? ' (' + unit + ')' : ''), min: min, max: max, step: step || 'any' } }
  function choice(name, label, options) { return { kind: 'select', name: name, label: label, options: options } }
  var CARE = [['unknown', 'Not documented'], ['within_12_months', 'Within 12 months'], ['over_12_months', 'Over 12 months'], ['never', 'Never']]
  var SECTIONS = [
    { title: 'Patient', fields: [num('age', 'Age', 'years', 18, 120, 1), choice('sex', 'Sex', [['female', 'Female'], ['male', 'Male'], ['other', 'Other'], ['unknown', 'Unknown']]),
      choice('pregnancy_status', 'Pregnancy', [['not_applicable', 'Not applicable'], ['no', 'Not pregnant'], ['yes', 'Pregnant'], ['unknown', 'Unknown']])] },
    { title: 'Vital signs', fields: [num('systolic_bp', 'Systolic BP', 'mmHg', 40, 300, 1), num('diastolic_bp', 'Diastolic BP', 'mmHg', 20, 200, 1),
      num('repeat_systolic_bp', 'Repeat systolic', 'mmHg', 40, 300, 1), num('repeat_diastolic_bp', 'Repeat diastolic', 'mmHg', 20, 200, 1), num('pulse', 'Pulse', '/min', 20, 250, 1),
      num('oxygen_saturation', 'SpO2', '%', 30, 100), num('respiratory_rate', 'Respiratory rate', '/min', 4, 80, 1), num('weight_kg', 'Weight', 'kg', 20, 350),
      num('height_cm', 'Height', 'cm', 100, 250), num('waist_cm', 'Waist', 'cm', 40, 250)] },
    { title: 'Symptoms now', symptoms: true },
    { title: 'History', history: true, fields: [choice('tobacco_use', 'Tobacco', [['unknown', 'Unknown'], ['current', 'Current'], ['former', 'Former'], ['never', 'Never']]),
      choice('adherence', 'Medicine adherence', [['unknown', 'Unknown'], ['taking', 'Taking as prescribed'], ['missed', 'Missed doses']]), choice('frailty', 'Frailty', [['unknown', 'Unknown'], ['no', 'Not frail'], ['yes', 'Frail']])] },
    { title: 'Laboratory', fields: [num('hba1c', 'HbA1c', '%', 2, 25), num('glucose', 'Glucose', 'mmol/L', 0.1, 83), choice('glucose_context', 'Glucose timing', [['unknown', 'Unknown'], ['fasting', 'Fasting'], ['random', 'Random']]),
      num('creatinine_umol', 'Creatinine', 'µmol/L', 10, 3000), num('egfr', 'eGFR (lab)', 'mL/min', 0, 200), num('urine_acr_mg_mmol', 'Urine ACR', 'mg/mmol', 0, 3000),
      num('potassium', 'Potassium', 'mmol/L', 1, 10), num('total_cholesterol_mmol', 'Total cholesterol', 'mmol/L', 1, 20), num('hdl_mmol', 'HDL', 'mmol/L', 0.2, 5),
      num('ldl_mmol', 'LDL', 'mmol/L', 0.2, 15), num('hemoglobin_g_dl', 'Haemoglobin', 'g/dL', 3, 25)], hint: 'Blank eGFR is calculated from creatinine (CKD-EPI 2021, female or male sex).' },
    { title: 'Medicines & allergies', medicines: true },
    { title: 'Disease control', fields: [num('hypoglycaemia_episodes_3m', 'Hypos in 3 months', '', 0, 100, 1), choice('eye_screen', 'Eye screening', CARE), choice('foot_exam', 'Foot exam', CARE),
      num('exacerbations_past_year', 'Asthma/COPD exacerbations, 12 months', '', 0, 50, 1), num('reliever_use_per_week', 'Reliever use per week', '', 0, 100, 1)] },
    { title: 'Assessment completed', checks: true },
  ]
  var INTEGER_FIELDS = ['age', 'hypoglycaemia_episodes_3m', 'exacerbations_past_year', 'reliever_use_per_week']
  var medicines = []

  function field(spec) {
    var input
    if (spec.kind === 'select') input = h('select', { name: spec.name, id: 'f-' + spec.name }, spec.options.map(function (o) { return h('option', { value: o[0], text: o[1] }) }))
    else input = h('input', { type: 'number', inputmode: spec.step === 1 ? 'numeric' : 'decimal', name: spec.name, id: 'f-' + spec.name, min: spec.min, max: spec.max, step: spec.step, placeholder: '—' })
    return h('label', { class: 'f', for: 'f-' + spec.name }, spec.label, input)
  }
  function tri(name, label) {
    return h('div', { class: 'tri', role: 'radiogroup', 'aria-label': label }, h('span', { text: label }),
      h('div', { class: 'seg' }, [['yes', 'Yes'], ['no', 'No'], ['unknown', '?']].map(function (o) {
        return h('label', {}, h('input', { type: 'radio', name: name, value: o[0], 'aria-label': label + ': ' + (o[0] === 'unknown' ? 'unknown' : o[1]) }), o[1])
      })))
  }
  function renderMedicines() {
    var list = document.getElementById('medlist')
    list.replaceChildren.apply(list, medicines.map(function (m, i) {
      return h('li', {}, m.name + (m.dose ? ' ' + m.dose + ' mg' : ''), h('button', { type: 'button', 'aria-label': 'Remove ' + m.name, onclick: function () { medicines.splice(i, 1); renderMedicines() }, text: '×' }))
    }))
  }
  function buildForm() {
    SECTIONS.forEach(function (section) {
      var body = []
      if (section.symptoms) body.push(h('div', { class: 'chips' }, SYMPTOMS.map(function (s) { return h('label', { class: 'chip' }, h('input', { type: 'checkbox', name: 'symptoms', value: s[0] }), s[1]) })))
      if (section.history) body.push(h('div', { class: 'grid' }, HISTORY.map(function (p) { return tri(p[0], p[1]) })))
      if (section.fields) body.push(h('div', { class: 'grid', style: section.history ? 'margin-top:12px' : null }, section.fields.map(field)))
      if (section.medicines) {
        var name = h('input', { id: 'med-name', list: 'med-options', placeholder: 'Medicine', autocomplete: 'off' })
        var dose = h('input', { id: 'med-dose', type: 'number', inputmode: 'decimal', min: 0, step: 'any', placeholder: 'mg (optional)' })
        function addMedicine() {
          var value = name.value.trim()
          if (!value) { name.focus(); return }
          medicines.push({ name: value, dose: dose.value === '' ? null : Number(dose.value) })
          name.value = ''; dose.value = ''; renderMedicines(); name.focus()
        }
        name.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addMedicine() } })
        body.push(h('div', { class: 'grid' }, h('label', { class: 'f', for: 'med-name' }, 'Current medicine', name), h('label', { class: 'f', for: 'med-dose' }, 'Dose', dose)),
          h('datalist', { id: 'med-options' }, MEDICINES.map(function (m) { return h('option', { value: m }) })),
          h('div', { class: 'row', style: 'margin-top:8px' }, h('button', { type: 'button', class: 'ghost', onclick: addMedicine, text: 'Add medicine' })),
          h('ul', { class: 'medlist', id: 'medlist', 'aria-label': 'Current medicines' }),
          h('label', { class: 'f', for: 'f-allergies', style: 'margin-top:12px' }, 'Allergies and reactions (one per line)', h('textarea', { id: 'f-allergies', name: 'allergies', rows: 2, placeholder: 'e.g. enalapril - angioedema' })))
      }
      if (section.checks) body.push(h('div', { style: 'display:grid;gap:10px' },
        [['measured_now', 'Measurements were taken today'], ['medications_reviewed', 'Medicine list reconciled'], ['allergies_reviewed', 'Allergies reviewed'], ['symptoms_reviewed', 'Symptoms reviewed']]
          .map(function (c) { return h('label', { class: 'toggle' }, h('input', { type: 'checkbox', name: c[0] }), c[1]) })))
      if (section.hint) body.push(h('p', { class: 'hint', text: section.hint }))
      form.appendChild(h('fieldset', {}, h('legend', { text: section.title }), body))
    })
  }

  // ---- read and fill ------------------------------------------------------
  function read() {
    var data = { glucose_unit: 'mmol/L', dosing_context: {} }, age = null, sex = 'unknown'
    SECTIONS.forEach(function (section) {
      (section.fields || []).forEach(function (spec) {
        var el = form.elements[spec.name], value = el.value
        if (spec.kind === 'number') {
          if (value === '') return
          value = Number(value)
          if (INTEGER_FIELDS.indexOf(spec.name) >= 0) value = Math.trunc(value)
        }
        if (spec.name === 'age') age = value
        else if (spec.name === 'sex') sex = value
        else if (spec.name === 'frailty') data.dosing_context.frailty = value
        else data[spec.name] = value
      })
    })
    HISTORY.forEach(function (p) { var checked = form.querySelector('input[name="' + p[0] + '"]:checked'); data[p[0]] = checked ? checked.value : 'unknown' })
    data.symptoms = Array.prototype.map.call(form.querySelectorAll('input[name="symptoms"]:checked'), function (el) { return el.value })
    data.medications = medicines.map(function (m) { var code = m.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''); return Object.assign({ code: code, name: m.name }, m.dose != null ? { dose: m.dose, unit: 'mg' } : {}) })
    data.allergies = form.elements.allergies.value.split('\n').map(function (a) { return a.trim() }).filter(Boolean)
    ;['medications_reviewed', 'allergies_reviewed', 'symptoms_reviewed'].forEach(function (k) { data[k] = form.elements[k].checked })
    data.observed_at = form.elements.measured_now.checked ? new Date().toISOString() : null
    return { data: data, age: age, sex: sex }
  }
  function fill(example) {
    form.reset(); medicines = []
    var values = example ? example.values : {}
    SECTIONS.forEach(function (section) {
      (section.fields || []).forEach(function (spec) {
        var el = form.elements[spec.name], value = spec.name === 'frailty' ? (values.dosing_context || {}).frailty : values[spec.name]
        if (value != null) el.value = String(value)
        else if (spec.kind === 'select') el.value = spec.options[0][0]
      })
    })
    HISTORY.forEach(function (p) { var input = form.querySelector('input[name="' + p[0] + '"][value="' + (values[p[0]] || 'unknown') + '"]'); if (input) input.checked = true })
    ;(values.symptoms || []).forEach(function (s) { var el = form.querySelector('input[name="symptoms"][value="' + s + '"]'); if (el) el.checked = true })
    medicines = (values.medications || []).map(function (m) { return { name: m.name, dose: m.dose != null ? m.dose : null } })
    renderMedicines()
    form.elements.allergies.value = (values.allergies || []).join('\n')
    ;['medications_reviewed', 'allergies_reviewed', 'symptoms_reviewed', 'measured_now'].forEach(function (k) { form.elements[k].checked = example ? values[k] !== false : false })
  }

  // ---- examples (clearly marked, fictional) --------------------------------
  function meds() { return Array.prototype.map.call(arguments, function (m) { return typeof m === 'string' ? { name: m } : m }) }
  var EXAMPLES = [
    { id: 'cardiometabolic', label: 'Diabetes, hypertension, CKD', values: { age: 58, sex: 'male', pregnancy_status: 'not_applicable', systolic_bp: 162, diastolic_bp: 98, repeat_systolic_bp: 158, repeat_diastolic_bp: 96, pulse: 78,
      weight_kg: 92, height_cm: 172, hba1c: 9.2, creatinine_umol: 130, urine_acr_mg_mmol: 12, potassium: 4.3, total_cholesterol_mmol: 5.6, hdl_mmol: 1.0, ldl_mmol: 3.4,
      known_hypertension: 'yes', known_diabetes: 'yes', known_ckd: 'unknown', known_ascvd: 'no', prior_stroke_tia: 'no', known_heart_failure: 'no', known_atrial_fibrillation: 'no', known_asthma: 'no', known_copd: 'no', known_cancer: 'no', acutely_unwell: 'no', acute_kidney_injury: 'no',
      tobacco_use: 'current', adherence: 'taking', eye_screen: 'never', medications: meds({ name: 'Amlodipine', dose: 5 }, { name: 'Metformin', dose: 1000 }, 'Ibuprofen') } },
    { id: 'af', label: 'AF with heart failure', values: { age: 76, sex: 'female', pregnancy_status: 'not_applicable', systolic_bp: 138, diastolic_bp: 84, pulse: 118, egfr: 48, potassium: 4.6,
      known_hypertension: 'yes', known_diabetes: 'no', known_heart_failure: 'yes', known_atrial_fibrillation: 'yes', prior_stroke_tia: 'no', known_ascvd: 'no', known_ckd: 'unknown', known_asthma: 'no', known_copd: 'no', known_cancer: 'no', acutely_unwell: 'no', acute_kidney_injury: 'no',
      tobacco_use: 'never', adherence: 'taking', medications: meds('Enalapril', 'Furosemide', 'Aspirin', 'Diclofenac') } },
    { id: 'asthma', label: 'Asthma on reliever only', values: { age: 34, sex: 'female', pregnancy_status: 'no', systolic_bp: 118, diastolic_bp: 72, pulse: 96, oxygen_saturation: 95, respiratory_rate: 20,
      known_asthma: 'yes', known_hypertension: 'no', known_diabetes: 'no', known_copd: 'no', known_ckd: 'no', known_cancer: 'no', acutely_unwell: 'no', acute_kidney_injury: 'no', reliever_use_per_week: 5, exacerbations_past_year: 1,
      tobacco_use: 'never', adherence: 'taking', medications: meds('Salbutamol', 'Propranolol') } },
    { id: 'young_htn', label: 'Hypertension at 32, low potassium', values: { age: 32, sex: 'male', pregnancy_status: 'not_applicable', systolic_bp: 168, diastolic_bp: 104, repeat_systolic_bp: 164, repeat_diastolic_bp: 102, potassium: 3.1,
      weight_kg: 70, height_cm: 175, known_hypertension: 'no', known_diabetes: 'no', known_asthma: 'no', known_copd: 'no', known_ckd: 'no', known_cancer: 'no', acutely_unwell: 'no', acute_kidney_injury: 'no', tobacco_use: 'never', adherence: 'unknown' } },
  ]

  // ---- render consult -----------------------------------------------------
  function sources(ids, registry) {
    return ids.length ? h('span', { class: 'src' }, ids.map(function (id) { var s = registry[id]; return h('a', { href: s ? s.url : '#', target: '_blank', rel: 'noopener noreferrer', title: s ? s.title : id, text: id.replace(/_/g, ' ') }) })) : null
  }
  function tone(status) { return status === 'acute' ? 't-crit' : ['uncontrolled', 'untreated', 'above_target', 'high_risk', 'review'].indexOf(status) >= 0 ? 't-warn' : ['at_target', 'established'].indexOf(status) >= 0 ? 't-good' : 't-info' }
  function renderConsult(result) {
    var c = result.consultant, registry = {}
    c.sources.forEach(function (s) { registry[s.source_id] = s })
    var urgentTitle = { emergency: 'Emergency: act now', urgent: 'Same-day assessment', soon: 'Review soon', routine: 'Routine review' }[result.urgency]
    var important = result.recommendations.filter(function (r) { return r.severity !== 'info' && r.rule_id !== 'DATA_COMPLETENESS' })
    var nodes = []
    if (activeExample) nodes.push(h('p', { class: 'notice example', text: 'Example patient (fictional): ' + activeExample.label + '. Tap Patient data to edit, or New patient to start your own.' }))
    nodes.push(h('div', { class: 'card triage u-' + result.urgency },
      h('div', { class: 'row' }, h('span', { class: 'pill p-' + result.urgency, text: result.urgency }), h('span', { class: 'eyebrow', text: 'Safety triage' })),
      h('h2', { text: urgentTitle }), h('p', { style: 'margin:0;font-size:14px', text: result.summary }),
      important.length ? (function () {
        var list = h('ul', { class: 'findings' }, important.map(function (r) { return h('li', {}, h('strong', {}, r.title + ' ', h('span', { class: 'pill p-' + r.severity, text: r.severity })), h('p', { text: r.detail })) }))
        return result.urgency === 'emergency' || result.urgency === 'urgent' ? list : h('details', {}, h('summary', { text: 'Safety findings (' + important.length + ')' }), list)
      })() : null,
      result.missing_data.length ? h('details', {}, h('summary', { text: 'Information still needed (' + result.missing_data.length + ')' }), h('ul', { class: 'plain' }, result.missing_data.map(function (m) { return h('li', { text: words(m) }) }))) : null))
    nodes.push(h('div', { class: 'card lead' }, h('span', { class: 'eyebrow', text: 'Consultant synthesis' }), h('h2', { text: c.one_liner }), h('p', { class: c.acute_first ? 'acute' : null, text: c.impression })))
    if (c.derived.length) nodes.push(h('div', { class: 'tiles' }, c.derived.map(function (d) { return h('div', { class: 'tile', title: d.method }, h('span', { text: d.label }), h('strong', {}, d.value, d.unit ? h('small', { text: ' ' + d.unit }) : null), h('em', { text: d.interpretation })) })))
    c.problems.forEach(function (p) {
      nodes.push(h('article', { class: 'card problem ' + tone(p.status) },
        h('div', { class: 'problem-head' }, h('span', { class: 'rank', text: String(p.rank) }), h('h3', { text: p.title }), h('span', { class: 'pill p-' + p.status, text: words(p.status) })),
        p.facts.length ? h('ul', { class: 'facts' }, p.facts.map(function (f) { return h('li', { text: f }) })) : null,
        p.assessment ? h('p', { class: 'assessment', text: p.assessment }) : null,
        p.targets.map(function (t) { return h('p', { class: 'target' }, h('b', { text: 'Target' }), t) }),
        p.plan.length ? h('ol', { class: 'plan' }, p.plan.map(function (s) { return h('li', {}, s.text, sources(s.source_ids, registry)) })) : null))
    })
    if (c.medication_review.length) nodes.push(h('div', { class: 'card' }, h('h3', { class: 'section-title', text: 'Medication review' }),
      h('ul', { class: 'review' }, c.medication_review.map(function (m) { return h('li', {}, h('span', { class: 'pill p-' + m.severity, text: m.severity }), h('div', {}, h('strong', { text: m.finding }), m.action, sources(m.source_ids, registry))) }))))
    if (c.considerations.length) nodes.push(h('div', { class: 'card' }, h('h3', { class: 'section-title', text: 'Diagnostic considerations' }),
      h('ul', { class: 'plain' }, c.considerations.map(function (x) { return h('li', {}, x.text, sources(x.source_ids, registry)) }))))
    if (c.monitoring.length) nodes.push(h('div', { class: 'card' }, h('h3', { class: 'section-title', text: 'Monitoring' }),
      h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', { text: 'Test' }), h('th', { text: 'When' }))),
        h('tbody', {}, c.monitoring.map(function (m) { return h('tr', {}, h('td', { text: m.test }), h('td', { text: m.timing })) }))))))
    var copyStatus = h('span', { class: 'hint', role: 'status' })
    var pre = h('pre', { text: c.summary_text })
    nodes.push(h('div', { class: 'card' }, h('h3', { class: 'section-title', text: 'Follow-up' }), h('p', { style: 'margin:0;font-weight:650', text: c.follow_up }),
      c.data_gaps.length ? h('div', {}, h('p', { class: 'hint', text: 'Would sharpen this consult:' }), h('ul', { class: 'plain' }, c.data_gaps.map(function (g) { return h('li', {}, h('strong', { text: words(g.field).replace(/ mmol| mg mmol| umol/g, '') }), ': ' + g.why) }))) : null,
      h('div', { class: 'row', style: 'margin-top:12px' }, h('button', { type: 'button', class: 'ghost', text: 'Copy summary for notes', onclick: function () {
        var done = function (ok) { copyStatus.textContent = ok ? 'Copied. Paste it into the notes or a referral.' : 'Copy was blocked. Select the text in the summary below.'; if (!ok) { details.open = true; var range = document.createRange(); range.selectNodeContents(pre); var sel = getSelection(); sel.removeAllRanges(); sel.addRange(range) } }
        try { navigator.clipboard.writeText(c.summary_text).then(function () { done(true) }, function () { done(false) }) } catch (e) { done(false) }
      } }), copyStatus)))
    var details = h('details', { class: 'card' }, h('summary', { text: 'Plain-text summary' }), pre)
    nodes.push(details)
    nodes.push(h('details', { class: 'card' }, h('summary', { text: 'Guidelines cited (' + c.sources.length + ')' }),
      h('ul', { class: 'plain', style: 'margin-top:8px' }, c.sources.map(function (s) { return h('li', {}, h('a', { href: s.url, target: '_blank', rel: 'noopener noreferrer', text: s.title }), h('div', { class: 'hint', text: s.section })) }))))
    nodes.push(h('p', { class: 'boundary', text: c.boundary }))
    consultView.replaceChildren.apply(consultView, nodes)
  }
  function renderError(message) {
    consultView.replaceChildren(h('p', { class: 'notice error', text: 'Could not generate the consult: ' + message + ' Check the patient data and try again.' }))
  }
  function renderEmpty() {
    consultView.replaceChildren(h('div', { class: 'card' }, h('span', { class: 'eyebrow', text: 'New patient' }), h('h2', { style: 'margin:6px 0', text: 'Enter findings, then generate the consult.' }),
      h('p', { class: 'hint', text: 'Open Patient data. Age and sex are required; everything else is optional, and blanks stay unknown rather than normal.' })))
  }

  // ---- behaviour ----------------------------------------------------------
  function show(tab) {
    var consult = tab === 'consult'
    tabs.consult.setAttribute('aria-selected', String(consult)); tabs.patient.setAttribute('aria-selected', String(!consult))
    consultView.hidden = !consult; form.hidden = consult
    window.scrollTo({ top: 0 })
  }
  function generate() {
    var input = read()
    if (!Number.isInteger(input.age)) { show('patient'); form.elements.age.focus(); renderError('Age is required.'); return }
    try { lastResult = Engine.assess(input.data, input.age, input.sex); renderConsult(lastResult) } catch (error) { renderError(error.message) }
    show('consult')
  }
  function loadExample(example) {
    activeExample = example
    Array.prototype.forEach.call(examplesBar.querySelectorAll('button'), function (b) { b.setAttribute('aria-pressed', String(b.dataset.id === example.id)) })
    fill(example); generate()
  }
  buildForm()
  EXAMPLES.forEach(function (example) { examplesBar.appendChild(h('button', { type: 'button', 'data-id': example.id, 'aria-pressed': 'false', text: example.label, onclick: function () { loadExample(example) } })) })
  examplesBar.insertBefore(h('span', { class: 'eyebrow', style: 'align-self:center;flex:0 0 auto', text: 'Examples' }), examplesBar.firstChild)
  tabs.consult.addEventListener('click', function () { show('consult') })
  tabs.patient.addEventListener('click', function () { show('patient') })
  document.getElementById('generate').addEventListener('click', generate)
  form.addEventListener('input', function () { if (activeExample) { activeExample = null; Array.prototype.forEach.call(examplesBar.querySelectorAll('button'), function (b) { b.setAttribute('aria-pressed', 'false') }) } })
  document.getElementById('new-patient').addEventListener('click', function () {
    activeExample = null; lastResult = null; fill(null)
    Array.prototype.forEach.call(examplesBar.querySelectorAll('button'), function (b) { b.setAttribute('aria-pressed', 'false') })
    renderEmpty(); show('patient'); form.elements.age.focus()
  })
  document.getElementById('versions').textContent = Engine.RULESET_VERSION + ' · ' + Engine.REASONING_VERSION + ' · evidence ' + Engine.EVIDENCE_VERSION
  loadExample(EXAMPLES[0])
})()
