'use strict'
const net = require('node:net')

function isFree(port) {
  return new Promise((resolve) => {
    const s = net.createServer()
    s.once('error', () => resolve(false))
    s.listen({ port, host: '127.0.0.1', exclusive: true }, () => s.close(() => resolve(true)))
  })
}

// Prima la porta preferita, poi le successive; in ultimo una porta qualsiasi assegnata dal sistema.
async function findFreePort(preferred = 8765, tries = 50) {
  for (let p = preferred; p < preferred + tries; p++) if (await isFree(p)) return p
  return new Promise((resolve, reject) => {
    const s = net.createServer()
    s.once('error', reject)
    s.listen({ port: 0, host: '127.0.0.1' }, () => {
      const { port } = s.address()
      s.close(() => resolve(port))
    })
  })
}

module.exports = { findFreePort, isFree }
