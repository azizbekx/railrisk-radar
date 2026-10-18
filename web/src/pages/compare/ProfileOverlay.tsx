// Risk profile overlay: pick up to 5 suppliers, dot plot across all 18 scores vs the dataset mean.
import { useEffect, useState } from 'react'
import { CartesianGrid, ComposedChart, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts'
import { Chip, ChartTooltip, Legend } from '../../components/ui'
import { axisProps, gridProps, INK, seriesColor } from '../../lib/chart'
import { label as labelOf } from '../../lib/format'
import { familyOrder, type CompareResp } from './types'

const MAX_PICK = 5

export function ProfileOverlay({ data, order }: { data: CompareResp; order: string[] }) {
  const [picked, setPicked] = useState<string[]>(order.slice(0, 3))
  useEffect(() => {
    setPicked(p => {
      const kept = p.filter(id => order.includes(id))
      return kept.length ? kept : order.slice(0, 3)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order.join(',')])

  const cols = familyOrder(data.families)
  const rows = cols.map(c => ({ label: labelOf(c), c }))
  const toggle = (id: string) =>
    setPicked(p => (p.includes(id) ? p.filter(x => x !== id) : p.length >= MAX_PICK ? p : [...p, id]))

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {order.map(id => (
          <Chip key={id} active={picked.includes(id)} dot={picked.includes(id) ? seriesColor(picked, id) : undefined} onClick={() => toggle(id)}>
            {id}
          </Chip>
        ))}
      </div>
      {picked.length === 0 ? (
        <div className="py-10 text-center text-sm text-muted">Pick at least one supplier to overlay.</div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={Math.max(360, 26 * rows.length)}>
            <ComposedChart data={rows} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 4 }}>
              <CartesianGrid {...gridProps} horizontal={false} />
              <XAxis type="number" dataKey="value" domain={[0, 100]} {...axisProps} />
              <YAxis type="category" dataKey="label" width={150} {...axisProps} interval={0} allowDuplicatedCategory={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f4f6' }} />
              {picked.map(id => (
                <Scatter isAnimationActive={false}
                  key={id} name={id} data={cols.map(c => ({ label: labelOf(c), value: data.scores[id]?.[c] }))}
                  fill={seriesColor(picked, id)} shape="circle"
                />
              ))}
              <Scatter isAnimationActive={false}
                name="Dataset mean" data={cols.map(c => ({ label: labelOf(c), value: data.means[c] }))}
                fill={INK.muted} shape="diamond"
              />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-3">
            <Legend items={[...picked.map(id => ({ label: id, color: seriesColor(picked, id) })), { label: 'Dataset mean', color: INK.muted }]} />
          </div>
        </>
      )}
    </div>
  )
}
