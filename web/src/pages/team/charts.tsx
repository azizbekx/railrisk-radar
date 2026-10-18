// Chart building blocks for the agent-team page: specialist charts drawn from real values (no plotly),
// team scorecard, score build-up and the leader -> specialists -> verdict flow diagram.
import { ArrowRight, Star } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import { ChartTooltip, clsx, Legend } from '../../components/ui'
import { eur, levelOf } from '../../lib/format'
import { post } from '../../lib/api'
import type { SupplierRow } from '../../lib/types'
import { axisProps, INK, LEVEL, seqColor, SERIES, seriesColor } from '../../lib/chart'

/* ---------- shared types ---------- */

export interface TeamReport {
  best: string; worst: string; verdict: string; findings: string[]
  red_flags: { supplier: string; issue: string }[]
  confidence: string; brief: string; reasoning: string; seconds: number
  chart: { kind: string; columns: string[]; suppliers: string[]; title: string }
}

export interface TeamResult {
  ids: string[]; context: string; lens: string
  weights: Record<string, number>; default_weights: Record<string, number>; why: string
  area_index: Record<string, Record<string, number>>; team_score: Record<string, number>
  ranking: string[]; reports: Record<string, TeamReport>; pick: string
  memo: string; model: string; leader_reasoning: string; created_at: string
}

export interface ChartData {
  kind: 'bars' | 'grouped_bars' | 'scatter' | 'dotplot' | 'heatmap'
  title: string
  columns: { key: string; label: string }[]
  ids: string[]
  mean: Record<string, number>
  rows: Record<string, any>[]
  background?: { x: number; y: number }[]
}

const round1 = (x: number) => Math.round(x * 10) / 10

/* ---------- a specialist's self-designed chart ---------- */

export function SpecChart({ data, shortlistIds }: { data: ChartData | null | undefined; shortlistIds: string[] }) {
  if (data === undefined) return <div className="grid h-32 place-items-center text-xs text-muted">loading chart…</div>
  if (!data) return <div className="grid h-32 place-items-center text-xs text-muted">Chart unavailable</div>
  const color = (id: string) => seriesColor(shortlistIds, id)

  if (data.kind === 'bars') {
    const col = data.columns[0]
    const rows = [...data.rows].sort((a, b) => b[col.key] - a[col.key])
    const currency = data.mean[col.key] > 100
    return (
      <ResponsiveContainer width="100%" height={Math.max(130, rows.length * 34)}>
        <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 28, top: 4, bottom: 4 }}>
          <CartesianGrid stroke={INK.grid} horizontal={false} />
          <XAxis type="number" {...axisProps} tickFormatter={v => currency ? eur(v) : String(v)} />
          <YAxis type="category" dataKey="id" {...axisProps} width={78} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
          <ReferenceLine x={data.mean[col.key]} stroke={INK.muted} strokeDasharray="3 3" />
          <Bar isAnimationActive={false} dataKey={col.key} name={col.label} radius={[0, 4, 4, 0]} maxBarSize={20}
            label={{ position: 'right', fontSize: 11, fill: INK.secondary, formatter: (v: any) => (currency ? eur(v) : String(v)) }}>
            {rows.map(r => <Cell key={r.id} fill={currency ? SERIES[0] : seqColor(r[col.key])} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (data.kind === 'grouped_bars') {
    return (
      <div>
        <Legend items={data.columns.map((c, i) => ({ label: c.label, color: SERIES[i % SERIES.length] }))} />
        <ResponsiveContainer width="100%" height={Math.max(130, data.rows.length * 42)}>
          <BarChart data={data.rows} layout="vertical" margin={{ left: 4, right: 8, top: 8, bottom: 4 }}>
            <CartesianGrid stroke={INK.grid} horizontal={false} />
            <XAxis type="number" {...axisProps} />
            <YAxis type="category" dataKey="id" {...axisProps} width={78} />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
            {data.columns.map((c, i) => (
              <Bar isAnimationActive={false} key={c.key} dataKey={c.key} name={c.label} fill={SERIES[i % SERIES.length]} radius={[0, 4, 4, 0]} maxBarSize={13} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (data.kind === 'scatter' && data.columns.length >= 2) {
    const [cx, cy] = data.columns
    const points = data.rows.map(r => ({ x: r[cx.key], y: r[cy.key], id: r.id }))
    return (
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ left: 4, right: 16, top: 8, bottom: 4 }}>
          <CartesianGrid stroke={INK.grid} />
          <XAxis type="number" dataKey="x" name={cx.label} {...axisProps} />
          <YAxis type="number" dataKey="y" name={cy.label} {...axisProps} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} content={
            <ChartTooltip render={(payload: any) => {
              const p = payload?.[0]?.payload
              return p?.id ? (
                <div><div className="mb-0.5 font-semibold text-ink">{p.id}</div>
                  <div className="text-ink-2">{cx.label}: <b className="text-ink">{p.x}</b></div>
                  <div className="text-ink-2">{cy.label}: <b className="text-ink">{p.y}</b></div></div>
              ) : <div className="text-ink-2">{cx.label} {p?.x} · {cy.label} {p?.y}</div>
            }} />
          } />
          {data.background && <Scatter data={data.background} fill={INK.grid} isAnimationActive={false} />}
          <Scatter data={points} isAnimationActive={false}>
            {points.map(p => <Cell key={p.id} fill={color(p.id)} stroke="#fff" strokeWidth={1} r={6} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    )
  }

  if (data.kind === 'dotplot') {
    return (
      <div className="space-y-3 py-1">
        <Legend items={data.ids.map(id => ({ label: id, color: color(id) }))} />
        {data.columns.map(c => (
          <div key={c.key}>
            <div className="mb-1 flex justify-between text-[11px] text-ink-2"><span>{c.label}</span><span className="text-muted">avg {data.mean[c.key]}</span></div>
            <div className="relative h-2 rounded-full bg-sunken ring-1 ring-line/60">
              {data.rows.map(r => (
                <span key={r.id} title={`${r.id}: ${r[c.key]}`}
                  className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface"
                  style={{ left: `${Math.min(100, Math.max(0, r[c.key]))}%`, background: color(r.id) }} />
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  if (data.kind === 'heatmap') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-separate" style={{ borderSpacing: 4 }}>
          <thead><tr><th /> {data.columns.map(c => <th key={c.key} className="pb-1 text-[10px] font-semibold text-ink-2">{c.label}</th>)}</tr></thead>
          <tbody>
            {data.rows.map(r => (
              <tr key={r.id}>
                <td className="pr-2 text-[11px] font-semibold whitespace-nowrap text-ink">{r.id}</td>
                {data.columns.map(c => (
                  <td key={c.key} className="rounded-lg px-2 py-1.5 text-center text-[11px] font-semibold"
                    style={{ background: seqColor(r[c.key]), color: r[c.key] > 65 ? '#fff' : INK.primary }}>{r[c.key]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return null
}

/* ---------- team scorecard: team score per supplier, lowest = best ---------- */

/** Suppliers ranked by team score: each agent's area risk index (weight under the name), team score and official TRI. */
export function TeamScorecard({ res }: { res: TeamResult }) {
  const areas = Object.keys(res.area_index)
  const [tri, setTri] = useState<Record<string, number>>({})
  useEffect(() => {
    post<SupplierRow[]>('/rows', { ids: res.ranking }).then(r => setTri(Object.fromEntries(r.map(x => [x.id, x.tri])))).catch(() => {})
  }, [res.ranking])
  const cell = (v: number | undefined, bold?: boolean) => (
    <div className={clsx('grid h-8 min-w-14 place-items-center rounded-lg text-[11px] tabular-nums', bold ? 'font-bold' : 'font-semibold')}
      style={v == null ? { background: INK.grid } : { background: seqColor(v), color: v >= 65 ? '#fff' : 'var(--color-ink)' }}>
      {v == null ? '—' : Math.round(v * 10) / 10}
    </div>
  )
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate" style={{ borderSpacing: '3px' }}>
        <thead>
          <tr className="align-bottom text-[10px] font-semibold text-ink-2">
            <th />
            {areas.map(a => <th key={a} className="px-1 pb-1 text-center leading-tight">{a}<div className="font-normal text-muted">{Math.round(res.weights[a] * 100)}%</div></th>)}
            <th className="px-1 pb-1 text-center text-ink">Team score</th>
            <th className="px-1 pb-1 text-center">TRI</th>
          </tr>
        </thead>
        <tbody>
          {res.ranking.map(id => (
            <tr key={id}>
              <td className="pr-2 text-xs font-medium whitespace-nowrap text-ink">
                {id === res.pick && <Star className="mr-1 inline size-3 fill-current text-accent" />}{id}
              </td>
              {areas.map(a => <td key={a} className="p-0">{cell(res.area_index[a][id])}</td>)}
              <td className="p-0">{cell(res.team_score[id], true)}</td>
              <td className="p-0">{cell(tri[id])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function TeamScoreBars({ res }: { res: TeamResult }) {
  const rows = res.ranking.map(id => ({ id, score: res.team_score[id] }))
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, rows.length * 44)}>
      <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 32, top: 4, bottom: 4 }}>
        <CartesianGrid stroke={INK.grid} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} {...axisProps} />
        <YAxis type="category" dataKey="id" {...axisProps} width={84} />
        <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
        <Bar isAnimationActive={false} dataKey="score" name="Team score" radius={[0, 4, 4, 0]} maxBarSize={22}
          label={{ position: 'right', fontSize: 11, fill: INK.secondary }}>
          {rows.map(r => <Cell key={r.id} fill={LEVEL[levelOf(r.score)].dot} fillOpacity={r.id === res.pick ? 1 : 0.5} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/* ---------- score build-up: weight x area index, stacked per supplier ---------- */

export function BuildUpBars({ res }: { res: TeamResult }) {
  const areas = Object.keys(res.weights)
  const rows = res.ranking.map(id => {
    const row: Record<string, any> = { id }
    areas.forEach(a => { row[a] = round1(res.weights[a] * res.area_index[a][id]) })
    return row
  })
  return (
    <div>
      <Legend items={areas.map((a, i) => ({ label: `${a} (${Math.round(res.weights[a] * 100)}%)`, color: SERIES[i % SERIES.length] }))} />
      <ResponsiveContainer width="100%" height={Math.max(140, rows.length * 44)}>
        <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 36, top: 8, bottom: 4 }}>
          <CartesianGrid stroke={INK.grid} horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...axisProps} />
          <YAxis type="category" dataKey="id" {...axisProps} width={84} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
          {areas.map((a, i) => (
            <Bar isAnimationActive={false} key={a} dataKey={a} name={a} stackId="s" fill={SERIES[i % SERIES.length]} maxBarSize={22}
              radius={i === areas.length - 1 ? [0, 4, 4, 0] : undefined} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- leader vs lens default area weights ---------- */

export function WeightsChart({ res }: { res: TeamResult }) {
  const areas = Object.keys(res.weights)
  const rows = areas.map(a => ({ area: a, Leader: round1(res.weights[a] * 100), 'Lens default': round1((res.default_weights[a] ?? 0) * 100) }))
  return (
    <div>
      <Legend items={[{ label: 'Leader (this purchase)', color: SERIES[0] }, { label: 'Lens default', color: SERIES[1] }]} />
      <ResponsiveContainer width="100%" height={210}>
        <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 24, top: 8, bottom: 4 }}>
          <CartesianGrid stroke={INK.grid} horizontal={false} />
          <XAxis type="number" unit="%" {...axisProps} />
          <YAxis type="category" dataKey="area" width={150} {...axisProps} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
          <Bar isAnimationActive={false} dataKey="Leader" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={13} />
          <Bar isAnimationActive={false} dataKey="Lens default" fill={SERIES[1]} radius={[0, 4, 4, 0]} maxBarSize={13} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- flow diagram: buyer -> leader -> 4 specialists -> verdict ---------- */

function FlowNode({ title, subtitle, tone = 'neutral', compact }: { title: string; subtitle?: string; tone?: 'neutral' | 'accent' | 'good'; compact?: boolean }) {
  const toneClass = tone === 'accent' ? 'border-accent/40 bg-accent-soft text-accent-strong'
    : tone === 'good' ? 'border-low-dot/30 bg-low text-low-ink' : 'border-line bg-sunken text-ink-2'
  return (
    <div className={clsx('flex min-w-[148px] flex-col justify-center rounded-2xl border px-3.5 text-center', compact ? 'py-2' : 'py-4', toneClass)}>
      <div className="text-[12px] font-bold">{title}</div>
      {subtitle && <div className="mt-0.5 line-clamp-2 text-[10.5px] opacity-90">{subtitle}</div>}
    </div>
  )
}

export function FlowDiagram({ res }: { res: TeamResult }) {
  const areas = Object.keys(res.weights)
  return (
    <div className="flex items-stretch gap-2.5 overflow-x-auto py-1">
      <FlowNode title="Buyer" subtitle={res.context || 'no buying context given'} />
      <div className="flex items-center text-muted"><ArrowRight className="size-5" /></div>
      <FlowNode title="Leader agent" subtitle="weighs areas, briefs the team" tone="accent" />
      <div className="flex items-center text-muted"><ArrowRight className="size-5" /></div>
      <div className="flex flex-col justify-center gap-2">
        {areas.map(a => (
          <FlowNode key={a} title={a} subtitle={`picks ${res.reports[a]?.best ?? '?'} · ${Math.round(res.weights[a] * 100)}%`}
            tone={res.reports[a]?.best === res.pick ? 'good' : 'neutral'} compact />
        ))}
      </div>
      <div className="flex items-center text-muted"><ArrowRight className="size-5" /></div>
      <FlowNode title="Leader verdict" subtitle={res.pick} tone="good" />
    </div>
  )
}
