import { useEffect, useMemo, useState } from 'react'
import { BookOpen, CheckCircle2, ChevronDown, ClipboardCopy, ExternalLink, Pill, ShieldAlert, Sparkles } from 'lucide-react'
import { api, message } from './api'
import { formatDate, reviewErrors, safeEvidenceUrl, titleCase } from './clinical'
import { Badge, Field, Notice } from './components'
import type { CarePlan, Decision, DecisionAction, Encounter, Evidence, Recommendation } from './types'
import DosingResults from './DosingResults'
import ConsultantSynthesis from './ConsultantSynthesis'

const QUICK_REASONS: Record<Exclude<DecisionAction, 'accept'>, string[]> = {
  modify: ['Adjusted to this patient’s context', 'Different medicine or dose chosen', 'Timing changed'],
  defer: ['Review at next visit', 'Awaiting results', 'Medicine not available', 'Needs physician review'],
  reject: ['Already addressed', 'Not appropriate for this patient', 'Contraindicated or not tolerated', 'Patient declined'],
}
const GROUPS: { key: string; title: string; hint: string; match: (r: Recommendation) => boolean }[] = [
  { key: 'critical', title: 'Act now', hint: 'Critical findings. Decide on each individually.', match: r => r.severity === 'critical' },
  { key: 'treatment', title: 'Treatment options', hint: 'Medicine options for this patient: blood pressure and diabetes steps and doses from the Kenya MOH protocol, statins from NICE NG238. Their targets can differ from the international targets in the consultant synthesis above; the prescriber decides.', match: r => r.category === 'treatment' || r.category === 'dosing' },
  { key: 'review', title: 'Review', hint: 'Findings to confirm or follow up.', match: r => r.severity === 'warning' },
  { key: 'info', title: 'For information', hint: 'Routine reminders and follow-up.', match: () => true },
]

export default function AssessmentReview({ encounter, onReviewed, onUpdated, onConflict }: { encounter: Encounter; onReviewed: (encounter: Encounter) => void; onUpdated: (encounter: Encounter) => void; onConflict: () => void }) {
  const [decisions, setDecisions] = useState<Record<string, Partial<Decision>>>({}), [note, setNote] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const assessment = encounter.assessment!
  const reviewed = encounter.status === 'reviewed'
  const decisionCount = assessment.recommendations.filter(r => decisions[r.id]?.action).length
  const [aiBusy, setAiBusy] = useState(false), [aiError, setAiError] = useState('')
  // One numbered reference list for the whole assessment; cards cite these numbers.
  const references = useMemo(() => {
    const list: Evidence[] = []
    for (const source of assessment.recommendations.flatMap(r => r.evidence)) if (!list.some(item => item.source_id === source.source_id)) list.push(source)
    return list
  }, [assessment])
  const grouped = useMemo(() => {
    const used = new Set<string>()
    return GROUPS.map(group => ({ ...group, items: assessment.recommendations.filter(r => !used.has(r.id) && group.match(r) && used.add(r.id)) })).filter(group => group.items.length)
  }, [assessment])
  const bulkIds = assessment.recommendations.filter(r => r.severity !== 'critical' && !decisions[r.id]?.action).map(r => r.id)
  async function prepareBriefing() {
    setAiBusy(true); setAiError('')
    try { onUpdated(await api<Encounter>(`/encounters/${encounter.id}/ai-briefing`, { method: 'POST', body: { expected_version: encounter.version, assessment_id: assessment.id } })) }
    catch (error) { setAiError(message(error)); if (error instanceof Error && 'status' in error && error.status === 409) onConflict() }
    finally { setAiBusy(false) }
  }
  function change(id: string, patch: Partial<Decision>) { setError(''); setDecisions(current => ({ ...current, [id]: { ...current[id], ...patch, recommendation_id: id } })) }
  function acceptRemaining() { setError(''); setDecisions(current => ({ ...current, ...Object.fromEntries(bulkIds.map(id => [id, { recommendation_id: id, action: 'accept' as const }])) })) }
  async function submit() {
    const errors = reviewErrors(assessment.recommendations, decisions)
    if (errors.length) { setError(errors.join(' ')); return }
    setError(''); setBusy(true)
    try {
      onReviewed(await api<Encounter>(`/encounters/${encounter.id}/review`, { method: 'POST', body: { assessment_id: assessment.id, expected_version: encounter.version, decisions: assessment.recommendations.map(r => {
        const item = decisions[r.id]
        return { recommendation_id: r.id, action: item.action, ...(item.action !== 'accept' ? { reason: item.reason?.trim() } : {}), ...(item.action === 'modify' ? { modified_text: item.modified_text?.trim() } : {}) }
      }), note: note.trim() || undefined } }))
    } catch (error) { setError(message(error)); if (error instanceof Error && 'status' in error && error.status === 409) onConflict() } finally { setBusy(false) }
  }
  let index = 0
  return <div className="assessment-content">
    <div className={`assessment-summary urgency-${assessment.urgency}`}>
      <div className="assessment-summary-icon">{['emergency', 'urgent'].includes(assessment.urgency) ? <ShieldAlert size={27} /> : <BookOpen size={26} />}</div>
      <div><div className="assessment-summary-top"><span className="eyebrow">CLINICAL PRIORITY</span><Badge value={assessment.urgency} /></div><h2>{assessment.urgency === 'emergency' ? 'Emergency findings require immediate clinical attention' : assessment.urgency === 'urgent' ? 'Urgent clinical review is indicated' : 'Decision support for this encounter'}</h2><p>{assessment.summary}</p>{assessment.urgency === 'emergency' && <strong className="emergency-reminder">Do not delay emergency care to complete this review.</strong>}{['emergency', 'urgent'].includes(assessment.urgency) && <p className="field-note">Routine treatment options are withheld until the urgent findings are addressed.</p>}</div>
    </div>
    <div className="assessment-meta"><span><BookOpen size={15} /> Evidence {assessment.evidence_version}</span><span>{formatDate(assessment.generated_at, true)}</span><span>Saved input version {encounter.version}</span>{assessment.derived?.bmi != null && <span>BMI {assessment.derived.bmi} kg/m² ({assessment.derived.bmi_category})</span>}</div>
    {assessment.care_plan && <PatientSummary plan={assessment.care_plan} />}
    {assessment.consultant && <ConsultantSynthesis synthesis={assessment.consultant} />}
    {assessment.missing_data.length > 0 && <details className="missing-data" open><summary>Information still needed <span className="count-pill">{assessment.missing_data.length}</span></summary><ul>{assessment.missing_data.map((item, i) => <li key={i}>{titleCase(item)}</li>)}</ul><p>Add these on the Clinical intake tab and assess again for more specific recommendations.</p></details>}
    {reviewed && <Notice tone="success"><strong>Clinician review recorded.</strong> This encounter is immutable. Create a new encounter to document a subsequent assessment.{encounter.review?.reviewed_at && <> Recorded {formatDate(encounter.review.reviewed_at, true)}{encounter.review.reviewer_name ? ` by ${encounter.review.reviewer_name}` : ''}.</>}</Notice>}
    <details className="ai-briefing-details" open={!!assessment.ai_briefing}><summary><Sparkles size={16} /> AI-assisted review focus <span className="summary-hint">{assessment.ai_briefing ? titleCase(assessment.ai_briefing.status) : 'Optional'}</span></summary>
      <div className="ai-briefing"><div className="ai-status"><Sparkles size={19} /><div><strong>{titleCase(assessment.model_info.mode)} · {titleCase(assessment.model_info.status)}</strong><p>{assessment.model_info.model ? `${assessment.model_info.provider ?? 'Configured provider'} / ${assessment.model_info.model}` : 'No generative model is supplying recommendations in this assessment.'} Clinical rules remain subject to clinician review.</p></div></div><div className="subsection-heading"><div><p>Optional: organize the existing evidence-linked recommendations for review.</p></div>{!reviewed && <button className="button button-secondary button-small" disabled={busy || aiBusy} onClick={prepareBriefing}><Sparkles size={15} />{aiBusy ? 'Preparing briefing…' : 'Prepare AI briefing'}</button>}</div>{aiBusy && <p className="field-note" role="status">Preparing a bounded briefing. The clinical safety recommendations below remain available.</p>}{aiError && <Notice tone="error">{aiError} Your original safety recommendations remain available.</Notice>}{assessment.ai_briefing ? <><div className="assessment-meta"><Badge value={assessment.ai_briefing.status} /><span>{assessment.ai_briefing.provider} {assessment.ai_briefing.model}</span><span>{assessment.ai_briefing.prompt_version}</span></div>{assessment.ai_briefing.status === 'ready' ? <><p className="field-note">This focus uses existing recommendations; it does not replace your review of the complete assessment below.</p><ul className="ai-focus-list">{assessment.ai_briefing.focus?.map(item => <li key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></li>)}</ul>{!!assessment.ai_briefing.checklist?.length && <details><summary>Information checklist</summary><ul>{assessment.ai_briefing.checklist.map((item, i) => <li key={i}>{titleCase(item)}</li>)}</ul></details>}</> : <Notice tone="warning">AI briefing {assessment.ai_briefing.status}. {titleCase(assessment.ai_briefing.reason_code ?? 'No briefing was returned')}. Continue with the rule-based assessment below.</Notice>}</> : <p className="field-note">No AI briefing requested. When configured, the provider receives only a minimized set of rule references and checks for this encounter; names and free-text notes are excluded.</p>}</div>
    </details>
    <DosingResults dosing={assessment.dosing} />
    <div className="recommendations-header"><div><h2>{assessment.recommendations.length} recommendation{assessment.recommendations.length === 1 ? '' : 's'} to review</h2>{!reviewed && <span>{decisionCount} of {assessment.recommendations.length} decided</span>}</div>{!reviewed && bulkIds.length > 0 && <button type="button" className="button button-secondary button-small" disabled={busy} onClick={acceptRemaining}><CheckCircle2 size={15} />Accept remaining non-critical ({bulkIds.length})</button>}</div>
    {!reviewed && <div className="review-progress" aria-hidden="true"><span style={{ width: `${assessment.recommendations.length ? decisionCount / assessment.recommendations.length * 100 : 0}%` }} /></div>}
    {!reviewed && <p className="field-note">Accept, or choose modify, defer or reject with a reason. Quick reasons can be tapped. Critical items are never bulk-accepted, and you can change any decision until you record the review.</p>}
    {grouped.map(group => <section key={group.key} className={`recommendation-group group-${group.key}`} aria-labelledby={`group-${group.key}`}>
      <div className="recommendation-group-heading">{group.key === 'treatment' ? <Pill size={17} /> : group.key === 'critical' ? <ShieldAlert size={17} /> : <BookOpen size={17} />}<h3 id={`group-${group.key}`}>{group.title} <span className="count-pill">{group.items.length}</span></h3><small>{group.hint}</small></div>
      {group.items.map(recommendation => { const number = ++index; return <RecommendationCard key={recommendation.id} recommendation={recommendation} index={number} references={references} decision={reviewed ? encounter.review?.decisions.find(d => d.recommendation_id === recommendation.id) : decisions[recommendation.id]} reviewed={reviewed} readOnly={reviewed || busy} onChange={patch => change(recommendation.id, patch)} /> })}
    </section>)}
    {references.length > 0 && <details className="reference-list" id="assessment-references"><summary><BookOpen size={15} /> References used in this assessment <span className="count-pill">{references.length}</span></summary><ol>{references.map((source, i) => <li key={source.source_id} id={`ref-${i + 1}`}><SourceLink source={source} /><p>{source.section}</p><small>Version {source.version} · {source.source_id}</small></li>)}</ol></details>}
    {assessment.warnings.length > 0 && <details className="limitations"><summary>Checks and limitations ({assessment.warnings.length})</summary><ul>{assessment.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></details>}
    {!reviewed && <div className="review-footer"><Field label="Overall review note (optional)"><textarea rows={3} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} placeholder="Clinical context, follow-up plan or considerations for the next visit…" disabled={busy || aiBusy} /></Field><p>Saving records your decisions against this assessment and its inputs{assessment.consultant ? ", including the consultant synthesis" : ""}. Accepting a recommendation does not certify its clinical appropriateness. Each action remains your clinical decision.</p>{error && <Notice tone="error">{error}</Notice>}<div className="review-footer-actions"><span>{decisionCount} of {assessment.recommendations.length} decided</span><button className="button button-primary" type="button" disabled={busy || aiBusy} onClick={submit}><CheckCircle2 size={18} />{busy ? 'Recording review…' : 'Record review & lock encounter'}</button></div></div>}
    {reviewed && encounter.review?.note && <div className="recorded-note"><h3>Clinician review note</h3><p>{encounter.review.note}</p></div>}
  </div>
}

const TONE_LABEL = { ok: 'On target', attention: 'Needs action', urgent: 'Urgent', unknown: 'Not assessed' }
export function planText(plan: CarePlan): string {
  return [plan.headline, '', 'Problems:', ...plan.problems.map(p => `- ${p.name}: ${p.status}`), '', 'Medicines:', ...(plan.medicines.length ? plan.medicines.map(m => `- ${m.name} ${m.dose}${m.note ? ` (${m.note})` : ''}`) : ['- None recorded']), '', 'Monitoring:', ...plan.monitoring.map(m => `- ${m.item}: ${m.when}`)].join('\n')
}
function PatientSummary({ plan }: { plan: CarePlan }) {
  const [copied, setCopied] = useState('')
  async function copy() { try { await navigator.clipboard.writeText(planText(plan)); setCopied('Summary copied for the patient file.') } catch { setCopied('Copy is unavailable in this browser; select the text instead.') } }
  return <section className="patient-summary" aria-labelledby="patient-summary-heading">
    <div className="patient-summary-head"><div><span className="eyebrow">PATIENT SUMMARY</span><h2 id="patient-summary-heading">{plan.headline}</h2></div><button type="button" className="button button-secondary button-small" onClick={copy}><ClipboardCopy size={15} />Copy summary</button></div>
    {copied && <p className="field-note" role="status">{copied}</p>}
    {plan.problems.length > 0 && <table className="problem-table"><caption className="sr-only">Problems and status against target</caption><thead><tr><th scope="col">Problem</th><th scope="col">Status for this patient</th><th scope="col">State</th></tr></thead><tbody>{plan.problems.map(problem => <tr key={problem.name}><th scope="row">{problem.name}</th><td>{problem.status}</td><td><span className={`tone tone-${problem.tone}`}>{TONE_LABEL[problem.tone]}</span></td></tr>)}</tbody></table>}
    <div className="summary-columns">
      <div><h3>Current medicines</h3>{plan.medicines.length ? <ul className="summary-list">{plan.medicines.map((medicine, i) => <li key={`${medicine.name}-${i}`}><strong>{medicine.name}</strong> {medicine.dose}<small>{medicine.class}{medicine.note ? ` · ${medicine.note}` : ''}</small></li>)}</ul> : <p className="field-note">No medicines recorded.</p>}</div>
      <div><h3>Monitoring plan</h3>{plan.monitoring.length ? <ul className="summary-list">{plan.monitoring.map(item => <li key={`${item.item}-${item.when}`}><strong>{item.item}</strong> {item.when}</li>)}</ul> : <p className="field-note">No scheduled monitoring from the recorded conditions.</p>}</div>
    </div>
    <p className="field-note">Restates this patient’s recorded values against their targets. Decisions are made on the recommendations below.</p>
  </section>
}

export function sourceLabel(source: Evidence): string {
  const page = /printed pages? ([\d-]+)/.exec(source.section)?.[1]
  const table = /^(Table \d+|\d+(\.\d+)? [^,;(]+)/.exec(source.section)?.[1]
  if (source.source_id.startsWith('KENYA')) return ['Kenya MOH NCD Protocols', table, page && `p. ${page}`].filter(Boolean).join(', ')
  return source.title.replace(/ prescribing information$/, ' label')
}
function SourceLink({ source }: { source: Evidence }) {
  const url = safeEvidenceUrl(source.url)
  return url ? <a href={url} target="_blank" rel="noreferrer noopener" title={`${source.title} · ${source.section}`}>{sourceLabel(source)}<ExternalLink size={12} aria-hidden="true" /></a> : <span title={source.section}>{sourceLabel(source)}</span>
}

function RecommendationCard({ recommendation, index, references, decision, reviewed, readOnly, onChange }: { recommendation: Recommendation; index: number; references: Evidence[]; decision?: Partial<Decision>; reviewed: boolean; readOnly: boolean; onChange: (decision: Partial<Decision>) => void }) {
  const actions: { value: DecisionAction; label: string }[] = [{ value: 'accept', label: 'Accept' }, { value: 'modify', label: 'Modify' }, { value: 'defer', label: 'Defer' }, { value: 'reject', label: 'Reject' }]
  const decidedComplete = !reviewed && decision?.action && (decision.action === 'accept' || (decision.reason?.trim() && (decision.action !== 'modify' || decision.modified_text?.trim())))
  const [expanded, setExpanded] = useState(true)
  useEffect(() => { if (decision?.action === 'accept') setExpanded(false) }, [decision?.action])
  const collapsed = !!decidedComplete && !expanded
  return <article className={`recommendation recommendation-${recommendation.severity} ${collapsed ? 'recommendation-collapsed' : ''}`}>
    <div className="recommendation-top"><span className="recommendation-number">{String(index).padStart(2, '0')}</span><div><div className="recommendation-category">{titleCase(recommendation.category)} <Badge value={recommendation.severity} />{decision?.action && <span className={`decision-chip decision-${decision.action}`}>{titleCase(decision.action)}</span>}</div><h3>{recommendation.title}</h3></div>{decidedComplete && <button type="button" className="icon-button" aria-expanded={!collapsed} aria-label={`${collapsed ? 'Show' : 'Hide'} details for recommendation ${index}`} onClick={() => setExpanded(value => !value)}><ChevronDown size={18} className={collapsed ? '' : 'rotate-180'} /></button>}</div>
    {!!recommendation.basis?.length && !collapsed && <div className="recommendation-basis"><span>Based on</span>{recommendation.basis.map(item => <em key={item}>{item}</em>)}</div>}
    {!collapsed && <p className="recommendation-detail">{recommendation.detail}</p>}
    {recommendation.evidence.length > 0 && !collapsed && <div className="recommendation-sources"><span>Source{recommendation.evidence.length === 1 ? '' : 's'}</span>{recommendation.evidence.map(source => <span key={source.source_id} className="source-chip"><a className="source-number" href={`#ref-${references.findIndex(item => item.source_id === source.source_id) + 1}`} onClick={() => { const list = document.getElementById('assessment-references'); if (list instanceof HTMLDetailsElement) list.open = true }} aria-label={`Reference ${references.findIndex(item => item.source_id === source.source_id) + 1}`}>{references.findIndex(item => item.source_id === source.source_id) + 1}</a><SourceLink source={source} /></span>)}<small className="mono">Rule {recommendation.rule_id}</small></div>}
    <div className="recommendation-decision"><fieldset disabled={readOnly}><legend>Your decision for recommendation {index}</legend><div className="decision-options">{actions.map(action => <label key={action.value} className={decision?.action === action.value ? 'decision-selected' : ''}><input type="radio" name={`decision-${recommendation.id}`} value={action.value} checked={decision?.action === action.value} onChange={() => onChange({ action: action.value })} /><span>{action.label}</span></label>)}</div>
        {decision?.action && decision.action !== 'accept' && <>{!readOnly && <div className="quick-reasons" aria-label="Quick reasons">{QUICK_REASONS[decision.action].map(reason => <button type="button" key={reason} className={decision.reason === reason ? 'selected' : ''} onClick={() => onChange({ reason })}>{reason}</button>)}</div>}<Field label={`Reason for ${decision.action === 'modify' ? 'modification' : decision.action === 'defer' ? 'deferral' : 'rejection'} (required)`}><textarea rows={2} maxLength={2000} value={decision.reason ?? ''} onChange={e => onChange({ reason: e.target.value })} required /></Field></>}
        {decision?.action === 'modify' && <Field label="Modified clinical action (required)"><textarea rows={2} maxLength={3000} value={decision.modified_text ?? ''} onChange={e => onChange({ modified_text: e.target.value })} required /></Field>}</fieldset>{readOnly && !decision && <p className="muted">Review recorded. Decision details were not included in this response.</p>}</div>
  </article>
}
