// chat page. Owned by the chat slice.
// "Ask the data": a tool-calling assistant grounded in the 10,000-supplier dataset (core/agent.py DATA_TOOLS).
import { AlertTriangle, Bot, Send, Sparkles, SquareStack, User, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { create } from 'zustand'
import { AgentTrace, type TraceStep } from '../components/AgentTrace'
import { Button, Card, Chip, Markdown, PageHeader, TextArea } from '../components/ui'
import { streamPost } from '../lib/api'
import { useApp } from '../lib/store'
import { ChatChart, type ChatChartData } from './chat/ChatChart'

const SUPP_RE = /SUPP_\d{5}/g

const SUGGESTIONS = [
  'Which of SUPP_00012, SUPP_00450 and SUPP_00731 has the lowest financial risk?',
  'Why is the Total Risk Index of SUPP_00018 so high?',
  'Show 10 suppliers with Low sourcing risk and delivery rating above 95',
  'How does financial health differ by supply chain complexity?',
  'Find 5 easy-to-replace suppliers with no Critical scores and shortlist them',
  'Compare compliance and cyber risk for my shortlist',
]

interface Msg {
  role: 'user' | 'assistant'
  content: string
  trace?: TraceStep[]
  charts?: ChatChartData[]
  running?: boolean
  error?: string
}

const PRESETS: Record<string, string> = {  // short label -> full question (same quick asks as the Streamlit tab)
  'Lowest financial risk of 3?': SUGGESTIONS[0],
  'Why is SUPP_00018 so risky?': SUGGESTIONS[1],
  'Shortlist 5 reliable, easy swaps': 'Find 5 easy-to-replace suppliers with delivery rating above 97% and no Critical scores, and shortlist them',
  'Compliance & cyber of my shortlist': SUGGESTIONS[5],
}

// Conversation lives outside the component so it survives switching tabs, and a running answer keeps streaming.
const useChat = create<{ messages: Msg[]; sending: boolean }>(() => ({ messages: [], sending: false }))
let controller: AbortController | null = null

async function ask(question: string) {
  if (!question.trim() || useChat.getState().sending) return
  const { messages } = useChat.getState()
  const history = messages.slice(-8).map(m => ({ role: m.role, content: m.content }))
  useChat.setState({
    messages: [...messages, { role: 'user', content: question }, { role: 'assistant', content: '', trace: [], charts: [], running: true }],
    sending: true,
  })
  controller = new AbortController()
  const update = (fn: (m: Msg) => Msg) => useChat.setState(st => ({ messages: st.messages.map((m, i) => (i === st.messages.length - 1 ? fn(m) : m)) }))
  try {
    await streamPost('/chat', { question, history, shortlist: useApp.getState().shortlist }, ev => {
      if (ev.event === 'error') { update(m => ({ ...m, error: ev.data, running: false })); return }
      if (ev.event === 'done') { update(m => ({ ...m, running: false })); return }
      if (ev.event !== 'step') return
      const step = ev.data
      if (step.type === 'answer') { update(m => ({ ...m, content: step.content })); return }
      if (step.type === 'error') { update(m => ({ ...m, error: step.content, running: false })); return }
      if (step.type === 'tool_result' && step.name === 'show_chart' && step.chart) {
        update(m => ({ ...m, charts: [...(m.charts ?? []), step.chart] }))
      }
      if (step.type === 'tool_result' && step.name === 'add_to_shortlist' && step.content?.added?.length) {
        useApp.getState().addToShortlist(step.content.added)
      }
      update(m => ({ ...m, trace: [...(m.trace ?? []), step] }))
    }, controller.signal)
  } catch (e: any) {
    if (e?.name !== 'AbortError') update(m => ({ ...m, error: e?.message || 'Something went wrong.', running: false }))
    else update(m => ({ ...m, running: false }))
  } finally {
    useChat.setState({ sending: false })
    controller = null
  }
}

function SupplierChips({ text }: { text: string }) {
  const ids = Array.from(new Set(text.match(SUPP_RE) ?? []))
  const openProfile = useApp(s => s.openProfile)
  const addToShortlist = useApp(s => s.addToShortlist)
  if (!ids.length) return null
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-line pt-3">
      {ids.map(id => (
        <button key={id} onClick={() => openProfile(id)}
          className="rounded-full border border-line bg-sunken px-2.5 py-1 font-mono text-[11px] font-semibold text-ink-2 transition hover:border-accent hover:text-accent-strong">
          {id}
        </button>
      ))}
      {ids.length > 1 && (
        <button onClick={() => addToShortlist(ids)}
          className="rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-semibold text-accent-strong transition hover:brightness-95">
          + Add all to shortlist
        </button>
      )}
    </div>
  )
}

function Bubble({ msg, idx }: { msg: Msg; idx: number }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-3xl rounded-tr-lg bg-accent-soft px-4 py-2.5 text-sm text-ink">{msg.content}</div>
      </div>
    )
  }
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-accent text-white"><Bot className="size-4.5" /></div>
      <Card className="min-w-0 flex-1 space-y-3">
        {!!msg.trace?.length && <AgentTrace steps={msg.trace} running={msg.running} title="Agent trace" />}
        {msg.error ? (
          <div className="flex items-start gap-2 text-sm text-critical-ink"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{msg.error}</div>
        ) : msg.content ? (
          <Markdown className="text-sm">{msg.content}</Markdown>
        ) : msg.running ? (
          <div className="rr-pulse text-sm text-muted">Thinking…</div>
        ) : null}
        {msg.charts?.map((c, j) => <ChatChart key={idx + '-' + j} chart={c} />)}
        {msg.content && !msg.running && <SupplierChips text={msg.content} />}
      </Card>
    </div>
  )
}

export default function Page() {
  const meta = useApp(s => s.meta)
  const { messages, sending } = useChat()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const llmReady = meta?.keys?.llm ?? true

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const send = (q: string) => { setInput(''); ask(q) }
  const stop = () => controller?.abort()

  return (
    // main's wrapper div (owned by App.tsx) has py-7 (3.5rem vertical padding) and auto height, so a plain
    // h-full collapses to content. Pin to the viewport instead so messages scroll and the composer stays put.
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <PageHeader title="Ask the data" subtitle="Grounded on the 10,000-supplier dataset — every number traces back to a tool call."
        icon={<Sparkles className="size-5" />}
        actions={messages.length ? <Button size="sm" variant="ghost" onClick={() => useChat.setState({ messages: [] })}>Clear conversation</Button> : null} />

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1 pb-4">
          {!messages.length && (
            <div className="flex h-full flex-col items-center justify-center gap-6 py-6 text-center">
              <div>
                <div className="mx-auto mb-3 grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent"><SquareStack className="size-7" /></div>
                <h2 className="text-xl font-bold text-ink">Ask the data</h2>
                <p className="mx-auto mt-1 max-w-md text-sm text-ink-2">Plain-language questions over the supplier base. The assistant calls real tools and shows its trace, so every answer is traceable.</p>
              </div>
              <div className="grid w-full max-w-3xl grid-cols-1 gap-2.5 sm:grid-cols-2">
                {SUGGESTIONS.map(q => (
                  <button key={q} onClick={() => send(q)}
                    className="rounded-2xl border border-line bg-surface p-3.5 text-left text-[13px] leading-snug text-ink-2 shadow-[var(--shadow-soft)] transition hover:border-accent hover:text-ink">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => <Bubble key={i} msg={m} idx={i} />)}
          <div ref={bottomRef} />
        </div>

        {!llmReady && (
          <div className="mb-3 flex items-center gap-2 rounded-2xl border border-line bg-sunken px-4 py-2.5 text-xs text-ink-2">
            <AlertTriangle className="size-4 shrink-0 text-high-dot" /> No LLM key configured — the assistant can't answer right now.
          </div>
        )}

        {messages.length > 0 && (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {Object.entries(PRESETS).map(([short, q]) => <Chip key={short} onClick={() => !sending && send(q)}><span title={q}>{short}</span></Chip>)}
          </div>
        )}

        <form onSubmit={e => { e.preventDefault(); send(input) }} className="flex items-end gap-2 rounded-[1.75rem] border border-line bg-surface p-2 pl-4 shadow-[var(--shadow-soft)]">
          <User className="mb-2.5 size-4 shrink-0 text-muted" />
          <TextArea value={input} onChange={e => setInput(e.target.value)} disabled={!llmReady}
            placeholder="e.g. Which High-sourcing-risk suppliers have the best delivery rating?"
            rows={1} className="max-h-32 min-h-[2.25rem] flex-1 resize-none border-none !rounded-none bg-transparent px-0 py-1.5 shadow-none focus:ring-0"
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }} />
          {sending ? (
            <Button type="button" variant="danger" size="md" icon={<X className="size-4" />} onClick={stop}>Stop</Button>
          ) : (
            <Button type="submit" variant="primary" size="md" icon={<Send className="size-4" />} disabled={!input.trim() || !llmReady}>Send</Button>
          )}
        </form>
      </div>
    </div>
  )
}
