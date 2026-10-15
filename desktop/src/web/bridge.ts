// Archivio del browser per la versione online: i fascicoli restano sul PC dell'utente (IndexedDB),
// cifrati con AES-256-GCM. Chiave master da PBKDF2-SHA256, una chiave casuale per ogni fascicolo.
import type { CaseData, CaseSummary, DocMeta } from '../types'

const DB = 'ius-italia-ai'
const STORE = 'vault'
const ITER = 600_000
const MAX_DOC = 200 * 1024 * 1024
const CASE_FIELDS = ['title', 'client', 'matter', 'notes', 'drafts', 'analyses', 'agenda'] as const
const enc = new TextEncoder()
const dec = new TextDecoder()

type Rec = Uint8Array | string
interface VaultMeta {
  version: 1
  kdf: { alg: 'PBKDF2-SHA256'; iterations: number; salt: string }
  check: string
  createdAt: string
}

const b64 = (u: Uint8Array) => btoa(String.fromCharCode(...u))
const unb64 = (s: string) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0))
const buf = (u: Uint8Array) => u.buffer.slice(u.byteOffset, u.byteOffset + u.byteLength) as ArrayBuffer

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1)
    r.onupgradeneeded = () => r.result.createObjectStore(STORE)
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await openDb()
  try {
    return await new Promise<T>((resolve, reject) => {
      const t = db.transaction(STORE, mode)
      const req = fn(t.objectStore(STORE))
      t.oncomplete = () => resolve(req.result)
      t.onerror = () => reject(t.error)
    })
  } finally {
    db.close()
  }
}

const get = <T extends Rec>(k: string) => tx<T | undefined>('readonly', (s) => s.get(k))
const put = (k: string, v: Rec) => tx('readwrite', (s) => s.put(v, k))
const keys = () => tx('readonly', (s) => s.getAllKeys()) as Promise<string[]>

async function seal(key: CryptoKey, plain: Uint8Array, aad: string): Promise<Uint8Array> {
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: enc.encode(aad) }, key, buf(plain)))
  const out = new Uint8Array(12 + ct.length)
  out.set(iv)
  out.set(ct, 12)
  return out
}

async function unseal(key: CryptoKey, blob: Uint8Array, aad: string): Promise<Uint8Array> {
  const plain = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: buf(blob.subarray(0, 12)), additionalData: enc.encode(aad) },
    key,
    buf(blob.subarray(12)),
  )
  return new Uint8Array(plain)
}

const aes = (raw: Uint8Array) => crypto.subtle.importKey('raw', buf(raw), 'AES-GCM', false, ['encrypt', 'decrypt'])
const sha256 = async (u: Uint8Array) =>
  Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buf(u))), (b) => b.toString(16).padStart(2, '0')).join('')

async function derive(passphrase: string, salt: Uint8Array, iterations: number): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey('raw', enc.encode(passphrase.normalize('NFKC')), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt: buf(salt), iterations }, base, { name: 'AES-GCM', length: 256 }, false, [
    'encrypt',
    'decrypt',
  ])
}

export function createWebVault(iterations = ITER) {
  let master: CryptoKey | null = null
  const status = async () => ({ exists: !!(await get('vault')), unlocked: !!master })
  const need = () => {
    if (!master) throw new Error('Archivio bloccato')
    return master
  }
  const caseKey = async (id: string) => {
    const k = await get<Uint8Array>(`case:${id}:key`)
    if (!k) throw new Error('Fascicolo non trovato')
    return aes(await unseal(need(), k, `case:${id}`))
  }
  const readMeta = async (id: string, key?: CryptoKey): Promise<CaseData> => {
    const m = await get<Uint8Array>(`case:${id}:meta`)
    if (!m) throw new Error('Fascicolo non trovato')
    return JSON.parse(dec.decode(await unseal(key ?? (await caseKey(id)), m, `meta:${id}`)))
  }
  const writeMeta = async (meta: CaseData, key: CryptoKey) => {
    meta.updatedAt = new Date().toISOString()
    await put(`case:${meta.id}:meta`, await seal(key, enc.encode(JSON.stringify(meta)), `meta:${meta.id}`))
    return meta
  }
  const readDoc = async (id: string, docId: string) => {
    const key = await caseKey(id)
    const doc = (await readMeta(id, key)).documents.find((d) => d.id === docId)
    const blob = await get<Uint8Array>(`doc:${id}:${docId}`)
    if (!doc || !blob) throw new Error('Documento non trovato')
    const data = await unseal(key, blob, `doc:${id}:${docId}`)
    if ((await sha256(data)) !== doc.sha256) throw new Error('Integrità documento non verificata')
    return { doc, data }
  }

  return {
    status,
    async create(passphrase: string) {
      if ((await status()).exists) throw new Error('Archivio già esistente')
      if (passphrase.length < 10) throw new Error('La passphrase deve avere almeno 10 caratteri')
      const salt = crypto.getRandomValues(new Uint8Array(16))
      const key = await derive(passphrase, salt, iterations)
      const meta: VaultMeta = {
        version: 1,
        kdf: { alg: 'PBKDF2-SHA256', iterations, salt: b64(salt) },
        check: b64(await seal(key, enc.encode('IUS-VAULT-OK'), 'vault')),
        createdAt: new Date().toISOString(),
      }
      await put('vault', JSON.stringify(meta))
      master = key
      return status()
    },
    async unlock(passphrase: string) {
      const raw = await get<string>('vault')
      if (!raw) throw new Error('Archivio non trovato')
      const meta: VaultMeta = JSON.parse(raw)
      const key = await derive(passphrase, unb64(meta.kdf.salt), meta.kdf.iterations)
      try {
        await unseal(key, unb64(meta.check), 'vault')
      } catch {
        throw new Error('Passphrase errata')
      }
      master = key
      return status()
    },
    async lock() {
      master = null
      return status()
    },
    async listCases(): Promise<CaseSummary[]> {
      need()
      const ids = (await keys()).filter((k) => k.endsWith(':meta')).map((k) => k.slice(5, -5))
      const out: CaseSummary[] = []
      for (const id of ids) {
        const m = await readMeta(id)
        out.push({
          id,
          title: m.title,
          client: m.client,
          matter: m.matter,
          createdAt: m.createdAt,
          updatedAt: m.updatedAt,
          documents: m.documents.length,
          drafts: m.drafts.length,
          agenda: m.agenda.length,
        })
      }
      return out.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
    },
    async createCase(input: { title: string; client: string; matter: string }) {
      const title = String(input?.title || '').trim()
      if (!title) throw new Error('Titolo obbligatorio')
      const id = crypto.randomUUID()
      const raw = crypto.getRandomValues(new Uint8Array(32))
      await put(`case:${id}:key`, await seal(need(), raw, `case:${id}`))
      const now = new Date().toISOString()
      const meta: CaseData = {
        id,
        title,
        client: String(input.client || ''),
        matter: String(input.matter || ''),
        notes: '',
        createdAt: now,
        updatedAt: now,
        documents: [],
        drafts: [],
        analyses: [],
        agenda: [],
      }
      return writeMeta(meta, await aes(raw))
    },
    getCase: (id: string) => readMeta(id),
    async updateCase(id: string, patch: Partial<CaseData>) {
      const key = await caseKey(id)
      const meta = await readMeta(id, key)
      const target = meta as unknown as Record<string, unknown>
      for (const f of CASE_FIELDS) if (patch && f in patch) target[f] = patch[f]
      return writeMeta(meta, key)
    },
    async importDocument(id: string, name: string, data: Uint8Array): Promise<DocMeta> {
      if (data.length > MAX_DOC) throw new Error('File troppo grande (max 200 MB)')
      if (dec.decode(data.subarray(0, 5)) !== '%PDF-') throw new Error('Il file non è un PDF valido')
      const key = await caseKey(id)
      const meta = await readMeta(id, key)
      const docId = crypto.randomUUID()
      await put(`doc:${id}:${docId}`, await seal(key, data, `doc:${id}:${docId}`))
      const doc: DocMeta = {
        id: docId,
        name: name.split(/[\\/]/).pop() || 'documento.pdf',
        mime: 'application/pdf',
        size: data.length,
        sha256: await sha256(data),
        importedAt: new Date().toISOString(),
      }
      meta.documents.push(doc)
      await writeMeta(meta, key)
      return doc
    },
    readDocument: readDoc,
  }
}

function pickPdfs(): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/pdf,.pdf'
    input.multiple = true
    input.onchange = () => resolve(Array.from(input.files ?? []))
    input.oncancel = () => resolve([])
    input.click()
  })
}

function download(data: BlobPart, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([data], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
  return name
}

function printHtml(html: string): Promise<string> {
  return new Promise((resolve) => {
    const frame = document.createElement('iframe')
    frame.style.cssText = 'position:fixed;width:0;height:0;border:0'
    frame.setAttribute('sandbox', 'allow-modals allow-same-origin')
    frame.srcdoc = html
    frame.onload = () => {
      frame.contentWindow?.print()
      setTimeout(() => frame.remove(), 1000)
      resolve('ok')
    }
    document.body.appendChild(frame)
  })
}

export function installWebBridge() {
  if (window.ius) return
  const v = createWebVault()
  window.ius = {
    web: true,
    backendUrl: import.meta.env.VITE_BACKEND_URL || window.location.origin,
    vault: { status: v.status, create: v.create, unlock: v.unlock, lock: v.lock },
    cases: { list: v.listCases, create: v.createCase, get: v.getCase, update: v.updateCase },
    docs: {
      async importPdf(caseId) {
        const out: DocMeta[] = []
        for (const f of await pickPdfs()) out.push(await v.importDocument(caseId, f.name, new Uint8Array(await f.arrayBuffer())))
        return out
      },
      read: v.readDocument,
      async saveCopy(caseId, docId) {
        const { doc, data } = await v.readDocument(caseId, docId)
        return download(buf(data), doc.name, 'application/pdf')
      },
    },
    exportDocx: async (bytes, name) =>
      download(buf(bytes), `${name}.docx`, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
    exportPdf: (html) => printHtml(html),
    print: (html) => printHtml(html),
  }
}
