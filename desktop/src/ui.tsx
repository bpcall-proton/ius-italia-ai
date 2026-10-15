import type { ReactNode } from 'react'

export const eur = (cents: number) => (cents / 100).toLocaleString('it-IT', { style: 'currency', currency: 'EUR' })
export const usd = (micro: number) => `$ ${(micro / 1_000_000).toLocaleString('it-IT', { maximumFractionDigits: 4 })}`
export const num = (n: number) => n.toLocaleString('it-IT')
export const dt = (s?: string | null) => (s ? new Date(s).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' }) : '—')
export const uid = () => crypto.randomUUID()

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-h">
          <h3>{title}</h3>
          <div className="row">{actions}</div>
        </header>
      )}
      {children}
    </section>
  )
}

export function Kpi({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="kpi">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  )
}

export function Item({ value }: { value: unknown }) {
  if (value === null || value === undefined) return null
  if (typeof value !== 'object') return <>{String(value)}</>
  if (Array.isArray(value)) return <>{value.map((v) => String(v)).join(', ')}</>
  return (
    <>
      {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
        <span key={k} className="kv">
          <em>{k.replace(/_/g, ' ')}:</em> <Item value={v} />
        </span>
      ))}
    </>
  )
}

export function List({ title, items, empty }: { title: string; items: unknown[]; empty?: string }) {
  return (
    <div className="list-block">
      <h4>{title}</h4>
      {items.length ? (
        <ul>
          {items.map((it, i) => (
            <li key={i}>
              <Item value={it} />
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{empty ?? 'Nessun elemento.'}</p>
      )}
    </div>
  )
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="error">{error}</div> : null
}
