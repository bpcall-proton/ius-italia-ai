import { type FormEvent, useCallback, useEffect, useState } from 'react'
import type { AgendaItem, CaseData, Draft } from '../types'
import { Card, dt, ErrorBox, uid } from '../ui'
import Analysis from './Analysis'
import Editor from './Editor'

type Tab = 'docs' | 'drafts' | 'analysis' | 'agenda' | 'notes'
const TABS: [Tab, string][] = [
  ['docs', 'Documenti'],
  ['drafts', 'Atti e bozze'],
  ['analysis', 'Analisi IUS'],
  ['agenda', 'Agenda'],
  ['notes', 'Note'],
]

export default function CaseView({ id, onBack }: { id: string; onBack: () => void }) {
  const [c, setC] = useState<CaseData | null>(null)
  const [tab, setTab] = useState<Tab>('docs')
  const [draftId, setDraftId] = useState<string | null>(null)
  const [viewer, setViewer] = useState<{ url: string; name: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    window.ius!.cases.get(id).then(setC, (e) => setError(e.message))
  }, [id])
  useEffect(
    () => () => {
      if (viewer) URL.revokeObjectURL(viewer.url)
    },
    [viewer],
  )

  const save = useCallback(
    async (patch: Partial<CaseData>) => {
      try {
        const next = await window.ius!.cases.update(id, patch)
        setC(next)
        return next
      } catch (e) {
        setError((e as Error).message)
        throw e
      }
    },
    [id],
  )

  if (!c) return <ErrorBox error={error} />

  const importPdf = async () => {
    try {
      await window.ius!.docs.importPdf(id)
      setC(await window.ius!.cases.get(id))
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const view = async (docId: string) => {
    const { doc, data } = await window.ius!.docs.read(id, docId)
    setViewer({ url: URL.createObjectURL(new Blob([new Uint8Array(data)], { type: 'application/pdf' })), name: doc.name })
  }
  const newDraft = async () => {
    const d: Draft = {
      id: uid(),
      title: 'Nuovo atto',
      html: '<h1>Titolo dell’atto</h1><p></p>',
      status: 'bozza',
      source: 'manuale',
      updatedAt: new Date().toISOString(),
    }
    await save({ drafts: [...c.drafts, d] })
    setDraftId(d.id)
  }
  const draft = c.drafts.find((d) => d.id === draftId)

  return (
    <>
      <header className="page-h">
        <button onClick={onBack}>← Fascicoli</button>
        <div>
          <h2>{c.title}</h2>
          <span className="muted">
            {c.client} {c.matter && `· ${c.matter}`} · creato {dt(c.createdAt)}
          </span>
        </div>
        <span className="badge ok">Cifrato localmente</span>
      </header>
      <div className="tabs">
        {TABS.map(([t, label]) => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {label}
          </button>
        ))}
      </div>
      <ErrorBox error={error} />

      {tab === 'docs' && (
        <Card title="Documenti del fascicolo" actions={<button className="primary" onClick={importPdf}>Importa PDF</button>}>
          <p className="muted">L&apos;originale viene conservato integro, cifrato, con impronta SHA-256 verificata a ogni apertura.</p>
          <table>
            <tbody>
              {c.documents.map((d) => (
                <tr key={d.id}>
                  <td>
                    <strong>{d.name}</strong>
                    <div className="muted mono">SHA-256 {d.sha256.slice(0, 16)}…</div>
                  </td>
                  <td>{(d.size / 1024).toFixed(0)} KB</td>
                  <td>{dt(d.importedAt)}</td>
                  <td className="row">
                    <button onClick={() => view(d.id)}>Visualizza</button>
                    <button onClick={() => window.ius!.docs.saveCopy(id, d.id)}>Esporta copia</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {viewer && (
            <div className="viewer">
              <div className="row between">
                <strong>{viewer.name}</strong>
                <button onClick={() => setViewer(null)}>Chiudi</button>
              </div>
              <iframe title={viewer.name} src={viewer.url} />
            </div>
          )}
        </Card>
      )}

      {tab === 'drafts' &&
        (draft ? (
          <Editor
            draft={draft}
            onClose={() => setDraftId(null)}
            onSave={async (d, extraAgenda) => {
              await save({
                drafts: c.drafts.map((x) => (x.id === d.id ? d : x)),
                ...(extraAgenda ? { agenda: [...c.agenda, extraAgenda] } : {}),
              })
            }}
          />
        ) : (
          <Card title="Atti e bozze" actions={<button className="primary" onClick={newDraft}>Nuovo atto</button>}>
            <table>
              <tbody>
                {c.drafts.map((d) => (
                  <tr key={d.id} className="clickable" onClick={() => setDraftId(d.id)}>
                    <td>
                      <strong>{d.title}</strong>
                    </td>
                    <td>
                      <span className={`badge ${d.status === 'approvata' ? 'ok' : 'warn'}`}>{d.status}</span>
                    </td>
                    <td className="muted">{d.source}</td>
                    <td>{dt(d.updatedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        ))}

      {tab === 'analysis' && (
        <Analysis
          c={c}
          save={save}
          openDraft={(dId) => {
            setDraftId(dId)
            setTab('drafts')
          }}
        />
      )}

      {tab === 'agenda' && <Agenda items={c.agenda} save={(agenda) => save({ agenda })} />}

      {tab === 'notes' && <Notes value={c.notes} save={(notes) => save({ notes })} />}
    </>
  )
}

function Agenda({ items, save }: { items: AgendaItem[]; save: (a: AgendaItem[]) => Promise<unknown> }) {
  const [form, setForm] = useState({ kind: 'appuntamento' as AgendaItem['kind'], title: '', date: '' })
  const add = async (e: FormEvent) => {
    e.preventDefault()
    await save([...items, { id: uid(), ...form, confirmed: true }])
    setForm({ ...form, title: '', date: '' })
  }
  const sorted = [...items].sort((a, b) => a.date.localeCompare(b.date))
  return (
    <Card title="Agenda del fascicolo">
      <form className="row wrap" onSubmit={add}>
        <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as AgendaItem['kind'] })}>
          <option value="appuntamento">Appuntamento</option>
          <option value="scadenza">Scadenza</option>
          <option value="attività">Attività</option>
        </select>
        <input placeholder="Descrizione" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
        <input type="datetime-local" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
        <button className="primary">Aggiungi</button>
      </form>
      <p className="muted">Le scadenze proposte da IUS restano “da confermare” finché l&apos;avvocato non le verifica.</p>
      <table>
        <tbody>
          {sorted.map((a) => (
            <tr key={a.id}>
              <td>{a.date ? new Date(a.date).toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' }) : 'data da definire'}</td>
              <td>{a.kind}</td>
              <td>
                {a.title}
                {a.note && <div className="muted">{a.note}</div>}
              </td>
              <td>
                {a.confirmed ? (
                  <span className="badge ok">confermato</span>
                ) : (
                  <button onClick={() => save(items.map((x) => (x.id === a.id ? { ...x, confirmed: true } : x)))}>Conferma</button>
                )}
              </td>
              <td>
                <button onClick={() => save(items.filter((x) => x.id !== a.id))}>Elimina</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function Notes({ value, save }: { value: string; save: (v: string) => Promise<unknown> }) {
  const [text, setText] = useState(value)
  const [saved, setSaved] = useState(true)
  return (
    <Card
      title="Note riservate"
      actions={
        <button className="primary" disabled={saved} onClick={() => save(text).then(() => setSaved(true))}>
          {saved ? 'Salvato' : 'Salva'}
        </button>
      }
    >
      <textarea
        rows={16}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setSaved(false)
        }}
      />
    </Card>
  )
}
