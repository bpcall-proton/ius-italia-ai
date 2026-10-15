export const backendUrl = window.ius?.backendUrl ?? 'http://127.0.0.1:8765'

let token: string | null = null
export const setToken = (t: string | null) => {
  token = t
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function detail(data: unknown, status: number): string {
  const d = (data as { detail?: unknown })?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? '').join('; ')
  return `Errore ${status}`
}

function headers(): HeadersInit {
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

export async function api<T>(path: string, body?: unknown, method?: string): Promise<T> {
  const r = await fetch(backendUrl + path, {
    method: method ?? (body === undefined ? 'GET' : 'POST'),
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new ApiError(r.status, detail(data, r.status))
  return data as T
}

export async function stream(path: string, body: unknown, onEvent: (event: string, data: unknown) => void) {
  const r = await fetch(backendUrl + path, { method: 'POST', headers: headers(), body: JSON.stringify(body) })
  if (!r.ok || !r.body) {
    const data = await r.json().catch(() => ({}))
    throw new ApiError(r.status, detail(data, r.status))
  }
  const reader = r.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i: number
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7)
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) onEvent(event, JSON.parse(data))
    }
  }
}

export async function waitBackend(tries = 40): Promise<boolean> {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(`${backendUrl}/health`)
      if (r.ok) return true
    } catch {
      /* server in avvio */
    }
    await new Promise((res) => setTimeout(res, 500))
  }
  return false
}
