import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { describe, expect, it } from 'vitest'

const { Vault } = createRequire(import.meta.url)('../electron/vault.cjs')
const KDF = { N: 2 ** 10, r: 8, p: 1 }
const PDF = Buffer.from('%PDF-1.4\nCONTENUTO-RISERVATO-XYZ\n%%EOF')
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'ius-vault-'))

function walk(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]))
}

describe('vault locale cifrato', () => {
  it('cifra fascicoli e documenti e li riapre con la passphrase corretta', () => {
    const root = tmp()
    const v = new Vault(root, { kdf: KDF })
    v.create('passphrase-di-prova')
    const c = v.createCase({ title: 'Rossi c/ Bianchi', client: 'Mario Rossi' })
    const doc = v.importDocument(c.id, 'atto.pdf', PDF)
    v.updateCase(c.id, { notes: 'nota riservata' })
    for (const f of walk(root)) {
      const raw = fs.readFileSync(f)
      expect(raw.includes('CONTENUTO-RISERVATO')).toBe(false)
      expect(raw.includes('Rossi')).toBe(false)
      expect(raw.includes('nota riservata')).toBe(false)
    }
    v.lock()
    expect(() => v.listCases()).toThrow('Archivio bloccato')

    const v2 = new Vault(root)
    expect(() => v2.unlock('passphrase-sbagliata')).toThrow('Passphrase errata')
    v2.unlock('passphrase-di-prova')
    expect(v2.listCases()[0].title).toBe('Rossi c/ Bianchi')
    expect(v2.getCase(c.id).notes).toBe('nota riservata')
    expect(Buffer.from(v2.readDocument(c.id, doc.id).data).equals(PDF)).toBe(true)
  })

  it('usa chiavi distinte per fascicolo e rileva manomissioni', () => {
    const root = tmp()
    const v = new Vault(root, { kdf: KDF })
    v.create('passphrase-di-prova')
    const a = v.createCase({ title: 'A' })
    const b = v.createCase({ title: 'B' })
    expect(v.caseKey(a.id).equals(v.caseKey(b.id))).toBe(false)
    const doc = v.importDocument(a.id, 'x.pdf', PDF)
    const f = path.join(root, 'cases', a.id, 'docs', `${doc.id}.bin`)
    const raw = fs.readFileSync(f)
    raw[raw.length - 1] ^= 1
    fs.writeFileSync(f, raw)
    expect(() => v.readDocument(a.id, doc.id)).toThrow()
    fs.copyFileSync(path.join(root, 'cases', b.id, 'meta.bin'), path.join(root, 'cases', a.id, 'meta.bin'))
    expect(() => v.getCase(a.id)).toThrow()
  })

  it('rifiuta file non PDF e identificativi non validi', () => {
    const v = new Vault(tmp(), { kdf: KDF })
    v.create('passphrase-di-prova')
    const c = v.createCase({ title: 'C' })
    expect(() => v.importDocument(c.id, 'x.pdf', Buffer.from('MZ...'))).toThrow('PDF')
    expect(() => v.getCase('../../etc')).toThrow('Identificativo non valido')
    expect(() => new Vault(tmp(), { kdf: KDF }).create('corta')).toThrow('10 caratteri')
  })
})
