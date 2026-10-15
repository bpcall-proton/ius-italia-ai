'use strict'
const { contextBridge, ipcRenderer } = require('electron')

const call = (channel, ...args) =>
  ipcRenderer.invoke(channel, ...args).then((r) => {
    if (r && r.error) throw new Error(r.error)
    return r ? r.data : undefined
  })

contextBridge.exposeInMainWorld('ius', {
  backendUrl: process.env.IUS_BACKEND_URL || `http://127.0.0.1:${process.env.IUS_BACKEND_PORT || 8765}`,
  vault: {
    status: () => call('vault:status'),
    create: (passphrase) => call('vault:create', passphrase),
    unlock: (passphrase) => call('vault:unlock', passphrase),
    lock: () => call('vault:lock'),
  },
  cases: {
    list: () => call('cases:list'),
    create: (input) => call('cases:create', input),
    get: (id) => call('cases:get', id),
    update: (id, patch) => call('cases:update', id, patch),
  },
  docs: {
    importPdf: (caseId) => call('docs:import', caseId),
    read: (caseId, docId) => call('docs:read', caseId, docId),
    saveCopy: (caseId, docId) => call('docs:saveCopy', caseId, docId),
  },
  exportDocx: (bytes, name) => call('export:docx', bytes, name),
  exportPdf: (html, name) => call('export:pdf', html, name),
  print: (html) => call('print', html),
})
