// 18-score heatmap: suppliers x scores, coloured by the sequential risk ramp, best-in-set per column outlined.
import { SERIES, seqColor } from '../../lib/chart'
import { label as labelOf } from '../../lib/format'
import type { CompareResp } from './types'

export function Heatmap({ data, order }: { data: CompareResp; order: string[] }) {
  const families = Object.entries(data.families)
  const cols = families.flatMap(([, cs]) => cs)

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate" style={{ borderSpacing: '3px' }}>
        <thead>
          <tr>
            <th className="sticky left-0 z-10 w-36 bg-surface" />
            {families.map(([fam, cs], fi) => (
              <th key={fam} colSpan={cs.length} className="pb-1.5 text-center">
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-ink-2">
                  <span className="size-1.5 rounded-full" style={{ background: SERIES[fi % SERIES.length] }} />
                  {fam}
                </span>
              </th>
            ))}
          </tr>
          <tr>
            <th className="sticky left-0 z-10 bg-surface text-left text-xs font-semibold text-ink">Supplier</th>
            {cols.map(c => (
              <th key={c} className="h-28 w-11 pb-1.5 align-bottom" title={labelOf(c)}>
                <div className="mx-auto h-24 text-[10px] whitespace-nowrap text-muted" style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}>
                  {labelOf(c)}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {order.map(sid => (
            <tr key={sid}>
              <td className="sticky left-0 z-10 bg-surface py-0.5 pr-2 text-xs font-medium whitespace-nowrap text-ink">{sid}</td>
              {cols.map(c => {
                const v = data.scores[sid]?.[c]
                const best = data.columns[c]?.lowest_risk === sid
                return (
                  <td key={c} className="p-0 text-center" title={`${sid} · ${labelOf(c)}: ${v}`}>
                    <div
                      className="grid h-8 w-11 place-items-center rounded-lg text-[11px] font-semibold tabular-nums"
                      style={{
                        background: seqColor(v),
                        color: v >= 65 ? '#fff' : 'var(--color-ink)',
                        boxShadow: best ? 'inset 0 0 0 2px var(--color-ink)' : undefined,
                      }}
                    >
                      {v}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-2 text-[11px] text-muted">
        <span className="grid size-4 place-items-center rounded ring-2 ring-accent" /> best in shortlist for that score
      </div>
    </div>
  )
}
