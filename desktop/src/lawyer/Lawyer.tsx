import { type FormEvent, useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Me } from '../Login'
import type { CaseSummary } from '../types'
import { Card, dt, ErrorBox, eur, Item, Kpi, num } from '../ui'
import CaseView from './CaseView'

interface Account {
  subscription: {
    status: string
    plan: string
    plan_code: string
    trial_ends_at: string | null
    version: { price_month_cents: number; monthly_credits: number; monthly_token_limit: number }
  } | null
  credits: { balance: number; reserved: number; monthly: number }
  usage: { month_tokens: number; month_token_limit: number; percent: number; warning: string | null }
}

function VaultGate({ onOpen }: { onOpen: () => void }) {
  const [exists, setExists] = useState<boolean | null>(null)
  const [pass, setPass] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    window.ius?.vault.status().then((s) => (s.unlocked ? onOpen() : setExists(s.exists)))
  }, [onOpen])

  if (!window.ius)
    return <div className="splash">L&apos;archivio cifrato è disponibile solo nell&apos;applicazione desktop.</div>
  if (exists === null) return null

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!exists && pass !== confirm) return setError('Le due passphrase non coincidono')
    setBusy(true)
    try {
      await (exists ? window.ius!.vault.unlock(pass) : window.ius!.vault.create(pass))
      onOpen()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="vault-gate card" onSubmit={submit}>
      <h2>{exists ? 'Sblocca l’archivio dello studio' : 'Crea l’archivio cifrato dello studio'}</h2>
      <p className="muted">
        Fascicoli e documenti restano su questo computer, cifrati con AES-256-GCM e una chiave distinta per ogni fascicolo.
        La passphrase non viene mai inviata al server: se la perdi, i dati non sono recuperabili.
      </p>
      <label>
        Passphrase
        <input type="password" value={pass} onChange={(e) => setPass(e.target.value)} minLength={10} required autoFocus />
      </label>
      {!exists && (
        <label>
          Ripeti passphrase
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
        </label>
      )}
      <ErrorBox error={error} />
      <button className="primary" disabled={busy}>
        {busy ? 'Derivazione chiave…' : exists ? 'Sblocca' : 'Crea archivio'}
      </button>
    </form>
  )
}

function Dashboard({ cases, open }: { cases: CaseSummary[]; open: (id: string) => void }) {
  const [acc, setAcc] = useState<Account | null>(null)
  useEffect(() => {
    api<Account>('/me').then(setAcc)
  }, [])
  return (
    <>
      <div className="kpis">
        <Kpi
          label="Piano"
          value={acc?.subscription ? `${acc.subscription.plan}` : '—'}
          hint={acc?.subscription ? `${acc.subscription.status} · ${eur(acc.subscription.version.price_month_cents)}/mese` : ''}
        />
        <Kpi label="Crediti disponibili" value={acc ? num(acc.credits.balance) : '—'} hint={acc ? `su ${num(acc.credits.monthly)} mensili` : ''} />
        <Kpi
          label="Token AI del mese"
          value={acc ? `${acc.usage.percent.toLocaleString('it-IT')}%` : '—'}
          hint={acc ? `${num(acc.usage.month_tokens)} / ${num(acc.usage.month_token_limit)}` : ''}
        />
        <Kpi label="Fascicoli locali" value={cases.length} hint="cifrati su questo computer" />
      </div>
      {acc?.usage.warning && <div className="warning">{acc.usage.warning}</div>}
      <Topup />
      <Card title="Fascicoli recenti">
        <CaseTable cases={cases.slice(0, 8)} open={open} />
      </Card>
    </>
  )
}

function CaseTable({ cases, open }: { cases: CaseSummary[]; open: (id: string) => void }) {
  if (!cases.length) return <p className="muted">Nessun fascicolo. Creane uno da “Fascicoli”.</p>
  return (
    <table>
      <thead>
        <tr>
          <th>Fascicolo</th>
          <th>Cliente</th>
          <th>Documenti</th>
          <th>Atti</th>
          <th>Aggiornato</th>
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.id} className="clickable" onClick={() => open(c.id)}>
            <td>
              <strong>{c.title}</strong>
              <div className="muted">{c.matter}</div>
            </td>
            <td>{c.client}</td>
            <td>{c.documents}</td>
            <td>{c.drafts}</td>
            <td>{dt(c.updatedAt)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Cases({ cases, open, reload }: { cases: CaseSummary[]; open: (id: string) => void; reload: () => void }) {
  const [form, setForm] = useState({ title: '', client: '', matter: '' })
  const [q, setQ] = useState('')
  const [error, setError] = useState<string | null>(null)
  const create = async (e: FormEvent) => {
    e.preventDefault()
    try {
      const c = await window.ius!.cases.create(form)
      setForm({ title: '', client: '', matter: '' })
      reload()
      open(c.id)
    } catch (err) {
      setError((err as Error).message)
    }
  }
  const needle = q.toLowerCase()
  const shown = cases.filter((c) => `${c.title} ${c.client} ${c.matter}`.toLowerCase().includes(needle))
  return (
    <>
      <Card title="Nuovo fascicolo">
        <form className="row wrap" onSubmit={create}>
          <input placeholder="Titolo (es. Rossi c/ Bianchi)" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          <input placeholder="Cliente" value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} />
          <input placeholder="Materia / oggetto" value={form.matter} onChange={(e) => setForm({ ...form, matter: e.target.value })} />
          <button className="primary">Crea</button>
        </form>
        <ErrorBox error={error} />
      </Card>
      <Card title="Fascicoli" actions={<input placeholder="Cerca…" value={q} onChange={(e) => setQ(e.target.value)} />}>
        <CaseTable cases={shown} open={open} />
      </Card>
    </>
  )
}

interface SessionRow {
  id: string
  current?: boolean
  [k: string]: unknown
}

function Sessions() {
  const [rows, setRows] = useState<SessionRow[]>([])
  const load = useCallback(() => api<SessionRow[]>('/auth/sessions').then(setRows), [])
  useEffect(() => {
    load()
  }, [load])
  return (
    <Card title="Sessioni attive">
      <table>
        <tbody>
          {rows.map((s) => (
            <tr key={s.id}>
              <td>
                <Item value={Object.fromEntries(Object.entries(s).filter(([k]) => k !== 'id'))} />
              </td>
              <td>
                <button onClick={() => api(`/auth/sessions/${s.id}/revoke`, {}).then(load)}>Revoca</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

type View = 'dashboard' | 'cases' | 'sessions'

export default function Lawyer({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [unlocked, setUnlocked] = useState(false)
  const [view, setView] = useState<View>('dashboard')
  const [caseId, setCaseId] = useState<string | null>(null)
  const [cases, setCases] = useState<CaseSummary[]>([])
  const reload = useCallback(() => {
    window.ius?.cases.list().then(setCases)
  }, [])
  const onOpen = useCallback(() => {
    setUnlocked(true)
    reload()
  }, [reload])

  const lock = async () => {
    await window.ius?.vault.lock()
    setUnlocked(false)
    setCaseId(null)
  }

  const nav = (v: View) => {
    setView(v)
    setCaseId(null)
  }

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="logo sm">IUS</div>
          <div>
            <strong>IUS Italia AI</strong>
            <small>{me.firm?.name}</small>
          </div>
        </div>
        <nav>
          <button className={view === 'dashboard' && !caseId ? 'active' : ''} onClick={() => nav('dashboard')}>Scrivania</button>
          <button className={view === 'cases' || caseId ? 'active' : ''} onClick={() => nav('cases')}>Fascicoli</button>
          <button className={view === 'sessions' ? 'active' : ''} onClick={() => nav('sessions')}>Sicurezza</button>
        </nav>
        <div className="side-foot">
          <small>
            {me.first_name} {me.last_name}
          </small>
          {unlocked && <button onClick={lock}>Blocca archivio</button>}
          <button onClick={onLogout}>Esci</button>
        </div>
      </aside>
      <main className="content">
        {!unlocked ? (
          <VaultGate onOpen={onOpen} />
        ) : caseId ? (
          <CaseView
            id={caseId}
            onBack={() => {
              setCaseId(null)
              reload()
            }}
          />
        ) : view === 'dashboard' ? (
          <Dashboard cases={cases} open={setCaseId} />
        ) : view === 'cases' ? (
          <Cases cases={cases} open={setCaseId} reload={reload} />
        ) : (
          <Sessions />
        )}
      </main>
    </div>
  )
}

interface TopupRow {
  id: string
  credits: number
  status: string
  created_at: string
}

function Topup() {
  const [rows, setRows] = useState<TopupRow[]>([])
  const [credits, setCredits] = useState(1000)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    api<TopupRow[]>('/credits/topups').then(setRows, (e) => setError(e.message))
  }, [])
  useEffect(load, [load])
  const send = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    api('/credits/topups', { credits }).then(load, (err) => setError(err.message))
  }
  return (
    <Card title="Ricarica crediti AI">
      <p className="muted">I crediti si usano per l&apos;AI del servizio IUS (OpenAI e Ollama). La ricarica viene attivata dall&apos;amministrazione.</p>
      <form className="row" onSubmit={send}>
        <select value={credits} onChange={(e) => setCredits(Number(e.target.value))}>
          {[500, 1000, 2500, 5000, 10000].map((n) => (
            <option key={n} value={n}>
              {num(n)} crediti
            </option>
          ))}
        </select>
        <button className="primary" disabled={rows.some((r) => r.status === 'in_attesa')}>
          Richiedi ricarica
        </button>
      </form>
      <ErrorBox error={error} />
      {rows.map((r) => (
        <div key={r.id} className="muted">
          {num(r.credits)} crediti · {r.status} · {dt(r.created_at)}
        </div>
      ))}
    </Card>
  )
}
