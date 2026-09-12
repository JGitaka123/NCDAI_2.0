import { ExternalLink } from 'lucide-react'
import { safeEvidenceUrl } from './clinical'
import type { DosingAssessment } from './types'

const statusLabels = { reference: 'Reference available for clinician review', blocked: 'Reference withheld', outside_reference: 'Proposed regimen outside reference' }
export default function DosingResults({ dosing }: { dosing?: DosingAssessment }) {
  if (!dosing?.results.length) return null
  return <section className="dosing-results" aria-labelledby="dosing-results-heading"><h2 id="dosing-results-heading">Medicine reference checks</h2><p className="field-note">Catalogue {dosing.version}. These are bounded references, not prescriptions. Record your decision using the corresponding recommendations below.</p>
    {dosing.results.map((result, index) => <article className={`dose-result dose-result-${result.status}`} key={`${result.medicine_id}-${index}`}><h3>{result.name}</h3><strong>{statusLabels[result.status]}</strong>
      {result.reasons.length > 0 && <ul>{result.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>}
      {result.status !== 'blocked' && result.reference && <dl className="dose-reference"><div><dt>Reference initial dose</dt><dd>{result.reference.initial_dose_mg} mg per administration</dd></div><div><dt>Reference frequency</dt><dd>{result.reference.frequency_per_day} administration{result.reference.frequency_per_day === 1 ? '' : 's'} per day</dd></div><div><dt>Reference maximum</dt><dd>{result.reference.max_daily_mg} mg per day</dd></div></dl>}
      {result.proposed_daily_mg != null && <p>Entered proposal: {result.proposed_daily_mg} mg per day. {result.status === 'reference' ? 'A numerical match does not establish suitability.' : 'This is the entered proposal, not an endorsed regimen.'}</p>}
      {!!result.evidence.length && <details className="evidence-details"><summary>Medicine reference sources</summary><div className="evidence-list">{result.evidence.map((source, i) => <div key={`${source.source_id}-${i}`}><strong>{safeEvidenceUrl(source.url) ? <a href={safeEvidenceUrl(source.url)} target="_blank" rel="noreferrer noopener">{source.title}<ExternalLink size={13} /></a> : source.title}</strong><p>{source.section}</p><small>Version {source.version} · {source.source_id}</small></div>)}</div></details>}
    </article>)}
  </section>
}
