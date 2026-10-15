import { type FormEvent, type ReactNode, useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Me } from '../Login'
import { Card, dt, ErrorBox, eur, Kpi, num, usd } from '../ui'

type Row = Record<string, unknown>
type Col = [string, string, ((r: Row) => ReactNode)?]

function Table({ rows, cols }: { rows: Row[]; cols: Col[] }) {
  if (!rows.length) return <p className="muted">Nessun dato.</p>
  return (
    <table>
      <thead>
        <tr>
          {cols.map(([k, l]) => (
            <th key={k}>{l}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={String(r.id ?? r.request_id ?? i)}>
            {cols.map(([k, , f]) => (
              <td key={k}>{f ? f(r) : String(r[k] ?? '—')}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function useLoad<T>(path: string): [T | null, () => void, string | null] {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    api<T>(path).then(setData, (e) => setError(e.message))
  }, [path])
  useEffect(load, [load])
  return [data, load, error]
}

const simBadge = (r: Row) => (r.simulated ? <span className="badge warn">SIMULATO</span> : <span className="badge ok">reale</span>)

function Dashboard() {
  const [d, , error] = useLoad<Row & { ai_usage: Row[] }>('/admin/dashboard')
  if (!d) return <ErrorBox error={error} />
  return (
    <>
      <div className="kpis">
        <Kpi label="Avvocati registrati" value={num(d.registered as number)} hint={`${d.active} attivi · ${d.suspended} sospesi`} />
        <Kpi label="Studi" value={num(d.firms as number)} hint={`${d.paying} paganti · ${d.trials} in prova`} />
        <Kpi label="MRR" value={eur(d.mrr_cents as number)} hint={String(d.mrr_note)} />
        <Kpi label="ARR" value={eur(d.arr_cents as number)} />
      </div>
      <Card title="Consumi AI (aggregati)">
        <Table
          rows={d.ai_usage}
          cols={[
            ['simulated', 'Tipo', simBadge],
            ['requests', 'Richieste'],
            ['tokens', 'Token', (r) => num(r.tokens as number)],
            ['cost_micro', 'Costo provider', (r) => usd(r.cost_micro as number)],
          ]}
        />
      </Card>
    </>
  )
}

function Lawyers() {
  const [q, setQ] = useState('')
  const [rows, load, error] = useLoad<Row[]>(`/admin/lawyers?q=${encodeURIComponent(q)}`)
  const [bonus, setBonus] = useState<{ firm: string; amount: number } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const act = (p: Promise<unknown>) => p.then(load, (e) => setErr(e.message))
  const give = (e: FormEvent) => {
    e.preventDefault()
    act(api(`/admin/firms/${bonus!.firm}/credits`, { amount: bonus!.amount, reason: 'bonus', idempotency_key: crypto.randomUUID() }))
    setBonus(null)
  }
  return (
    <Card title="Avvocati e studi" actions={<input placeholder="Cerca nome, email, studio…" value={q} onChange={(e) => setQ(e.target.value)} />}>
      <ErrorBox error={error ?? err} />
      {bonus && (
        <form className="row" onSubmit={give}>
          <span>Crediti bonus:</span>
          <input type="number" min={1} value={bonus.amount} onChange={(e) => setBonus({ ...bonus, amount: Number(e.target.value) })} />
          <button className="primary">Assegna</button>
          <button type="button" onClick={() => setBonus(null)}>
            Annulla
          </button>
        </form>
      )}
      <Table
        rows={rows ?? []}
        cols={[
          ['name', 'Avvocato', (r) => `${r.first_name} ${r.last_name}`],
          ['email', 'Email'],
          ['firm', 'Studio', (r) => (r.firm as Row)?.name as string],
          ['plan', 'Piano', (r) => `${r.plan ?? '—'} (${r.subscription_status ?? '—'})`],
          ['credits', 'Crediti', (r) => num(r.credits as number)],
          ['tokens', 'Token mese', (r) => num(r.tokens as number)],
          ['last_login_at', 'Ultimo accesso', (r) => dt(r.last_login_at as string)],
          ['status', 'Stato', (r) => <span className={`badge ${r.status === 'active' ? 'ok' : 'err'}`}>{String(r.status)}</span>],
          [
            'actions',
            '',
            (r) => (
              <div className="row">
                <button
                  onClick={() =>
                    act(api(`/admin/lawyers/${r.id}/status`, { status: r.status === 'active' ? 'suspended' : 'active' }))
                  }
                >
                  {r.status === 'active' ? 'Sospendi' : 'Riattiva'}
                </button>
                <button onClick={() => setBonus({ firm: (r.firm as Row).id as string, amount: 50 })}>+ Crediti</button>
              </div>
            ),
          ],
        ]}
      />
    </Card>
  )
}

function Topups() {
  const [rows, load, error] = useLoad<Row[]>('/admin/topups')
  const [err, setErr] = useState<string | null>(null)
  const decide = (id: unknown, d: 'approve' | 'reject') => api(`/admin/topups/${id}/${d}`, {}).then(load, (e) => setErr(e.message))
  return (
    <Card title="Richieste di ricarica crediti">
      <ErrorBox error={error ?? err} />
      <Table
        rows={rows ?? []}
        cols={[
          ['firm', 'Studio'],
          ['email', 'Richiesta da'],
          ['credits', 'Crediti', (r) => num(r.credits as number)],
          ['created_at', 'Data', (r) => dt(r.created_at as string)],
          ['status', 'Stato'],
          [
            'actions',
            '',
            (r) =>
              r.status === 'in_attesa' && (
                <div className="row">
                  <button className="primary" onClick={() => decide(r.id, 'approve')}>
                    Approva e accredita
                  </button>
                  <button onClick={() => decide(r.id, 'reject')}>Rifiuta</button>
                </div>
              ),
          ],
        ]}
      />
    </Card>
  )
}

interface Plan {
  code: string
  name: string
  versions: Row[]
}

function Plans() {
  const [plans, load, error] = useLoad<Plan[]>('/admin/plans')
  const [edit, setEdit] = useState<{ code: string; price: string; credits: string; tokens: string; note: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const body = {
      price_month_cents: Math.round(Number(edit!.price.replace(',', '.')) * 100),
      monthly_credits: Number(edit!.credits),
      monthly_token_limit: Number(edit!.tokens),
      note: edit!.note || null,
    }
    api(`/admin/plans/${edit!.code}/versions`, body).then(() => {
      setEdit(null)
      load()
    }, (e2) => setErr(e2.message))
  }
  return (
    <>
      <ErrorBox error={error ?? err} />
      <p className="muted">Ogni modifica crea una nuova versione del listino: gli abbonamenti esistenti restano sulla versione sottoscritta.</p>
      {plans?.map((p) => {
        const cur = p.versions.at(-1)!
        return (
          <Card
            key={p.code}
            title={`${p.name} — ${eur(cur.price_month_cents as number)}/mese`}
            actions={
              <button
                onClick={() =>
                  setEdit({
                    code: p.code,
                    price: String((cur.price_month_cents as number) / 100),
                    credits: String(cur.monthly_credits),
                    tokens: String(cur.monthly_token_limit),
                    note: '',
                  })
                }
              >
                Nuovo prezzo
              </button>
            }
          >
            {edit?.code === p.code && (
              <form className="row wrap" onSubmit={submit}>
                <label className="inline">
                  € / mese
                  <input value={edit.price} onChange={(e) => setEdit({ ...edit, price: e.target.value })} required />
                </label>
                <label className="inline">
                  Crediti
                  <input type="number" value={edit.credits} onChange={(e) => setEdit({ ...edit, credits: e.target.value })} required />
                </label>
                <label className="inline">
                  Token / mese
                  <input type="number" value={edit.tokens} onChange={(e) => setEdit({ ...edit, tokens: e.target.value })} required />
                </label>
                <input placeholder="Nota" value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} />
                <button className="primary">Salva versione</button>
                <button type="button" onClick={() => setEdit(null)}>
                  Annulla
                </button>
              </form>
            )}
            <Table
              rows={p.versions}
              cols={[
                ['version', 'Versione'],
                ['price_month_cents', 'Mensile', (r) => eur(r.price_month_cents as number)],
                ['price_year_cents', 'Annuale', (r) => (r.price_year_cents == null ? '—' : eur(r.price_year_cents as number))],
                ['monthly_credits', 'Crediti', (r) => num(r.monthly_credits as number)],
                ['monthly_token_limit', 'Token', (r) => num(r.monthly_token_limit as number)],
                ['valid_from', 'Dal', (r) => dt(r.valid_from as string)],
                ['subscriptions', 'Abbonati'],
                ['note', 'Nota'],
              ]}
            />
          </Card>
        )
      })}
    </>
  )
}

function Usage() {
  const [d, , error] = useLoad<{ records: Row[]; by_model: Row[] }>('/admin/ai-usage')
  return (
    <>
      <ErrorBox error={error} />
      <Card title="Per modello">
        <Table
          rows={d?.by_model ?? []}
          cols={[
            ['provider', 'Provider'],
            ['model', 'Modello'],
            ['simulated', 'Tipo', simBadge],
            ['requests', 'Richieste'],
            ['tokens', 'Token', (r) => num(r.tokens as number)],
            ['cost_micro', 'Costo', (r) => usd(r.cost_micro as number)],
          ]}
        />
      </Card>
      <Card title="Registro richieste (solo metadati: nessun testo del prompt)">
        <Table
          rows={d?.records ?? []}
          cols={[
            ['created_at', 'Data', (r) => dt(r.created_at as string)],
            ['user', 'Utente'],
            ['firm', 'Studio'],
            ['model', 'Modello', (r) => `${r.provider}/${r.model}`],
            ['operation', 'Operazione'],
            ['tokens', 'Token in/out', (r) => `${num(r.input_tokens as number)} / ${num(r.output_tokens as number)}`],
            ['credits', 'Crediti'],
            ['cost_micro', 'Costo', (r) => usd(r.cost_micro as number)],
            ['outcome', 'Esito'],
            ['simulated', 'Tipo', simBadge],
          ]}
        />
      </Card>
    </>
  )
}

function Models() {
  const [rows, load, error] = useLoad<Row[]>('/admin/models')
  const [edit, setEdit] = useState<{ id: string; inp: string; out: string; note: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    api(`/admin/models/${edit!.id}/prices`, {
      currency: 'USD',
      input_per_mtok_micro: Math.round(Number(edit!.inp) * 1_000_000),
      output_per_mtok_micro: Math.round(Number(edit!.out) * 1_000_000),
      source_note: edit!.note || null,
    }).then(() => {
      setEdit(null)
      load()
    }, (e2) => setErr(e2.message))
  }
  return (
    <Card title="Modelli e listini provider">
      <ErrorBox error={error ?? err} />
      <p className="muted">Le chiavi API si configurano solo sul server (variabili d&apos;ambiente) e non sono mai visibili qui.</p>
      {edit && (
        <form className="row wrap" onSubmit={submit}>
          <label className="inline">
            $ input / 1M token
            <input value={edit.inp} onChange={(e) => setEdit({ ...edit, inp: e.target.value })} required />
          </label>
          <label className="inline">
            $ output / 1M token
            <input value={edit.out} onChange={(e) => setEdit({ ...edit, out: e.target.value })} required />
          </label>
          <input placeholder="Fonte del prezzo" value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} />
          <button className="primary">Salva nuovo listino</button>
        </form>
      )}
      <Table
        rows={rows ?? []}
        cols={[
          ['provider', 'Provider'],
          ['model', 'Modello'],
          ['task', 'Compito'],
          ['enabled', 'Attivo', (r) => (r.enabled ? 'sì' : 'no')],
          ['credits_per_1k_tokens', 'Crediti / 1k token'],
          ['price', 'Prezzo in/out per 1M', (r) => {
            const p = r.price as Row | null
            return p ? `${usd(p.input_per_mtok_micro as number)} / ${usd(p.output_per_mtok_micro as number)}` : '—'
          }],
          ['note', 'Fonte', (r) => String((r.price as Row | null)?.source_note ?? '—')],
          ['act', '', (r) => <button onClick={() => setEdit({ id: r.id as string, inp: '0', out: '0', note: '' })}>Nuovo prezzo</button>],
        ]}
      />
    </Card>
  )
}

function Audit() {
  const [audit, , e1] = useLoad<Row[]>('/admin/audit')
  const [sec, , e2] = useLoad<Row[]>('/admin/security-events')
  const fmt = (r: Row) => dt((r.at ?? r.created_at) as string)
  return (
    <>
      <ErrorBox error={e1 ?? e2} />
      <Card title="Registro azioni amministrative">
        <Table
          rows={audit ?? []}
          cols={[
            ['at', 'Data', fmt],
            ['admin', 'Admin'],
            ['action', 'Azione'],
            ['target', 'Oggetto', (r) => String(r.target ?? r.target_id ?? '—')],
          ]}
        />
      </Card>
      <Card title="Eventi di sicurezza">
        <Table rows={sec ?? []} cols={[['at', 'Data', fmt], ['user', 'Utente'], ['kind', 'Evento']]} />
      </Card>
    </>
  )
}

function Isolation() {
  const [d, , error] = useLoad<{ tables: Record<string, string[]>; content_columns: string[]; case_endpoints: boolean; explanation: string }>(
    '/admin/isolation',
  )
  if (!d) return <ErrorBox error={error} />
  return (
    <Card title="Isolamento dei dati riservati">
      <p>{d.explanation}</p>
      <div className="kpis">
        <Kpi label="Endpoint fascicoli sul server" value={d.case_endpoints ? 'presenti' : 'nessuno'} />
        <Kpi label="Colonne con contenuti riservati" value={d.content_columns.length} />
        <Kpi label="Tabelle del database commerciale" value={Object.keys(d.tables).length} />
      </div>
      <ul className="cols">
        {Object.keys(d.tables).map((t) => (
          <li key={t} className="mono">
            {t}
          </li>
        ))}
      </ul>
    </Card>
  )
}

const VIEWS: [string, string, () => ReactNode][] = [
  ['dash', 'Dashboard', Dashboard],
  ['lawyers', 'Avvocati', Lawyers],
  ['plans', 'Piani e prezzi', Plans],
  ['usage', 'Consumi AI', Usage],
  ['topups', 'Ricariche crediti', Topups],
  ['models', 'Modelli AI', Models],
  ['audit', 'Audit e sicurezza', Audit],
  ['iso', 'Isolamento dati', Isolation],
]

export default function Admin({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [view, setView] = useState('dash')
  const View = VIEWS.find(([k]) => k === view)![2]
  return (
    <div className="shell admin">
      <aside className="side">
        <div className="brand">
          <div className="logo sm">IUS</div>
          <div>
            <strong>IUS Admin</strong>
            <small>{me.role}</small>
          </div>
        </div>
        <nav>
          {VIEWS.map(([k, l]) => (
            <button key={k} className={view === k ? 'active' : ''} onClick={() => setView(k)}>
              {l}
            </button>
          ))}
        </nav>
        <div className="side-foot">
          <small>{me.email}</small>
          <button onClick={onLogout}>Esci</button>
        </div>
      </aside>
      <main className="content">
        <div className="warning">Ambiente dimostrativo: dati commerciali fittizi. L&apos;amministrazione non ha accesso a fascicoli, documenti o bozze.</div>
        <View />
      </main>
    </div>
  )
}
