// Renders the real-data chart payloads the backend attaches to show_chart tool results (api/routes/chat.py _chart).
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, ChartTooltip, Legend } from '../../components/ui'
import { axisProps, BAR_RADIUS_H, gridProps, INK, LEVEL, seriesColor } from '../../lib/chart'
import { eur, num } from '../../lib/format'

type RiskBreakdown = { kind: 'risk_breakdown'; title: string; supplier: string; tri: number; level: string; average: number
  bars: { key: string; label: string; value: number; level: string; vs_average: number; weight: number }[] }
type CompareBars = { kind: 'compare_bars'; title: string; suppliers: string[]; names: Record<string, string>
  columns: { key: string; label: string; isPO: boolean }[]; rows: Record<string, string | number>[] }
type Heatmap = { kind: 'heatmap'; title: string; suppliers: string[]; scores: { key: string; label: string }[]
  values: Record<string, Record<string, number>>; tri: Record<string, number> }
type Profile = { kind: 'profile'; title: string; suppliers: string[]; scores: { key: string; label: string }[]
  values: Record<string, Record<string, number>> }
type Distribution = { kind: 'distribution'; title: string; column: string; label: string
  bins: { x0: number; x1: number; count: number }[]; marks: { id: string; value: number }[] }

export type ChatChartData = RiskBreakdown | CompareBars | Heatmap | Profile | Distribution

const short = (sid: string) => sid.replace('SUPP_', 'S')
const heatColor = (v: number) => (v >= 75 ? LEVEL.Critical : v >= 50 ? LEVEL.High : v >= 25 ? LEVEL.Medium : LEVEL.Low)
const colorForLevel = (level: string) => LEVEL[level as keyof typeof LEVEL] ?? LEVEL.Low

function RiskBreakdownChart({ c }: { c: RiskBreakdown }) {
  const data = c.bars.map(b => ({ ...b, name: b.label }))
  return (
    <div>
      <ResponsiveContainer width="100%" height={Math.max(260, data.length * 24)}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
          <CartesianGrid {...gridProps} horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...axisProps} />
          <YAxis type="category" dataKey="name" width={150} {...axisProps} />
          <ReferenceLine x={c.average} stroke={INK.axis} strokeDasharray="3 3" />
          <Bar isAnimationActive={false} dataKey="value" radius={BAR_RADIUS_H} barSize={12}>
            {data.map(d => <Cell key={d.key} fill={colorForLevel(d.level).dot} />)}
          </Bar>
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-1 text-[11px] text-muted">Dashed line = dataset average TRI ({num(c.average, 1)}).</div>
    </div>
  )
}

function CompareBarsChart({ c }: { c: CompareBars }) {
  const isPO = c.columns.some(col => col.isPO)
  return (
    <div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={c.rows} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="column" {...axisProps} />
          <YAxis {...axisProps} tickFormatter={v => (isPO ? eur(v) : String(v))} />
          <Tooltip content={<ChartTooltip render={(payload: any[]) => (
            <>{payload.map(p => (
              <div key={p.dataKey} className="flex items-center gap-2 text-ink-2">
                <span className="size-2 rounded-full" style={{ background: p.color }} />
                <span>{c.names[p.dataKey] ?? p.dataKey}</span>
                <span className="ml-auto pl-3 font-semibold text-ink tabular-nums">{p.payload.isPO ? eur(p.value) : num(p.value, 1)}</span>
              </div>
            ))}</>
          )} />} cursor={{ fill: '#f3f4f6' }} />
          {c.suppliers.map(sid => (
            <Bar isAnimationActive={false} key={sid} dataKey={sid} name={sid} fill={seriesColor(c.suppliers, sid)} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2">
        <Legend items={c.suppliers.map(sid => ({ label: `${sid} · ${c.names[sid] ?? ''}`, color: seriesColor(c.suppliers, sid) }))} />
      </div>
    </div>
  )
}

function HeatmapGrid({ c }: { c: Heatmap }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr>
            <th className="sticky left-0 bg-surface px-2 py-1.5 text-left font-semibold text-ink-2">Supplier</th>
            <th className="px-2 py-1.5 text-center font-semibold text-ink-2">TRI</th>
            {c.scores.map(s => <th key={s.key} className="min-w-[64px] px-1.5 py-1.5 text-center font-medium text-muted">{s.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {c.suppliers.map(sid => (
            <tr key={sid} className="border-t border-line">
              <td className="sticky left-0 bg-surface px-2 py-1 font-semibold text-ink whitespace-nowrap">{short(sid)}</td>
              <td className="px-2 py-1 text-center font-bold" style={{ color: heatColor(c.tri[sid]).ink }}>{c.tri[sid]}</td>
              {c.scores.map(s => {
                const v = c.values[sid]?.[s.key] ?? 0
                const col = heatColor(v)
                return <td key={s.key} className="px-1.5 py-1 text-center font-semibold" style={{ background: col.bg, color: col.ink }}>{v}</td>
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ProfileChart({ c }: { c: Profile }) {
  const data = c.scores.map(s => ({ name: s.label, ...Object.fromEntries(c.suppliers.map(sid => [sid, c.values[sid]?.[s.key] ?? 0])) }))
  return (
    <div>
      <ResponsiveContainer width="100%" height={Math.max(260, data.length * 32)}>
        <BarChart data={data} layout="vertical" barGap={2} margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid {...gridProps} horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...axisProps} />
          <YAxis type="category" dataKey="name" width={150} {...axisProps} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
          {c.suppliers.map(sid => <Bar isAnimationActive={false} key={sid} dataKey={sid} name={sid} fill={seriesColor(c.suppliers, sid)} radius={BAR_RADIUS_H} barSize={10} />)}
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2">
        <Legend items={c.suppliers.map(sid => ({ label: short(sid), color: seriesColor(c.suppliers, sid) }))} />
      </div>
    </div>
  )
}

function DistributionChart({ c }: { c: Distribution }) {
  const data = c.bins.map(b => ({ x: (b.x0 + b.x1) / 2, count: b.count }))
  const ids = c.marks.map(m => m.id)
  return (
    <div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} {...axisProps} />
          <YAxis {...axisProps} />
          <Tooltip content={<ChartTooltip render={(payload: any[], label: any) => (
            <div className="text-ink-2">{c.label} ≈ {num(label, 0)}: <span className="font-semibold text-ink">{payload[0].value}</span> suppliers</div>
          )} />} cursor={{ fill: '#f3f4f6' }} />
          <Bar isAnimationActive={false} dataKey="count" fill="#cde2fb" radius={[2, 2, 0, 0]} />
          {c.marks.map(m => (
            <ReferenceLine key={m.id} x={m.value} stroke={seriesColor(ids, m.id)} strokeWidth={2}
              label={{ value: short(m.id), position: 'top', fill: seriesColor(ids, m.id), fontSize: 11, fontWeight: 600 }} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ChatChart({ chart }: { chart: ChatChartData }) {
  return (
    <Card className="mt-1">
      <div className="mb-3 text-sm font-semibold text-ink">{chart.title}</div>
      {chart.kind === 'risk_breakdown' && <RiskBreakdownChart c={chart} />}
      {chart.kind === 'compare_bars' && <CompareBarsChart c={chart} />}
      {chart.kind === 'heatmap' && <HeatmapGrid c={chart} />}
      {chart.kind === 'profile' && <ProfileChart c={chart} />}
      {chart.kind === 'distribution' && <DistributionChart c={chart} />}
    </Card>
  )
}
