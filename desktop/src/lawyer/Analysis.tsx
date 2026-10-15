import { useEffect, useState } from 'react'
import { api, stream } from '../api'
import { sanitizeHtml } from '../sanitize'
import type { Analysis as A, Brief, CaseData, DraftResult, SavedAnalysis } from '../types'
import { Card, dt, ErrorBox, Item, List, uid } from '../ui'

interface Provider {
  name: string
  label: string
  tasks: string[]
  model: string | null
  status: string
  external: boolean
}

interface Pending {
  operation: 'analyze' | 'draft'
  provider: Provider
  chars: number
  categories: string[]
  go: (consentId: string) => Promise<void>
}

const DOC_TYPES: [string, string][] = [
  ['richiesta_documenti', 'Richiesta documenti al cliente'],
  ['lettera', 'Lettera'],
  ['diffida', 'Diffida'],
  ['parere', 'Parere preliminare'],
]

const text = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v))

export default function Analysis({
  c,
  save,
  openDraft,
}: {
  c: CaseData
  save: (patch: Partial<CaseData>) => Promise<CaseData>
  openDraft: (id: string) => void
}) {
  const [providers, setProviders] = useState<Provider[]>([])
  const [provider, setProvider] = useState('simulation')
  const [description, setDescription] = useState(c.matter)
  const [pending, setPending] = useState<Pending | null>(null)
  const [steps, setSteps] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [current, setCurrent] = useState<SavedAnalysis | null>(c.analyses.at(-1) ?? null)
  const [brief, setBrief] = useState<Brief | null>(null)
  const [apptDate, setApptDate] = useState('')

  useEffect(() => {
    api<Provider[]>('/ai/providers').then(setProviders, (e) => setError(e.message))
  }, [])

  const usable = (op: string) => providers.filter((p) => p.status === 'attivo' && p.tasks.includes(op))
  const pick = (op: string) => usable(op).find((p) => p.name === provider) ?? usable(op)[0]

  const ask = (operation: Pending['operation'], chars: number, categories: string[], go: Pending['go']) => {
    const p = pick(operation)
    if (!p) return setError('Nessun motore disponibile per questa operazione.')
    setError(null)
    setPending({ operation, provider: p, chars, categories, go })
  }

  const authorize = async () => {
    const p = pending!
    setPending(null)
    setBusy(true)
    setSteps([])
    try {
      const consent = await api<{ id: string }>('/ai/consents', {
        provider: p.provider.name,
        operation: p.operation,
        data_categories: p.categories,
        char_count: p.chars,
      })
      await p.go(consent.id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const runStream = async <T,>(path: string, body: object): Promise<{ data: T; simulated: boolean; provider: string }> => {
    let result: { data: T; simulated: boolean; provider: string } | null = null
    await stream(path, body, (event, data) => {
      const d = data as { label?: string; message?: string }
      if (event === 'step') setSteps((s) => [...s, d.label ?? ''])
      else if (event === 'error') throw new Error(d.message ?? 'Errore del motore AI')
      else if (event === 'result') result = data as typeof result
    })
    if (!result) throw new Error('Connessione interrotta prima del risultato: nessun credito addebitato oltre il consumo registrato.')
    return result
  }

  const analyze = () =>
    ask('analyze', description.length, ['descrizione del caso'], async (consentId) => {
      const r = await runStream<A>('/ai/analyze', { consent_id: consentId, provider: pick('analyze')!.name, description })
      const saved: SavedAnalysis = { id: uid(), at: new Date().toISOString(), provider: r.provider, simulated: r.simulated, data: r.data }
      await save({ analyses: [...c.analyses, saved] })
      setCurrent(saved)
      setBrief({ ...r.data.draft_brief, recipient: c.client || '' })
    })

  const draft = () => {
    const b = brief!
    const chars = JSON.stringify(b).length
    ask('draft', chars, ['fatti approvati', 'richieste approvate', 'norme approvate'], async (consentId) => {
      const r = await runStream<DraftResult>('/ai/draft', { consent_id: consentId, provider: pick('draft')!.name, brief: b })
      const d = {
        id: uid(),
        title: r.data.title,
        html: sanitizeHtml(r.data.html),
        status: 'bozza' as const,
        source: r.simulated ? ('ai-simulazione' as const) : ('ai' as const),
        updatedAt: new Date().toISOString(),
      }
      await save({ drafts: [...c.drafts, d] })
      openDraft(d.id)
    })
  }

  const addAppointment = async () => {
    const appt = current!.data.secretary.appointment
    await save({
      agenda: [
        ...c.agenda,
        {
          id: uid(),
          kind: 'appuntamento',
          title: `${appt.type} (${appt.duration_min} min)`,
          date: apptDate,
          note: appt.reason,
          confirmed: false,
        },
      ],
    })
    setApptDate('')
  }

  const a = current?.data
  const facts = a ? [...a.facts.declared, ...a.facts.documented].map(text) : []
  const toggle = (key: 'approved_facts' | 'requests' | 'approved_norm_ids', v: string) =>
    setBrief((b) => b && { ...b, [key]: b[key].includes(v) ? b[key].filter((x) => x !== v) : [...b[key], v] })

  return (
    <>
      <Card title="Descrivi il caso">
        <textarea
          rows={7}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Fatti, date, soggetti, documenti disponibili e obiettivo del cliente…"
        />
        <div className="row between">
          <div className="row">
            <label className="inline">
              Motore
              <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                {providers.map((p) => (
                  <option key={p.name} value={p.name} disabled={p.status !== 'attivo'}>
                    {p.label} — {p.status}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button className="primary" disabled={busy || description.trim().length < 10} onClick={analyze}>
            Analizza
          </button>
        </div>
        {busy && (
          <ol className="steps">
            {steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        )}
        <ErrorBox error={error} />
      </Card>

      {pending && (
        <div className="modal">
          <div className="card">
            <h3>Autorizzazione all&apos;elaborazione</h3>
            <p>
              Operazione: <strong>{pending.operation === 'analyze' ? 'analisi del caso' : 'redazione bozza'}</strong>
              <br />
              Motore: <strong>{pending.provider.label}</strong>
              <br />
              Dati: {pending.categories.join(', ')} — {pending.chars.toLocaleString('it-IT')} caratteri
            </p>
            {pending.provider.external ? (
              <div className="warning">I dati indicati verranno inviati al fornitore cloud tramite il server IUS. I documenti del fascicolo non vengono inviati.</div>
            ) : pending.provider.name === 'simulation' ? (
              <div className="success">Motore dimostrativo: nessun dato viene inviato a fornitori AI esterni.</div>
            ) : (
              <div className="success">Motore AI locale su questo computer: i dati non escono dal PC.</div>
            )}
            <div className="row end">
              <button onClick={() => setPending(null)}>Annulla</button>
              <button className="primary" onClick={authorize}>
                Autorizzo
              </button>
            </div>
          </div>
        </div>
      )}

      {a && current && (
        <>
          {current.simulated && (
            <div className="warning">
              Risultato della modalità DIMOSTRATIVA (motore a regole, non OpenAI/DeepSeek). Le norme sono candidate e vanno verificate sul testo vigente.
            </div>
          )}
          <Card title={`Analisi preliminare · ${dt(current.at)}`}>
            <p>
              <strong>{a.summary}</strong>
            </p>
            <span className="badge warn">{a.conclusion_status}</span>
            <div className="grid2">
              <List title="Fatti dichiarati" items={a.facts.declared} />
              <List title="Fatti documentati" items={a.facts.documented} />
              <List title="Fatti controversi" items={a.facts.controversial} />
              <List title="Informazioni mancanti" items={a.missing_information} />
            </div>
            <List title="Questioni giuridiche" items={a.legal_questions} />
            <div className="list-block">
              <h4>Norme candidate</h4>
              <table>
                <tbody>
                  {a.candidate_norms.map((n) => (
                    <tr key={n.id}>
                      <td>
                        <strong>{n.citation}</strong> — {n.heading}
                      </td>
                      <td>
                        <span className="badge warn">{n.status}</span>
                      </td>
                      <td className="muted mono">{n.url}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">{a.case_law_note}</p>
            </div>
            <div className="grid2">
              <List title="Elementi favorevoli" items={a.favorable} />
              <List title="Elementi sfavorevoli" items={a.unfavorable} />
              <List title="Rischi" items={a.risks} />
              <List title="Scenari (condizionati)" items={a.scenarios} />
            </div>
            <List title="Problemi probatori" items={a.evidence_issues} />
            <List title="Attività successive" items={a.next_actions} />
            {a.citation_check?.length > 0 && <List title="Controllo citazioni: segnalazioni" items={a.citation_check} />}
          </Card>

          <Card title="IUS Smart Secretary">
            <div className="grid2">
              <div>
                <h4>Richiesta documenti suggerita</h4>
                <p className="muted">
                  Destinatario: <Item value={a.secretary.document_request.recipient} /> · termine proposto {a.secretary.document_request.due_days} giorni
                </p>
                <ul>
                  {a.secretary.document_request.items.map((it) => (
                    <li key={it}>{it}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>Appuntamento suggerito</h4>
                <p>
                  {a.secretary.appointment.type} · {a.secretary.appointment.duration_min} min — {a.secretary.appointment.reason}
                </p>
                <p className="muted">Disponibilità: {a.secretary.appointment.availability}</p>
                <div className="row">
                  <input type="datetime-local" value={apptDate} onChange={(e) => setApptDate(e.target.value)} />
                  <button disabled={!apptDate} onClick={addAppointment}>
                    Proponi in agenda
                  </button>
                </div>
              </div>
            </div>
          </Card>

          {brief && (
            <Card title="Brief per la bozza (solo elementi approvati)">
              <div className="row wrap">
                <select value={brief.doc_type} onChange={(e) => setBrief({ ...brief, doc_type: e.target.value })}>
                  {DOC_TYPES.map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </select>
                <input placeholder="Oggetto" value={brief.subject} onChange={(e) => setBrief({ ...brief, subject: e.target.value })} />
                <input placeholder="Destinatario" value={brief.recipient ?? ''} onChange={(e) => setBrief({ ...brief, recipient: e.target.value })} />
                <input placeholder="Avvocato mittente" value={brief.sender ?? ''} onChange={(e) => setBrief({ ...brief, sender: e.target.value })} />
                <label className="inline">
                  Termine (giorni)
                  <input
                    type="number"
                    min={1}
                    max={365}
                    value={brief.due_days ?? ''}
                    onChange={(e) => setBrief({ ...brief, due_days: e.target.value ? Number(e.target.value) : undefined })}
                  />
                </label>
              </div>
              <div className="grid3">
                <Checks title="Fatti approvati" options={facts.map((f) => [f, f])} selected={brief.approved_facts} toggle={(v) => toggle('approved_facts', v)} />
                <Checks
                  title="Richieste"
                  options={a.secretary.document_request.items.map((r) => [r, r])}
                  selected={brief.requests}
                  toggle={(v) => toggle('requests', v)}
                />
                <Checks
                  title="Norme da citare"
                  options={a.candidate_norms.map((n) => [n.id, n.citation])}
                  selected={brief.approved_norm_ids}
                  toggle={(v) => toggle('approved_norm_ids', v)}
                />
              </div>
              <div className="row end">
                <button className="primary" disabled={busy} onClick={draft}>
                  Prepara bozza
                </button>
              </div>
            </Card>
          )}
        </>
      )}
    </>
  )
}

function Checks({
  title,
  options,
  selected,
  toggle,
}: {
  title: string
  options: [string, string][]
  selected: string[]
  toggle: (v: string) => void
}) {
  return (
    <div className="list-block">
      <h4>{title}</h4>
      {options.length === 0 && <p className="muted">Nessuno.</p>}
      {options.map(([v, l]) => (
        <label key={v} className="check">
          <input type="checkbox" checked={selected.includes(v)} onChange={() => toggle(v)} /> {l}
        </label>
      ))}
    </div>
  )
}
