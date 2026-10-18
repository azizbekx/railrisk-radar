// Head-to-head: diverging score differences + ops comparison + a computed takeaway sentence.
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartTooltip, Field, Select } from '../../components/ui'
import { axisProps, DIVERGE, gridProps, INK } from '../../lib/chart'
import { eur, label as labelOf, num } from '../../lib/format'
import { familyOrder, type CompareResp } from './types'

const OPS: { key: 'delivery' | 'confirmation' | 'change' | 'po'; label: string; higherBetter: boolean | null; fmt: (v: number) => string }[] = [
  { key: 'delivery', label: 'Delivery rating', higherBetter: true, fmt: v => `${num(v, 1)}%` },
  { key: 'confirmation', label: 'Order confirmation', higherBetter: true, fmt: v => `${num(v, 1)}%` },
  { key: 'change', label: 'Order change rate', higherBetter: false, fmt: v => `${num(v, 1)}%` },
  { key: 'po', label: 'PO volume', higherBetter: null, fmt: eur },
]

export function HeadToHead({ data, order }: { data: CompareResp; order: string[] }) {
  const [a, setA] = useState(order[0])
  const [b, setB] = useState(order[1] ?? order[0])
  const ra = data.ranking.find(r => r.id === a)
  const rb = data.ranking.find(r => r.id === b)
  if (!ra || !rb) return null

  const cols = familyOrder(data.families)
  const diffs = cols.map(c => ({ label: labelOf(c), c, diff: (data.scores[a]?.[c] ?? 0) - (data.scores[b]?.[c] ?? 0) }))
  const aSafer = diffs.filter(d => d.diff < 0).length
  const bSafer = diffs.filter(d => d.diff > 0).length
  const leader = aSafer >= bSafer ? a : b
  const leaderCount = Math.max(aSafer, bSafer)
  const top = [...diffs]
    .filter(d => (leader === a ? d.diff < 0 : d.diff > 0))
    .sort((x, y) => Math.abs(y.diff) - Math.abs(x.diff))
    .slice(0, 3)
    .map(d => d.label)

  return (
    <div>
      <div className="mb-4 grid grid-cols-2 gap-3 sm:max-w-md">
        <Field label="Supplier A">
          <Select value={a} onChange={e => setA(e.target.value)}>
            {order.map(id => <option key={id} value={id}>{id} · {data.ranking.find(r => r.id === id)?.name}</option>)}
          </Select>
        </Field>
        <Field label="Supplier B">
          <Select value={b} onChange={e => setB(e.target.value)}>
            {order.map(id => <option key={id} value={id}>{id} · {data.ranking.find(r => r.id === id)?.name}</option>)}
          </Select>
        </Field>
      </div>

      {a === b ? (
        <div className="py-6 text-center text-sm text-muted">Pick two different suppliers to compare.</div>
      ) : (
        <>
          <p className="mb-4 text-sm text-ink-2">
            <strong className="text-ink">{leader}</strong> is lower risk on <strong className="text-ink">{leaderCount}</strong> of {diffs.length} scores
            {top.length ? <>, mainly <strong className="text-ink">{top.join(', ')}</strong></> : null}.
          </p>
          <ResponsiveContainer width="100%" height={Math.max(360, 26 * diffs.length)}>
            <BarChart data={diffs} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 4 }}>
              <CartesianGrid {...gridProps} horizontal={false} />
              <XAxis type="number" domain={['dataMin', 'dataMax']} {...axisProps} tickFormatter={v => `${v > 0 ? '+' : ''}${v}`} />
              <YAxis type="category" dataKey="label" width={150} {...axisProps} interval={0} />
              <Tooltip content={<ChartTooltip render={(payload: any) => (
                <div className="text-ink-2">{a} minus {b}: <span className="font-semibold text-ink">{payload[0]?.value > 0 ? '+' : ''}{payload[0]?.value}</span></div>
              )} />} cursor={{ fill: '#f3f4f6' }} />
              <ReferenceLine x={0} stroke={INK.axis} />
              <Bar isAnimationActive={false} dataKey="diff" radius={4}>
                {diffs.map((d, i) => <Cell key={i} fill={d.diff < 0 ? DIVERGE.better : d.diff > 0 ? DIVERGE.worse : DIVERGE.neutral} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-2 text-[11px] text-muted">Bars left (blue) = {a} is lower risk on that score. Bars right (red) = {b} is lower risk.</p>

          <div className="mt-6 overflow-hidden rounded-2xl border border-line">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-sunken text-left text-xs font-semibold text-ink-2">
                  <th className="px-4 py-2">Operational metric</th>
                  <th className="px-4 py-2">{a}</th>
                  <th className="px-4 py-2">{b}</th>
                  <th className="px-4 py-2">Better</th>
                </tr>
              </thead>
              <tbody>
                {OPS.map(m => {
                  const va = ra[m.key], vb = rb[m.key]
                  const better = m.higherBetter === null ? null : (m.higherBetter ? va > vb : va < vb) ? a : va === vb ? null : b
                  return (
                    <tr key={m.key} className="border-t border-line">
                      <td className="px-4 py-2 text-ink-2">{m.label}</td>
                      <td className="px-4 py-2 font-medium text-ink tabular-nums">{m.fmt(va)}</td>
                      <td className="px-4 py-2 font-medium text-ink tabular-nums">{m.fmt(vb)}</td>
                      <td className="px-4 py-2 text-ink-2">{better ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
