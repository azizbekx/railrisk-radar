import { Activity, Bot, Building2, Compass, Target, GitCompareArrows, Globe, LogOut, MessagesSquare, Radar, ScanSearch, SlidersHorizontal, Users, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { post } from '../lib/api'
import { LEVEL } from '../lib/chart'
import { MAX_SHORTLIST, OFFICIAL_LENS, useApp, useLens, type Page } from '../lib/store'
import type { SupplierRow } from '../lib/types'
import { clsx, Select } from './ui'

const NAV: { page: Page; label: string; icon: React.ReactNode; hint: string }[] = [
  { page: 'source', label: 'Find suppliers', icon: <Target className="size-[18px]" />, hint: 'Agents pick your top 3' },
  { page: 'explore', label: 'Explore suppliers', icon: <Compass className="size-[18px]" />, hint: 'Filter & rank 10,000' },
  { page: 'compare', label: 'Compare shortlist', icon: <GitCompareArrows className="size-[18px]" />, hint: 'Up to 20 side by side' },
  { page: 'team', label: 'Agent team', icon: <Users className="size-[18px]" />, hint: 'Multi-agent decision' },
  { page: 'profile', label: 'Supplier profile', icon: <ScanSearch className="size-[18px]" />, hint: 'Why is the TRI high?' },
  { page: 'chat', label: 'Ask the data', icon: <MessagesSquare className="size-[18px]" />, hint: 'Grounded assistant' },
  { page: 'research', label: 'Research agent', icon: <Building2 className="size-[18px]" />, hint: 'Real company due diligence' },
  { page: 'tracking', label: 'Live tracking', icon: <Activity className="size-[18px]" />, hint: 'Daily agent monitoring' },
]

export function Sidebar({ user, onLogout }: { user: string | null; onLogout: () => void }) {
  const { page, go, shortlist, removeFromShortlist, setShortlist, lensName, setLens, meta, openProfile } = useApp()
  const lens = useLens()
  const [rows, setRows] = useState<SupplierRow[]>([])

  useEffect(() => {
    if (!shortlist.length) { setRows([]); return }
    post<SupplierRow[]>('/rows', { ids: shortlist }).then(setRows).catch(() => {})
  }, [shortlist])

  const top = lens.weights ?? meta?.lenses[OFFICIAL_LENS]
  const topWeights = top ? Object.entries(top).sort((a, b) => b[1] - a[1]).slice(0, 3) : []

  return (
    <aside className="flex h-full w-[272px] shrink-0 flex-col gap-4 overflow-y-auto border-r border-line bg-surface px-4 py-5">
      <div className="flex items-center gap-2.5 px-2">
        <div className="grid size-9 place-items-center rounded-xl bg-accent text-white shadow-sm"><Radar className="size-5" /></div>
        <div>
          <div className="text-[15px] leading-tight font-bold tracking-tight">RailRisk Radar</div>
          <div className="text-[11px] text-muted">Supplier risk intelligence</div>
        </div>
      </div>

      <nav className="flex flex-col gap-0.5">
        {NAV.map(n => (
          <button key={n.page} onClick={() => go(n.page)}
            className={clsx('group flex items-center gap-3 rounded-2xl px-3 py-2.5 text-left transition',
              page === n.page ? 'bg-accent-soft text-accent-strong' : 'text-ink-2 hover:bg-sunken hover:text-ink')}>
            <span className={clsx(page === n.page ? 'text-accent' : 'text-muted group-hover:text-ink-2')}>{n.icon}</span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">{n.label}</span>
              <span className={clsx('block text-[11px]', page === n.page ? 'text-accent/80' : 'text-muted')}>{n.hint}</span>
            </span>
            {n.page === 'compare' && shortlist.length > 0 && (
              <span className="ml-auto rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold text-white">{shortlist.length}</span>
            )}
          </button>
        ))}
      </nav>

      <div className="rounded-2xl border border-line bg-sunken/70 p-3">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-ink"><SlidersHorizontal className="size-3.5 text-accent" />Risk lens</div>
        <Select value={lensName} onChange={e => setLens(e.target.value)} className="h-9 text-xs">
          {Object.keys(meta?.lenses ?? { [OFFICIAL_LENS]: 1 }).map(n => <option key={n}>{n}</option>)}
          <option>Custom</option>
        </Select>
        <div className="mt-2 text-[11px] leading-relaxed text-muted">
          {topWeights.map(([k, v]) => `${k.replace('_Score', '').replace(/_/g, ' ')} ${Math.round(v * 100)}%`).join(' · ')}
        </div>
        {lensName === 'Custom' && page !== 'explore' && (
          <button onClick={() => go('explore')} className="mt-1.5 text-[11px] font-semibold text-accent hover:underline">Edit weights in Explore suppliers</button>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col rounded-2xl border border-line p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-semibold text-ink">Shortlist <span className="font-normal text-muted">{shortlist.length}/{MAX_SHORTLIST}</span></span>
          {shortlist.length > 0 && <button onClick={() => setShortlist([])} className="text-[11px] font-semibold text-muted hover:text-critical-ink">Clear</button>}
        </div>
        {rows.length === 0 ? (
          <div className="rounded-xl bg-sunken px-3 py-4 text-center text-[11px] leading-relaxed text-muted">Empty. Add suppliers from Find suppliers, a profile or the assistant.</div>
        ) : (
          <div className="-mx-1 flex flex-col gap-0.5 overflow-y-auto">
            {rows.map(r => (
              <div key={r.id} className="group flex items-center gap-2 rounded-xl px-1.5 py-1 hover:bg-sunken">
                <span className="size-2 shrink-0 rounded-full" style={{ background: LEVEL[r.level].dot }} />
                <button onClick={() => openProfile(r.id)} className="min-w-0 flex-1 truncate text-left text-xs font-medium text-ink-2 hover:text-ink">{r.id}</button>
                <span className="text-xs font-semibold text-ink tabular-nums">{r.tri}</span>
                <button onClick={() => removeFromShortlist(r.id)} className="text-muted opacity-0 group-hover:opacity-100 hover:text-critical-ink"><X className="size-3.5" /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-1.5 px-2 text-[11px] text-muted">
        <div className="flex items-center gap-1.5"><Bot className="size-3.5" />
          <span className="truncate" title={meta?.model ?? undefined}>{meta?.keys.llm ? 'Nemotron' : 'No LLM key'}{meta?.model && <span className="ml-1 font-mono text-[10px]">{meta.model}</span>}</span>
          <span className={clsx('ml-auto size-1.5 rounded-full', meta?.keys.llm ? 'bg-low-dot' : 'bg-critical-dot')} />
        </div>
        <div className="flex items-center gap-1.5"><Globe className="size-3.5" />
          <span className="truncate">Web search</span>
          <span className={clsx('ml-auto size-1.5 rounded-full', meta?.keys.tavily ? 'bg-low-dot' : 'bg-critical-dot')} />
        </div>
        {meta && (
          <div className="leading-relaxed">
            {meta.summary.suppliers.toLocaleString()} anonymized suppliers · avg TRI {meta.summary.avg_tri} · {meta.summary.critical} Critical · {meta.summary.high.toLocaleString()} High · €{(meta.summary.po_volume / 1e9).toFixed(1)}bn purchase volume. TRI formula reproduced exactly ({Math.round(meta.tri_check * 100)}% of rows).
          </div>
        )}
        {user && user !== 'guest' && (
          <button onClick={onLogout} className="flex items-center gap-1.5 hover:text-ink"><LogOut className="size-3.5" />Sign out {user}</button>
        )}
      </div>
    </aside>
  )
}
