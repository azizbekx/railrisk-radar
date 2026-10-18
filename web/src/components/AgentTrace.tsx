// Live agent trace: a soft timeline of the steps an agent streams (api/common.py stream / stream_steps).
// Step shape (from core/): { type: 'thought'|'tool_call'|'tool_result'|'status'|'done'|'error'|'answer', content?, name?, args?, summary?, agent?, supplier? }
import { AlertTriangle, CheckCircle2, ChevronDown, Lightbulb, Loader2, Wrench } from 'lucide-react'
import { useState } from 'react'
import { clsx, Markdown } from './ui'

export interface TraceStep {
  type: string
  content?: any
  name?: string
  args?: Record<string, unknown>
  summary?: string
  agent?: string
  supplier?: string
}

const argText = (args?: Record<string, unknown>) =>
  Object.entries(args ?? {}).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join(', ')

function StepRow({ s }: { s: TraceStep }) {
  const who = s.agent || s.supplier
  const icon =
    s.type === 'tool_call' ? <Wrench className="size-3.5" /> :
    s.type === 'error' ? <AlertTriangle className="size-3.5" /> :
    s.type === 'done' ? <CheckCircle2 className="size-3.5" /> :
    <Lightbulb className="size-3.5" />
  const tone = s.type === 'error' ? 'bg-critical text-critical-ink' : s.type === 'done' ? 'bg-low text-low-ink' : s.type === 'tool_call' ? 'bg-accent-soft text-accent' : 'bg-sunken text-ink-2'
  if (s.type === 'tool_result') {
    return <div className="ml-9 -mt-1 truncate font-mono text-[11px] text-muted">↳ {s.summary ?? (typeof s.content === 'string' ? s.content : '')}</div>
  }
  if (s.type === 'answer') return null
  return (
    <div className="rr-in flex items-start gap-2.5">
      <div className={clsx('mt-0.5 grid size-6.5 shrink-0 place-items-center rounded-full', tone)}>{icon}</div>
      <div className="min-w-0 flex-1 text-[13px] leading-relaxed text-ink-2">
        {who && <span className="mr-1.5 font-semibold text-ink">{who}</span>}
        {s.type === 'tool_call'
          ? <span className="font-mono text-xs"><span className="font-semibold text-accent-strong">{s.name}</span><span className="text-muted">({argText(s.args)})</span></span>
          : <Markdown className="inline [&>p]:inline [&>p]:m-0">{String(s.content ?? '')}</Markdown>}
      </div>
    </div>
  )
}

/** running: shows a pulsing "working" row at the end. collapsible: header toggles the list (open while running). */
export function AgentTrace({ steps, running, title = 'Agent trace', collapsible = true, max }: { steps: TraceStep[]; running?: boolean; title?: string; collapsible?: boolean; max?: number }) {
  const [open, setOpen] = useState(false)
  const show = running || open || !collapsible
  const visible = max ? steps.slice(-max) : steps
  const calls = steps.filter(s => s.type === 'tool_call').length
  return (
    <div className="rounded-2xl border border-line bg-sunken/60">
      <button onClick={() => collapsible && setOpen(o => !o)} className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-xs font-semibold text-ink-2">
        {running ? <Loader2 className="size-3.5 animate-spin text-accent" /> : <CheckCircle2 className="size-3.5 text-low-dot" />}
        <span>{title}</span>
        <span className="font-normal text-muted">· {steps.length} steps{calls ? ` · ${calls} tool calls` : ''}</span>
        {collapsible && !running && <ChevronDown className={clsx('ml-auto size-4 transition', open && 'rotate-180')} />}
      </button>
      {show && (
        <div className="space-y-2.5 border-t border-line px-4 py-3">
          {visible.map((s, i) => <StepRow key={i} s={s} />)}
          {running && <div className="rr-pulse ml-9 text-xs text-muted">working…</div>}
        </div>
      )}
    </div>
  )
}
