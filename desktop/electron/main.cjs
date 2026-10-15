'use strict'
const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { spawn } = require('node:child_process')
const { Vault } = require('./vault.cjs')

const PORT = Number(process.env.IUS_BACKEND_PORT || 8765)
let win = null
let backend = null
let vault = null

function startBackend() {
  if (process.env.IUS_BACKEND_URL) return
  const exe = path.join(process.resourcesPath, 'backend', process.platform === 'win32' ? 'ius_server.exe' : 'ius_server')
  if (!app.isPackaged || !fs.existsSync(exe)) return
  const dataDir = path.join(app.getPath('userData'), 'server')
  fs.mkdirSync(dataDir, { recursive: true })
  backend = spawn(exe, ['--host', '127.0.0.1', '--port', String(PORT), '--data-dir', dataDir], {
    windowsHide: true,
    stdio: 'ignore',
  })
  backend.on('exit', () => (backend = null))
}

function printWindow(html) {
  const w = new BrowserWindow({ show: false, webPreferences: { sandbox: true, javascript: false } })
  return w.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`).then(() => w)
}

const handlers = {
  'vault:status': () => vault.status(),
  'vault:create': (p) => vault.create(p),
  'vault:unlock': (p) => vault.unlock(p),
  'vault:lock': () => vault.lock(),
  'cases:list': () => vault.listCases(),
  'cases:create': (input) => vault.createCase(input),
  'cases:get': (id) => vault.getCase(id),
  'cases:update': (id, patch) => vault.updateCase(id, patch),
  'docs:import': async (caseId) => {
    const r = await dialog.showOpenDialog(win, {
      title: 'Importa PDF nel fascicolo',
      filters: [{ name: 'PDF', extensions: ['pdf'] }],
      properties: ['openFile', 'multiSelections'],
    })
    if (r.canceled) return []
    return r.filePaths.map((f) => vault.importDocument(caseId, path.basename(f), fs.readFileSync(f)))
  },
  'docs:read': (caseId, docId) => {
    const { doc, data } = vault.readDocument(caseId, docId)
    return { doc, data: new Uint8Array(data) }
  },
  'docs:saveCopy': async (caseId, docId) => {
    const { doc, data } = vault.readDocument(caseId, docId)
    const r = await dialog.showSaveDialog(win, { defaultPath: doc.name, filters: [{ name: 'PDF', extensions: ['pdf'] }] })
    if (r.canceled || !r.filePath) return null
    fs.writeFileSync(r.filePath, data)
    return r.filePath
  },
  'export:docx': async (bytes, name) => {
    const r = await dialog.showSaveDialog(win, { defaultPath: `${name}.docx`, filters: [{ name: 'Word', extensions: ['docx'] }] })
    if (r.canceled || !r.filePath) return null
    fs.writeFileSync(r.filePath, Buffer.from(bytes))
    return r.filePath
  },
  'export:pdf': async (html, name) => {
    const r = await dialog.showSaveDialog(win, { defaultPath: `${name}.pdf`, filters: [{ name: 'PDF', extensions: ['pdf'] }] })
    if (r.canceled || !r.filePath) return null
    const w = await printWindow(html)
    try {
      fs.writeFileSync(r.filePath, await w.webContents.printToPDF({ pageSize: 'A4', printBackground: true }))
    } finally {
      w.destroy()
    }
    return r.filePath
  },
  print: async (html) => {
    const w = await printWindow(html)
    return new Promise((resolve) =>
      w.webContents.print({}, (ok, reason) => {
        w.destroy()
        resolve(ok ? 'ok' : reason)
      }),
    )
  },
}

function registerIpc() {
  for (const [channel, fn] of Object.entries(handlers)) {
    ipcMain.handle(channel, async (event, ...args) => {
      if (!win || event.sender !== win.webContents) return { error: 'Origine non autorizzata' }
      try {
        return { data: await fn(...args) }
      } catch (e) {
        return { error: e instanceof Error ? e.message : String(e) }
      }
    })
  }
}

function createWindow() {
  win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'IUS Italia AI',
    backgroundColor: '#0b1f3a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      plugins: true,
      spellcheck: true,
    },
  })
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e, url) => {
    if (!url.startsWith('file://') && !url.startsWith('http://localhost:5173')) e.preventDefault()
  })
  if (process.env.VITE_DEV_SERVER_URL) win.loadURL(process.env.VITE_DEV_SERVER_URL)
  else win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
}

app.whenReady().then(() => {
  vault = new Vault(path.join(app.getPath('userData'), 'vault'))
  if (app.isPackaged) Menu.setApplicationMenu(null)
  startBackend()
  registerIpc()
  createWindow()
})

app.on('window-all-closed', () => {
  if (vault) vault.lock()
  app.quit()
})

app.on('quit', () => {
  if (backend) backend.kill()
})
