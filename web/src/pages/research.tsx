// research page. Owned by the research slice.
// A buyer names a real company; the agent plans research, searches, reads the site, digs into red flags,
// then scores it on the dataset's 18 dimensions with a cited report.
import { CheckCircle2, ChevronDown, Download, Globe, Loader2, Search, ShieldAlert } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis,
} from 'recharts'
import { AgentTrace, type TraceStep } from '../components/AgentTrace'
import {
  Button, Card, CardHeader, ChartTooltip, Chip, clsx, Empty, Input, Legend, LevelBadge, Markdown, Meter, PageHeader, Tag,
} from '../components/ui'
import { get, streamPost } from '../lib/api'
import { useApp } from '../lib/store'
import { axisProps, BAR_RADIUS_H, gridProps, INK, LEVEL } from '../lib/chart'
import { label as fmtLabel, levelOf } from '../lib/format'
import type { Level, Meta } from '../lib/types'

const EXAMPLES = ['Knorr-Bremse', 'Alstom', 'Stadler Rail', 'CAF']
const STAGE_LABELS = ['Plan', 'Search', 'Triage red flags', 'Dig deeper', 'Score & report']
const VERDICT_LEVEL: Record<string, Level> = { approve: 'Low', 'approve with conditions': 'Medium', escalate: 'High', reject: 'Critical' }

/** Old cached runs stored the trace as pre-rendered markdown lines; new runs store raw step objects. */
function normalizeTrace(trace: unknown): TraceStep[] {
  if (!Array.isArray(trace)) return []
  return trace.map((t): TraceStep => (typeof t === 'string' ? { type: 'thought', content: t.replace(/^[^\w]+/, '') } : t))
}

function domain(url?: string): string {
  if (!url) return ''
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}

/** Turns "...[6][9]" citations into links against the numbered source list. */
function Cited({ text, src }: { text?: string; src: Record<number, { url: string }> }) {
  const linked = (text || '').replace(/\[(\d+)\]/g, (m, n) => (src[+n] ? `[\\[${n}\\]](${src[+n].url})` : m))
  return <Markdown className="inline leading-relaxed [&>p]:inline [&>p]:m-0">{linked}</Markdown>
}

/** Source numbers a finding or score cites, as links (mirrors the Streamlit `cites`). */
function SourceLinks({ ns, src }: { ns?: number[]; src: Record<number, { url: string }> }) {
  const known = (ns ?? []).filter(n => src[n])
  if (!known.length) return null
  return <span className="ml-1.5 inline-flex flex-wrap gap-1">{known.map(n => <a key={n} href={src[n].url} target="_blank" rel="noreferrer" className="text-[11px] font-semibold text-accent hover:underline">[{n}]</a>)}</span>
}

function VerdictTag({ verdict }: { verdict?: string }) {
  const v = (verdict || '').toLowerCase()
  const c = LEVEL[VERDICT_LEVEL[v] ?? 'Medium']
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-bold tracking-wide uppercase" style={{ background: c.bg, color: c.ink }}>
      <span className="size-1.5 rounded-full" style={{ background: c.dot }} />
      {v || 'no verdict'}
    </span>
  )
}

function Severity({ n }: { n: number }) {
  const color = n >= 4 ? LEVEL.Critical.dot : n >= 3 ? LEVEL.High.dot : n >= 2 ? LEVEL.Medium.dot : LEVEL.Low.dot
  return (
    <span className="inline-flex shrink-0 items-center gap-0.5" title={`severity ${n}/5`}>
      {Array.from({ length: 5 }).map((_, i) => <span key={i} className="size-1.5 rounded-full" style={{ background: i < n ? color : '#e5e7eb' }} />)}
    </span>
  )
}

function ProgressStrip({ stage, running }: { stage: number; running: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {STAGE_LABELS.map((s, i) => (
        <div key={s} className="flex items-center gap-1.5">
          <div className={clsx('flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition',
            i < stage ? 'bg-accent-soft text-accent-strong' : i === stage && running ? 'bg-accent text-white'
              : i === stage ? 'bg-accent-soft text-accent-strong' : 'bg-sunken text-muted')}>
            {i < stage ? <CheckCircle2 className="size-3.5" /> : i === stage && running ? <Loader2 className="size-3.5 animate-spin" /> : null}
            {s}
          </div>
          {i < STAGE_LABELS.length - 1 && <div className={clsx('h-px w-4', i < stage ? 'bg-accent' : 'bg-line')} />}
        </div>
      ))}
    </div>
  )
}

interface ScoreRow { key: string; label: string; value: number; known: boolean; evidence?: string }

function DimensionChart({ report, meta }: { report: any; meta: Meta }) {
  const rows = useMemo<ScoreRow[]>(() => {
    const out: ScoreRow[] = []
    for (const keys of Object.values(meta.groups)) {
      for (const key of keys) {
        const d = report.scores?.[key]
        const sm = meta.scores.find(s => s.key === key)
        const known = typeof d?.score === 'number'
        out.push({ key, label: sm?.label ?? fmtLabel(key), value: known ? d.score : (report.filled_scores?.[key] ?? 50), known, evidence: d?.evidence })
      }
    }
    return out
  }, [report, meta])
  const byLabel = useMemo(() => Object.fromEntries(rows.map(r => [r.label, r])), [rows])

  return (
    <div>
      <ResponsiveContainer width="100%" height={rows.length * 25 + 16}>
        <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 20, top: 4, bottom: 4 }} barCategoryGap={5}>
          <CartesianGrid {...gridProps} vertical horizontal={false} />
          <XAxis type="number" domain={[0, 100]} {...axisProps} />
          <YAxis type="category" dataKey="label" width={172} {...axisProps} />
          {[25, 50, 75].map(v => <ReferenceLine key={v} x={v} stroke={INK.axis} strokeDasharray="3 3" />)}
          <RTooltip cursor={{ fill: '#f3f4f6' }} content={<ChartTooltip render={(_: any, lbl: any) => {
            const row = byLabel[lbl]
            if (!row) return null
            return (
              <div className="max-w-xs">
                <div className="font-semibold text-ink">{row.label}</div>
                <div className="text-ink-2">{row.known ? `Score ${row.value}` : 'No evidence · dataset average shown'}</div>
                {row.evidence && <div className="mt-1 text-muted">{row.evidence}</div>}
              </div>
            )
          }} />} />
          <Bar isAnimationActive={false} dataKey="value" radius={BAR_RADIUS_H} maxBarSize={13}>
            {rows.map(r => <Cell key={r.key} fill={r.known ? LEVEL[levelOf(r.value) as Level].dot : INK.axis} fillOpacity={r.known ? 1 : 0.45} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <Legend items={[
        { label: 'Low', color: LEVEL.Low.dot }, { label: 'Medium', color: LEVEL.Medium.dot },
        { label: 'High', color: LEVEL.High.dot }, { label: 'Critical', color: LEVEL.Critical.dot },
        { label: 'No evidence (dataset avg used)', color: INK.axis },
      ]} />
    </div>
  )
}

function EvidenceTable({ report, meta, src }: { report: any; meta: Meta; src: Record<number, { url: string }> }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs font-semibold text-muted">
            <th className="pb-2 pr-3 font-semibold">Dimension</th><th className="pb-2 pr-3 font-semibold">Score</th><th className="pb-2 font-semibold">Evidence</th>
          </tr>
        </thead>
        <tbody>
          {meta.scores.map(sm => {
            const d = report.scores?.[sm.key]
            return (
              <tr key={sm.key} className="border-t border-line align-top">
                <td className="py-2 pr-3 font-medium whitespace-nowrap text-ink">{sm.label}</td>
                <td className="py-2 pr-3 tabular-nums">{d?.score ?? <span className="text-muted">—</span>}</td>
                <td className="py-2 text-ink-2">{d?.evidence ? <><Cited text={d.evidence} src={src} /><SourceLinks ns={d.sources} src={src} /></> : <span className="text-muted">no evidence</span>}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ReportView({ report, meta, src, onDownload }: { report: any; meta: Meta; src: Record<number, { url: string }>; onDownload: () => void }) {
  const [showPlan, setShowPlan] = useState(false)
  const flags = (report.red_flags ?? []).filter((f: any) => f && typeof f === 'object')
    .sort((a: any, b: any) => (b.severity ?? 0) - (a.severity ?? 0))
  const sources: any[] = report.sources ?? []

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h2 className="text-xl font-bold text-ink">{report.company}</h2>
              <VerdictTag verdict={report.verdict} />
            </div>
            {report.website && (
              <a href={report.website} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-accent hover:underline">
                <Globe className="size-3" />{report.website}
              </a>
            )}
            <p className="mt-2 max-w-2xl text-sm text-ink-2"><Cited text={report.overview} src={src} /></p>
            <p className="mt-2 text-xs text-muted">Researched {report.researched_at} · {sources.length} sources</p>
          </div>
          <div className="flex shrink-0 gap-3">
            <div className="rounded-2xl bg-sunken px-4 py-3 text-right">
              <div className="text-[11px] font-medium text-muted">Total Risk Index</div>
              <div className="text-2xl font-bold tracking-tight text-ink tabular-nums">{report.total_risk_index}</div>
              <div className="mt-1"><LevelBadge level={report.level} size="sm" /></div>
            </div>
            <div className="rounded-2xl bg-sunken px-4 py-3 text-right">
              <div className="text-[11px] font-medium text-muted">Red flags</div>
              <div className={clsx('text-2xl font-bold tracking-tight tabular-nums', flags.length ? 'text-critical-ink' : 'text-ink')}>{flags.length}</div>
              <div className="text-[11px] text-muted">found</div>
            </div>
            <div className="rounded-2xl bg-sunken px-4 py-3 text-right">
              <div className="text-[11px] font-medium text-muted">vs 10,000 suppliers</div>
              <div className="text-lg font-bold text-ink tabular-nums">{Math.round(report.riskier_than_pct)}%</div>
              <div className="text-[11px] text-muted">riskier than</div>
            </div>
          </div>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-medium text-ink-2">
              <span>Evidence coverage</span><span className="font-semibold text-ink">{Math.round(report.evidence_coverage * 100)}%</span>
            </div>
            <Meter value={report.evidence_coverage * 100} color="var(--color-accent)" />
            <div className="mt-1 text-[11px] text-muted">Share of the TRI weight backed by sources; the rest uses the dataset average.</div>
          </div>
          <div className="rounded-2xl bg-accent-soft px-4 py-3 text-sm text-accent-strong">
            <Cited text={report.recommendation} src={src} />
          </div>
        </div>
      </Card>

      <div className="grid gap-5 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader title="Scored on the dataset's 18 risk dimensions" subtitle="Grey bars = no evidence found; the dataset average stands in for the index." />
          <DimensionChart report={report} meta={meta} />
        </Card>
        <div className="space-y-5">
          <Card>
            <CardHeader title="Red flags" icon={<ShieldAlert className="size-4" />} />
            {flags.length === 0 ? (
              <div className="text-sm text-ink-2">No red flags found in the sources.</div>
            ) : (
              <div className="space-y-2.5">
                {flags.map((f: any, i: number) => (
                  <div key={i} className="rounded-2xl border border-line bg-sunken/50 p-3.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="text-sm font-semibold text-ink">{f.title}</div>
                      <Severity n={f.severity ?? 0} />
                    </div>
                    {f.status && <Tag tone="neutral" className="mt-1.5">{f.status}</Tag>}
                    <p className="mt-1.5 text-xs text-ink-2"><Cited text={f.detail} src={src} /><SourceLinks ns={f.sources} src={src} /></p>
                  </div>
                ))}
              </div>
            )}
          </Card>
          {report.strengths?.length > 0 && (
            <Card>
              <CardHeader title="Strengths" />
              <ul className="space-y-1.5 text-sm text-ink-2">
                {report.strengths.map((s: string, i: number) => (
                  <li key={i} className="flex gap-2"><span className="mt-1 size-1.5 shrink-0 rounded-full bg-low-dot" /><Cited text={s} src={src} /></li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      <Card>
        <CardHeader title="Evidence per dimension" subtitle="Every score is sourced, or marked as no evidence." />
        <EvidenceTable report={report} meta={meta} src={src} />
      </Card>

      <Card>
        <button onClick={() => setShowPlan(s => !s)} className="flex w-full items-center justify-between text-left text-sm font-semibold text-ink">
          Research plan &amp; triage
          <ChevronDown className={clsx('size-4 text-muted transition', showPlan && 'rotate-180')} />
        </button>
        {showPlan && (
          <div className="mt-3 space-y-4 text-sm">
            {report.plan?.hypothesis && <p className="text-ink-2">{report.plan.hypothesis}</p>}
            {report.plan?.queries?.length > 0 && (
              <div>
                <div className="mb-1.5 text-xs font-semibold text-muted">Planned queries</div>
                <ul className="space-y-1.5 text-xs text-ink-2">
                  {report.plan.queries.map((q: any, i: number) => (
                    <li key={i} className="flex items-start gap-1.5"><Tag tone="accent" className="mt-0.5 shrink-0">{q.area}</Tag><span>{q.query}</span></li>
                  ))}
                </ul>
              </div>
            )}
            {report.triage_flags?.length > 0 && (
              <div>
                <div className="mb-1.5 text-xs font-semibold text-muted">Triage: what the agent chose to dig into</div>
                <ul className="space-y-1.5 text-xs text-ink-2">
                  {report.triage_flags.map((f: any, i: number) => (
                    <li key={i}><span className="font-semibold text-ink">{f.flag}</span> (severity {f.severity}) — {f.evidence}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title={`Sources (${sources.length})`} actions={
          <Button size="sm" icon={<Download className="size-3.5" />} onClick={onDownload}>Download report (.md)</Button>
        } />
        <ol className="grid gap-1.5 text-xs text-ink-2 sm:grid-cols-2">
          {sources.map(s => (
            <li key={s.n} className="flex min-w-0 items-center gap-1.5">
              <span className="shrink-0 text-muted">{s.n}.</span>
              <a href={s.url} target="_blank" rel="noreferrer" className="min-w-0 truncate text-accent hover:underline" title={s.title}>{s.title || domain(s.url)}</a>
              {s.area && <Tag tone="neutral" className="shrink-0">{s.area}</Tag>}
            </li>
          ))}
        </ol>
      </Card>
    </div>
  )
}

export default function Page() {
  const meta = useApp(s => s.meta)!
  const notify = useApp(s => s.notify)
  const [company, setCompany] = useState('')
  const [running, setRunning] = useState(false)
  const [steps, setSteps] = useState<TraceStep[]>([])
  const [stage, setStage] = useState(0)
  const [report, setReport] = useState<any>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    get<any>('/research/last').then(rep => {
      if (rep) { setReport(rep); setSteps(normalizeTrace(rep.trace)); setStage(STAGE_LABELS.length) }
    }).catch(() => {})
    return () => abortRef.current?.abort()
  }, [])

  const run = async (name: string) => {
    if (!name.trim() || running) return
    setRunning(true); setSteps([]); setStage(0); setReport(null)
    const ac = new AbortController()
    abortRef.current = ac
    let st = 0
    const bump = (n: number) => { if (n > st) { st = n; setStage(n) } }
    try {
      await streamPost('/research', { company: name }, e => {
        if (e.event === 'step') {
          setSteps(s => [...s, e.data])
          const c = typeof e.data?.content === 'string' ? e.data.content : ''
          if (/Planning research/i.test(c)) bump(0)
          else if (/Research plan:/i.test(c)) bump(1)
          else if (/Red flags to verify|No red flags/i.test(c)) bump(2)
          else if (/Closing evidence gaps|Follow-up research/i.test(c)) bump(3)
          else if (/Writing the cited report/i.test(c)) bump(4)
          else if (e.data?.type === 'tool_call' && st >= 2) bump(3)
        } else if (e.event === 'result') {
          setReport(e.data); bump(4)
        } else if (e.event === 'error') {
          notify(`Research failed: ${e.data}`, 'warn')
        }
      }, ac.signal)
    } catch (e: any) {
      if (e?.name !== 'AbortError') notify(`Research failed: ${e.message}`, 'warn')
    } finally {
      setRunning(false)
    }
  }

  const download = () => {
    if (!report) return
    const md = report.markdown ?? `# ${report.company}\n\n${report.overview ?? ''}`
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = `risk_report_${(report.company || 'company').replace(/\s+/g, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const src = useMemo(() => Object.fromEntries((report?.sources ?? []).map((s: any) => [s.n, s])), [report])
  const keys = meta.keys
  const disabled = !keys.llm || !keys.tavily || !company.trim() || running

  return (
    <div>
      <PageHeader title="Research agent" icon={<Search className="size-5" />}
        subtitle="Name a real company. The agent plans its research, searches news and the web, reads the company site, digs deeper on red flags, then scores it on the dataset's 18 dimensions with a source behind each finding." />

      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-2.5">
          <Input className="min-w-[260px] flex-1" placeholder="e.g. Knorr-Bremse, Alstom, Stadler Rail, CAF…" value={company}
            onChange={e => setCompany(e.target.value)} onKeyDown={e => e.key === 'Enter' && run(company)} />
          <Button variant="primary" icon={<Search className="size-4" />} loading={running} disabled={disabled} onClick={() => run(company)}>
            Research
          </Button>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Try:</span>
          {EXAMPLES.map(ex => <Chip key={ex} onClick={() => setCompany(ex)}>{ex}</Chip>)}
        </div>
        {(!keys.llm || !keys.tavily) && <div className="mt-2 text-xs text-muted">Needs an LLM key and TAVILY_API_KEY. Showing the last cached report below.</div>}
      </Card>

      {(running || steps.length > 0) && (
        <Card className="mb-5 space-y-3">
          <ProgressStrip stage={stage} running={running} />
          <AgentTrace steps={steps} running={running} title="How the agent researched this" collapsible={!running} />
        </Card>
      )}

      {!report && !running && (
        <Empty icon={<Search className="size-6" />} title="No report yet">Research a real company above to generate a cited risk report.</Empty>
      )}

      {report && <ReportView report={report} meta={meta} src={src} onDownload={download} />}
    </div>
  )
}
