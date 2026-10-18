// profile page. Owned by the profile slice.
import clsx from 'clsx'
import { ArrowDown, ArrowUp, Plus, Search, ShieldCheck, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { get } from '../lib/api'
import { axisProps, DIVERGE, gridProps, INK, BAR_RADIUS_V } from '../lib/chart'
import { eur, num } from '../lib/format'
import { useApp, useLens } from '../lib/store'
import type { Level, SupplierRow } from '../lib/types'
import { Gauge } from '../components/Gauge'
import { ShortlistButton } from '../components/ShortlistButton'
import { SupplierPicker } from '../components/SupplierPicker'
import { Button, Card, CardHeader, ChartTooltip, Empty, LevelBadge, LevelPill, Legend, Markdown, Meter, PageHeader, Skeleton, Stat, Tag } from '../components/ui'

interface Contribution {
  score: string; label: string; value: number; level: Level; weight: number
  points: number; vs_average: number; riskier_than_pct: number
}
interface WaterfallStep {
  label: string; delta: number; start: number; end: number
  value: number | null; weight: number | null; points: number | null
}
interface OpsMetric { metric: string; value: number; average: number; riskier_than_pct: number }
interface Alternative extends SupplierRow { tri_delta: number }
interface ProfileData {
  id: string; row: SupplierRow; narrative: string; total_risk_index: number; level: Level
  riskier_than_pct: number; dataset_average_tri: number; formula: string; recomputed: number
  sourcing_risk_level: string; supply_chain_complexity: string; po_volume: number
  contributions: Contribution[]; waterfall: WaterfallStep[]
  operational_metrics: OpsMetric[]; alternatives: Alternative[]
}

const DEFAULT_SID = 'SUPP_00018'

function Waterfall({ data }: { data: ProfileData }) {
  const chartData = data.waterfall.map(s => ({
    label: s.label, base: Math.min(s.start, s.end), delta: Math.max(0.01, Math.abs(s.end - s.start)),
    rawDelta: s.delta, value: s.value, weight: s.weight, points: s.points, worse: s.delta >= 0, total: false,
  }))
  // zoom the axis onto the walk so small steps stay visible; bookend with neutral total bars
  const ends = data.waterfall.flatMap(s => [s.start, s.end])
  const lo = Math.max(0, Math.floor((Math.min(...ends) - 4) / 5) * 5)
  const hi = Math.min(100, Math.ceil((Math.max(...ends) + 4) / 5) * 5)
  const total = (label: string, v: number) => ({ label, base: lo, delta: v - lo, rawDelta: 0, value: v, weight: 0, points: 0, worse: false, total: true })
  chartData.unshift(total('Dataset average', data.dataset_average_tri))
  chartData.push(total(`${data.id} TRI`, data.total_risk_index))
  return (
    <Card>
      <CardHeader
        title="From the dataset average to this supplier"
        subtitle={`Average TRI ${data.dataset_average_tri} → ${data.id} TRI ${data.total_risk_index}, one step per score`}
        actions={<Legend items={[{ label: 'Pushes TRI up', color: DIVERGE.worse }, { label: 'Pulls TRI down', color: DIVERGE.better }]} />}
      />
      <div className="h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 56 }} barCategoryGap="22%">
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="label" {...axisProps} angle={-40} textAnchor="end" interval={0} height={64} />
            <YAxis {...axisProps} domain={[lo, hi]} allowDataOverflow />
            <Tooltip
              cursor={{ fill: '#f3f4f6' }}
              content={<ChartTooltip render={(payload: any) => {
                const p = payload[0].payload
                return (
                  <div>
                    <div className="mb-1 font-semibold text-ink">{p.label}</div>
                    {p.total ? <div className="text-ink-2">TRI {p.value}</div> : null}
                    {!p.total && p.value != null && <div className="text-ink-2">score {p.value} · weight {(p.weight * 100).toFixed(0)}% · {p.points.toFixed(2)} pts</div>}
                    {!p.total && <div className="font-medium" style={{ color: p.worse ? DIVERGE.worse : DIVERGE.better }}>{p.rawDelta >= 0 ? '+' : ''}{p.rawDelta.toFixed(2)} vs average</div>}
                  </div>
                )
              }} />}
            />
            <ReferenceLine y={data.dataset_average_tri} stroke={INK.axis} strokeDasharray="4 4" />
            <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="delta" stackId="w" radius={BAR_RADIUS_V} isAnimationActive={false}>
              {chartData.map((d, i) => <Cell key={i} fill={d.total ? INK.muted : d.worse ? DIVERGE.worse : DIVERGE.better} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function ScoreGrid({ groups, contributions }: { groups: Record<string, string[]>; contributions: Contribution[] }) {
  const byKey = Object.fromEntries(contributions.map(c => [c.score, c]))
  return (
    <Card>
      <CardHeader title="All 18 risk scores" subtitle="Grouped by family — value, weight in the TRI, and how this supplier compares to the other 10,000" />
      <div className="grid grid-cols-1 gap-x-6 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
        {Object.entries(groups).map(([group, keys]) => (
          <div key={group}>
            <div className="mb-2.5 text-[11px] font-semibold tracking-wide text-muted uppercase">{group}</div>
            <div className="space-y-3">
              {keys.map(k => {
                const c = byKey[k]
                if (!c) return null
                return (
                  <div key={k}>
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-ink-2">{c.label}</span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] text-muted">w {(c.weight * 100).toFixed(0)}%</span>
                        <LevelBadge level={c.level} value={c.value} size="sm" />
                      </div>
                    </div>
                    <Meter value={c.value} />
                    <div className="mt-1 text-[11px] text-muted">riskier than {c.riskier_than_pct.toFixed(0)}% of suppliers</div>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

function OpsMetrics({ metrics, higherIsBetter }: { metrics: OpsMetric[]; higherIsBetter: string[] }) {
  return (
    <Card>
      <CardHeader title="Operational performance" subtitle="Not part of the TRI formula — but delivery correlates strongly with it (r ≈ −0.71), a cross-check that the scores predict real problems" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {metrics.map(m => {
          const isPO = m.metric.startsWith('Purchase Order')
          if (isPO) {
            return <Stat key={m.metric} label="PO volume (exposure)" value={eur(m.value)} sub={`larger than ${m.riskier_than_pct.toFixed(0)}% of suppliers`} />
          }
          const better = higherIsBetter.includes(m.metric)
          const diff = m.value - m.average
          const good = better ? diff >= 0 : diff <= 0
          return (
            <Stat
              key={m.metric} label={m.metric} value={`${num(m.value, 1)}%`}
              sub={
                <span className={clsx('inline-flex items-center gap-1 font-medium', good ? 'text-low-dot' : 'text-critical-ink')}>
                  {diff >= 0 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
                  {diff >= 0 ? '+' : ''}{diff.toFixed(1)} vs avg {num(m.average, 1)}
                </span>
              }
            />
          )
        })}
      </div>
    </Card>
  )
}

function Alternatives({ alts, current, onOpen, onAddAll }: {
  alts: Alternative[]; current: string; onOpen: (id: string) => void; onAddAll: () => void
}) {
  if (!alts.length) {
    return (
      <Card>
        <CardHeader title="Lower-risk alternatives with a similar profile" />
        <Empty icon={<ShieldCheck className="size-5" />} title="No close match is meaningfully safer">
          No supplier with the same sourcing risk and complexity is at least 10 TRI points lower.
        </Empty>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader
        title="Lower-risk alternatives with a similar profile"
        subtitle="Same sourcing risk and complexity, closest PO volume, TRI at least 10 points lower"
        actions={<Button size="sm" icon={<Plus className="size-3.5" />} onClick={onAddAll}>Shortlist {current} + these {alts.length}</Button>}
      />
      <div className="space-y-2">
        {alts.map(a => (
          <div key={a.id} className="flex items-center justify-between gap-3 rounded-2xl border border-line bg-sunken/50 px-4 py-3 transition hover:border-line-strong">
            <button className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={() => onOpen(a.id)}>
              <LevelBadge level={a.level} value={a.tri} />
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">{a.id} · {a.name}</div>
                <div className="text-xs text-ink-2">Delivery {num(a.delivery, 0)}% · confirm {num(a.confirmation, 0)}% · PO {eur(a.po)}</div>
              </div>
            </button>
            <div className="flex shrink-0 items-center gap-2.5">
              <Tag tone="good">−{a.tri_delta} TRI</Tag>
              <ShortlistButton id={a.id} size="sm" />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export default function Page() {
  const meta = useApp(s => s.meta)!
  const profileId = useApp(s => s.profileId)
  const shortlist = useApp(s => s.shortlist)
  const openProfile = useApp(s => s.openProfile)
  const addToShortlist = useApp(s => s.addToShortlist)
  const lens = useLens()

  const sid = profileId ?? shortlist[0] ?? DEFAULT_SID
  const [data, setData] = useState<ProfileData | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setErr(null)
    const q = lens.weights ? `?lens=${encodeURIComponent(JSON.stringify(lens.weights))}` : ''
    get<ProfileData>(`/profile/${sid}${q}`)
      .then(d => { if (!cancelled) setData(d) })
      .catch(e => { if (!cancelled) setErr(e.message || 'Could not load this supplier') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, JSON.stringify(lens.weights)])

  return (
    <div>
      <PageHeader
        title="Supplier profile"
        subtitle="Exact TRI decomposition, operational performance and lower-risk alternatives for one supplier"
        icon={<UserRound className="size-5" />}
        actions={<SupplierPicker onSelect={openProfile} />}
      />

      {loading && (
        <div className="space-y-5">
          <Skeleton className="h-32" />
          <Skeleton className="h-48" />
          <Skeleton className="h-96" />
        </div>
      )}

      {!loading && err && (
        <Empty title="Supplier not found" icon={<Search className="size-5" />}>
          "{sid}" doesn't match a supplier ID or name in the dataset. Try an ID like SUPP_00018, or search above.
        </Empty>
      )}

      {!loading && !err && data && (
        <div className="space-y-5">
          <Card className="grid items-center gap-6 md:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <h2 className="text-2xl font-bold tracking-tight text-ink">{data.id} · {data.row.name}</h2>
                <LevelPill level={data.level}>TRI {data.total_risk_index} · {data.level}</LevelPill>
                {lens.weights && <Tag tone="accent"><Sparkles className="size-3" />{lens.label} {data.row.lens_index}</Tag>}
              </div>
              <Markdown className="mt-3">{data.narrative}</Markdown>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Sourcing risk <b className="font-semibold text-ink-2">{data.sourcing_risk_level}</b> · supply chain <b className="font-semibold text-ink-2">{data.supply_chain_complexity}</b> · PO volume <b className="font-semibold text-ink-2">{eur(data.po_volume)}</b> · TRI recomputed from the 18 weighted scores: {data.recomputed.toFixed(2)} → {Math.round(data.recomputed)}
              </p>
              <ShortlistButton id={sid} size="lg" className="mt-4 w-full sm:min-w-[260px] sm:w-auto" />
            </div>
            <div className="text-center">
              <Gauge value={data.total_risk_index} className="mx-auto w-full max-w-[280px]" />
              <div className="mt-1 text-xs text-ink-2">Riskier than <span className="font-semibold text-ink">{data.riskier_than_pct.toFixed(0)}%</span> of suppliers</div>
            </div>
          </Card>

          <Waterfall data={data} />

          <ScoreGrid groups={meta.groups} contributions={data.contributions} />

          <OpsMetrics metrics={data.operational_metrics} higherIsBetter={meta.higher_is_better} />

          <Alternatives
            alts={data.alternatives}
            current={data.id}
            onOpen={openProfile}
            onAddAll={() => addToShortlist([data.id, ...data.alternatives.map(a => a.id)])}
          />
        </div>
      )}
    </div>
  )
}
