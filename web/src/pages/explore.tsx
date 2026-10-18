// explore page. Owned by the explore slice: filter & rank the 10,000 suppliers, build a shortlist.
import { useVirtualizer } from '@tanstack/react-virtual'
import { Compass, Plus, RotateCcw, Search, SlidersHorizontal } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import {
  Button, Card, CardHeader, Checkbox, ChartTooltip, Chip, Empty, Field, Input, Legend, LevelBadge, Meter,
  PageHeader, Segmented, Select, Skeleton, Slider, Stat, Tag,
} from '../components/ui'
import { ShortlistButton } from '../components/ShortlistButton'
import { PartTypePicker, type Gate } from './explore/PartTypePicker'
import { post } from '../lib/api'
import { axisProps, gridProps, LEVEL } from '../lib/chart'
import { eur } from '../lib/format'
import { MAX_SHORTLIST, OFFICIAL_LENS, useApp, useLens } from '../lib/store'
import type { Level, PartType, SupplierRow } from '../lib/types'

interface Filters {
  tri_min: number; tri_max: number
  levels: string[]; sourcing: string[]; complexity: string[]
  delivery_min: number; confirmation_min: number; change_max: number
  po_min: number; po_max: number
  knockout: string[]
  max_score: number
  text: string
}

const PO_MAX = 50_000_000
const DEFAULT_FILTERS: Filters = {
  tri_min: 0, tri_max: 100, levels: [], sourcing: [], complexity: [],
  delivery_min: 50, confirmation_min: 50, change_max: 35,
  po_min: 0, po_max: PO_MAX, knockout: [], max_score: 100, text: '',
}

const SORTS: { value: string; label: string }[] = [
  { value: 'tri', label: 'TRI' }, { value: 'lens_index', label: 'Lens index' },
  { value: 'percentile', label: 'TRI percentile' }, { value: 'delivery', label: 'Delivery rating' },
  { value: 'confirmation', label: 'Confirmation rate' }, { value: 'change', label: 'Order change rate' },
  { value: 'po', label: 'PO volume' }, { value: 'name', label: 'Name' },
]

interface QueryResult {
  total: number
  summary: { suppliers: number; avg_tri: number; critical: number; high: number; po_volume: number; avg_lens?: number }
  rows: SupplierRow[]
  sourcing_levels: ({ sourcing: string; avg_tri: number | null } & Record<Level, number>)[]
  histogram: { from: number; to: number; count: number; level: Level }[]
  scatter: { id: string; tri: number; delivery: number; level: Level }[]
  rank_basis: 'tri' | 'lens_index'
  gate: Gate | null
}

const ROW_H = 46

/** TRI level by sourcing risk: hard-to-replace suppliers skew riskier. */
function SourcingLevels({ rows }: { rows: QueryResult['sourcing_levels'] }) {
  const avg = (s: string) => rows.find(r => r.sourcing === s)?.avg_tri
  const levels: Level[] = ['Low', 'Medium', 'High', 'Critical']
  return (
    <Card className="mb-5">
      <CardHeader title="TRI level by sourcing risk"
        subtitle={avg('High') != null && avg('Low') != null
          ? `Hard-to-replace suppliers skew riskier (avg TRI ${Math.round(avg('High')!)} vs ${Math.round(avg('Low')!)} for easy-to-replace).`
          : 'Matching suppliers by replaceability and TRI level'} />
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left font-semibold text-muted">
              <th className="px-2 py-1.5">Sourcing risk</th>
              {levels.map(l => <th key={l} className="px-2 py-1.5 text-right"><span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: LEVEL[l].dot }} />{l}</span></th>)}
              <th className="px-2 py-1.5 text-right">Avg TRI</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.sourcing} className="border-t border-line">
                <td className="px-2 py-2 font-semibold text-ink">{r.sourcing}</td>
                {levels.map(l => <td key={l} className="px-2 py-2 text-right tabular-nums text-ink-2">{r[l].toLocaleString()}</td>)}
                <td className="px-2 py-2 text-right font-semibold tabular-nums text-ink">{r.avg_tri ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export default function Page() {
  const meta = useApp(s => s.meta)!
  const shortlist = useApp(s => s.shortlist)
  const addToShortlist = useApp(s => s.addToShortlist)
  const openProfile = useApp(s => s.openProfile)
  const customWeights = useApp(s => s.customWeights)
  const setCustomWeights = useApp(s => s.setCustomWeights)
  const partType = useApp(s => s.partType)
  const setPartType = useApp(s => s.setPartType)
  const setLens = useApp(s => s.setLens)
  const lens = useLens()

  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [sort, setSort] = useState(() => (lens.isOfficial ? 'tri' : 'lens_index'))
  const [ascending, setAscending] = useState(true)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setFilters(f => ({ ...f, [k]: v }))
  const toggleIn = (k: 'levels' | 'sourcing' | 'complexity' | 'knockout', v: string) =>
    setFilters(f => ({ ...f, [k]: f[k].includes(v) ? f[k].filter(x => x !== v) : [...f[k], v] }))

  // a part type ranks by its own lens index (the official TRI lens has no separate index)
  const pickPartType = (p: PartType) => {
    setPartType(p)
    setSort(meta.part_types[p].lens === OFFICIAL_LENS ? 'tri' : 'lens_index')
  }
  const useSuggestedLens = () => {
    const l = meta.part_types[partType].lens
    setLens(l); setSort(l === OFFICIAL_LENS ? 'tri' : 'lens_index')
  }

  const effectiveSort = !lens.weights && sort === 'lens_index' ? 'tri' : sort

  useEffect(() => {
    const t = setTimeout(() => {
      setLoading(true)
      post<QueryResult>('/suppliers/query', { filters, lens_weights: lens.weights, sort: effectiveSort, ascending, limit: 300, part_type: partType })
        .then(r => { setResult(r); setSelected(new Set()) })
        .catch(() => {})
        .finally(() => setLoading(false))
    }, 260)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, effectiveSort, ascending, partType, JSON.stringify(lens.weights)])

  const rows = result?.rows ?? []
  const shortlistSet = useMemo(() => new Set(shortlist), [shortlist])
  const showLens = !lens.isOfficial

  const parentRef = useRef<HTMLDivElement>(null)
  const rv = useVirtualizer({ count: rows.length, getScrollElement: () => parentRef.current, estimateSize: () => ROW_H, overscan: 10 })

  const gridCols = showLens
    ? '32px minmax(0,2fr) 88px 72px minmax(0,1.3fr) 76px 84px 64px 64px 60px 84px 84px 110px'
    : '32px minmax(0,2fr) 88px minmax(0,1.3fr) 76px 84px 64px 64px 60px 84px 84px 110px'

  const allVisibleSelected = rows.length > 0 && rows.every(r => selected.has(r.id))
  const toggleSelectAll = () => setSelected(allVisibleSelected ? new Set() : new Set(rows.map(r => r.id)))
  const toggleRow = (id: string) => setSelected(s => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  const addSelected = () => { addToShortlist(Array.from(selected)); setSelected(new Set()) }

  // custom weights editor defaults to the official TRI weights, scaled to the 0-30 slider range
  const weightsFor = (key: string) => customWeights?.[key] ?? Math.round((meta.lenses[Object.keys(meta.lenses)[0]]?.[key] ?? 0.05) * 100)

  return (
    <div>
      <PageHeader title="Find suppliers" icon={<Compass className="size-5" />}
        subtitle="Narrow 10,000 suppliers to a shortlist. Rank by the official Total Risk Index or by a risk lens (sidebar) that re-weights the 18 scores for your sourcing situation." />

      <PartTypePicker value={partType} types={meta.part_types} lensName={lens.name} gate={result?.gate ?? null}
        onPick={pickPartType} onUseSuggested={useSuggestedLens} />

      <Card className="mb-5">
        <CardHeader title="Filters" icon={<SlidersHorizontal className="size-4" />}
          actions={<Button size="sm" variant="ghost" icon={<RotateCcw className="size-3.5" />} onClick={() => setFilters(DEFAULT_FILTERS)}>Reset</Button>} />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Field label="Supplier ID or name">
            <Input icon={<Search className="size-4" />} placeholder="SUPP_00012 or 'Apex'" value={filters.text}
              onChange={e => set('text', e.target.value)} />
          </Field>
          <Slider label="Total Risk Index ≥" value={filters.tri_min} min={0} max={100} onChange={v => set('tri_min', v)} />
          <Slider label="Total Risk Index ≤" value={filters.tri_max} min={0} max={100} onChange={v => set('tri_max', v)} />
          <Slider label="Max. order change rate" value={filters.change_max} min={0} max={35} onChange={v => set('change_max', v)} format={v => `${v}%`} />
          <Slider label="Min. delivery rating" value={filters.delivery_min} min={50} max={100} onChange={v => set('delivery_min', v)} format={v => `${v}%`} />
          <Slider label="Min. order confirmation" value={filters.confirmation_min} min={50} max={100} onChange={v => set('confirmation_min', v)} format={v => `${v}%`} />
          <Slider label="No single score above" value={filters.max_score} min={50} max={100} onChange={v => set('max_score', v)} />
          <Slider label="Min. PO volume" value={filters.po_min} min={0} max={PO_MAX} step={50_000} onChange={v => set('po_min', v)} format={eur} />
          <Slider label="Max. PO volume" value={filters.po_max} min={0} max={PO_MAX} step={50_000} onChange={v => set('po_max', v)} format={eur} />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
          <Field label="TRI level">
            <div className="flex flex-wrap gap-1.5">
              {meta.levels.map(lv => (
                <Chip key={lv} active={filters.levels.includes(lv)} dot={LEVEL[lv].dot} onClick={() => toggleIn('levels', lv)}>{lv}</Chip>
              ))}
            </div>
          </Field>
          <Field label="Sourcing risk (replaceability)">
            <div className="flex flex-wrap gap-1.5">
              {meta.categorical['Sourcing Risk Level'].map(v => (
                <Chip key={v} active={filters.sourcing.includes(v)} onClick={() => toggleIn('sourcing', v)}>{v}</Chip>
              ))}
            </div>
          </Field>
          <Field label="Supply chain complexity">
            <div className="flex flex-wrap gap-1.5">
              {meta.categorical['Supply Chain Complexity'].map(v => (
                <Chip key={v} active={filters.complexity.includes(v)} onClick={() => toggleIn('complexity', v)}>{v}</Chip>
              ))}
            </div>
          </Field>
        </div>

        <div className="mt-4">
          <Field label="Knock-out: exclude suppliers that are Critical in" hint="e.g. Financial Health, Compliance Risk">
            <div className="flex flex-wrap gap-1.5">
              {meta.scores.map(s => (
                <Chip key={s.key} active={filters.knockout.includes(s.key)} onClick={() => toggleIn('knockout', s.key)}>{s.label}</Chip>
              ))}
            </div>
          </Field>
        </div>
      </Card>

      {lens.name === 'Custom' && (
        <Card className="mb-5">
          <CardHeader title="Custom lens weights" subtitle="Weight each score 0-30. Weights are normalised to 100% server-side." />
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3">
            {meta.scores.map(s => (
              <Slider key={s.key} label={s.label} value={weightsFor(s.key)} min={0} max={30}
                onChange={v => setCustomWeights({ ...Object.fromEntries(meta.scores.map(m => [m.key, weightsFor(m.key)])), [s.key]: v })} />
            ))}
          </div>
        </Card>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3.5 md:grid-cols-5">
        <Stat label="Matching suppliers" value={result ? result.total.toLocaleString() : '—'} sub={`of ${meta.summary.suppliers.toLocaleString()}`} />
        <Stat label={`Average ${lens.label}`} value={result ? (lens.isOfficial ? result.summary.avg_tri : (result.summary.avg_lens ?? result.summary.avg_tri)) : '—'} />
        <Stat label="Critical TRI" value={result ? result.summary.critical.toLocaleString() : '—'} tone={result && result.summary.critical > 0 ? 'bad' : undefined} />
        <Stat label="PO volume" value={result ? eur(result.summary.po_volume) : '—'} />
        <Stat label="Shortlist" value={`${shortlist.length}/${MAX_SHORTLIST}`} sub={shortlist.length >= MAX_SHORTLIST ? 'full' : undefined} />
      </div>

        <div className="mb-5 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title={`${lens.label} distribution`} subtitle="Count of matching suppliers in 5-point bands" />
            {result && result.histogram.some(b => b.count > 0) ? (
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={result.histogram.map(b => ({ ...b, bucket: `${b.from}` }))} margin={{ left: 0, right: 8, top: 4 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="bucket" {...axisProps} interval={3} />
                    <YAxis {...axisProps} width={40} allowDecimals={false} />
                    <Tooltip content={<ChartTooltip render={(payload: any) => { const d = payload[0].payload; return (
                      <div><div className="font-semibold text-ink">{d.from}-{d.to}</div><div className="text-ink-2">{d.count} suppliers</div></div>
                    ) }} />} cursor={{ fill: '#f3f4f6' }} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                      {result.histogram.map((b, i) => <Cell key={i} fill={LEVEL[b.level].dot} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="grid h-[240px] place-items-center text-xs text-muted">No data</div>}
            <div className="mt-2"><Legend items={(['Low', 'Medium', 'High', 'Critical'] as Level[]).map(l => ({ label: l, color: LEVEL[l].dot }))} /></div>
          </Card>

          <Card>
            <CardHeader title="Risk landscape" subtitle="TRI vs. delivery rating · ring = on shortlist" />
            {result && result.scatter.length > 0 ? (
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ left: 0, right: 8, top: 4, bottom: 0 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis type="number" dataKey="tri" name="TRI" domain={[0, 100]} {...axisProps} />
                    <YAxis type="number" dataKey="delivery" name="Delivery" domain={[40, 100]} {...axisProps} width={40} />
                    <Tooltip cursor={{ strokeDasharray: '3 3' }}
                      content={({ active, payload }: any) => {
                        if (!active || !payload?.length) return null
                        const d = payload[0].payload
                        return <div className="rounded-xl border border-line bg-surface/95 px-3 py-2 text-xs shadow-[var(--shadow-pop)]">
                          <div className="font-semibold text-ink">{d.id}</div>
                          <div className="text-ink-2">TRI {d.tri} · Delivery {d.delivery.toFixed(1)}%</div>
                        </div>
                      }} />
                    <Scatter data={result.scatter} isAnimationActive={false} shape={(p: any) => <circle cx={p.cx} cy={p.cy} r={3} fill={LEVEL[p.payload.level as Level].dot} fillOpacity={0.75} />} />
                    <Scatter isAnimationActive={false} data={result.scatter.filter(p => shortlistSet.has(p.id))}
                      shape={(p: any) => <circle cx={p.cx} cy={p.cy} r={5} fill="none" stroke="var(--color-accent)" strokeWidth={2} />} />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="grid h-[240px] place-items-center text-xs text-muted">No data</div>}
            <div className="mt-2"><Legend items={(['Low', 'Medium', 'High', 'Critical'] as Level[]).map(l => ({ label: l, color: LEVEL[l].dot }))} /></div>
          </Card>
        </div>
          {result && result.sourcing_levels.some(s => s.avg_tri != null) && <SourcingLevels rows={result.sourcing_levels} />}
          <Card pad={false}>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line p-4">
              <div className="flex items-center gap-2">
                <Button size="sm" variant="primary" icon={<Plus className="size-3.5" />} disabled={selected.size === 0} onClick={addSelected}>
                  Add {selected.size || ''} selected to shortlist
                </Button>
                <Button size="sm" variant="secondary" disabled={rows.length === 0}
                  onClick={() => addToShortlist(rows.slice(0, 5).map(r => r.id))}>Add top 5</Button>
              </div>
              <div className="flex items-center gap-2">
                <Select value={effectiveSort} onChange={e => setSort(e.target.value)} className="h-9 w-44 text-xs">
                  {SORTS.filter(s => s.value !== 'lens_index' || showLens).map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </Select>
                <Segmented size="sm" value={ascending ? 'asc' : 'desc'} onChange={v => setAscending(v === 'asc')}
                  options={[{ value: 'asc', label: 'Asc' }, { value: 'desc', label: 'Desc' }]} />
              </div>
            </div>

            {!result || rows.length === 0 ? (
              loading ? <div className="space-y-2 p-4"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
                : <Empty icon={<Search className="size-6" />} title="No supplier matches these filters">Loosen a filter or clear the search text.</Empty>
            ) : (
              <>
                <div className="overflow-x-auto">
                <div className="min-w-[1240px]">
                <div className="grid items-center gap-2 border-b border-line bg-sunken/60 px-4 py-2 text-[11px] font-semibold text-muted" style={{ gridTemplateColumns: gridCols }}>
                  <Checkbox checked={allVisibleSelected} onChange={toggleSelectAll} />
                  <span>Supplier</span>
                  <span className="text-right">TRI</span>
                  {showLens && <span className="text-right">Lens</span>}
                  <span>Worst score</span>
                  <span>Sourcing</span>
                  <span>Complexity</span>
                  <span className="text-right">Delivery</span>
                  <span className="text-right">Confirm</span>
                  <span className="text-right">Change</span>
                  <span className="text-right">PO €</span>
                  <span>Percentile</span>
                  <span />
                </div>
                <div ref={parentRef} className="overflow-y-auto" style={{ height: 560 }}>
                  <div style={{ height: rv.getTotalSize(), position: 'relative' }}>
                    {rv.getVirtualItems().map(vi => {
                      const r = rows[vi.index]
                      const inShortlist = shortlistSet.has(r.id)
                      return (
                        <div key={r.id}
                          className="absolute inset-x-0 grid cursor-pointer items-center gap-2 border-b border-line/60 px-4 text-xs transition hover:bg-sunken/70"
                          style={{ transform: `translateY(${vi.start}px)`, height: ROW_H, gridTemplateColumns: gridCols, background: inShortlist ? 'var(--color-accent-soft)' : undefined }}
                          onClick={() => openProfile(r.id)}>
                          <span onClick={e => e.stopPropagation()}><Checkbox checked={selected.has(r.id)} onChange={() => toggleRow(r.id)} /></span>
                          <span className="min-w-0 truncate">
                            <span className="block truncate font-semibold text-ink">{r.name}</span>
                            <span className="block truncate text-[10.5px] text-muted">{r.id}</span>
                          </span>
                          <span className="text-right"><LevelBadge level={r.level} value={r.tri} size="sm" /></span>
                          {showLens && <span className="text-right font-semibold text-ink tabular-nums">{r.lens_index?.toFixed(1)}</span>}
                          <span className="min-w-0 truncate text-ink-2">{r.worst_label} <span className="font-semibold text-ink">{r.worst_value}</span></span>
                          <span><Tag>{r.sourcing}</Tag></span>
                          <span><Tag>{r.complexity}</Tag></span>
                          <span className="text-right tabular-nums text-ink-2">{r.delivery.toFixed(1)}</span>
                          <span className="text-right tabular-nums text-ink-2">{r.confirmation.toFixed(1)}</span>
                          <span className="text-right tabular-nums text-ink-2">{r.change.toFixed(1)}</span>
                          <span className="text-right tabular-nums text-ink-2">{eur(r.po)}</span>
                          <span className="flex items-center gap-1.5"><Meter value={r.tri_percentile} /><span className="w-7 shrink-0 text-right text-[10.5px] text-muted tabular-nums">{Math.round(r.tri_percentile)}</span></span>
                          <span onClick={e => e.stopPropagation()}><ShortlistButton id={r.id} size="sm" /></span>
                        </div>
                      )
                    })}
                  </div>
                </div>
                </div>
                </div>
                <div className="border-t border-line px-4 py-2 text-[11px] text-muted">
                  Showing {rows.length.toLocaleString()} of {result.total.toLocaleString()}. Click a row to open its profile.
                </div>
              </>
            )}
          </Card>
    </div>
  )
}
