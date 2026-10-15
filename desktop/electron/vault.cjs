'use strict'
// Archivio locale cifrato: AES-256-GCM, chiave master derivata dalla passphrase (scrypt),
// una chiave casuale distinta per ogni fascicolo, cifrata con la chiave master.
const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const MAGIC = Buffer.from('IUS1')
const ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const DEFAULT_KDF = { N: 2 ** 16, r: 8, p: 1 }
const MAX_DOC = 200 * 1024 * 1024
const CASE_FIELDS = ['title', 'client', 'matter', 'notes', 'drafts', 'analyses', 'agenda']

function seal(key, plain, aad) {
  const iv = crypto.randomBytes(12)
  const c = crypto.createCipheriv('aes-256-gcm', key, iv)
  c.setAAD(Buffer.from(aad))
  const ct = Buffer.concat([c.update(plain), c.final()])
  return Buffer.concat([MAGIC, iv, c.getAuthTag(), ct])
}

function unseal(key, blob, aad) {
  if (blob.length < 32 || !blob.subarray(0, 4).equals(MAGIC)) throw new Error('File cifrato non valido')
  const d = crypto.createDecipheriv('aes-256-gcm', key, blob.subarray(4, 16))
  d.setAAD(Buffer.from(aad))
  d.setAuthTag(blob.subarray(16, 32))
  return Buffer.concat([d.update(blob.subarray(32)), d.final()])
}

function writeAtomic(file, data) {
  const tmp = `${file}.${process.pid}.tmp`
  fs.writeFileSync(tmp, data)
  fs.renameSync(tmp, file)
}

function checkId(id) {
  if (typeof id !== 'string' || !ID_RE.test(id)) throw new Error('Identificativo non valido')
  return id
}

class Vault {
  constructor(root, opts = {}) {
    this.root = root
    this.kdf = opts.kdf || DEFAULT_KDF
    this.key = null
  }

  get file() {
    return path.join(this.root, 'vault.json')
  }

  status() {
    return { exists: fs.existsSync(this.file), unlocked: !!this.key }
  }

  derive(passphrase, salt, kdf) {
    return crypto.scryptSync(String(passphrase).normalize('NFKC'), salt, 32, { ...kdf, maxmem: 256 * 1024 * 1024 })
  }

  create(passphrase) {
    if (this.status().exists) throw new Error('Archivio già esistente')
    if (String(passphrase).length < 10) throw new Error('La passphrase deve avere almeno 10 caratteri')
    fs.mkdirSync(path.join(this.root, 'cases'), { recursive: true })
    const salt = crypto.randomBytes(16)
    const key = this.derive(passphrase, salt, this.kdf)
    const meta = {
      version: 1,
      cipher: 'AES-256-GCM',
      kdf: { alg: 'scrypt', ...this.kdf, salt: salt.toString('base64') },
      check: seal(key, Buffer.from('IUS-VAULT-OK'), 'vault').toString('base64'),
      createdAt: new Date().toISOString(),
    }
    writeAtomic(this.file, JSON.stringify(meta, null, 2))
    this.key = key
    return this.status()
  }

  unlock(passphrase) {
    const meta = JSON.parse(fs.readFileSync(this.file, 'utf8'))
    const { alg, salt, ...kdf } = meta.kdf
    if (alg !== 'scrypt') throw new Error('Algoritmo non supportato')
    const key = this.derive(passphrase, Buffer.from(salt, 'base64'), kdf)
    try {
      unseal(key, Buffer.from(meta.check, 'base64'), 'vault')
    } catch {
      key.fill(0)
      throw new Error('Passphrase errata')
    }
    this.key = key
    return this.status()
  }

  lock() {
    if (this.key) this.key.fill(0)
    this.key = null
    return this.status()
  }

  master() {
    if (!this.key) throw new Error('Archivio bloccato')
    return this.key
  }

  dir(id) {
    return path.join(this.root, 'cases', checkId(id))
  }

  caseKey(id) {
    return unseal(this.master(), fs.readFileSync(path.join(this.dir(id), 'key.bin')), `case:${id}`)
  }

  readMeta(id, key = this.caseKey(id)) {
    return JSON.parse(unseal(key, fs.readFileSync(path.join(this.dir(id), 'meta.bin')), `meta:${id}`).toString('utf8'))
  }

  writeMeta(meta, key = this.caseKey(meta.id)) {
    meta.updatedAt = new Date().toISOString()
    writeAtomic(path.join(this.dir(meta.id), 'meta.bin'), seal(key, Buffer.from(JSON.stringify(meta)), `meta:${meta.id}`))
    return meta
  }

  listCases() {
    this.master()
    const base = path.join(this.root, 'cases')
    if (!fs.existsSync(base)) return []
    return fs
      .readdirSync(base)
      .filter((d) => ID_RE.test(d))
      .map((id) => {
        const m = this.readMeta(id)
        return {
          id,
          title: m.title,
          client: m.client,
          matter: m.matter,
          createdAt: m.createdAt,
          updatedAt: m.updatedAt,
          documents: m.documents.length,
          drafts: m.drafts.length,
          agenda: m.agenda.length,
        }
      })
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  }

  createCase(input) {
    const title = String(input?.title || '').trim()
    if (!title) throw new Error('Titolo obbligatorio')
    const id = crypto.randomUUID()
    const key = crypto.randomBytes(32)
    fs.mkdirSync(path.join(this.dir(id), 'docs'), { recursive: true })
    writeAtomic(path.join(this.dir(id), 'key.bin'), seal(this.master(), key, `case:${id}`))
    const now = new Date().toISOString()
    const meta = {
      id,
      title,
      client: String(input.client || ''),
      matter: String(input.matter || ''),
      notes: '',
      createdAt: now,
      documents: [],
      drafts: [],
      analyses: [],
      agenda: [],
    }
    return this.writeMeta(meta, key)
  }

  getCase(id) {
    return this.readMeta(id)
  }

  updateCase(id, patch) {
    const key = this.caseKey(id)
    const meta = this.readMeta(id, key)
    for (const f of CASE_FIELDS) if (patch && f in patch) meta[f] = patch[f]
    return this.writeMeta(meta, key)
  }

  importDocument(id, name, data) {
    const buf = Buffer.from(data)
    if (buf.length > MAX_DOC) throw new Error('File troppo grande (max 200 MB)')
    const isPdf = buf.subarray(0, 5).toString('latin1') === '%PDF-'
    if (!isPdf) throw new Error('Il file non è un PDF valido')
    const key = this.caseKey(id)
    const meta = this.readMeta(id, key)
    const docId = crypto.randomUUID()
    writeAtomic(path.join(this.dir(id), 'docs', `${docId}.bin`), seal(key, buf, `doc:${id}:${docId}`))
    const doc = {
      id: docId,
      name: path.basename(String(name)),
      mime: 'application/pdf',
      size: buf.length,
      sha256: crypto.createHash('sha256').update(buf).digest('hex'),
      importedAt: new Date().toISOString(),
    }
    meta.documents.push(doc)
    this.writeMeta(meta, key)
    return doc
  }

  readDocument(id, docId) {
    const key = this.caseKey(id)
    const doc = this.readMeta(id, key).documents.find((d) => d.id === checkId(docId))
    if (!doc) throw new Error('Documento non trovato')
    const buf = unseal(key, fs.readFileSync(path.join(this.dir(id), 'docs', `${docId}.bin`)), `doc:${id}:${docId}`)
    if (crypto.createHash('sha256').update(buf).digest('hex') !== doc.sha256) throw new Error('Integrità documento non verificata')
    return { doc, data: buf }
  }
}

module.exports = { Vault, seal, unseal }
