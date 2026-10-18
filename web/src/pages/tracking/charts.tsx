// Charts for live tracking: portfolio history + forecast, sparklines, small multiples, per-area lines and bars.
import { Area as RArea, Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ReferenceArea, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartTooltip, clsx, Legend, LevelBadge } from '../../components/ui'
import { axisProps, gridProps, INK, LEVEL, SERIES } from '../../lib/chart'
import { levelOf } from '../../lib/format'
import { Delta, TrendMark } from './bits'
import { AREA_COLOR, AREA_SHORT, AREAS, domainOf, fmtDate, n1, signed } from './util'
import type { Area, ForecastPoint, Point, TrackedSupplier } from './types'

type Row = { date: string; score?: number; fscore?: number; band?: [number, number] }

/** History + forecast on one date axis. The forecast line/band start at today's value so the two join up. */
function joinRows(series: Point[], forecast: ForecastPoint[]): Row[] {
  const rows: Row[] = series.map(p => ({ date: p.date, score: p.score }))
  const last = rows[rows.length - 1]
  if (last && forecast.length) { last.fscore = last.score; last.band = [last.score!, last.score!] }
  for (const f of forecast) rows.push({ date: f.date, fscore: f.score, band: [f.low, f.high] })
  return rows
}

const LINE = SERIES[0]
const LEVELS = [['Low', 0, 25], ['Medium', 25, 50], ['High', 50, 75], ['Critical', 75, 100]] as const

/** Faint level bands (25/50/75) behind the lines, clipped to the visible domain. */
const levelBands = (labels: boolean) => LEVELS.map(([l, a, b]) => (
  <ReferenceArea key={l} y1={a} y2={b} ifOverflow="hidden" fill={LEVEL[l].dot} fillOpacity={0.07} stroke="none"
    label={labels ? { value: l, position: 'insideTopRight', fontSize: 10, fill: LEVEL[l].ink } : undefined} />
))

/* ---------- main chart: last 30 days + 30-day forecast ---------- */

export function PortfolioChart({ series, forecast, height = 340 }: { series: Point[]; forecast: ForecastPoint[]; height?: number }) {
  const rows = joinRows(series, forecast)
  const today = series[series.length - 1]?.date
  const dom = domainOf([...series.map(p => p.score), ...forecast.flatMap(f => [f.low, f.high])], 6)
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 rounded" style={{ background: LINE }} />Risk score (last 30 days)</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-5 border-t-2 border-dashed" style={{ borderColor: LINE }} />Forecast (next 30 days)</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm" style={{ background: LINE, opacity: 0.18 }} />Low–high range</span>
        <Legend items={LEVELS.map(([l]) => ({ label: l, color: LEVEL[l].dot }))} />
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ left: 0, right: 12, top: 8, bottom: 0 }}>
          {levelBands(true)}
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="date" {...axisProps} tickFormatter={d => fmtDate(d)} minTickGap={36} />
          <YAxis {...axisProps} domain={dom} width={34} allowDecimals={false} />
          <Tooltip content={<ChartTooltip render={(p: any) => {
            const r: Row = p[0].payload
            const fc = r.score == null
            return (
              <div>
                <div className="mb-1 font-semibold text-ink">{fmtDate(r.date, true)}{fc && <span className="ml-1.5 font-normal text-muted">forecast</span>}</div>
                <div className="text-ink-2">Risk score <b className="text-ink">{n1((fc ? r.fscore : r.score) ?? 0)}</b> · {levelOf((fc ? r.fscore : r.score) ?? 0)}</div>
                {fc && r.band && <div className="text-ink-2">Range <b className="text-ink">{n1(r.band[0])}–{n1(r.band[1])}</b></div>}
              </div>
            )
          }} />} />
          <RArea dataKey="band" stroke="none" fill={LINE} fillOpacity={0.16} isAnimationActive={false} activeDot={false} legendType="none" />
          <Line dataKey="score" stroke={LINE} strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line dataKey="fscore" stroke={LINE} strokeWidth={2.5} strokeDasharray="6 5" dot={false} isAnimationActive={false} />
          {today && <ReferenceLine x={today} stroke={INK.secondary} strokeDasharray="2 3" label={{ value: 'Today', position: 'insideTopLeft', fontSize: 11, fill: INK.secondary, fontWeight: 600 }} />}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- sparkline (table cells + small multiples) ---------- */

export function Spark({ series, forecast, level, domain, height = 32, band = false, bands = false }:
  { series: Point[]; forecast: ForecastPoint[]; level: string | null; domain?: [number, number]; height?: number; band?: boolean; bands?: boolean }) {
  if (!series.length) return <div className="text-[11px] text-muted" style={{ height }}>–</div>
  const rows = joinRows(series, forecast)
  const today = series[series.length - 1]
  const dom = domain ?? domainOf([...series.map(p => p.score), ...forecast.flatMap(f => [f.low, f.high])], 3)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ left: 2, right: 4, top: 4, bottom: 4 }}>
        {bands && levelBands(false)}
        <XAxis dataKey="date" hide />
        <YAxis hide domain={dom} />
        {band && <RArea dataKey="band" stroke="none" fill={LINE} fillOpacity={0.16} isAnimationActive={false} />}
        <Line dataKey="score" stroke={LINE} strokeWidth={1.75} dot={false} isAnimationActive={false} />
        <Line dataKey="fscore" stroke={LINE} strokeWidth={1.75} strokeDasharray="3 3" strokeOpacity={0.8} dot={false} isAnimationActive={false} />
        <ReferenceDot x={today.date} y={today.score} r={3.5} fill={LEVEL[(level ?? levelOf(today.score)) as keyof typeof LEVEL]?.dot ?? LINE} stroke="#fff" strokeWidth={1.5} ifOverflow="visible" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/* ---------- second chart: every supplier as a small multiple on one shared scale ---------- */

export function SmallMultiples({ suppliers, selected, onOpen }: { suppliers: TrackedSupplier[]; selected?: string | null; onOpen: (id: string) => void }) {
  const tracked = suppliers.filter(s => s.series.length)
  const dom = domainOf(tracked.flatMap(s => [...s.series.map(p => p.score), ...s.forecast.flatMap(f => [f.low, f.high])]), 3)
  if (!tracked.length) return <div className="grid h-24 place-items-center text-xs text-muted">No history yet. Run the agents to backfill the last 30 days.</div>
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="h-0.5 w-5 rounded" style={{ background: LINE }} />Last 30 days</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-5 border-t-2 border-dashed" style={{ borderColor: LINE }} />Next 30 days</span>
        <span className="text-muted">Same scale ({dom[0]}–{dom[1]}) in every card, shaded bands are Low / Medium / High / Critical</span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {tracked.map(s => (
          <button key={s.id} onClick={() => onOpen(s.id)} aria-label={`Open ${s.name}`}
            className={clsx('rounded-2xl border bg-surface p-3 text-left transition hover:border-line-strong hover:shadow-[var(--shadow-soft)] focus-visible:ring-4 focus-visible:ring-accent/20 focus-visible:outline-none',
              selected === s.id ? 'border-accent ring-2 ring-accent/20' : 'border-line')}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-[13px] font-semibold text-ink">{s.name}</div>
                <div className="flex items-center gap-2 text-[11px] text-muted"><Delta v={s.delta_7d} /><span>7d</span><TrendMark trend={s.trend} /></div>
              </div>
              {s.score != null && s.level && <LevelBadge level={s.level} value={n1(s.score)} size="sm" />}
            </div>
            <Spark series={s.series} forecast={s.forecast} level={s.level} domain={dom} height={76} band bands />
            {s.outlook && <div className="text-[11px] text-ink-2">Next 30 days <b className="tabular-nums text-ink">{signed(s.outlook.delta_30d)}</b> · {Math.round(s.outlook.disruption_prob_90d * 100)}% disruption risk in 90 days</div>}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ---------- supplier detail charts ---------- */

export function AreaLines({ data }: { data: ({ date: string } & Record<Area, number>)[] }) {
  const dom = domainOf(data.flatMap(r => AREAS.map(a => r[a])), 4)
  return (
    <div>
      <div className="mb-2"><Legend items={AREAS.map(a => ({ label: AREA_SHORT[a], color: AREA_COLOR[a] }))} /></div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: 0, right: 8, top: 6, bottom: 0 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="date" {...axisProps} tickFormatter={d => fmtDate(d)} minTickGap={36} />
          <YAxis {...axisProps} domain={dom} width={30} allowDecimals={false} />
          <Tooltip content={<ChartTooltip render={(p: any, label: string) => (
            <div>
              <div className="mb-1 font-semibold text-ink">{fmtDate(label, true)}</div>
              {AREAS.map(a => <div key={a} className="flex items-center gap-2 text-ink-2"><span className="size-2 rounded-full" style={{ background: AREA_COLOR[a] }} />{AREA_SHORT[a]}<span className="ml-auto pl-3 font-semibold text-ink tabular-nums">{n1(p[0].payload[a])}</span></div>)}
            </div>
          )} />} />
          {AREAS.map(a => <Line key={a} dataKey={a} name={AREA_SHORT[a]} stroke={AREA_COLOR[a]} strokeWidth={2} dot={false} isAnimationActive={false} />)}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Current area scores (level-coloured) next to the structural baseline (grey). */
export function AreaBars({ areas, baseline }: { areas: Record<Area, number>; baseline: Record<Area, number> | null }) {
  const rows = AREAS.map(a => ({ area: AREA_SHORT[a], Current: Math.round(areas[a] * 10) / 10, Baseline: baseline ? Math.round(baseline[a] * 10) / 10 : undefined }))
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: SERIES[0] }} />Current</span>
        {baseline && <span className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: '#c3c9d4' }} />Baseline (before recent events)</span>}
      </div>
      <ResponsiveContainer width="100%" height={Math.max(150, rows.length * (baseline ? 48 : 34))}>
        <BarChart data={rows} layout="vertical" margin={{ left: 4, right: 30, top: 4, bottom: 0 }}>
          <CartesianGrid stroke={INK.grid} horizontal={false} />
          <XAxis type="number" {...axisProps} domain={[0, 100]} />
          <YAxis type="category" dataKey="area" {...axisProps} width={96} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
          <Bar dataKey="Current" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={14} isAnimationActive={false}
            label={{ position: 'right', fontSize: 11, fill: INK.secondary }} />
          {baseline && <Bar dataKey="Baseline" fill="#c3c9d4" radius={[0, 4, 4, 0]} maxBarSize={10} isAnimationActive={false} />}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
