import { CheckCircle2, Loader2, Radar, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { Button, Card, Input } from './components/ui'
import { get, post } from './lib/api'
import { useApp } from './lib/store'
import type { Meta } from './lib/types'
import Chat from './pages/chat'
import Compare from './pages/compare'
import Explore from './pages/explore'
import Profile from './pages/profile'
import Research from './pages/research'
import Source from './pages/source'
import Team from './pages/team'
import Tracking from './pages/tracking'

function Login({ onDone }: { onDone: (u: string) => void }) {
  const [u, setU] = useState(''), [p, setP] = useState(''), [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    try { onDone((await post<{ user: string }>('/login', { username: u, password: p })).user) }
    catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="grid min-h-full place-items-center bg-[radial-gradient(ellipse_at_top,var(--color-accent-soft),transparent_60%)] p-4">
      <Card className="w-full max-w-sm p-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid size-11 place-items-center rounded-2xl bg-accent text-white"><Radar className="size-6" /></div>
          <div><div className="text-lg font-bold">RailRisk Radar</div><div className="text-xs text-muted">Supplier risk intelligence for rail procurement</div></div>
        </div>
        <form onSubmit={submit} className="space-y-3">
          <Input placeholder="Username" value={u} onChange={e => setU(e.target.value)} autoFocus />
          <Input placeholder="Password" type="password" value={p} onChange={e => setP(e.target.value)} />
          {err && <div className="text-xs font-medium text-critical-ink">{err}</div>}
          <Button variant="primary" className="w-full" loading={busy} type="submit">Sign in</Button>
        </form>
      </Card>
    </div>
  )
}

function Toast() {
  const toast = useApp(s => s.toast)
  const [shown, setShown] = useState(toast)
  useEffect(() => {
    if (!toast) return
    setShown(toast)
    const t = setTimeout(() => setShown(null), 2600)
    return () => clearTimeout(t)
  }, [toast])
  if (!shown) return null
  return (
    <div key={shown.id} className="rr-in fixed right-6 bottom-6 z-50 flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2.5 text-sm font-medium shadow-[var(--shadow-pop)]">
      {shown.tone === 'warn' ? <TriangleAlert className="size-4 text-high-dot" /> : <CheckCircle2 className="size-4 text-low-dot" />}
      {shown.text}
    </div>
  )
}

const PAGES = { source: Source, explore: Explore, compare: Compare, team: Team, profile: Profile, chat: Chat, research: Research, tracking: Tracking }

export default function App() {
  const { page, setMeta, meta } = useApp()
  const [auth, setAuth] = useState<{ user: string | null; login_required: boolean } | null>(null)

  useEffect(() => {
    get<{ user: string | null; login_required: boolean }>('/me').then(setAuth).catch(() => setAuth({ user: null, login_required: true }))
    const onUnauth = () => setAuth(a => ({ login_required: true, ...a, user: null }))
    window.addEventListener('rr:unauthorized', onUnauth)
    const onHash = () => {
      const h = window.location.hash.replace('#/', '').split('/')[0]
      if (h in PAGES) useApp.setState({ page: h as keyof typeof PAGES })
    }
    window.addEventListener('hashchange', onHash)
    return () => { window.removeEventListener('rr:unauthorized', onUnauth); window.removeEventListener('hashchange', onHash) }
  }, [])

  useEffect(() => { if (auth?.user) get<Meta>('/meta').then(setMeta).catch(() => {}) }, [auth?.user, setMeta])

  if (!auth) return <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-accent" /></div>
  if (!auth.user) return <Login onDone={user => setAuth({ ...auth, user })} />

  const PageView = PAGES[page]
  return (
    <div className="flex h-full">
      <Sidebar user={auth.user} onLogout={() => post('/logout').finally(() => setAuth({ ...auth, user: null }))} />
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-8 py-7">
          {meta ? <PageView /> : <div className="grid h-64 place-items-center"><Loader2 className="size-6 animate-spin text-accent" /></div>}
        </div>
      </main>
      <Toast />
    </div>
  )
}
