// Agent team page: a leader agent + 4 specialists analyse the shortlist in parallel, the leader decides and writes
// the selection memo. Ported from views/team.py + the trigger in views/compare.py; logic lives in core/team.py.
import {
  AlertTriangle, Brain, CheckCircle2, ChevronDown, Clock, Compass, Download, Factory, Globe2, Landmark, Loader2,
  Scale, Sparkles, Trophy, Users,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AgentTrace, type TraceStep } from '../components/AgentTrace'
import { Button, Card, CardHeader, Chip, clsx, Empty, Field, LevelBadge, Markdown, PageHeader, Skeleton, Tag, TextArea } from '../components/ui'
import { get, post, streamPost } from '../lib/api'
import { levelOf } from '../lib/format'
import type { SupplierRow } from '../lib/types'
import { useApp, useLens } from '../lib/store'
import { BuildUpBars, type ChartData, FlowDiagram, SpecChart, type TeamReport, type TeamResult, TeamScorecard, TeamScoreBars, WeightsChart } from './team/charts'

const LANE_ICON: Record<string, any> = {
  Leader: Compass, Financial: Landmark, 'Operations & Quality': Factory,
  'Compliance & ESG': Scale, 'Geopolitics & Reputation': Globe2,
}
const LANE_ORDER = ['Leader', 'Financial', 'Operations & Quality', 'Compliance & ESG', 'Geopolitics & Reputation']
const SPECIALISTS = LANE_ORDER.slice(1)
const EXAMPLES = [
  'Brake control units for a regional train, safety-critical, 5-year frame contract',
  'Standard fasteners and brackets, low criticality, spot-buy order',
  'Signalling software modules, safety-critical, single-source, multi-year contract',
]

function laneStatus(steps: TraceStep[]): 'waiting' | 'working' | 'done' | 'error' {
  if (!steps.length) return 'waiting'
  const last = steps[steps.length - 1]
  return last.type === 'done' ? 'done' : last.type === 'error' ? 'error' : 'working'
}

function Lane({ name, steps }: { name: string; steps: TraceStep[] }) {
  const Icon = LANE_ICON[name] ?? Compass
  const status = laneStatus(steps)
  const last = steps[steps.length - 1]
  return (
    <Card className="flex flex-col gap-2.5">
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
            <span>{status === 'waiting' ? 'waiting for the brief' : status}</span>
          </div>
        </div>
      </div>
      <div className="min-h-[34px] text-[12px] leading-snug text-ink-2">
        {last ? <Markdown className="[&>p]:m-0">{String(last.content ?? '')}</Markdown> : <span className="text-muted">…</span>}
      </div>
      {steps.length > 0 && <AgentTrace steps={steps} title="steps" max={6} />}
    </Card>
  )
}

function Collapsible({ title, children }: { title: string; children: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-3 rounded-2xl border border-line bg-sunken/60">
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs font-semibold text-ink-2">
        <Brain className="size-3.5" /><span>{title}</span>
        <ChevronDown className={clsx('ml-auto size-4 transition', open && 'rotate-180')} />
      </button>
      {open && <pre className="max-h-72 overflow-y-auto border-t border-line px-4 py-3 text-[11px] leading-relaxed whitespace-pre-wrap text-ink-2">{children}</pre>}
    </div>
  )
}

function SpecialistCard({ name, rep, res, chart }: { name: string; rep: TeamReport; res: TeamResult; chart: ChartData | null | undefined }) {
  const Icon = LANE_ICON[name] ?? Compass
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="grid size-8 place-items-center rounded-xl bg-accent-soft text-accent"><Icon className="size-4" /></div>
          <div>
            <div className="text-sm font-semibold text-ink">{name}</div>
            <div className="text-[11px] text-muted">weight {Math.round(res.weights[name] * 100)}% · picks {rep.best} · {rep.confidence} confidence · {rep.seconds}s</div>
          </div>
        </div>
        {rep.best === res.pick && <Tag tone="good">agrees with team</Tag>}
      </div>
      {rep.brief && <div className="mb-2 text-[11px] text-muted">Leader's brief: {rep.brief}</div>}
      <Markdown className="mb-2 text-[13px]">{rep.verdict}</Markdown>
      {!!rep.findings?.length && (
        <ul className="mb-2 list-disc space-y-1 pl-4 text-[12px] text-ink-2">
          {rep.findings.map((f, i) => <li key={i}>{f}</li>)}
        </ul>
      )}
      {!!rep.red_flags?.length && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {rep.red_flags.map((f, i) => <Tag key={i} tone="bad" className="max-w-full whitespace-normal! rounded-xl! py-1 leading-snug">{f.supplier}: {f.issue}</Tag>)}
        </div>
      )}
      <div className="rounded-xl border border-line bg-sunken/40 p-3">
        {rep.chart?.title && <div className="mb-2 text-[11px] font-medium text-ink-2">{rep.chart.title}</div>}
        {chart === undefined ? <Skeleton className="h-32" /> : <SpecChart data={chart} shortlistIds={res.ids} />}
      </div>
      {rep.reasoning && <Collapsible title="How the agent reasoned">{rep.reasoning}</Collapsible>}
    </Card>
  )
}

function recommendation(memo: string): string {
  const m = memo.match(/## Recommendation\s*\n+([\s\S]*?)(\n##|$)/)
  return (m ? m[1] : '').trim()
}

export default function Page() {
  const shortlist = useApp(s => s.shortlist)
  const notify = useApp(s => s.notify)
  const go = useApp(s => s.go)
  const lens = useLens()
  const [context, setContext] = useState('')
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<Record<string, TraceStep[]>>({})
  const [result, setResult] = useState<TeamResult | null>(null)
  const [charts, setCharts] = useState<Record<string, ChartData | null>>({})
  const [rows, setRows] = useState<SupplierRow[]>([])
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    get<TeamResult | null>('/team/last').then(r => { if (r) { setResult(r); loadCharts(r) } }).catch(() => {})
    return () => abortRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!shortlist.length) { setRows([]); return }
    post<SupplierRow[]>('/rows', { ids: shortlist, lens_weights: lens.weights }).then(setRows).catch(() => {})
  }, [shortlist, lens.weights])

  function loadCharts(res: TeamResult) {
    setCharts({})
    SPECIALISTS.forEach(name => {
      const rep = res.reports[name]
      if (!rep) return
      post<ChartData | null>('/team/chart', { ids: res.ids, spec: rep.chart, area: name })
        .then(d => setCharts(c => ({ ...c, [name]: d })))
        .catch(() => setCharts(c => ({ ...c, [name]: null })))
    })
  }

  function run() {
    if (shortlist.length < 2) { notify('Add at least 2 suppliers to the shortlist first', 'warn'); return }
    setRunning(true); setSteps({}); setResult(null); setCharts({})
    const ctrl = new AbortController()
    abortRef.current = ctrl
    streamPost<TraceStep, TeamResult>('/team/run', { ids: shortlist, context, lens_name: lens.name, lens_weights: lens.weights }, ev => {
      if (ev.event === 'step') {
        const a = ev.data.agent || 'Leader'
        setSteps(s => ({ ...s, [a]: [...(s[a] || []), ev.data] }))
      } else if (ev.event === 'result') {
        setResult(ev.data); setRunning(false); loadCharts(ev.data)
      } else if (ev.event === 'error') {
        notify(`Agent team failed: ${ev.data}`, 'warn'); setRunning(false)
      }
    }, ctrl.signal).catch(e => { if (e?.name !== 'AbortError') notify(String(e?.message || e), 'warn'); setRunning(false) })
  }

  function downloadMemo() {
    if (!result) return
    const blob = new Blob([result.memo], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `selection_memo_${result.pick}.md`; a.click()
    URL.revokeObjectURL(url)
  }

  const stale = !!(result && shortlist.length && JSON.stringify([...result.ids].sort()) !== JSON.stringify([...shortlist].sort()))

  return (
    <div>
      <PageHeader title="Agent team" icon={<Users className="size-5" />}
        subtitle="A leader agent and four specialists — Financial, Operations & Quality, Compliance & ESG, Geopolitics & Reputation — analyse the shortlist in parallel. The leader then weighs their reports into one decision and writes the selection memo. Every number comes from the dataset." />

      <Card className="mb-6">
        <CardHeader title="Ask the agent team"
          subtitle={`${shortlist.length} supplier${shortlist.length === 1 ? '' : 's'} in the shortlist · risk lens: ${lens.name}`} />
        {shortlist.length < 2 ? (
          <Empty icon={<Users className="size-5" />} title="Add at least 2 suppliers to the shortlist"
            action={<Button variant="primary" onClick={() => go('explore')}>Go to Explore</Button>}>
            Build a shortlist in Explore or Compare, then come back to ask the agent team to pick one.
          </Empty>
        ) : (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {rows.map(r => <LevelBadge key={r.id} level={r.level} value={r.id.replace('SUPP_', 'S')} size="sm" />)}
            </div>
            <Field label="What are you buying?">
              <TextArea rows={2} value={context} onChange={e => setContext(e.target.value)}
                placeholder="e.g. brake control units for a regional train, safety-critical, 5-year frame contract" />
            </Field>
            <div className="flex flex-wrap gap-1.5">
              {EXAMPLES.map(ex => <Chip key={ex} active={context === ex} onClick={() => setContext(ex)}>{ex}</Chip>)}
            </div>
            <div className="flex items-center justify-between gap-3 pt-1">
              <Tag tone="accent">Lens: {lens.name}</Tag>
              <Button variant="primary" icon={<Sparkles className="size-4" />} loading={running} onClick={run}>Ask the agent team</Button>
            </div>
          </div>
        )}
      </Card>

      {running && (
        <Card className="mb-6">
          <CardHeader title="The team is working" subtitle="The leader plans and briefs; four specialists analyse the shortlist at the same time." />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
            {LANE_ORDER.map(name => <Lane key={name} name={name} steps={steps[name] || []} />)}
          </div>
        </Card>
      )}

      {result && (
        <div className="space-y-6">
          <div className="text-xs text-muted">Showing the agent team's {stale ? 'last' : 'latest'} run · {result.created_at}
            {stale && ' · the shortlist has changed since — ask again for an up-to-date decision'}</div>

          <Card className="bg-gradient-to-br from-accent-soft/50 to-transparent">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="grid size-14 shrink-0 place-items-center rounded-2xl bg-accent text-white"><Trophy className="size-7" /></div>
                <div>
                  <div className="text-xs font-semibold tracking-wide text-muted uppercase">Team pick</div>
                  <div className="flex items-center gap-2 text-xl font-bold text-ink">
                    {result.pick} <LevelBadge level={levelOf(result.team_score[result.pick])} value={result.team_score[result.pick]} />
                  </div>
                  <p className="mt-1.5 max-w-xl text-sm text-ink-2">{recommendation(result.memo) || "The leader's recommendation is in the memo below."}</p>
                </div>
              </div>
              <div className="text-right text-xs text-muted whitespace-nowrap">
                <div>{result.model}</div>
                <div>lens: {result.lens}</div>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader title="How the team got there" subtitle={result.why || 'Area weights taken from the risk lens, unchanged for this purchase'} />
            <FlowDiagram res={result} />
            {result.leader_reasoning && <Collapsible title="How the leader reasoned">{result.leader_reasoning}</Collapsible>}
          </Card>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader title="Team scorecard" subtitle="Risk per area (weight under each agent), team score and TRI — lower is better" />
              <TeamScorecard res={result} />
              <div className="mt-4 border-t border-line pt-3"><TeamScoreBars res={result} /></div>
            </Card>
            <Card>
              <CardHeader title="Score build-up" subtitle="Each area's weighted contribution to the team score" />
              <BuildUpBars res={result} />
            </Card>
          </div>

          <Card>
            <CardHeader title="Area weights" subtitle="How much the leader made each area count for this purchase, vs the lens default" />
            <WeightsChart res={result} />
          </Card>

          <Card>
            <CardHeader title="Selection memo" actions={
              <Button size="sm" variant="secondary" icon={<Download className="size-3.5" />} onClick={downloadMemo}>Download memo (.md)</Button>
            } />
            <div className="max-h-[560px] overflow-y-auto rounded-xl border border-line bg-sunken/40 p-4">
              <Markdown>{result.memo}</Markdown>
            </div>
          </Card>

          <div>
            <h2 className="mb-3 text-sm font-semibold text-ink">The specialists' reports</h2>
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              {SPECIALISTS.map(name => result.reports[name] && (
                <SpecialistCard key={name} name={name} rep={result.reports[name]} res={result} chart={charts[name]} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
