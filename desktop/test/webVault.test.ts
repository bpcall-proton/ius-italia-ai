import 'fake-indexeddb/auto'
import { describe, expect, it } from 'vitest'
import { createWebVault } from '../src/web/bridge'

const pdf = new TextEncoder().encode('%PDF-1.4 SEGRETO-CANARY-123')

describe('archivio online nel browser', () => {
  it('cifra i documenti in IndexedDB e richiede la passphrase', async () => {
    const v = createWebVault(1000)
    await v.create('passphrase-lunga-1')
    const c = await v.createCase({ title: 'Rossi c. Bianchi', client: 'Rossi', matter: 'civile' })
    const doc = await v.importDocument(c.id, 'C:\\atti\\diffida.pdf', pdf)
    expect(doc.name).toBe('diffida.pdf')

    const raw: unknown[] = await new Promise((resolve) => {
      const r = indexedDB.open('ius-italia-ai')
      r.onsuccess = () => {
        const q = r.result.transaction('vault').objectStore('vault').getAll()
        q.onsuccess = () => resolve(q.result)
      }
    })
    const dump = raw.map((x) => (typeof x === 'string' ? x : new TextDecoder('latin1').decode(x as Uint8Array))).join('|')
    expect(dump).not.toContain('SEGRETO-CANARY')
    expect(dump).not.toContain('Rossi')

    await v.lock()
    await expect(v.listCases()).rejects.toThrow('Archivio bloccato')
    await expect(v.unlock('sbagliata-123')).rejects.toThrow('Passphrase errata')
    await v.unlock('passphrase-lunga-1')
    const { data } = await v.readDocument(c.id, doc.id)
    expect(new TextDecoder().decode(data)).toContain('SEGRETO-CANARY')
    expect((await v.listCases())[0].documents).toBe(1)
    await expect(v.importDocument(c.id, 'x.pdf', new TextEncoder().encode('ciao'))).rejects.toThrow('PDF')
  })
})
