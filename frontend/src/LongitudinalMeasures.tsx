import type { Encounter } from './types'

const columns = [
  ['systolic_bp', 'Systolic BP', 'mmHg'], ['diastolic_bp', 'Diastolic BP', 'mmHg'],
  ['hba1c', 'HbA1c', '%'], ['egfr', 'eGFR', 'mL/min/1.73 m²'],
] as const

export default function LongitudinalMeasures({ records }: { records: Encounter[] }) {
  const ordered = [...records].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5)
  if (ordered.length < 2) return null
  return <section className="panel" aria-label="Measurements across visits">
    <div className="panel-heading"><h2>Measurements across visits</h2><p>Five most recently saved encounters. Recorded values only; missing measurements stay blank. This table does not infer treatment response.</p></div>
    <div style={{ overflowX: 'auto' }} tabIndex={0} role="region" aria-label="Scrollable visit measurements">
      <table style={{ width: '100%', textAlign: 'left', borderSpacing: '12px' }}>
        <caption>Observation time and encounter review status are shown for each visit.</caption>
        <thead><tr><th scope="col">Observation time</th><th scope="col">Review</th>{columns.map(([field, label, unit]) => <th key={field} scope="col">{label}<br /><small>{unit}</small></th>)}</tr></thead>
        <tbody>{ordered.map(record => <tr key={record.id}>
          <th scope="row">{record.data.observed_at || 'Observation time not recorded'}<br /><small>Saved: {record.created_at}</small></th>
          <td>{record.status}</td>
          {columns.map(([field]) => <td key={field}>{record.data[field] ?? 'Not recorded'}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
  </section>
}
