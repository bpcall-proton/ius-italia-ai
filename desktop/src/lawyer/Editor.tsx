import { useEffect, useRef, useState } from 'react'
import { htmlToDocx, printableHtml } from '../docx'
import { sanitizeHtml } from '../sanitize'
import type { AgendaItem, Draft } from '../types'
import { ErrorBox, uid } from '../ui'

const TOOLS: [string, string, string?][] = [
  ['bold', 'G'],
  ['italic', 'C'],
  ['underline', 'S'],
  ['formatBlock', 'Titolo', 'H2'],
  ['formatBlock', 'Paragrafo', 'P'],
  ['insertUnorderedList', '• Elenco'],
  ['insertOrderedList', '1. Elenco'],
  ['justifyLeft', 'Sx'],
  ['justifyCenter', 'Centro'],
  ['justifyFull', 'Giust.'],
]

export default function Editor({
  draft,
  onSave,
  onClose,
}: {
  draft: Draft
  onSave: (d: Draft, agenda?: AgendaItem) => Promise<void>
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [title, setTitle] = useState(draft.title)
  const [dirty, setDirty] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ref.current) ref.current.innerHTML = sanitizeHtml(draft.html)
  }, [draft.id, draft.html])

  const html = () => sanitizeHtml(ref.current?.innerHTML ?? '')
  const fileName = title.replace(/[\\/:*?"<>|]+/g, '_').slice(0, 80) || 'atto'

  const persist = async (patch: Partial<Draft> = {}, agenda?: AgendaItem) => {
    const content = html()
    const changed = content !== draft.html || title !== draft.title
    const next: Draft = {
      ...draft,
      title,
      html: content,
      updatedAt: new Date().toISOString(),
      ...(changed && draft.status === 'approvata' ? { status: 'bozza' as const, approvedAt: undefined } : {}),
      ...patch,
    }
    await onSave(next, agenda)
    setDirty(false)
    return next
  }

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setError(null)
    setMsg(null)
    try {
      const r = await fn()
      if (r !== null) setMsg(label)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const approve = () =>
    run('Atto approvato e salvato nel fascicolo.', async () => {
      const placeholders = (ref.current?.innerText.match(/\[DA COMPLETARE[^\]]*\]/g) ?? []).length
      const ok = window.confirm(
        (placeholders ? `Attenzione: ci sono ancora ${placeholders} campi [DA COMPLETARE].\n\n` : '') +
          'Confermi di aver revisionato personalmente l’atto e di approvarlo?',
      )
      if (!ok) return null
      const due = /entro\s+(\d{1,3})\s+giorni/i.exec(ref.current?.innerText ?? '')
      let agenda: AgendaItem | undefined
      if (due) {
        const d = new Date()
        d.setDate(d.getDate() + Number(due[1]))
        agenda = {
          id: uid(),
          kind: 'scadenza',
          title: `Verifica riscontro: ${title}`,
          date: `${d.toISOString().slice(0, 10)}T09:00`,
          note: `Termine di ${due[1]} giorni indicato nell’atto, calcolato dalla data di approvazione: da confermare.`,
          confirmed: false,
        }
      }
      return persist({ status: 'approvata', approvedAt: new Date().toISOString() }, agenda)
    })

  return (
    <div className="editor card">
      <div className="row between">
        <div className="row">
          <button onClick={onClose}>← Atti</button>
          <input
            className="title-input"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              setDirty(true)
            }}
          />
          <span className={`badge ${draft.status === 'approvata' ? 'ok' : 'warn'}`}>{draft.status}</span>
          {draft.source !== 'manuale' && <span className="badge info">{draft.source}</span>}
        </div>
        <div className="row">
          <button className="primary" onClick={() => run('Salvato.', () => persist())} disabled={!dirty}>
            Salva
          </button>
          <button onClick={approve}>Approva</button>
          <button onClick={() => run('DOCX esportato.', async () => window.ius!.exportDocx(await htmlToDocx(html(), title), fileName))}>
            DOCX
          </button>
          <button onClick={() => run('PDF esportato.', () => window.ius!.exportPdf(printableHtml(html(), title), fileName))}>PDF</button>
          <button onClick={() => run('Inviato alla stampante.', () => window.ius!.print(printableHtml(html(), title)))}>Stampa</button>
        </div>
      </div>
      <div className="toolbar">
        {TOOLS.map(([cmd, label, arg]) => (
          <button
            key={label}
            onMouseDown={(e) => {
              e.preventDefault()
              document.execCommand(cmd, false, arg)
              setDirty(true)
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {msg && <div className="success">{msg}</div>}
      <ErrorBox error={error} />
      <div ref={ref} className="page" contentEditable suppressContentEditableWarning spellCheck onInput={() => setDirty(true)} />
    </div>
  )
}
