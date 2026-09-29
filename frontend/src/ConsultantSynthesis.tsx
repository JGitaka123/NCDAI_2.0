import { useState } from 'react'
import { ClipboardCopy, ExternalLink, FlaskConical, Pill, Stethoscope } from 'lucide-react'
import { safeEvidenceUrl, titleCase } from './clinical'
import type { ConsultantSynthesis as Synthesis, Evidence } from './types'

const statusLabel: Record<string, string> = {
  acute: 'Acute', uncontrolled: 'Uncontrolled', untreated: 'Untreated', above_target: 'Above target', high_risk: 'High risk',
  review: 'Needs review', unconfirmed: 'Unconfirmed', needs_confirmation: 'Needs confirmation', at_risk: 'At risk',
  needs_data: 'Needs data', established: 'Established', withheld: 'Withheld', at_target: 'At target',
}
const statusTone = (status: string) => ['acute'].includes(status) ? 'critical' : ['uncontrolled', 'untreated', 'above_target', 'high_risk', 'review'].includes(status) ? 'warning' : status === 'at_target' ? 'good' : 'neutral'

function SourceTags({ ids, sources }: { ids: string[]; sources: Record<string, Evidence> }) {
  if (!ids.length) return null
  return <span className="cs-sources">{ids.map(id => {
    const source = sources[id], url = source && safeEvidenceUrl(source.url), label = id.replace(/_/g, ' ')
    return url ? <a key={id} href={url} target="_blank" rel="noreferrer noopener" title={`${source.title} · ${source.section}`}>{label}</a> : <span key={id} title={source?.title}>{label}</span>
  })}</span>
}

export default function ConsultantSynthesis({ synthesis }: { synthesis: Synthesis }) {
  const [copied, setCopied] = useState('')
  const sources = Object.fromEntries(synthesis.sources.map(source => [source.source_id, source]))
  async function copy() {
    try { await navigator.clipboard.writeText(synthesis.summary_text); setCopied('Summary copied. Paste it into the notes or a referral letter.') }
    catch { setCopied('Copy was blocked by the browser. Open the plain-text summary below and select it.') }
  }
  return <section className="consultant" aria-labelledby="consultant-heading">
    <div className="cs-head">
      <div className="cs-head-icon"><Stethoscope size={22} aria-hidden="true" /></div>
      <div className="cs-head-text">
        <div className="eyebrow">CONSULTANT SYNTHESIS</div>
        <h2 id="consultant-heading">{synthesis.one_liner}</h2>
        <p className={`cs-impression ${synthesis.acute_first ? 'cs-impression-acute' : ''}`}>{synthesis.impression}</p>
      </div>
      <button type="button" className="button button-secondary button-small" onClick={copy}><ClipboardCopy size={15} />Copy summary</button>
    </div>
    {copied && <p className="field-note" role="status">{copied}</p>}

    {synthesis.derived.length > 0 && <div className="cs-derived" aria-label="Derived measures">{synthesis.derived.map(item => <div key={item.id} className="cs-measure" title={item.method}>
      <span>{item.label}</span><strong>{item.value}{item.unit && <small> {item.unit}</small>}</strong><em>{item.interpretation}</em>
    </div>)}</div>}

    {synthesis.problems.length > 0 ? <ol className="cs-problems">{synthesis.problems.map(problem => <li key={problem.id} className={`cs-problem cs-tone-${statusTone(problem.status)}`}>
      <div className="cs-problem-top"><span className="cs-rank">{problem.rank}</span><h3>{problem.title}</h3><span className={`cs-status cs-status-${statusTone(problem.status)}`}>{statusLabel[problem.status] ?? titleCase(problem.status)}</span></div>
      {problem.facts.length > 0 && <ul className="cs-facts">{problem.facts.map((fact, i) => <li key={i}>{fact}</li>)}</ul>}
      {problem.assessment && <p className="cs-assessment">{problem.assessment}</p>}
      {problem.targets.map((target, i) => <p key={i} className="cs-target"><strong>Target</strong> {target}</p>)}
      {problem.plan.length > 0 && <ol className="cs-plan">{problem.plan.map((step, i) => <li key={i}><span>{step.text}</span><SourceTags ids={step.source_ids} sources={sources} /></li>)}</ol>}
    </li>)}</ol> : <p className="field-note">No chronic-disease problem was identified from the structured fields. This does not exclude disease.</p>}

    {synthesis.medication_review.length > 0 && <div className="cs-block"><h3><Pill size={16} aria-hidden="true" />Medication review</h3><ul className="cs-review">{synthesis.medication_review.map(entry => <li key={entry.id}>
      <span className={`cs-sev cs-sev-${entry.severity}`}>{entry.severity}</span><div><strong>{entry.finding}</strong><p>{entry.action} <SourceTags ids={entry.source_ids} sources={sources} /></p></div>
    </li>)}</ul></div>}

    {synthesis.considerations.length > 0 && <div className="cs-block"><h3><FlaskConical size={16} aria-hidden="true" />Diagnostic considerations</h3><ul className="cs-list">{synthesis.considerations.map(entry => <li key={entry.id}>{entry.text} <SourceTags ids={entry.source_ids} sources={sources} /></li>)}</ul></div>}

    <div className="cs-columns">
      {synthesis.monitoring.length > 0 && <div className="cs-block"><h3>Monitoring</h3><div className="table-wrap"><table className="cs-table"><thead><tr><th scope="col">Test</th><th scope="col">When</th><th scope="col">Why</th></tr></thead><tbody>{synthesis.monitoring.map(entry => <tr key={entry.id}><td>{entry.test}</td><td>{entry.timing}</td><td>{entry.reason}</td></tr>)}</tbody></table></div></div>}
      <div className="cs-block"><h3>Follow-up</h3><p className="cs-followup">{synthesis.follow_up}</p>
        {synthesis.data_gaps.length > 0 && <><h4>Would sharpen this assessment</h4><ul className="cs-list">{synthesis.data_gaps.map(gap => <li key={gap.field}><strong>{titleCase(gap.field.replace(/_mmol|_mg_mmol|_umol/g, ''))}</strong>: {gap.why}</li>)}</ul></>}
      </div>
    </div>

    <details className="cs-details"><summary>Plain-text summary</summary><pre>{synthesis.summary_text}</pre></details>
    <details className="cs-details"><summary>Guidelines cited <span className="count-pill">{synthesis.sources.length}</span></summary><ul className="cs-source-list">{synthesis.sources.map(source => <li key={source.source_id}><strong>{safeEvidenceUrl(source.url) ? <a href={safeEvidenceUrl(source.url)} target="_blank" rel="noreferrer noopener">{source.title}<ExternalLink size={12} /></a> : source.title}</strong><span>{source.section}</span><small>{source.version} · {source.source_id}</small></li>)}</ul></details>
    <p className="cs-boundary">{synthesis.boundary} <span className="mono">{synthesis.version}</span></p>
  </section>
}
