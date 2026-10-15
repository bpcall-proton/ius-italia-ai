import QRCode from 'qrcode'
import { type FormEvent, useState } from 'react'
import { api, setToken } from './api'
import { ErrorBox } from './ui'

export interface Me {
  id: string
  email: string
  first_name: string
  last_name: string
  role: string
  is_admin: boolean
  firm?: { id: string; name: string } | null
}

interface LoginOut {
  access_token?: string
  mfa_required?: boolean
  mfa_setup_required?: boolean
  challenge?: string
  otpauth_uri?: string
  secret?: string
}

export default function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [mode, setMode] = useState<'lawyer' | 'admin'>('lawyer')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mfa, setMfa] = useState<LoginOut | null>(null)
  const [qr, setQr] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const finish = async (accessToken: string) => {
    setToken(accessToken)
    onLogin(await api<Me>('/me'))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mfa?.challenge) {
        const r = await api<LoginOut>('/auth/mfa', { challenge: mfa.challenge, code: code.trim() })
        await finish(r.access_token!)
        return
      }
      const r = await api<LoginOut>('/auth/login', { email, password, device: 'IUS Desktop' })
      if (r.access_token) await finish(r.access_token)
      else {
        setMfa(r)
        if (r.otpauth_uri) setQr(await QRCode.toDataURL(r.otpauth_uri, { margin: 1, width: 180 }))
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const demo = mode === 'lawyer' ? ['avvocato@demo.ius', 'Demo-Avvocato-2026'] : ['admin@demo.ius', 'Demo-Admin-2026']

  return (
    <div className="login">
      <div className="login-brand">
        <div className="logo">IUS</div>
        <h1>IUS Italia AI</h1>
        <p>Dal fascicolo all&apos;atto, con le tue fonti, i tuoi documenti e il pieno controllo del tuo lavoro.</p>
      </div>
      <form className="login-box" onSubmit={submit}>
        <div className="tabs">
          {(['lawyer', 'admin'] as const).map((m) => (
            <button
              type="button"
              key={m}
              className={mode === m ? 'active' : ''}
              onClick={() => {
                setMode(m)
                setMfa(null)
                setQr(null)
                setError(null)
              }}
            >
              {m === 'lawyer' ? 'Avvocato / Studio' : 'Amministrazione'}
            </button>
          ))}
        </div>
        {!mfa ? (
          <>
            <label>
              Email
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
            </label>
            <label>
              Password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </label>
            {!(window.ius?.web && mode === 'admin') && (
            <button
              type="button"
              className="link"
              onClick={() => {
                setEmail(demo[0])
                setPassword(demo[1])
              }}
            >
              Usa account di prova ({demo[0]})
            </button>
            )}
          </>
        ) : (
          <>
            {mfa.mfa_setup_required && (
              <div className="mfa-setup">
                <p>Primo accesso amministratore: configura l&apos;autenticazione a due fattori con un&apos;app TOTP.</p>
                {qr && <img src={qr} alt="QR code MFA" />}
                <code>{mfa.secret}</code>
              </div>
            )}
            <label>
              Codice a 6 cifre
              <input inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} autoFocus required />
            </label>
          </>
        )}
        <ErrorBox error={error} />
        <button className="primary" disabled={busy}>
          {busy ? 'Verifica…' : mfa ? 'Verifica codice' : 'Accedi'}
        </button>
      </form>
    </div>
  )
}
