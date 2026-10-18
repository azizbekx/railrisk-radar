// TRI composition: one horizontal stacked bar per supplier, one segment per risk family.
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartTooltip, Legend } from '../../components/ui'
import { axisProps, BAR_RADIUS_H, gridProps, SERIES } from '../../lib/chart'
import type { CompareResp } from './types'

export function TriComposition({ data, order }: { data: CompareResp; order: string[] }) {
  const families = Object.keys(data.families)
  const rows = order.map(sid => ({ id: sid, ...data.tri_composition[sid] }))

  return (
    <div>
      <ResponsiveContainer width="100%" height={Math.max(220, 56 * order.length)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 36, left: 4, bottom: 4 }}>
          <CartesianGrid {...gridProps} />
          <XAxis type="number" domain={[0, 100]} {...axisProps} />
          <YAxis type="category" dataKey="id" width={84} {...axisProps} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
          {families.map((fam, i) => (
            <Bar isAnimationActive={false}
              key={fam} dataKey={fam} stackId="tri" name={fam} fill={SERIES[i % SERIES.length]} stroke="#fff" strokeWidth={2}
              radius={i === families.length - 1 ? BAR_RADIUS_H : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-3">
        <Legend items={families.map((f, i) => ({ label: f, color: SERIES[i % SERIES.length] }))} />
      </div>
    </div>
  )
}
