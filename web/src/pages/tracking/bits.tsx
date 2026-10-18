// Small shared marks for the live tracking page: delta, trend and severity.
import { ArrowRight, TrendingDown, TrendingUp } from 'lucide-react'
import { clsx } from '../../components/ui'
import { LEVEL } from '../../lib/chart'
import { signed } from './util'
import type { Direction } from './types'

/** Higher score = riskier, so a rise is red and a fall is green. Always shows arrow + sign, never colour alone. */
export function Delta({ v, className }: { v: number | null | undefined; className?: string }) {
  if (v == null) return <span className="text-muted">–</span>
  const up = Math.round(v * 10) > 0, down = Math.round(v * 10) < 0
  return (
    <span className={clsx('inline-flex items-center gap-0.5 font-semibold tabular-nums', up ? 'text-critical-ink' : down ? 'text-low-ink' : 'text-muted', className)}>
      <span aria-hidden>{up ? '↑' : down ? '↓' : '→'}</span>{signed(v)}
    </span>
  )
}

const TREND = {
  rising: { icon: TrendingUp, text: 'Rising', cls: 'text-critical-ink' },
  falling: { icon: TrendingDown, text: 'Falling', cls: 'text-low-ink' },
  stable: { icon: ArrowRight, text: 'Stable', cls: 'text-ink-2' },
} as const
export function TrendMark({ trend, label = true }: { trend: Direction | null | undefined; label?: boolean }) {
  if (!trend) return <span className="text-muted">–</span>
  const t = TREND[trend], Icon = t.icon
  return <span className={clsx('inline-flex items-center gap-1 text-xs font-semibold', t.cls)}><Icon className="size-3.5" />{label && t.text}</span>
}

export function Severity({ n }: { n: number }) {
  const color = n >= 4 ? LEVEL.Critical.dot : n >= 3 ? LEVEL.High.dot : n >= 2 ? LEVEL.Medium.dot : LEVEL.Low.dot
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5" title={`severity ${n}/5`} aria-label={`severity ${n} of 5`}>
      {Array.from({ length: 5 }).map((_, i) => <span key={i} className="size-1.5 rounded-full" style={{ background: i < n ? color : '#e5e7eb' }} />)}
    </span>
  )
}

