import { useEffect, useState } from 'react'
import { api, setToken, waitBackend } from './api'
import Admin from './admin/Admin'
import Lawyer from './lawyer/Lawyer'
import Login, { type Me } from './Login'

export default function App() {
  const [ready, setReady] = useState<boolean | null>(null)
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    waitBackend().then(setReady)
  }, [])

  const logout = async () => {
    await api('/auth/logout', {}).catch(() => undefined)
    setToken(null)
    await window.ius?.vault.lock().catch(() => undefined)
    setMe(null)
  }

  if (ready === null) return <div className="splash">Avvio di IUS Italia AI…</div>
  if (!ready)
    return (
      <div className="splash">
        Il servizio locale di IUS non risponde. Riavvia l&apos;applicazione.
      </div>
    )
  if (!me) return <Login onLogin={setMe} />
  return me.is_admin ? <Admin me={me} onLogout={logout} /> : <Lawyer me={me} onLogout={logout} />
}
