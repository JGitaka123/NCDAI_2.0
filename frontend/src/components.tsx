import { AlertCircle, CheckCircle2, LoaderCircle, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'error' | 'success' | 'warning' }) {
  return <div className={`notice notice-${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
    {tone === 'success' ? <CheckCircle2 size={18} aria-hidden="true" /> : <AlertCircle size={18} aria-hidden="true" />}<div>{children}</div>
  </div>
}
export function Loading({ label = 'Loading workspace…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle className="spin" size={22} />{label}</div>
}
export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <div className="empty"><ShieldCheck size={28} aria-hidden="true" /><h3>{title}</h3>{children && <p>{children}</p>}{action}</div>
}
export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description?: string; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>
}
export function Field({ label, hint, children, className = '' }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return <label className={`field ${className}`}><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>
}
export function Badge({ value }: { value: string }) { return <span className={`badge badge-${value}`}>{value.replace(/_/g, ' ')}</span> }
export function Panel({ title, subtitle, children, className = '' }: { title?: string; subtitle?: string; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{title && <div className="panel-heading"><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>}{children}</section>
}
