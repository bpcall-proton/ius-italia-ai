import net from 'node:net'
import { describe, expect, it } from 'vitest'
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { findFreePort } = require('../electron/port.cjs')

describe('porta del server locale', () => {
  it('se la porta preferita è occupata ne usa una libera', async () => {
    const busy = net.createServer()
    await new Promise<void>((r) => busy.listen({ port: 0, host: '127.0.0.1' }, () => r()))
    const taken = (busy.address() as net.AddressInfo).port
    const port = await findFreePort(taken)
    expect(port).not.toBe(taken)
    expect(port).toBeGreaterThan(0)
    busy.close()
  })
})
