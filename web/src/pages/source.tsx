// Find suppliers: the buyer says what they need, agents narrow 10,000 suppliers to 50 RFQs, 7 finalists and a
// recommended 3 with offer, quality, risk and live market facts. Logic lives in core/sourcing.py.
import { Download, GitCompareArrows, Newspaper, Receipt, Sparkles, Target, Users, Wand2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { AgentTrace, type TraceStep } from '../components/AgentTrace'
import { Button, Card, CardHeader, Field, Input, PageHeader, Select, Tag, TextArea } from '../components/ui'
import { get, post, streamPost } from '../lib/api'
import { useApp } from '../lib/store'
import type { PartType } from '../lib/types'
import { FinalistsTable, Funnel, Lanes, Longlist, MarketSignals, PickCard, SideBySide, SpecialistReports } from './source/parts'
import type { CatalogItem, Offer, Parsed, SourcingResult } from './source/types'

interface Form { component: string; quantity: string; need_by_weeks: string; target_unit_price: string }
const EMPTY: Form = { component: '', quantity: '', need_by_weeks: '', target_unit_price: '' }

const EXAMPLES: { text: string; form: Form }[] = [
  { text: '400 brake control units for a regional train fleet, needed within 30 weeks',
    form: { component: 'brake_control_unit', quantity: '400', need_by_weeks: '30', target_unit_price: '' } },
  { text: '48 HVAC units for 12 commuter trains in 20 weeks, target €28,000 each',
    form: { component: 'hvac_unit', quantity: '48', need_by_weeks: '20', target_unit_price: '28000' } },
  { text: '6,000 seat covers for an interior refurbishment within 8 weeks, under €90 each',
    form: { component: 'seat_cover', quantity: '6000', need_by_weeks: '8', target_unit_price: '90' } },
]

const STAGES = ['Suppliers in the dataset', 'Make the component', 'Pass the risk gate', 'Hold every certificate',
  'Lowest risk: sent an RFQ', 'Best offers: deep risk check', 'Recommended']
const STAGE_KEYS = ['all', 'makers', 'gate', 'certified', 'longlist', 'finalists', 'top']
const GROUPS: { key: PartType; label: string }[] = [
  { key: 'safety_critical', label: 'Safety-critical' }, { key: 'standard', label: 'Standard part' }, { key: 'budget', label: 'Non-critical / budget' },
]

const numOrNull = (s: string) => (s.trim() && Number(s.replace(/[, ]/g, '')) > 0 ? Number(s.replace(/[, ]/g, '')) : null)

/** Funnel counts while the agents run, read from the Sourcing steps; finalists and top fill when those agents finish. */
function liveFunnel(steps: Record<string, TraceStep[]>, total: number): (number | null)[] {
  const counts: (number | null)[] = [total, null, null, null, null, null, null]
  for (const s of steps.Sourcing ?? []) {
    const i = STAGE_KEYS.indexOf(s.name ?? '')
    const m = String(s.content ?? '').match(/([\d,]+)\s*$/)
    if (i > 0 && m) counts[i] = Number(m[1].replace(/,/g, ''))
  }
  if ((steps['Offer analyst'] ?? []).some(s => s.type === 'done')) counts[5] = 7
  if ((steps.Leader ?? []).some(s => s.type === 'done')) counts[6] = 3
  return counts
}

export default function Page() {
  const meta = useApp(s => s.meta)
  const notify = useApp(s => s.notify)
  const go = useApp(s => s.go)
  const addToShortlist = useApp(s => s.addToShortlist)
  const setPartType = useApp(s => s.setPartType)
  const setQuote = useApp(s => s.setQuote)
  const [catalog, setCatalog] = useState<Record<string, CatalogItem>>({})
  const [text, setText] = useState('')
  const [form, setForm] = useState<Form>(EMPTY)
  const [notes, setNotes] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parsedBy, setParsedBy] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<Record<string, TraceStep[]>>({})
  const [res, setRes] = useState<SourcingResult | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    get<Record<string, CatalogItem>>('/sourcing/catalog').then(setCatalog).catch(() => {})
    get<SourcingResult | null>('/sourcing/last').then(r => {
      if (!r) return
      setRes(r)
      const b = r.brief
      setForm({ component: b.component, quantity: String(b.quantity), need_by_weeks: b.need_by_weeks ? String(b.need_by_weeks) : '',
        target_unit_price: b.target_unit_price ? String(b.target_unit_price) : '' })
      setNotes(b.notes)
    }).catch(() => {})
    return () => abortRef.current?.abort()
  }, [])

  const item = catalog[form.component]
  const pt = item && meta?.part_types[item.part_type]
  const byId = useMemo(() => Object.fromEntries((res?.longlist ?? []).map(o => [o.id, o])) as Record<string, Offer>, [res])

  async function readRequest(): Promise<Form | null> {
    if (!text.trim()) return null
    setParsing(true)
    try {
      const p = await post<Parsed>('/sourcing/parse', { text })
      const f: Form = {
        component: p.component || form.component, quantity: p.quantity ? String(p.quantity) : form.quantity,
        need_by_weeks: p.need_by_weeks ? String(p.need_by_weeks) : form.need_by_weeks,
        target_unit_price: p.target_unit_price ? String(p.target_unit_price) : form.target_unit_price,
      }
      setForm(f); setParsedBy(p.parsed_by)
      if (p.notes) setNotes(p.notes)
      if (!p.component) notify('Could not tell which component you need: pick one from the list', 'warn')
      return f
    } catch (e: any) {
      notify(String(e?.message || e), 'warn'); return null
    } finally { setParsing(false) }
  }

  async function run() {
    let f = form
    if (!f.component) f = (await readRequest()) ?? f
    if (!f.component) { notify('Describe what you need or pick a component', 'warn'); return }
    setRunning(true); setSteps({}); setRes(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const body = {
      component: f.component, quantity: numOrNull(f.quantity) ?? 1, need_by_weeks: numOrNull(f.need_by_weeks),
      target_unit_price: numOrNull(f.target_unit_price), notes: [notes.trim(), text.trim()].filter(Boolean).join(' · ').slice(0, 300),
    }
    streamPost<TraceStep, SourcingResult>('/sourcing/run', body, ev => {
      if (ev.event === 'step') {
        const a = ev.data.agent || 'Leader'
        setSteps(s => ({ ...s, [a]: [...(s[a] || []), ev.data] }))
      } else if (ev.event === 'result') {
        setRes(ev.data); setRunning(false)
      } else if (ev.event === 'error') {
        notify(`Sourcing failed: ${ev.data}`, 'warn'); setRunning(false)
      }
    }, ctrl.signal).catch(e => { if (e?.name !== 'AbortError') notify(String(e?.message || e), 'warn'); setRunning(false) })
  }

  /** Top 3 to the shortlist; their offers become the quotes in Compare > Price vs risk. */
  function toCompare() {
    if (!res) return
    const ids = res.top.map(t => t.id)
    setPartType(res.brief.part_type)
    ids.forEach(i => setQuote(i, byId[i].unit_price))
    const { added, skipped } = addToShortlist(ids)
    notify(skipped.length && !added.length ? 'Already on the shortlist' : `Added ${added.length} to the shortlist with their offers as quotes`)
    go('compare')
  }

  function downloadMemo() {
    if (!res) return
    const url = URL.createObjectURL(new Blob([res.memo], { type: 'text/markdown' }))
    const a = document.createElement('a')
    a.href = url; a.download = `sourcing_${res.brief.component}.md`; a.click()
    URL.revokeObjectURL(url)
  }

  const total = meta?.summary.suppliers ?? 10000
  const counts = res ? STAGE_KEYS.map(k => res.funnel.find(f => f.stage === k)?.count ?? null) : running ? liveFunnel(steps, total) : STAGES.map((_, i) => (i === 0 ? total : null))
  const activeStage = running ? counts.findIndex(c => c == null) : undefined
  const allSteps = Object.values(steps).flat()

  return (
    <div>
      <PageHeader title="Find suppliers" icon={<Target className="size-5" />}
        subtitle="Say what you are buying. Agents screen 10,000 suppliers, send a request for quotation to the best 50, pick 7 on price, quality and delivery, then check those 7 with four risk specialists and live market news to recommend 3." />

      <Card className="mb-5">
        <CardHeader title="What do you need?" icon={<Sparkles className="size-4" />}
          subtitle="Write it like an email to a colleague, or fill the fields. The intake agent reads the component, quantity, deadline and target price." />
        <div className="flex flex-col gap-3 lg:flex-row">
          <TextArea rows={2} value={text} onChange={e => { setText(e.target.value); setParsedBy(null) }}
            placeholder="e.g. 400 brake control units for a regional train fleet, needed within 30 weeks"
            className="min-h-[64px] flex-1" />
          <Button onClick={readRequest} loading={parsing} disabled={!text.trim() || running} icon={<Wand2 className="size-4" />} className="self-start">Read my request</Button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-muted">Try:</span>
          {EXAMPLES.map(ex => (
            <button key={ex.text} disabled={running} onClick={() => { setText(ex.text); setForm(ex.form); setParsedBy(null); setNotes('') }}
              className="rounded-full bg-sunken px-3 py-1 text-[11px] font-medium text-ink-2 ring-1 ring-line hover:bg-accent-soft hover:text-accent-strong">
              {ex.text}
            </button>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr]">
          <Field label="Component" hint={item ? `Typical market price ${item.unit_eur >= 100 ? `€${item.unit_eur.toLocaleString()}` : `€${item.unit_eur}`} · ${item.lead_weeks} weeks lead time` : undefined}>
            <Select value={form.component} onChange={e => setForm({ ...form, component: e.target.value })}>
              <option value="">Choose a component…</option>
              {GROUPS.map(g => (
                <optgroup key={g.key} label={g.label}>
                  {Object.entries(catalog).filter(([, v]) => v.part_type === g.key).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Quantity (units)"><Input inputMode="numeric" value={form.quantity} onChange={e => setForm({ ...form, quantity: e.target.value })} placeholder="400" /></Field>
          <Field label="Needed within (weeks)"><Input inputMode="numeric" value={form.need_by_weeks} onChange={e => setForm({ ...form, need_by_weeks: e.target.value })} placeholder="optional" /></Field>
          <Field label="Target price (€ per unit)"><Input inputMode="decimal" value={form.target_unit_price} onChange={e => setForm({ ...form, target_unit_price: e.target.value })} placeholder="optional" /></Field>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
            {pt && <Tag tone={item.part_type === 'safety_critical' ? 'bad' : item.part_type === 'budget' ? 'good' : 'neutral'}>{pt.label}</Tag>}
            {pt && <span>price counts {Math.round(pt.price_weight * 100)}% · risk lens {pt.lens}</span>}
            {item && <span>· needs {item.certs.length ? item.certs.join(', ') : 'no certificate'}</span>}
            {parsedBy && <Tag tone="accent">read by {parsedBy === 'agent' ? 'the intake agent' : 'keyword match'}</Tag>}
          </div>
          <Button variant="primary" size="lg" loading={running} onClick={run} icon={<Target className="size-4" />}
            disabled={!form.component && !text.trim()}>Find my top 3</Button>
        </div>
      </Card>

      <Card className="mb-5">
        <Funnel stages={STAGES.map((label, i) => ({ label, count: counts[i] }))} active={activeStage} />
      </Card>

      {running && <div className="mb-6"><Lanes steps={steps} /></div>}

      {res && !running && (
        <div className="space-y-5">
          <Card>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-accent">Recommendation · {res.brief.quantity.toLocaleString()} × {res.brief.label}</div>
                <p className="mt-1 text-[14px] leading-relaxed text-ink">{res.summary || `The leader recommends ${res.top.map(t => t.id).join(', ')}.`}</p>
                <div className="mt-1.5 text-[11px] text-muted">{res.created_at} · {res.seconds}s · {res.model} · risk lens {res.lens}</div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" icon={<GitCompareArrows className="size-4" />} onClick={toCompare}>Compare the 3</Button>
                <Button icon={<Download className="size-4" />} onClick={downloadMemo}>Memo</Button>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {res.top.map(p => <PickCard key={p.id} pick={p} offer={byId[p.id]} res={res} />)}
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-[3fr_2fr]">
            <Card>
              <CardHeader title="The three side by side" subtitle="Offer, quality, delivery and risk in one view." />
              <SideBySide res={res} offers={res.top.map(t => byId[t.id])} />
            </Card>
            <Card>
              <CardHeader title="Live market check" icon={<Newspaper className="size-4" />}
                subtitle={`The market agent read ${res.market.sources?.length ?? 0} recent news articles about ${res.brief.label.toLowerCase()} supply.`} />
              <MarketSignals m={res.market} />
            </Card>
          </div>

          <Card>
            <CardHeader title="7 finalists: why these 3" icon={<Users className="size-4" />}
              subtitle="Final score = half offer score, half the four specialists' weighted risk score (both 0-100, lower = better). The leader may change the order for a stated reason." />
            <FinalistsTable res={res} byId={byId} />
          </Card>

          <Card>
            <CardHeader title="What the risk specialists found" subtitle="Each agent judged the 7 finalists on its own slice of the 18 risk scores." />
            <SpecialistReports res={res} />
          </Card>

          <Card>
            <CardHeader title={`${res.longlist.length} offers: how 7 were chosen`} icon={<Receipt className="size-4" />}
              subtitle={res.analyst.summary || 'The offer analyst picked 7 finalists from the 12 best-scored offers.'} />
            <Longlist res={res} />
          </Card>

          {allSteps.length > 0 && <AgentTrace steps={allSteps} title="Full agent trace" />}
          <p className="text-[11px] text-muted">{res.simulated} Risk scores, quality, delivery and confirmation rates come from the dataset; market news is live.</p>
        </div>
      )}
    </div>
  )
}
