// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { sanitizeHtml } from '../src/sanitize'

describe('sanitizeHtml', () => {
  it('rimuove script, eventi e link mantenendo la formattazione', () => {
    const out = sanitizeHtml('<p style="text-align:center" onclick="x()">Ciao <b>avv.</b><script>alert(1)</script><a href="javascript:x">link</a><img src=x onerror=alert(1)></p>')
    expect(out).toBe('<p style="text-align: center;">Ciao <b>avv.</b>link</p>')
  })
})
