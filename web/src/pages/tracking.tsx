// Live supplier tracking: one worker agent per supplier checks the web daily, a leader agent summarises and predicts.
// Logic lives in core/tracking.py, endpoints in api/tracking.py.
import { Activity, AlertTriangle, CheckCircle2, Clock, ExternalLink, Eye, Globe, Loader2, Play, Plus, Radar, Sparkles, TrendingUp, Users } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { AgentTrace, type TraceStep } from '../components/AgentTrace'
import { Button, Card, CardHeader, clsx, Empty, LevelBadge, LevelPill, Markdown, PageHeader, Skeleton, Stat, Tag } from '../components/ui'
import { get, post, streamPost } from '../lib/api'
import { useApp } from '../lib/store'
import { Delta, TrendMark } from './tracking/bits'
import { AREA_SHORT, fmtDate, fmtDateTime, n1, signed } from './tracking/util'
import { PortfolioChart, SmallMultiples, Spark } from './tracking/charts'
import { SupplierPanel } from './tracking/detail'
import { AddSupplier } from './tracking/form'
import type { Portfolio, TrackedSupplier } from './tracking/types'

const FIRST_RUN = 'The first run backfills 30 days of history from dated news, so the charts fill in immediately. Later runs only look at what is new since the last check.'

function Dot({ ok, label }: { ok: boolean; label: string }) {
  return <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-2"><span className={clsx('size-2 rounded-full', ok ? 'bg-low-dot' : 'bg-critical-dot')} />{label}<span className="text-muted">{ok ? 'ready' : 'missing'}</span></span>
}

function Strip({ pf, running }: { pf: Portfolio; running: boolean }) {
  const last = pf.runs[0]
  const lastAt = last?.finished_at ?? pf.schedule.last_run
  const item = (label: string, children: React.ReactNode) => <div><div className="text-[11px] font-medium text-muted">{label}</div><div className="mt-0.5 text-[13px] font-semibold text-ink">{children}</div></div>
  return (
    <Card className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-3 py-3.5">
      <div className="grid size-9 place-items-center rounded-xl bg-accent-soft text-accent"><Clock className="size-[18px]" /></div>
      {item('Last run', lastAt ? <>{fmtDateTime(lastAt)}{last && <span className="ml-1.5 text-[11px] font-normal text-muted">{last.trigger} · {last.new_events} new event{last.new_events === 1 ? '' : 's'}{last.errors ? ` · ${last.errors} error${last.errors === 1 ? '' : 's'}` : ''}</span>}</> : 'Never')}
      {item('Next scheduled run', pf.schedule.enabled ? <>{pf.schedule.next_run ? fmtDateTime(pf.schedule.next_run) : `daily after ${String(pf.schedule.hour_utc).padStart(2, '0')}:00 UTC`}</> : <span className="text-muted">Scheduler off</span>)}
      {item('Suppliers tracked', pf.suppliers.length)}
      <div className="flex flex-col gap-1"><Dot ok={pf.keys.llm} label="LLM" /><Dot ok={pf.keys.tavily} label="Web search" /></div>
      {(running || pf.running) && <Tag tone="accent" className="ml-auto"><Loader2 className="size-3 animate-spin" />Run in progress</Tag>}
    </Card>
  )
}

/** Live view of a run: one chip per worker agent + the interleaved trace. */
function RunTrace({ steps, running }: { steps: TraceStep[]; running: boolean }) {
  const workers = [...new Set(steps.map(s => s.agent).filter((a): a is string => !!a && a !== 'Leader'))]
  const status = (w: string) => { const l = steps.filter(s => s.agent === w).at(-1)?.type; return l === 'done' ? 'done' : l === 'error' ? 'error' : 'working' }
  return (
    <Card className="mb-6">
      <CardHeader icon={<Users className="size-4" />} title={running ? 'Agents are checking the web' : 'Last run'} subtitle="One worker agent per supplier searches recent news in parallel, then the leader agent writes the briefing and the outlook." />
      {workers.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {workers.map(w => {
            const st = status(w)
            return <Tag key={w} tone={st === 'done' ? 'good' : st === 'error' ? 'bad' : 'accent'}>
              {st === 'done' ? <CheckCircle2 className="size-3" /> : st === 'error' ? <AlertTriangle className="size-3" /> : <Loader2 className="size-3 animate-spin" />}{w}</Tag>
          })}
        </div>
      )}
      <AgentTrace steps={steps} running={running} title="Agent trace" max={running ? 40 : undefined} />
    </Card>
  )
}

function Briefing({ pf, onOpen, onRun, canRun, running }: { pf: Portfolio; onOpen: (id: string) => void; onRun: () => void; canRun: boolean; running: boolean }) {
  const L = pf.leader
  if (!L) {
    return (
      <Card className="mb-6">
        <Empty icon={<Sparkles className="size-5" />} title="No briefing yet"
          action={<Button variant="primary" icon={<Play className="size-4" />} disabled={!canRun} loading={running} onClick={onRun}>Run now</Button>}>
          {FIRST_RUN} Then the leader agent adds the portfolio headline, per-supplier outlook and watchlist.
        </Empty>
      </Card>
    )
  }
  const P = L.portfolio, last = pf.runs[0]
  const rising = pf.suppliers.filter(s => s.trend === 'rising').length
  const delta = P.delta_7d
  return (
    <div className="mb-6 space-y-4">
      <Card className="bg-gradient-to-br from-accent-soft/50 to-transparent">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-3xl">
            <div className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">Leader briefing</div>
            <p className="text-lg leading-snug font-semibold text-ink">{L.headline}</p>
          </div>
          <div className="text-right text-xs whitespace-nowrap text-muted"><div>{fmtDateTime(L.created_at)}</div><div>{L.model}</div></div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat icon={<Activity className="size-5" />} label="Portfolio risk score" value={n1(P.score)} sub={<LevelBadge level={P.level} size="sm" />} />
        <Stat icon={<TrendingUp className="size-5" />} label="Change in 7 days" tone={delta > 0 ? 'bad' : 'accent'} value={<Delta v={delta} />} sub={delta > 0 ? 'riskier' : delta < 0 ? 'safer' : 'unchanged'} />
        <Stat icon={<TrendingUp className="size-5" />} label="Suppliers rising" tone={rising ? 'bad' : 'accent'} value={rising} sub={`of ${pf.suppliers.length} tracked`} />
        <Stat icon={<Eye className="size-5" />} label="On the watchlist" value={L.watchlist.length} sub="needs buyer attention" />
        <Stat icon={<Globe className="size-5" />} label="New events, last run" value={last?.new_events ?? 0} sub={last ? fmtDate(last.started_at) : '–'} />
      </div>

      <Card>
        <CardHeader title="Portfolio risk, 30 days back and 30 days ahead" subtitle="Criticality-weighted mean of every tracked supplier. The dashed line and shaded range are the forecast: known events fading out plus the leader's expected change." />
        <PortfolioChart series={P.series} forecast={P.forecast} />
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader title="Summary" />
          <Markdown>{L.summary_md}</Markdown>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader title="Watchlist" subtitle="Predicted risk level in 30 days, with the recommended action" />
          {L.watchlist.length === 0 ? <div className="text-sm text-muted">Nothing needs attention right now.</div> : (
            <ul className="space-y-3">
              {L.watchlist.map(w => (
                <li key={w.id} className="rounded-2xl border border-line bg-sunken/50 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <button onClick={() => onOpen(w.id)} className="truncate text-sm font-semibold text-ink hover:text-accent hover:underline">{w.name}</button>
                    <LevelPill level={w.predicted_level}>{w.predicted_level}</LevelPill>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-2">{w.reason}</p>
                  <p className="mt-1.5 text-xs leading-relaxed text-ink"><b>Action:</b> {w.action}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

function SupplierRow({ s, onOpen, active }: { s: TrackedSupplier; onOpen: () => void; active: boolean }) {
  const e = s.latest_event
  return (
    <tr onClick={onOpen} className={clsx('cursor-pointer border-t border-line align-middle transition hover:bg-sunken/70', active && 'bg-accent-soft/40')}>
      <td className="max-w-[240px] py-3 pr-3 pl-5">
        <button onClick={onOpen} className="block max-w-full truncate text-left text-sm font-semibold text-ink hover:text-accent">{s.name}</button>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          <span className="truncate">{[s.country, s.category].filter(Boolean).join(' · ') || '–'}</span>
          <Tag tone={s.criticality === 'High' ? 'bad' : s.criticality === 'Medium' ? 'warn' : 'neutral'}>{s.criticality}</Tag>
        </div>
        {s.relationship && <div className="mt-0.5 truncate text-[11px] text-ink-2" title={s.relationship}>{s.relationship}</div>}
      </td>
      <td className="py-3 pr-3">
        {s.status === 'pending' ? <Tag>Not checked yet</Tag>
          : s.status === 'error' && s.score == null ? <span title={s.error ?? ''}><Tag tone="bad"><AlertTriangle className="size-3" />Check failed</Tag></span>
          : <div className="flex flex-col items-start gap-1">{s.score != null && s.level && <LevelBadge level={s.level} value={n1(s.score)} size="sm" />}{s.status === 'error' && <span title={s.error ?? ''}><Tag tone="bad"><AlertTriangle className="size-3" />last check failed</Tag></span>}</div>}
      </td>
      <td className="w-[150px] min-w-[120px] py-3 pr-3"><Spark series={s.series} forecast={s.forecast} level={s.level} /></td>
      <td className="py-3 pr-3 text-sm"><Delta v={s.delta_7d} /></td>
      <td className="py-3 pr-3"><TrendMark trend={s.trend} /></td>
      <td className="py-3 pr-3 text-xs">
        {s.outlook ? (
          <div className="leading-snug"><TrendMark trend={s.outlook.direction} /> <b className="text-ink tabular-nums">{signed(s.outlook.delta_30d)}</b> <span className="text-muted">in 30d</span>
            <div className="text-muted">{Math.round(s.outlook.disruption_prob_90d * 100)}% disruption in 90d</div></div>
        ) : <span className="text-muted">–</span>}
      </td>
      <td className="max-w-[280px] py-3 pr-3 text-xs">
        {e ? (
          <div className="leading-snug">
            <a href={e.url} target="_blank" rel="noreferrer" onClick={ev => ev.stopPropagation()} className="line-clamp-2 font-medium text-ink hover:text-accent hover:underline">{e.title}<ExternalLink className="ml-1 inline size-3 text-muted" /></a>
            <div className="text-muted">{fmtDate(e.date)} · {AREA_SHORT[e.area] ?? e.area}</div>
          </div>
        ) : <span className="text-muted">{s.status === 'pending' ? '–' : 'No events yet'}</span>}
      </td>
      <td className="py-3 pr-5 text-xs whitespace-nowrap text-ink-2">{s.last_checked ? fmtDateTime(s.last_checked) : '–'}</td>
    </tr>
  )
}

function SupplierTable({ suppliers, openId, onOpen }: { suppliers: TrackedSupplier[]; openId: string | null; onOpen: (id: string) => void }) {
  const heads = ['Supplier', 'Risk score', '30 days + forecast', '7d change', 'Trend', 'Leader outlook', 'Latest event', 'Last checked']
  return (
    <Card pad={false} className="mb-6 overflow-hidden">
      <div className="px-5 pt-5"><CardHeader title="Tracked suppliers" subtitle="Highest risk first. Click a row for the event timeline, area scores and the worker agent's note." /></div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px] text-left">
          <thead><tr className="text-[11px] font-semibold text-muted">
            {heads.map((h, i) => <th key={h} className={clsx('pb-2 font-semibold', i === 0 ? 'pl-5' : '', i === heads.length - 1 ? 'pr-5' : 'pr-3')}>{h}</th>)}
          </tr></thead>
          <tbody>{suppliers.map(s => <SupplierRow key={s.id} s={s} active={openId === s.id} onOpen={() => onOpen(s.id)} />)}</tbody>
        </table>
      </div>
    </Card>
  )
}

export default function Page() {
  const notify = useApp(s => s.notify)
  const [pf, setPf] = useState<Portfolio | null>(null)
  const [loadErr, setLoadErr] = useState('')
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<TraceStep[]>([])
  const [adding, setAdding] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [sampling, setSampling] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const refresh = useCallback(() => get<Portfolio>('/tracking').then(p => { setPf(p); setLoadErr('') }).catch(e => setLoadErr(String(e?.message || e))), [])
  useEffect(() => { refresh(); return () => abortRef.current?.abort() }, [refresh])

  // A run started by the scheduler or another tab: poll until the server says it is done.
  const serverRunning = !!pf?.running && !running
  useEffect(() => {
    if (!serverRunning) return
    const t = setInterval(refresh, 15000)
    return () => clearInterval(t)
  }, [serverRunning, refresh])

  function run() {
    setRunning(true); setSteps([])
    const ctrl = new AbortController()
    abortRef.current = ctrl
    let got = false
    streamPost<TraceStep, Portfolio>('/tracking/run', { ids: [] }, ev => {
      if (ev.event === 'step') setSteps(s => [...s, ev.data])
      else if (ev.event === 'result') { got = true; setPf(ev.data); const r = ev.data.runs[0]; notify(r ? `Run finished: ${r.new_events} new event${r.new_events === 1 ? '' : 's'}` : 'Run finished') }
      else if (ev.event === 'error') { notify(ev.data, 'warn'); setSteps(s => [...s, { type: 'error', content: ev.data, agent: 'Leader' }]) }
    }, ctrl.signal)
      .catch(e => { if (e?.name !== 'AbortError') notify(String(e?.message || e), 'warn') })
      .finally(() => { setRunning(false); if (!got) refresh() })
  }

  async function loadSample() {
    setSampling(true)
    try { setPf(await post<Portfolio>('/tracking/sample')); notify('Example suppliers added. Run the agents to build their history.') }
    catch (e: any) { notify(String(e?.message || e), 'warn') } finally { setSampling(false) }
  }

  const openSupplier = pf?.suppliers.find(s => s.id === openId) ?? null
  const keysOk = !!pf && pf.keys.llm && pf.keys.tavily
  const busy = running || !!pf?.running
  const canRun = keysOk && !busy && !!pf?.suppliers.length
  const runTitle = !pf?.suppliers.length ? 'Add a supplier first' : !keysOk ? 'Needs an LLM key and a Tavily key' : busy ? 'A run is in progress' : undefined
  const pending = pf?.suppliers.filter(s => s.status === 'pending').length ?? 0

  return (
    <div>
      <PageHeader title="Live tracking" icon={<Radar className="size-5" />}
        subtitle="Enter your real suppliers. Every day one worker agent per supplier checks the web for new risk news, then a leader agent summarises the portfolio, predicts the next 30 days and flags what to act on."
        actions={<>
          <Button icon={<Plus className="size-4" />} onClick={() => setAdding(a => !a)}>Add supplier</Button>
          <span title={runTitle}><Button variant="primary" icon={<Play className="size-4" />} loading={running} disabled={!canRun} onClick={run}>Run now</Button></span>
        </>} />

      {adding && <AddSupplier onCancel={() => setAdding(false)} onAdded={() => { setAdding(false); refresh() }} />}
      {loadErr && <Card className="mb-6 text-sm text-critical-ink">Could not load tracking data: {loadErr}</Card>}
      {!pf && !loadErr && <div className="space-y-4"><Skeleton className="h-16" /><Skeleton className="h-64" /></div>}

      {pf && (
        <>
          <Strip pf={pf} running={running} />
          {!keysOk && <Card className="mb-6 border-medium-dot/40 bg-medium text-[13px] text-medium-ink">Runs need an LLM key and a Tavily key in the server environment. You can still add suppliers and browse stored results.</Card>}
          {serverRunning && <Card className="mb-6 flex items-center gap-2 text-sm text-ink-2"><Loader2 className="size-4 animate-spin text-accent" />A tracking run is in progress on the server (scheduled or started elsewhere). This page refreshes every 15 seconds.</Card>}
          {(running || steps.length > 0) && <RunTrace steps={steps} running={running} />}

          {pf.suppliers.length === 0 ? (
            <Empty icon={<Radar className="size-5" />} title="No suppliers tracked yet"
              action={<div className="flex flex-wrap justify-center gap-2">
                <Button variant="primary" icon={<Sparkles className="size-4" />} loading={sampling} onClick={loadSample}>Load example Siemens suppliers</Button>
                <Button icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add your own supplier</Button>
              </div>}>
              The example portfolio has five real companies that public contracts, press releases and awards document as Siemens Mobility suppliers (Knorr-Bremse, Schaeffler, Hitachi Energy, Voith, HÜBNER), each with its source. {FIRST_RUN}
            </Empty>
          ) : (
            <>
              {pending > 0 && !pf.leader && <Card className="mb-6 text-[13px] text-ink-2"><b className="text-ink">{pending} supplier{pending === 1 ? ' is' : 's are'} waiting for the first check.</b> {FIRST_RUN}</Card>}
              <Briefing pf={pf} onOpen={setOpenId} onRun={run} canRun={canRun} running={running} />
              <Card className="mb-6">
                <CardHeader title="Every supplier at a glance" subtitle="Each card is one supplier: the last 30 days, then the forecast. Click to open it." />
                <SmallMultiples suppliers={pf.suppliers} selected={openId} onOpen={setOpenId} />
              </Card>
              <SupplierTable suppliers={pf.suppliers} openId={openId} onOpen={setOpenId} />
            </>
          )}
        </>
      )}

      {openSupplier && (
        <SupplierPanel key={openSupplier.id} base={openSupplier} version={`${pf?.runs[0]?.started_at ?? ''}|${pf?.suppliers.length}`}
          onClose={() => setOpenId(null)} onRemoved={() => { setOpenId(null); refresh() }} />
      )}
    </div>
  )
}
