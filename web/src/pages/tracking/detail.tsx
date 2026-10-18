// Slide-over with everything the agents know about one tracked supplier.
import { ExternalLink, Globe, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, Card, CardHeader, clsx, LevelBadge, Skeleton, Tag } from '../../components/ui'
import { del, get } from '../../lib/api'
import { useApp } from '../../lib/store'
import { Delta, Severity, TrendMark } from './bits'
import { AREA_COLOR, AREA_SHORT, fmtDate, fmtDateTime, n1, signed } from './util'
import { AreaBars, AreaLines } from './charts'
import type { SupplierDetail, TrackedSupplier } from './types'

export function SupplierPanel({ base, version, onClose, onRemoved }: { base: TrackedSupplier; version: string; onClose: () => void; onRemoved: () => void }) {
  const notify = useApp(s => s.notify)
  const [d, setD] = useState<SupplierDetail | null>(null)
  const [failed, setFailed] = useState(false)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    get<SupplierDetail>(`/tracking/supplier/${base.id}`).then(r => { if (live) { setD(r); setFailed(false) } }).catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [base.id, version])

  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])

  const s: TrackedSupplier = d ?? base
  const remove = async () => {
    setBusy(true)
    try { await del(`/tracking/suppliers/${s.id}`); notify(`Stopped tracking ${s.name}`); onRemoved() }
    catch (e: any) { notify(String(e?.message || e), 'warn'); setBusy(false) }
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-ink/25" onClick={onClose}>
      <aside role="dialog" aria-label={`${s.name} tracking detail`} onClick={e => e.stopPropagation()}
        className="rr-in h-full w-full max-w-[640px] space-y-4 overflow-y-auto bg-bg p-5 shadow-[var(--shadow-pop)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-xl font-bold tracking-tight text-ink">{s.name}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-ink-2">
              {[s.country, s.category].filter(Boolean).join(' · ')}
              <Tag tone={s.criticality === 'High' ? 'bad' : s.criticality === 'Medium' ? 'warn' : 'neutral'}>{s.criticality} criticality</Tag>
              {s.dataset_id && <Tag tone="accent">Dataset {s.dataset_id}</Tag>}
              {s.website && <a href={/^https?:/.test(s.website) ? s.website : `https://${s.website}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-accent hover:underline"><Globe className="size-3" />{s.website.replace(/^https?:\/\//, '')}</a>}
            </div>
            {s.relationship && (
              <div className="mt-1.5 text-xs text-ink-2">
                {s.relationship}
                {s.source && <a href={s.source} target="_blank" rel="noreferrer" className="ml-1.5 inline-flex items-center gap-0.5 font-semibold text-accent hover:underline">source<ExternalLink className="size-3" /></a>}
              </div>
            )}
          </div>
          <button onClick={onClose} aria-label="Close" className="grid size-9 shrink-0 place-items-center rounded-full text-ink-2 hover:bg-sunken hover:text-ink"><X className="size-5" /></button>
        </div>

        <Card>
          {s.status === 'pending' && <div className="text-sm text-ink-2">Not checked yet. The first run backfills 30 days of history from dated news.</div>}
          {s.status === 'error' && <div className="mb-3 rounded-xl bg-critical px-3 py-2 text-xs font-medium text-critical-ink">Last check failed: {s.error || 'unknown error'}</div>}
          {s.score != null && s.level && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <div><div className="text-xs text-muted">Risk score</div><LevelBadge level={s.level} value={n1(s.score)} /></div>
              <div><div className="text-xs text-muted">7 days</div><Delta v={s.delta_7d} /></div>
              <div><div className="text-xs text-muted">Trend</div><TrendMark trend={s.trend} />{s.slope_per_week != null && <span className="ml-1 text-xs text-muted tabular-nums">{signed(s.slope_per_week)}/wk</span>}</div>
              <div><div className="text-xs text-muted">Last checked</div><span className="text-xs font-medium text-ink">{fmtDateTime(s.last_checked)}</span></div>
            </div>
          )}
          {s.outlook && (
            <div className="mt-3 rounded-xl border border-line bg-sunken/60 p-3 text-[13px] leading-relaxed text-ink-2">
              <div className="mb-0.5 text-xs font-semibold text-ink">Leader outlook · {s.outlook.confidence} confidence</div>
              <b className="text-ink capitalize">{s.outlook.direction}</b>, expected <b className="text-ink tabular-nums">{signed(s.outlook.delta_30d)}</b> points in 30 days, <b className="text-ink tabular-nums">{Math.round(s.outlook.disruption_prob_90d * 100)}%</b> chance of a material disruption in 90 days. {s.outlook.reason}
            </div>
          )}
        </Card>

        {failed && !d && <Card className="text-sm text-ink-2">Could not load the detail for this supplier.</Card>}
        {!d && !failed && <Skeleton className="h-64" />}

        {d && (
          <>
            {(d.note || d.signals.length > 0) && (
              <Card>
                <CardHeader title="Worker agent note" subtitle={`${d.sources_checked} source${d.sources_checked === 1 ? '' : 's'} checked in the latest run`} />
                {d.note && <p className="text-[13px] leading-relaxed text-ink-2">{d.note}</p>}
                {d.signals.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-4 text-[13px] text-ink-2">{d.signals.map((x, i) => <li key={i}>{x}</li>)}</ul>}
              </Card>
            )}
            {d.area_series.length > 0 && (
              <Card>
                <CardHeader title="Risk by area, last 30 days" subtitle="Each area decays old events with a 14-day half-life" />
                <AreaLines data={d.area_series} />
              </Card>
            )}
            {d.areas && (
              <Card>
                <CardHeader title="Area scores now vs baseline" subtitle="Baseline is the supplier's structural risk before the recent news" />
                <AreaBars areas={d.areas} baseline={d.baseline} />
              </Card>
            )}
            <Card>
              <CardHeader title="Events" subtitle={`${d.events.length} stored · ${d.events_30d} in the last 30 days · impact in points: + riskier, − safer`} />
              {d.events.length === 0 ? <div className="text-sm text-muted">No risk events found yet.</div> : (
                <ol className="relative space-y-4 border-l border-line pl-4">
                  {d.events.map(e => (
                    <li key={e.id} className="relative">
                      <span className="absolute top-1.5 -left-[21px] size-2.5 rounded-full ring-4 ring-surface" style={{ background: AREA_COLOR[e.area] ?? '#8b93a1' }} />
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted">
                        <span className="font-semibold text-ink-2">{fmtDate(e.date, true)}</span>
                        <Tag>{AREA_SHORT[e.area] ?? e.area}</Tag>
                        <Severity n={e.severity} />
                        <span className={clsx('font-bold tabular-nums', e.impact > 0 ? 'text-critical-ink' : e.impact < 0 ? 'text-low-ink' : 'text-muted')}>{signed(e.impact)} pts</span>
                      </div>
                      <a href={e.url} target="_blank" rel="noreferrer" className="mt-0.5 inline-flex items-start gap-1 text-[13px] font-semibold text-ink hover:text-accent hover:underline">{e.title}<ExternalLink className="mt-0.5 size-3 shrink-0 text-muted" /></a>
                      {e.summary && <p className="mt-0.5 text-xs leading-relaxed text-ink-2">{e.summary}</p>}
                      <div className="text-[11px] text-muted">{e.source}</div>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </>
        )}

        <div className="flex items-center justify-between border-t border-line pt-4">
          <span className="text-[11px] text-muted">Added {fmtDate(s.added_at, true)}</span>
          {confirm ? (
            <div className="flex items-center gap-2 text-xs"><span className="text-ink-2">Stop tracking and delete its history?</span>
              <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button>
              <Button size="sm" variant="danger" loading={busy} icon={<Trash2 className="size-3.5" />} onClick={remove}>Remove</Button>
            </div>
          ) : <Button size="sm" variant="danger" icon={<Trash2 className="size-3.5" />} onClick={() => setConfirm(true)}>Remove supplier</Button>}
        </div>
      </aside>
    </div>
  )
}
