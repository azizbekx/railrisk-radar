// Semicircle risk gauge 0-100: Low/Medium/High/Critical bands, a dark progress arc and a needle dot at the value.
import { INK, LEVEL } from '../lib/chart'
import type { Level } from '../lib/types'

const CX = 100, CY = 100, R = 82
const BANDS: { from: number; to: number; level: Level }[] = [
  { from: 0, to: 25, level: 'Low' }, { from: 25, to: 50, level: 'Medium' },
  { from: 50, to: 75, level: 'High' }, { from: 75, to: 100, level: 'Critical' },
]

/** Point on the arc for a 0-100 value: 0 = far left, 100 = far right, over the top. */
const pt = (v: number, r = R) => {
  const a = Math.PI * (1 - v / 100)
  return [CX + r * Math.cos(a), CY - r * Math.sin(a)] as const
}
const arc = (from: number, to: number, r = R) => {
  const [x1, y1] = pt(from, r), [x2, y2] = pt(to, r)
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`
}

export function Gauge({ value, className }: { value: number; className?: string }) {
  const v = Math.min(100, Math.max(0, value))
  const [nx, ny] = pt(v)
  return (
    <svg viewBox="0 0 200 122" role="img" aria-label={`${value} out of 100`} className={className}>
      {BANDS.map(b => (
        <path key={b.level} d={arc(b.from + 0.4, b.to - 0.4)} fill="none" stroke={LEVEL[b.level].dot} strokeWidth={14} strokeOpacity={0.9} />
      ))}
      <path d={arc(0, 100, R - 15)} fill="none" stroke={INK.grid} strokeWidth={5} strokeLinecap="round" />
      <path d={arc(0, 100, R - 15)} pathLength={100} fill="none" stroke={INK.primary} strokeWidth={5} strokeLinecap="round"
        strokeDasharray={`${v} 100`} style={{ transition: 'stroke-dasharray 0.6s ease-out' }} />
      <circle cx={nx} cy={ny} r={8} fill="#fff" stroke={INK.primary} strokeWidth={3} />
      <text x={CX} y={CY - 6} textAnchor="middle" fontSize={34} fontWeight={700} fill={INK.primary}>
        {value}<tspan fontSize={13} fontWeight={600} fill={INK.muted}>/100</tspan>
      </text>
      {[0, 25, 50, 75, 100].map(t => {
        const [x, y] = pt(t, R + 14)
        return <text key={t} x={x} y={y + 3} textAnchor="middle" fontSize={8.5} fill={INK.muted}>{t}</text>
      })}
    </svg>
  )
}
