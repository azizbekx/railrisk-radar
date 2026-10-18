// Price vs risk: buyer quotes -> "best value" ranking that weighs risk against price by the kind of component.
// The dataset has no price column; prices come only from the quotes entered here (PO volume is spend, not price).
import { Euro, Sparkles, Trophy, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { Button, ChartTooltip, clsx, LevelBadge, Legend, Skeleton, Tag } from '../../components/ui'
import { post } from '../../lib/api'
import { axisProps, gridProps, INK, LEVEL, SERIES } from '../../lib/chart'
import { num } from '../../lib/format'
import { demoQuote, price as eurExact } from '../../lib/quotes'
import { useApp, useLens } from '../../lib/store'
import type { PartType } from '../../lib/types'
import type { ValueResp, ValueRow } from './types'

const PART_ORDER: PartType[] = ['safety_critical', 'standard', 'budget']
const BEST = SERIES[2]
const BAD = LEVEL.Critical.dot

export function Value({ ids, onOpen }: { ids: string[]; onOpen: (id: string) => void }) {
  const { meta, partType, setPartType, quotes, setQuote } = useApp()
  const lens = useLens()
  const [data, setData] = useState<ValueResp | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const shown = useMemo(() => Object.fromEntries(ids.filter(i => quotes[i] > 0).map(i => [i, quotes[i]])), [ids, quotes])
  const nQuotes = Object.keys(shown).length
  const key = ids.join(',') + '|' + partType + '|' + JSON.stringify(shown) + '|' + lens.name + '|' + JSON.stringify(lens.weights)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError('')
    post<ValueResp>('/compare/value', { ids, quotes: shown, part_type: partType, lens_weights: lens.weights })
      .then(r => { if (!cancelled) setData(r) })
      .catch(e => { if (!cancelled) setError(e.message || 'Failed to rank by value') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const spec = meta?.part_types[partType]
  const pw = spec?.price_weight ?? data?.price_weight ?? 0.4
  const byId = useMemo(() => Object.fromEntries((data?.rows ?? []).map(r => [r.id, r])), [data])
  const rows = ids.map(i => byId[i]).filter(Boolean) as ValueRow[]

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-3">
        {PART_ORDER.map(p => {
          const m = meta?.part_types[p]
          if (!m) return null
          const on = p === partType
          return (
            <button key={p} onClick={() => setPartType(p)} aria-pressed={on}
              className={clsx('rounded-2xl border p-3 text-left transition', on ? 'border-accent bg-accent-soft/60 ring-2 ring-accent/15' : 'border-line bg-surface hover:border-line-strong hover:bg-sunken')}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-ink">{m.label}</span>
                <span className={clsx('text-[11px] font-semibold tabular-nums', on ? 'text-accent-strong' : 'text-muted')}>
                  Risk {Math.round((1 - m.price_weight) * 100)}% · Price {Math.round(m.price_weight * 100)}%
                </span>
              </div>
              <div className="mt-0.5 text-xs text-muted">{m.examples}</div>
              <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-sunken">
                <div className="bg-accent" style={{ width: `${(1 - m.price_weight) * 100}%` }} />
                <div className="bg-medium-dot" style={{ width: `${m.price_weight * 100}%` }} />
              </div>
            </button>
          )
        })}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-3xl text-sm text-ink-2">
          {error ? <span className="text-critical-ink">{error}</span>
            : data ? <>{data.explanation}</>
            : <span className="text-muted">Weighing price against risk…</span>}
        </p>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="ghost" icon={<Sparkles className="size-3.5" />}
            title="Fills illustrative quotes between €800 and €1,200, derived from each supplier ID. Not real prices."
            onClick={() => ids.forEach(i => setQuote(i, demoQuote(i)))}>Fill demo quotes</Button>
          {nQuotes > 0 && <Button size="sm" variant="ghost" icon={<X className="size-3.5" />} onClick={() => ids.forEach(i => setQuote(i, null))}>Clear quotes</Button>}
        </div>
      </div>
      {nQuotes < 2 && (
        <div className="rounded-xl border border-dashed border-line-strong bg-sunken/50 px-3.5 py-2.5 text-xs text-ink-2">
          <Euro className="mr-1.5 inline size-3.5 -translate-y-px text-muted" />
          Enter quotes from your RFQ for at least two suppliers to see the best value. Demo quotes are made-up values for trying it out.
          Prices come only from your quotes: the dataset has no price column, and PO volume is existing spend, not a price.
        </div>
      )}

      {!data && loading ? <Skeleton className="h-48" /> : (
        <div className={clsx('space-y-5', loading && 'opacity-70 transition')}>
          <QuoteTable rows={rows} data={data} quotes={quotes} setQuote={setQuote} onOpen={onOpen} partType={partType} />
          <div>
            <ValueChart data={data} rows={rows} pw={pw} />
            {spec && <p className="mt-2 text-[11px] leading-snug text-muted">Risk gate: {spec.why}</p>}
          </div>
        </div>
      )}
    </div>
  )
}

function QuoteInput({ id, value, onCommit }: { id: string; value: number | undefined; onCommit: (v: number | null) => void }) {
  const [text, setText] = useState(value ? String(value) : '')
  const timer = useRef<number | undefined>(undefined)
  const typed = useRef(false)
  // follow external changes (demo fill, clear) but not our own typing
  useEffect(() => {
    if (typed.current) { typed.current = false; return }
    setText(value ? String(value) : '')
  }, [value])
  useEffect(() => () => window.clearTimeout(timer.current), [])
  return (
    <div className="relative w-28">
      <span className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-xs text-muted">€</span>
      <input inputMode="decimal" aria-label={`Quoted price for ${id} in EUR`} placeholder="no quote" value={text}
        onChange={e => {
          const t = e.target.value.replace(/[^\d.,]/g, '')
          setText(t)
          window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => {
            const n = parseFloat(t.replace(/,/g, ''))
            typed.current = true
            onCommit(n > 0 ? n : null)
          }, 450)
        }}
        className="h-8 w-full rounded-full border border-line bg-surface pr-2.5 pl-6 text-right text-sm text-ink tabular-nums placeholder:text-muted transition focus:border-accent focus:ring-4 focus:ring-accent/15 focus:outline-none" />
    </div>
  )
}

function QuoteTable({ rows, data, quotes, setQuote, onOpen, partType }: {
  rows: ValueRow[]; data: ValueResp | null; quotes: Record<string, number>
  setQuote: (id: string, p: number | null) => void; onOpen: (id: string) => void; partType: PartType
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs font-semibold text-ink-2">
            <th className="px-2 py-2">Supplier</th>
            <th className="px-2 py-2">{data?.risk_label ?? 'TRI'}</th>
            <th className="px-2 py-2 text-right">Quote (EUR)</th>
            <th className="px-2 py-2 text-right">vs cheapest</th>
            <th className="px-2 py-2 text-right" title="Lower is better: weighted blend of normalised risk and price">Value score</th>
            <th className="px-2 py-2 text-center">Rank</th>
            <th className="px-2 py-2">Flags</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const best = r.id === data?.best
            return (
              <tr key={r.id} className={clsx('border-t border-line transition', best ? 'bg-accent-soft/60' : 'hover:bg-sunken/70')}>
                <td className="px-2 py-2">
                  <button onClick={() => onOpen(r.id)} className="text-left font-semibold text-ink hover:text-accent-strong hover:underline">{r.id}</button>
                  <div className="max-w-[160px] truncate text-xs text-muted">{r.name}</div>
                </td>
                <td className="px-2 py-2"><LevelBadge level={r.level} value={num(r.risk, 1)} /></td>
                <td className="px-2 py-2"><div className="flex justify-end"><QuoteInput id={r.id} value={quotes[r.id]} onCommit={v => setQuote(r.id, v)} /></div></td>
                <td className="px-2 py-2 text-right tabular-nums text-ink-2">
                  {r.price_vs_cheapest == null ? '—' : r.price_vs_cheapest === 0 ? <span className="font-semibold text-low-ink">cheapest</span> : `+${num(r.price_vs_cheapest * 100, r.price_vs_cheapest < 0.095 ? 1 : 0)}%`}
                </td>
                <td className="px-2 py-2 text-right font-semibold tabular-nums text-ink">{r.value_score == null ? <span className="font-normal text-muted">—</span> : num(r.value_score, 1)}</td>
                <td className="px-2 py-2 text-center">
                  {best ? <span className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-bold text-white"><Trophy className="size-3" />{r.rank}</span>
                    : r.rank != null ? <span className="font-semibold text-muted">{r.rank}</span> : <span className="text-muted">—</span>}
                </td>
                <td className="px-2 py-2">
                  <div className="flex flex-wrap items-center gap-1">
                    {r.price != null && r.frontier && data && data.rows.filter(x => x.price != null).length >= 2 && <Tag tone="accent">Efficient</Tag>}
                    {!r.passes_gate && (
                      <span title={r.gate_reason ?? undefined}>
                        <Tag tone="bad">{partType === 'safety_critical' && r.price != null ? 'Fails gate · not ranked' : 'Fails gate'}</Tag>
                      </span>
                    )}
                  </div>
                  {!r.passes_gate && r.gate_reason && <div className="mt-0.5 max-w-xs text-[11px] leading-tight text-critical-ink">{r.gate_reason}</div>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ValueChart({ data, rows, pw }: { data: ValueResp | null; rows: ValueRow[]; pw: number }) {
  const quoted = rows.filter(r => r.price != null)
  if (!data || quoted.length < 2) {
    return (
      <div className="grid h-full min-h-56 place-items-center rounded-2xl border border-dashed border-line-strong bg-sunken/40 p-6 text-center text-sm text-muted">
        The price vs risk chart appears once two suppliers have a quote.
      </div>
    )
  }
  const pts = quoted.map(r => ({ ...r, x: r.price as number, y: r.risk }))
  const front = pts.filter(p => p.frontier).sort((a, b) => a.x - b.x || a.y - b.y)
  const lo = Math.min(...pts.map(p => p.x)), hi = Math.max(...pts.map(p => p.x))
  const pad = Math.max((hi - lo) * 0.12, hi * 0.02)
  const ymin = Math.min(...pts.map(p => p.y)), ymax = Math.max(...pts.map(p => p.y))
  const ypad = Math.max((ymax - ymin) * 0.15, 3)

  const Dot = (p: any) => {
    const d = p.payload as typeof pts[number]
    const best = d.id === data.best
    const bad = !d.passes_gate
    const cx = p.cx, cy = p.cy
    return (
      <g>
        {best && <circle cx={cx} cy={cy} r={11} fill={BEST} fillOpacity={0.18} />}
        {bad
          ? <circle cx={cx} cy={cy} r={best ? 7 : 5.5} fill="#fff" stroke={BAD} strokeWidth={2} />
          : <circle cx={cx} cy={cy} r={best ? 7 : 5} fill={best ? BEST : SERIES[0]} fillOpacity={best ? 1 : 0.55} stroke="#fff" strokeWidth={1.5} />}
        {(best || d.frontier || quoted.length <= 8) && (
          <text x={cx + 10} y={cy - 8} fontSize={10} fontWeight={best ? 700 : 500} fill={best ? INK.primary : INK.secondary}>{d.id.replace('SUPP_', 'S')}</text>
        )}
      </g>
    )
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 10, right: 24, left: 4, bottom: 22 }}>
          <CartesianGrid {...gridProps} vertical />
          <XAxis type="number" dataKey="x" name="Quoted price" domain={[Math.floor(lo - pad), Math.ceil(hi + pad)]} {...axisProps}
            tickFormatter={(v: number) => num(v)}
            label={{ value: 'Quoted price (EUR)  →  more expensive', position: 'insideBottom', offset: -12, fill: INK.muted, fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name={data.risk_label} width={44} domain={[Math.max(0, Math.floor(ymin - ypad)), Math.min(100, Math.ceil(ymax + ypad))]} {...axisProps}
            label={{ value: `${data.risk_label}  →  riskier`, angle: -90, position: 'insideLeft', offset: 8, fill: INK.muted, fontSize: 11, style: { textAnchor: 'middle' } }} />
          <Tooltip cursor={{ strokeDasharray: '3 3', stroke: INK.axis }} content={<ChartTooltip render={(payload: any[]) => {
            const d = payload[0]?.payload as ValueRow | undefined
            if (!d) return null
            return (
              <div className="space-y-0.5">
                <div className="font-semibold text-ink">{d.id} <span className="font-normal text-muted">{d.name}</span></div>
                <div className="text-ink-2">Quote <b className="text-ink">{d.price != null ? eurExact(d.price) : '—'}</b>
                  {d.price_vs_cheapest ? <> ({`+${num(d.price_vs_cheapest * 100, d.price_vs_cheapest < 0.095 ? 1 : 0)}%`})</> : null}</div>
                <div className="text-ink-2">{data.risk_label} <b className="text-ink">{num(d.risk, 1)}</b> · {d.level}</div>
                {d.value_score != null && <div className="text-ink-2">Value score <b className="text-ink">{num(d.value_score, 1)}</b>{d.rank ? <> · rank {d.rank}</> : null}</div>}
                {!d.passes_gate && <div className="text-critical-ink">Fails gate: {d.gate_reason}</div>}
              </div>
            )
          }} />} />
          <Scatter name="Efficient frontier" data={front} legendType="none" tooltipType="none" isAnimationActive={false}
            line={{ stroke: INK.muted, strokeWidth: 1.5, strokeDasharray: '5 4' }} shape={() => <g />} />
          <Scatter name="Quoted suppliers" data={pts} isAnimationActive={false} shape={Dot} />
        </ScatterChart>
      </ResponsiveContainer>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
        <Legend items={[
          { label: 'Quoted supplier', color: SERIES[0] },
          { label: `Best value${data.best ? ` (${data.best})` : ''}`, color: BEST },
          { label: 'Fails risk gate', color: BAD },
          { label: 'Efficient frontier (dashed)', color: INK.muted },
        ]} />
        <span className="text-[11px] text-muted">Lower-left is better · price weight {Math.round(pw * 100)}%</span>
      </div>
    </div>
  )
}
