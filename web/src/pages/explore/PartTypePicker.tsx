// "What are you buying?" selector for Find suppliers: the part type sets the risk gate and the default lens.
import { Info, PiggyBank, ShieldAlert, Wrench } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Button, Card, CardHeader, clsx } from '../../components/ui'
import type { PartType, PartTypeMeta } from '../../lib/types'

export interface Gate { part_type: PartType; label: string; why: string; hidden: number }

const OPTIONS: { key: PartType; icon: ReactNode; rank: string }[] = [
  { key: 'safety_critical', icon: <ShieldAlert className="size-5" />, rank: 'Safety-first ranking' },
  { key: 'standard', icon: <Wrench className="size-5" />, rank: 'Balanced ranking' },
  { key: 'budget', icon: <PiggyBank className="size-5" />, rank: 'Delivery-first ranking' },
]

export function PartTypePicker({ value, types, lensName, onPick, onUseSuggested, gate }: {
  value: PartType
  types: Record<PartType, PartTypeMeta>
  lensName: string
  onPick: (p: PartType) => void
  onUseSuggested: () => void
  gate: Gate | null
}) {
  const [why, setWhy] = useState(false)
  const suggested = types[value]?.lens
  return (
    <Card className="mb-5">
      <CardHeader title="What are you buying?"
        subtitle="Start with the kind of component. It sets how strictly risky suppliers are filtered out and how they are ranked. Price is compared later from your quotes." />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3" role="radiogroup" aria-label="What are you buying?">
        {OPTIONS.map(o => {
          const t = types[o.key]
          const on = value === o.key
          return (
            <button key={o.key} type="button" role="radio" aria-checked={on} onClick={() => onPick(o.key)}
              className={clsx('flex items-start gap-3 rounded-2xl border p-4 text-left transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent/20',
                on ? 'border-accent bg-accent-soft shadow-sm' : 'border-line bg-surface hover:border-line-strong hover:bg-sunken')}>
              <span className={clsx('grid size-10 shrink-0 place-items-center rounded-xl', on ? 'bg-accent text-white' : 'bg-sunken text-ink-2 ring-1 ring-line')}>{o.icon}</span>
              <span className="min-w-0">
                <span className={clsx('block text-sm font-semibold', on ? 'text-accent-strong' : 'text-ink')}>{t.label}</span>
                <span className="mt-0.5 block text-xs text-ink-2">e.g. {t.examples}</span>
                <span className="mt-1.5 block text-[11px] font-semibold text-muted">
                  {o.rank} · hides {t.gate_hidden.toLocaleString()} risky supplier{t.gate_hidden === 1 ? '' : 's'}
                </span>
              </span>
            </button>
          )
        })}
      </div>

      {gate && gate.hidden > 0 && (
        <div className="mt-3 rounded-xl bg-medium px-3.5 py-2.5 text-xs text-medium-ink">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-2 font-semibold">
              <Info className="size-4 shrink-0" />
              {gate.label}: {gate.hidden.toLocaleString()} supplier{gate.hidden === 1 ? '' : 's'} hidden by your current filters.
            </span>
            <button type="button" className="font-semibold underline underline-offset-2" onClick={() => setWhy(w => !w)}>{why ? 'Hide why' : 'Show why'}</button>
          </div>
          {why && <p className="mt-1.5 leading-relaxed">{gate.why}</p>}
        </div>
      )}

      {suggested && lensName !== suggested && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
          <span>Ranking uses lens <span className="font-semibold text-ink-2">{lensName}</span> (this part type suggests <span className="font-semibold text-ink-2">{suggested}</span>).</span>
          <Button size="sm" variant="ghost" onClick={onUseSuggested}>Use suggested</Button>
        </div>
      )}
    </Card>
  )
}
