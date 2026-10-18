// Building blocks for the Find suppliers page: the 10,000 -> 3 funnel, agent lanes, the three recommendation
// cards, the side-by-side table, the market signals and the finalist / longlist tables.
import {
  AlertTriangle, CheckCircle2, ChevronDown, Clock, ExternalLink, Factory, Globe2, Landmark, Loader2, Medal, Newspaper,
  Scale, ScanSearch, Search, ShieldCheck, Compass, Receipt,
} from 'lucide-react'
import { useState } from 'react'
import { AgentTrace, type TraceStep } from '../../components/AgentTrace'
import { ShortlistButton } from '../../components/ShortlistButton'
import { Button, Card, clsx, LevelBadge, Markdown, Tag } from '../../components/ui'
import { eur } from '../../lib/format'
import { price } from '../../lib/quotes'
import { useApp } from '../../lib/store'
import { DIM_LABEL, type Dim, type Offer, type Pick, type SourcingResult } from './types'

const money = (x: number) => (x >= 1e5 ? eur(x) : price(x))

/* ---------- funnel ---------- */

export function Funnel({ stages, active }: { stages: { label: string; count: number | null }[]; active?: number }) {
  const max = Math.max(...stages.map(s => s.count ?? 0), 1)
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {stages.map((s, i) => {
        const on = s.count != null
        const last = i === stages.length - 1
        return (
          <div key={i} className={clsx('rounded-2xl border p-3 transition', last && on ? 'border-accent bg-accent-soft' : 'border-line bg-surface',
            active === i && 'ring-4 ring-accent/15')}>
            <div className={clsx('text-xl font-bold tabular-nums', on ? (last ? 'text-accent-strong' : 'text-ink') : 'text-muted')}>
              {on ? s.count!.toLocaleString() : active === i ? <Loader2 className="size-5 animate-spin text-accent" /> : '—'}
            </div>
            <div className="mt-0.5 text-[11px] leading-snug text-ink-2">{s.label}</div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-sunken">
              {/* square-root scale so 3 of 10,000 is still visible */}
              <div className={clsx('h-full rounded-full', last ? 'bg-accent' : 'bg-accent/50')} style={{ width: on ? `${Math.max(3, Math.sqrt(s.count! / max) * 100)}%` : 0 }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- agent lanes ---------- */

const LANES: { name: string; icon: any; job: string }[] = [
  { name: 'Sourcing', icon: Search, job: 'screens 10,000 suppliers' },
  { name: 'Offer analyst', icon: Receipt, job: 'judges 50 offers, picks 7' },
  { name: 'Market', icon: Newspaper, job: 'reads live news' },
  { name: 'Financial', icon: Landmark, job: 'risk specialist' },
  { name: 'Operations & Quality', icon: Factory, job: 'risk specialist' },
  { name: 'Compliance & ESG', icon: Scale, job: 'risk specialist' },
  { name: 'Geopolitics & Reputation', icon: Globe2, job: 'risk specialist' },
  { name: 'Leader', icon: Compass, job: 'picks the final 3' },
]

function laneStatus(steps: TraceStep[]) {
  if (!steps.length) return 'waiting'
  const t = steps[steps.length - 1].type
  return t === 'done' ? 'done' : t === 'error' ? 'error' : 'working'
}

export function Lanes({ steps }: { steps: Record<string, TraceStep[]> }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
      {LANES.map(({ name, icon: Icon, job }) => {
        const s = steps[name] ?? []
        const status = laneStatus(s)
        const last = [...s].reverse().find(x => x.type !== 'tool_call')
        return (
          <Card key={name} className="flex flex-col gap-2 p-4!">
            <div className="flex items-center gap-2">
              <div className={clsx('grid size-8 shrink-0 place-items-center rounded-xl',
                status === 'done' ? 'bg-low text-low-ink' : status === 'error' ? 'bg-critical text-critical-ink' :
                status === 'working' ? 'bg-accent-soft text-accent' : 'bg-sunken text-muted')}>
                <Icon className="size-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold text-ink">{name}</div>
                <div className="flex items-center gap-1 text-[11px] text-muted">
                  {status === 'working' && <Loader2 className="size-3 animate-spin" />}
                  {status === 'done' && <CheckCircle2 className="size-3 text-low-dot" />}
                  {status === 'error' && <AlertTriangle className="size-3 text-critical-ink" />}
                  {status === 'waiting' && <Clock className="size-3" />}
                  <span>{status === 'waiting' ? job : status}</span>
                </div>
              </div>
            </div>
            <div className="min-h-[34px] text-[12px] leading-snug text-ink-2">
              {last ? <Markdown className="line-clamp-4 [&>p]:m-0">{String(last.summary ?? last.content ?? '')}</Markdown> : <span className="text-muted">…</span>}
            </div>
            {s.length > 1 && <AgentTrace steps={s} title="steps" max={8} />}
          </Card>
        )
      })}
    </div>
  )
}

/* ---------- the three recommendations ---------- */

const MEDAL = ['text-[#c9a227]', 'text-[#8b93a1]', 'text-[#b26b3a]']

function Fact({ label, value, sub, warn }: { label: string; value: React.ReactNode; sub?: React.ReactNode; warn?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/70 py-1.5 last:border-0">
      <span className="text-xs text-muted">{label}</span>
      <span className={clsx('text-right text-[13px] font-semibold tabular-nums', warn ? 'text-critical-ink' : 'text-ink')}>
        {value}{sub && <span className="ml-1 text-[11px] font-normal text-muted">{sub}</span>}
      </span>
    </div>
  )
}

export function PickCard({ pick, offer, res }: { pick: Pick; offer: Offer; res: SourcingResult }) {
  const openProfile = useApp(s => s.openProfile)
  const need = res.brief.need_by_weeks
  return (
    <Card className={clsx('flex flex-col', pick.rank === 1 && 'ring-2 ring-accent/40')}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <Medal className={clsx('size-7 shrink-0', MEDAL[pick.rank - 1])} />
          <div className="min-w-0">
            <div className="text-[15px] font-bold text-ink">#{pick.rank} {pick.id}</div>
            <div className="truncate text-xs text-muted">{offer.name}</div>
          </div>
        </div>
        <Tag tone={pick.rank === 1 ? 'accent' : 'neutral'}>{pick.role}</Tag>
      </div>

      <div className="mb-3 rounded-2xl bg-sunken px-4 py-3">
        <div className="text-[11px] font-medium text-muted">Offer per unit</div>
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-2xl font-bold tracking-tight text-ink tabular-nums">{money(offer.unit_price)}</span>
          <span className="text-xs text-ink-2">{eur(offer.total)} for {res.brief.quantity.toLocaleString()}</span>
        </div>
        {offer.over_budget && res.brief.target_unit_price && (
          <div className="mt-1 text-[11px] font-semibold text-high-ink">
            {Math.round((offer.unit_price / res.brief.target_unit_price - 1) * 100)}% over your target of {money(res.brief.target_unit_price)}
          </div>
        )}
      </div>

      <div className="mb-3">
        <Fact label="Lead time" value={`${offer.lead_weeks} weeks`} sub={need ? (offer.late ? `late, need ${need}` : `need ${need}`) : undefined} warn={offer.late} />
        <Fact label="Warranty" value={`${offer.warranty_years} years`} />
        <Fact label="Quality risk" value={<LevelBadge size="sm" level={levelOfScore(offer.quality_risk)} value={offer.quality_risk} />} />
        <Fact label="Delivery rating" value={`${offer.delivery.toFixed(1)}%`} />
        <Fact label="Order confirmation" value={`${offer.confirmation.toFixed(1)}%`} />
        <Fact label="Order change rate" value={`${offer.change_rate.toFixed(1)}%`} />
        <Fact label="Total risk index" value={<LevelBadge size="sm" level={offer.level} value={offer.tri} />} />
        <Fact label="Final score" value={pick.final_score} sub="lower = better" />
      </div>

      {pick.why && <p className="mb-3 text-[13px] leading-relaxed text-ink-2">{pick.why}</p>}
      {(pick.pros.length > 0 || pick.cons.length > 0) && (
        <div className="mb-3 space-y-1 text-[12px]">
          {pick.pros.map((p, i) => <div key={`p${i}`} className="flex gap-1.5 text-low-ink"><span>+</span><span>{p}</span></div>)}
          {pick.cons.map((c, i) => <div key={`c${i}`} className="flex gap-1.5 text-high-ink"><span>−</span><span>{c}</span></div>)}
        </div>
      )}
      {pick.red_flags.length > 0 && (
        <div className="mb-3 flex flex-col gap-1">
          {pick.red_flags.map((f, i) => (
            <div key={i} className="rounded-xl bg-critical px-2.5 py-1.5 text-[11px] leading-snug text-critical-ink"><b>{f.area}:</b> {f.issue}</div>
          ))}
        </div>
      )}
      {pick.watch && <div className="mb-3 rounded-xl bg-accent-soft px-3 py-2 text-[12px] text-accent-strong"><b>Watch:</b> {pick.watch}</div>}

      <div className="mb-3 flex flex-wrap gap-1">
        <Tag tone="good"><ShieldCheck className="size-3" />{offer.certs.length ? offer.certs.join(' · ') : 'no certificate needed'}</Tag>
        {pick.specialist_picks.map(a => <Tag key={a}>{a} agent's pick</Tag>)}
      </div>

      <div className="mt-auto flex gap-2">
        <Button size="sm" icon={<ScanSearch className="size-3.5" />} onClick={() => openProfile(pick.id)}>Profile</Button>
        <ShortlistButton id={pick.id} size="sm" />
      </div>
    </Card>
  )
}

const levelOfScore = (v: number) => (v >= 75 ? 'Critical' : v >= 50 ? 'High' : v >= 25 ? 'Medium' : 'Low')

/** The three side by side, with the best value in each row marked. */
export function SideBySide({ res, offers }: { res: SourcingResult; offers: Offer[] }) {
  const rows: { label: string; get: (o: Offer, p: Pick) => number; fmt: (v: number) => string; low: boolean }[] = [
    { label: 'Unit price', get: o => o.unit_price, fmt: money, low: true },
    { label: `Total (${res.brief.quantity.toLocaleString()} units)`, get: o => o.total, fmt: eur, low: true },
    { label: 'Lead time (weeks)', get: o => o.lead_weeks, fmt: v => String(v), low: true },
    { label: 'Warranty (years)', get: o => o.warranty_years, fmt: v => String(v), low: false },
    { label: 'Quality risk', get: o => o.quality_risk, fmt: v => String(v), low: true },
    { label: 'Delivery rating', get: o => o.delivery, fmt: v => `${v.toFixed(1)}%`, low: false },
    { label: 'Order confirmation', get: o => o.confirmation, fmt: v => `${v.toFixed(1)}%`, low: false },
    { label: 'Order change rate', get: o => o.change_rate, fmt: v => `${v.toFixed(1)}%`, low: true },
    { label: 'Total risk index', get: o => o.tri, fmt: v => String(v), low: true },
    ...Object.keys(res.area_weights).map(a => ({ label: `${a} risk`, get: (_: Offer, p: Pick) => p.area_index[a], fmt: (v: number) => v.toFixed(1), low: true })),
    { label: 'Offer score', get: o => o.score, fmt: v => v.toFixed(1), low: true },
    { label: 'Team risk score', get: (_, p) => p.team_score, fmt: v => v.toFixed(1), low: true },
    { label: 'Final score', get: (_, p) => p.final_score, fmt: v => v.toFixed(1), low: true },
  ]
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            <th className="py-2 pr-3 font-medium" />
            {res.top.map(p => <th key={p.id} className="px-3 py-2 text-right font-semibold text-ink">#{p.rank} {p.id}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => {
            const vals = res.top.map((p, i) => r.get(offers[i], p))
            const best = r.low ? Math.min(...vals) : Math.max(...vals)
            return (
              <tr key={r.label} className="border-b border-line/60 last:border-0">
                <td className="py-1.5 pr-3 text-xs text-ink-2">{r.label}</td>
                {vals.map((v, i) => (
                  <td key={i} className={clsx('px-3 py-1.5 text-right tabular-nums', v === best && vals.some(x => x !== best) ? 'font-bold text-low-ink' : 'text-ink')}>{r.fmt(v)}</td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="mt-2 text-[11px] text-muted">Green = best of the three. Risk scores and the agents' scores: lower = better.</div>
    </div>
  )
}

/* ---------- market ---------- */

export function MarketSignals({ m }: { m: SourcingResult['market'] }) {
  if (!m.signals.length) {
    return <div className="rounded-xl bg-sunken px-4 py-3 text-xs text-muted">
      {m.error ? `No live market news this run (${m.error}). The team decided on the dataset alone.` : 'No relevant market news in the last 120 days.'}
    </div>
  }
  return (
    <div className="space-y-3">
      {m.summary && <p className="text-[13px] leading-relaxed text-ink-2">{m.summary}</p>}
      {m.advice && <div className="rounded-xl bg-accent-soft px-3 py-2 text-[12px] text-accent-strong"><b>What this market favours:</b> {m.advice}</div>}
      <div className="space-y-2">
        {m.signals.map((s, i) => (
          <div key={i} className="flex gap-3 rounded-xl border border-line p-3">
            <div className={clsx('grid size-7 shrink-0 place-items-center rounded-lg text-xs font-bold',
              s.severity >= 4 ? 'bg-critical text-critical-ink' : s.severity === 3 ? 'bg-high text-high-ink' : 'bg-medium text-medium-ink')}
              title="severity 1-5">{s.severity}</div>
            <div className="min-w-0 flex-1">
              <a href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[13px] font-semibold text-ink hover:text-accent">
                <span className="truncate">{s.title}</span><ExternalLink className="size-3 shrink-0" />
              </a>
              <div className="text-[12px] leading-snug text-ink-2">{s.impact}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-muted">
                <span>{s.date || 'recent'} · {new URL(s.url).hostname.replace(/^www\./, '')}</span>
                {s.areas.map(a => <Tag key={a}>{a}</Tag>)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------- finalists and longlist ---------- */

export function FinalistsTable({ res, byId }: { res: SourcingResult; byId: Record<string, Offer> }) {
  const order = [...res.finalists].sort((a, b) => res.final_score[a] - res.final_score[b])
  const topRank = Object.fromEntries(res.top.map(t => [t.id, t.rank]))
  const why = Object.fromEntries(res.not_chosen.map(n => [n.id, n.reason]))
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-xs text-muted">
            {['Supplier', 'Unit price', 'Lead', 'Quality risk', 'Delivery', 'TRI', 'Offer score', 'Team risk', 'Final', 'Outcome'].map(h =>
              <th key={h} className={clsx('px-2 py-2 font-medium', h !== 'Supplier' && h !== 'Outcome' && 'text-right')}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {order.map(id => {
            const o = byId[id]
            return (
              <tr key={id} className={clsx('border-b border-line/60 align-top last:border-0', topRank[id] && 'bg-accent-soft/50')}>
                <td className="px-2 py-2 font-semibold whitespace-nowrap text-ink">{id}</td>
                <td className="px-2 py-2 text-right tabular-nums">{money(o.unit_price)}</td>
                <td className={clsx('px-2 py-2 text-right tabular-nums', o.late && 'text-critical-ink')}>{o.lead_weeks} wk</td>
                <td className="px-2 py-2 text-right tabular-nums">{o.quality_risk}</td>
                <td className="px-2 py-2 text-right tabular-nums">{o.delivery.toFixed(1)}%</td>
                <td className="px-2 py-2 text-right"><LevelBadge size="sm" level={o.level} value={o.tri} /></td>
                <td className="px-2 py-2 text-right tabular-nums">{o.score.toFixed(1)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{res.team_score[id].toFixed(1)}</td>
                <td className="px-2 py-2 text-right font-bold tabular-nums">{res.final_score[id].toFixed(1)}</td>
                <td className="px-2 py-2 text-xs text-ink-2">{topRank[id] ? <Tag tone="accent">Recommended #{topRank[id]}</Tag> : why[id]}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function Longlist({ res }: { res: SourcingResult }) {
  const [open, setOpen] = useState(false)
  const fin = new Set(res.finalists)
  const passed = Object.fromEntries(res.analyst.passed_over.map(p => [p.id, p.reason]))
  const dims = (Object.keys(res.weights) as Dim[])
  const rows = open ? res.longlist : res.longlist.slice(0, 12)
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5 text-[11px]">
        {dims.map(d => <Tag key={d}>{DIM_LABEL[d]} {Math.round(res.weights[d] * 100)}%</Tag>)}
        <span className="self-center text-muted">Points per dimension: 0 = best of the {res.longlist.length} offers, 100 = worst.</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-line text-left text-[11px] text-muted">
              {['#', 'Supplier', 'Unit price', 'Lead', 'Warranty', 'Quality', 'Reliability', 'Risk', ...dims.map(d => `${DIM_LABEL[d]} pts`), 'Score', ''].map((h, i) =>
                <th key={i} className={clsx('px-2 py-1.5 font-medium', i > 1 && 'text-right')}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(o => (
              <tr key={o.id} className={clsx('border-b border-line/50 last:border-0', fin.has(o.id) && 'bg-accent-soft/50')}>
                <td className="px-2 py-1.5 text-muted tabular-nums">{o.rank}</td>
                <td className="px-2 py-1.5 font-medium whitespace-nowrap text-ink">{o.id}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{money(o.unit_price)}{o.over_budget && <span className="ml-1 text-high-ink" title="over target price">▲</span>}</td>
                <td className={clsx('px-2 py-1.5 text-right tabular-nums', o.late && 'font-semibold text-critical-ink')}>{o.lead_weeks} wk</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{o.warranty_years} y</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{o.quality_risk}</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{o.reliability.toFixed(1)}%</td>
                <td className="px-2 py-1.5 text-right tabular-nums">{o.risk_index.toFixed(1)}</td>
                {dims.map(d => <td key={d} className="px-2 py-1.5 text-right text-muted tabular-nums">{Math.round(o.pts[d])}</td>)}
                <td className="px-2 py-1.5 text-right font-bold tabular-nums">{o.score.toFixed(1)}</td>
                <td className="px-2 py-1.5 text-[11px] text-ink-2">
                  {fin.has(o.id) ? <Tag tone="accent">finalist</Tag> : o.late ? <Tag tone="bad">misses date</Tag> : passed[o.id] ?? ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {res.longlist.length > 12 && (
        <button onClick={() => setOpen(o => !o)} className="mt-2 flex items-center gap-1 text-xs font-semibold text-accent hover:underline">
          <ChevronDown className={clsx('size-3.5 transition', open && 'rotate-180')} />{open ? 'Show the best 12' : `Show all ${res.longlist.length} offers`}
        </button>
      )}
    </div>
  )
}

/* ---------- specialists ---------- */

export function SpecialistReports({ res }: { res: SourcingResult }) {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {Object.entries(res.reports).map(([area, r]) => {
        const lane = LANES.find(l => l.name === area)
        const Icon = lane?.icon ?? Compass
        return (
          <div key={area} className="rounded-2xl border border-line p-4">
            <div className="mb-2 flex items-center gap-2">
              <div className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent"><Icon className="size-3.5" /></div>
              <div className="text-[13px] font-semibold text-ink">{area}</div>
              <span className="text-[11px] text-muted">weight {Math.round(res.area_weights[area] * 100)}% · picks {r.best}{r.confidence ? ` · ${r.confidence} confidence` : ''}</span>
            </div>
            <Markdown className="mb-1.5 text-[12.5px] [&>p]:m-0">{r.verdict ?? ''}</Markdown>
            {!!r.findings?.length && <ul className="list-disc space-y-0.5 pl-4 text-[12px] text-ink-2">{r.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>}
          </div>
        )
      })}
    </div>
  )
}
