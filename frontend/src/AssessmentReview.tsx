import { useState } from 'react'
import { BookOpen, CheckCircle2, ChevronRight, ExternalLink, ShieldAlert, Sparkles } from 'lucide-react'
import { api, message } from './api'
import { formatDate, reviewErrors, safeEvidenceUrl, titleCase } from './clinical'
import { Badge, Field, Notice } from './components'
import type { Decision, DecisionAction, Encounter, Recommendation } from './types'
import DosingResults from './DosingResults'

export default function AssessmentReview({ encounter, onReviewed, onUpdated, onConflict }: { encounter: Encounter; onReviewed: (encounter: Encounter) => void; onUpdated: (encounter: Encounter) => void; onConflict: () => void }) {
  const [decisions, setDecisions] = useState<Record<string, Partial<Decision>>>({}), [note, setNote] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const assessment = encounter.assessment!
  const reviewed = encounter.status === 'reviewed'
  const decisionCount = assessment.recommendations.filter(r => decisions[r.id]?.action).length
  const [aiBusy, setAiBusy] = useState(false), [aiError, setAiError] = useState('')
  async function prepareBriefing() {
    setAiBusy(true); setAiError('')
    try { onUpdated(await api<Encounter>(`/encounters/${encounter.id}/ai-briefing`, { method: 'POST', body: { expected_version: encounter.version, assessment_id: assessment.id } })) }
    catch (error) { setAiError(message(error)); if (error instanceof Error && 'status' in error && error.status === 409) onConflict() }
    finally { setAiBusy(false) }
  }
  function change(id: string, patch: Partial<Decision>) { setError(''); setDecisions(current => ({ ...current, [id]: { ...current[id], ...patch, recommendation_id: id } })) }
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
  return <div className="assessment-content">
    <div className={`assessment-summary urgency-${assessment.urgency}`}>
      <div className="assessment-summary-icon">{['emergency', 'urgent'].includes(assessment.urgency) ? <ShieldAlert size={27} /> : <BookOpen size={26} />}</div>
      <div><div className="assessment-summary-top"><span className="eyebrow">CLINICAL PRIORITY</span><Badge value={assessment.urgency} /></div><h2>{assessment.urgency === 'emergency' ? 'Emergency findings require immediate clinical attention' : assessment.urgency === 'urgent' ? 'Urgent clinical review is indicated' : 'Decision support for this encounter'}</h2><p>{assessment.summary}</p>{assessment.urgency === 'emergency' && <strong className="emergency-reminder">Do not delay emergency care to complete this review.</strong>}</div>
    </div>
    <div className="assessment-meta"><span><BookOpen size={15} /> Evidence {assessment.evidence_version}</span><span>{formatDate(assessment.generated_at, true)}</span><span>Saved input version {encounter.version}</span></div>
    <div className="ai-status"><Sparkles size={19} /><div><strong>{titleCase(assessment.model_info.mode)} · {titleCase(assessment.model_info.status)}</strong><p>{assessment.model_info.model ? `${assessment.model_info.provider ?? 'Configured provider'} / ${assessment.model_info.model}` : 'No generative model is supplying recommendations in this assessment.'} Clinical rules remain subject to clinician review.</p></div></div>
    <div className="ai-briefing"><div className="subsection-heading"><div><h3>AI-assisted review focus</h3><p>Optional: organize the existing evidence-linked recommendations for review.</p></div>{!reviewed && <button className="button button-secondary button-small" disabled={busy || aiBusy} onClick={prepareBriefing}><Sparkles size={15} />{aiBusy ? 'Preparing briefing…' : 'Prepare AI briefing'}</button>}</div>{aiBusy && <p className="field-note" role="status">Preparing a bounded briefing. The clinical safety recommendations below remain available.</p>}{aiError && <Notice tone="error">{aiError} Your original safety recommendations remain available.</Notice>}{assessment.ai_briefing ? <><div className="assessment-meta"><Badge value={assessment.ai_briefing.status} /><span>{assessment.ai_briefing.provider} {assessment.ai_briefing.model}</span><span>{assessment.ai_briefing.prompt_version}</span></div>{assessment.ai_briefing.status === 'ready' ? <><p className="field-note">This focus uses existing recommendations; it does not replace your review of the complete assessment below.</p><ul className="ai-focus-list">{assessment.ai_briefing.focus?.map(item => <li key={item.id}><strong>{item.title}</strong><span>{item.detail}</span></li>)}</ul>{!!assessment.ai_briefing.checklist?.length && <details><summary>Information checklist</summary><ul>{assessment.ai_briefing.checklist.map((item, i) => <li key={i}>{titleCase(item)}</li>)}</ul></details>}</> : <Notice tone="warning">AI briefing {assessment.ai_briefing.status}. {titleCase(assessment.ai_briefing.reason_code ?? 'No briefing was returned')}. Continue with the rule-based assessment below.</Notice>}</> : <p className="field-note">No AI briefing requested. When configured, the provider receives only a minimized set of rule references and checks for this encounter; names and free-text notes are excluded.</p>}</div>
    {assessment.warnings.length > 0 && <Notice tone="warning"><strong>Checks and limitations</strong><ul>{assessment.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></Notice>}
    {assessment.missing_data.length > 0 && <details className="missing-data" open><summary>Information still needed <span className="count-pill">{assessment.missing_data.length}</span></summary><ul>{assessment.missing_data.map((item, i) => <li key={i}>{titleCase(item)}</li>)}</ul><p>Review these gaps before acting. Update the intake and assess again when new information is available.</p></details>}
    {reviewed && <Notice tone="success"><strong>Clinician review recorded.</strong> This encounter is immutable. Create a new encounter to document a subsequent assessment.{encounter.review?.reviewed_at && <> Recorded {formatDate(encounter.review.reviewed_at, true)}{encounter.review.reviewer_name ? ` by ${encounter.review.reviewer_name}` : ''}.</>}</Notice>}
    <DosingResults dosing={assessment.dosing} />
    <div className="recommendations-header"><h2>{assessment.recommendations.length} recommendation{assessment.recommendations.length === 1 ? '' : 's'} to review</h2>{!reviewed && <span>{decisionCount} of {assessment.recommendations.length} decisions selected</span>}</div>
    {assessment.recommendations.map((recommendation, index) => <RecommendationCard key={recommendation.id} recommendation={recommendation} index={index} decision={reviewed ? encounter.review?.decisions.find(d => d.recommendation_id === recommendation.id) : decisions[recommendation.id]} readOnly={reviewed || busy} onChange={patch => change(recommendation.id, patch)} />)}
    {!reviewed && <div className="review-footer"><Field label="Overall review note (optional)"><textarea rows={3} maxLength={4000} value={note} onChange={e => setNote(e.target.value)} placeholder="Clinical context, follow-up plan or considerations for the next visit…" disabled={busy || aiBusy} /></Field><p>Saving records your decisions against this assessment and its inputs. Accepting a recommendation does not certify its clinical appropriateness. Each action remains your clinical decision.</p>{error && <Notice tone="error">{error}</Notice>}<button className="button button-primary" type="button" disabled={busy || aiBusy} onClick={submit}><CheckCircle2 size={18} />{busy ? 'Recording review…' : 'Record review & lock encounter'}</button></div>}
    {reviewed && encounter.review?.note && <div className="recorded-note"><h3>Clinician review note</h3><p>{encounter.review.note}</p></div>}
  </div>
}

function RecommendationCard({ recommendation, index, decision, readOnly, onChange }: { recommendation: Recommendation; index: number; decision?: Partial<Decision>; readOnly: boolean; onChange: (decision: Partial<Decision>) => void }) {
  const actions: { value: DecisionAction; label: string }[] = [{ value: 'accept', label: 'Accept' }, { value: 'modify', label: 'Modify' }, { value: 'defer', label: 'Defer' }, { value: 'reject', label: 'Reject' }]
  return <article className={`recommendation recommendation-${recommendation.severity}`}>
    <div className="recommendation-top"><span className="recommendation-number">{String(index + 1).padStart(2, '0')}</span><div><div className="recommendation-category">{titleCase(recommendation.category)} <Badge value={recommendation.severity} /></div><h3>{recommendation.title}</h3></div></div>
    <p className="recommendation-detail">{recommendation.detail}</p>
    <details className="evidence-details"><summary><BookOpen size={15} /> Supporting evidence <span>{recommendation.evidence.length} source{recommendation.evidence.length === 1 ? '' : 's'}</span><ChevronRight size={15} /></summary><div className="evidence-list">{recommendation.evidence.map((source, i) => <div key={`${source.source_id}-${i}`}><strong>{safeEvidenceUrl(source.url) ? <a href={safeEvidenceUrl(source.url)} target="_blank" rel="noreferrer noopener">{source.title}<ExternalLink size={13} /></a> : source.title}</strong><p>{source.section}</p><small>Version {source.version} · {source.source_id}</small></div>)}<small className="mono">Rule {recommendation.rule_id}</small></div></details>
    <div className="recommendation-decision"><fieldset disabled={readOnly}><legend>Your decision for recommendation {index + 1}</legend><div className="decision-options">{actions.map(action => <label key={action.value} className={decision?.action === action.value ? 'decision-selected' : ''}><input type="radio" name={`decision-${recommendation.id}`} value={action.value} checked={decision?.action === action.value} onChange={() => onChange({ action: action.value })} /><span>{action.label}</span></label>)}</div>{decision?.action && decision.action !== 'accept' && <Field label={`Reason for ${decision.action === 'modify' ? 'modification' : decision.action === 'defer' ? 'deferral' : 'rejection'} (required)`}><textarea rows={2} maxLength={2000} value={decision.reason ?? ''} onChange={e => onChange({ reason: e.target.value })} required /></Field>}{decision?.action === 'modify' && <Field label="Modified clinical action (required)"><textarea rows={2} maxLength={3000} value={decision.modified_text ?? ''} onChange={e => onChange({ modified_text: e.target.value })} required /></Field>}</fieldset>{readOnly && !decision && <p className="muted">Review recorded. Decision details were not included in this response.</p>}</div>
  </article>
}
