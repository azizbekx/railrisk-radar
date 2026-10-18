// compare page. Owned by the compare slice. Side-by-side comparison of the shortlist (up to 20 suppliers).
import { ArrowRight, Layers, Scale, Sparkles, Trophy, Users, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { SupplierPicker } from '../components/SupplierPicker'
import { Button, Card, CardHeader, Empty, LevelBadge, PageHeader, Skeleton, Tag } from '../components/ui'
import { post } from '../lib/api'
import { eur, num } from '../lib/format'
import { JURY_EXAMPLE, MAX_SHORTLIST, useApp, useLens } from '../lib/store'
import { Heatmap } from './compare/Heatmap'
import { HeadToHead } from './compare/HeadToHead'
import { ProfileOverlay } from './compare/ProfileOverlay'
import { TriComposition } from './compare/TriComposition'
import type { CompareResp } from './compare/types'

export default function Page() {
  const { shortlist, removeFromShortlist, addToShortlist, setShortlist, openProfile, go } = useApp()
  const lens = useLens()
  const [data, setData] = useState<CompareResp | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const ids = shortlist.slice(0, 20)
  const key = ids.join(',') + '|' + lens.name + '|' + JSON.stringify(lens.weights)

  useEffect(() => {
    if (ids.length < 2) { setData(null); return }
    let cancelled = false
    setLoading(true); setError('')
    post<CompareResp>('/compare', { ids, lens_weights: lens.weights }).then(r => { if (!cancelled) setData(r) })
      .catch(e => { if (!cancelled) setError(e.message || 'Failed to compare') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return (
    <div>
      <PageHeader
        title="Compare shortlist"
        subtitle={`${shortlist.length} supplier${shortlist.length === 1 ? '' : 's'} shortlisted${shortlist.length > 20 ? ' · showing the first 20' : ''}`}
        icon={<Scale className="size-5" />}
        actions={<>
          <SupplierPicker placeholder={`Add supplier by ID or name (up to ${MAX_SHORTLIST})`} onSelect={id => addToShortlist([id])} />
          <Button variant="secondary" icon={<Users className="size-4" />} title={JURY_EXAMPLE.join(', ')} onClick={() => setShortlist(JURY_EXAMPLE)}>Jury example</Button>
          {shortlist.length > 0 && <Button variant="ghost" onClick={() => setShortlist([])}>Clear shortlist</Button>}
        </>}
      />

      {shortlist.length === 0 && (
        <Empty icon={<Layers className="size-6" />} title="Your shortlist is empty"
          action={<div className="flex flex-wrap justify-center gap-2">
            <Button variant="primary" onClick={() => go('explore')}>Find suppliers to compare</Button>
            <Button onClick={() => setShortlist(JURY_EXAMPLE)}>Load jury example</Button>
          </div>}>
          Tick suppliers in Explore, or ask the assistant to shortlist some, then come back here to rank and compare them side by side.
        </Empty>
      )}

      {shortlist.length === 1 && (
        <Empty icon={<Layers className="size-6" />} title="Add one more supplier"
          action={<div className="flex flex-wrap justify-center gap-2">
            <Button variant="primary" onClick={() => go('explore')}>Back to Explore</Button>
            <Button onClick={() => setShortlist(JURY_EXAMPLE)}>Load jury example</Button>
          </div>}>
          Comparison needs at least two suppliers. You currently have one shortlisted.
        </Empty>
      )}

      {ids.length >= 2 && (
        <div className="space-y-6">
          {loading && !data && <Skeleton className="h-64" />}
          {error && <Card className="border-critical text-sm text-critical-ink">{error}</Card>}

          {data && data.ranking.length > 0 && (
            <>
              <Winner data={data} onOpen={openProfile} />

              <Card>
                <CardHeader title="Ranking" subtitle={`Sorted by ${data.lens_label === 'TRI' ? 'Total Risk Index' : lens.name}, lowest risk first`} icon={<Trophy className="size-4" />} />
                <RankingTable data={data} onOpen={openProfile} onRemove={removeFromShortlist} />
              </Card>

              <Card>
                <CardHeader title="18-score heatmap" subtitle="Columns grouped by risk family · outlined cell = best in this shortlist" />
                <Heatmap data={data} order={data.ids} />
              </Card>

              <Card>
                <CardHeader title="Where each TRI comes from" subtitle="Weighted points contributed by each risk family" />
                <TriComposition data={data} order={data.ids} />
              </Card>

              <Card>
                <CardHeader title="Risk profile overlay" subtitle="Pick up to 5 suppliers to compare across all 18 scores" icon={<Sparkles className="size-4" />} />
                <ProfileOverlay data={data} order={data.ids} />
              </Card>

              <Card>
                <CardHeader title="Head to head" subtitle="Score-by-score difference and operational metrics for two suppliers" />
                <HeadToHead data={data} order={data.ids} />
              </Card>

              <Card className="flex flex-col items-start justify-between gap-3 bg-accent-soft/60 sm:flex-row sm:items-center">
                <div>
                  <div className="text-sm font-semibold text-ink">Let the agent team weigh in</div>
                  <div className="text-xs text-ink-2">Run Financial, Quality, Compliance and ESG agents over this shortlist and get a defensible recommendation.</div>
                </div>
                <Button variant="primary" icon={<ArrowRight className="size-4" />} onClick={() => go('team')}>Open Agent team</Button>
              </Card>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function Winner({ data, onOpen }: { data: CompareResp; onOpen: (id: string) => void }) {
  const lead = data.ranking[0]
  const runner = data.ranking[1]
  const metric = data.lens_label === 'TRI' ? 'tri' : 'lens_index'
  return (
    <Card className="border-accent/30 bg-gradient-to-br from-accent-soft/70 to-surface">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div className="grid size-11 shrink-0 place-items-center rounded-2xl bg-accent text-white"><Trophy className="size-5" /></div>
          <div>
            <div className="text-xs font-semibold tracking-wide text-accent-strong uppercase">Lowest risk in this shortlist</div>
            <div className="mt-0.5 text-lg font-bold text-ink">{lead.id} · {lead.name}</div>
            <p className="mt-1 max-w-2xl text-sm text-ink-2">
              {data.lens_label} {num(lead[metric] ?? lead.tri, 1)}
              {runner && <> — runner-up {runner.id} at {num(runner[metric] ?? runner.tri, 1)}.</>}{' '}
              {lead.critical_scores > 0 ? `${lead.critical_scores} critical-level score(s).` : 'No critical-level scores.'}
              {lead.best_at.length > 0 && <> Safest in the set at {lead.best_at.slice(0, 3).join(', ')}.</>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <LevelBadge level={lead.level} value={lead.tri} />
          <Button size="sm" onClick={() => onOpen(lead.id)}>View profile</Button>
        </div>
      </div>
    </Card>
  )
}

function RankingTable({ data, onOpen, onRemove }: { data: CompareResp; onOpen: (id: string) => void; onRemove: (id: string) => void }) {
  const showLens = data.lens_label !== 'TRI'
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs font-semibold text-ink-2">
            <th className="w-10 px-2 py-2">#</th>
            <th className="px-2 py-2">Supplier</th>
            <th className="px-2 py-2">{showLens ? 'Lens index' : 'TRI'}</th>
            {showLens && <th className="px-2 py-2">TRI</th>}
            <th className="px-2 py-2">Critical</th>
            <th className="px-2 py-2">Safest in set at</th>
            <th className="px-2 py-2">Worst score</th>
            <th className="px-2 py-2">Delivery</th>
            <th className="px-2 py-2">Confirm</th>
            <th className="px-2 py-2">Change</th>
            <th className="px-2 py-2">PO volume</th>
            <th className="px-2 py-2">Sourcing</th>
            <th className="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {data.ranking.map(r => (
            <tr key={r.id} className="rounded-xl border-t border-line transition hover:bg-sunken/70">
              <td className="px-2 py-2.5 font-semibold text-muted">{r.rank}</td>
              <td className="px-2 py-2.5">
                <button onClick={() => onOpen(r.id)} className="text-left font-semibold text-ink hover:text-accent-strong hover:underline">{r.id}</button>
                <div className="text-xs text-muted">{r.name}</div>
              </td>
              <td className="px-2 py-2.5"><LevelBadge level={r.level} value={showLens ? num(r.lens_index ?? r.tri, 1) : r.tri} /></td>
              {showLens && <td className="px-2 py-2.5 text-ink-2 tabular-nums">{r.tri}</td>}
              <td className="px-2 py-2.5">{r.critical_scores > 0 ? <Tag tone="bad">{r.critical_scores}</Tag> : <Tag tone="good">0</Tag>}</td>
              <td className="max-w-[220px] px-2 py-2.5 text-xs text-ink-2">{r.best_at.length ? r.best_at.slice(0, 2).join(', ') + (r.best_at.length > 2 ? ` +${r.best_at.length - 2}` : '') : '—'}</td>
              <td className="px-2 py-2.5 text-xs text-ink-2">{r.worst_label} <span className="font-semibold text-ink">{r.worst_value}</span></td>
              <td className="px-2 py-2.5 tabular-nums text-ink-2">{num(r.delivery, 1)}%</td>
              <td className="px-2 py-2.5 tabular-nums text-ink-2">{num(r.confirmation, 1)}%</td>
              <td className="px-2 py-2.5 tabular-nums text-ink-2">{num(r.change, 1)}%</td>
              <td className="px-2 py-2.5 tabular-nums text-ink-2">{eur(r.po)}</td>
              <td className="px-2 py-2.5"><Tag>{r.sourcing}</Tag></td>
              <td className="px-2 py-2.5 text-right">
                <button onClick={() => onRemove(r.id)} title="Remove from shortlist" className="grid size-7 place-items-center rounded-full text-muted transition hover:bg-critical hover:text-critical-ink">
                  <X className="size-3.5" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
