// Shared component kit. Soft, rounded, consistent: build every page from these before writing new styles.
import clsx from 'clsx'
import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { LEVEL } from '../lib/chart'
import type { Level } from '../lib/types'

export { clsx }

/* ---------- layout ---------- */

export function PageHeader({ title, subtitle, icon, actions }: { title: string; subtitle?: ReactNode; icon?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="flex items-center gap-3.5">
        {icon && <div className="grid size-11 place-items-center rounded-2xl bg-accent-soft text-accent">{icon}</div>}
        <div>
          <h1 className="text-[1.6rem] font-bold tracking-tight text-ink">{title}</h1>
          {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Card({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <div className={clsx('rounded-[var(--radius-card)] border border-line bg-surface shadow-[var(--shadow-soft)]', pad && 'p-5', className)}>{children}</div>
}

export function CardHeader({ title, subtitle, actions, icon }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        {icon && <div className="mt-0.5 text-accent">{icon}</div>}
        <div>
          <h3 className="text-[0.95rem] font-semibold text-ink">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-muted">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

/* ---------- controls ---------- */

type BtnVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export function Button({ variant = 'secondary', size = 'md', loading, icon, children, className, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: 'sm' | 'md' | 'lg'; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-full font-semibold whitespace-nowrap transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent/20',
        size === 'sm' && 'h-8 px-3.5 text-xs', size === 'md' && 'h-10 px-4.5 text-sm', size === 'lg' && 'h-12 px-6 text-[0.95rem]',
        variant === 'primary' && 'bg-accent text-white shadow-sm hover:bg-accent-strong active:scale-[0.98]',
        variant === 'secondary' && 'border border-line bg-surface text-ink hover:border-line-strong hover:bg-sunken',
        variant === 'ghost' && 'text-ink-2 hover:bg-sunken hover:text-ink',
        variant === 'danger' && 'border border-line bg-surface text-critical-ink hover:bg-critical',
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  )
}

export function Input({ className, icon, ...rest }: InputHTMLAttributes<HTMLInputElement> & { icon?: ReactNode }) {
  return (
    <div className={clsx('relative', className)}>
      {icon && <div className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted">{icon}</div>}
      <input {...rest} className={clsx('h-10 w-full rounded-full border border-line bg-surface px-4 text-sm text-ink placeholder:text-muted transition focus:border-accent focus:ring-4 focus:ring-accent/15 focus:outline-none', icon && 'pl-10')} />
    </div>
  )
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={clsx('w-full rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-ink placeholder:text-muted transition focus:border-accent focus:ring-4 focus:ring-accent/15 focus:outline-none', props.className)} />
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={clsx("h-10 w-full appearance-none rounded-full border border-line bg-surface bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238b93a1' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")] bg-[right_0.9rem_center] bg-no-repeat pr-9 pl-4 text-sm text-ink transition focus:border-accent focus:ring-4 focus:ring-accent/15 focus:outline-none", className)}>
      {children}
    </select>
  )
}

/** Pill-shaped segmented control. */
export function Segmented<T extends string>({ value, options, onChange, size = 'md' }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; size?: 'sm' | 'md' }) {
  return (
    <div className="inline-flex rounded-full bg-sunken p-1 ring-1 ring-line">
      {options.map(o => (
        <button key={o.value} onClick={() => onChange(o.value)}
          className={clsx('rounded-full font-semibold transition', size === 'sm' ? 'px-3 py-1 text-xs' : 'px-4 py-1.5 text-sm',
            o.value === value ? 'bg-surface text-ink shadow-sm ring-1 ring-line' : 'text-ink-2 hover:text-ink')}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

/** Toggleable filter chip (multi-select). */
export function Chip({ active, onClick, children, dot }: { active?: boolean; onClick?: () => void; children: ReactNode; dot?: string }) {
  return (
    <button onClick={onClick}
      className={clsx('inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition',
        active ? 'border-accent bg-accent-soft text-accent-strong' : 'border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink')}>
      {dot && <span className="size-2 rounded-full" style={{ background: dot }} />}
      {children}
    </button>
  )
}

export function Checkbox({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink-2 select-none">
      <span onClick={e => { e.preventDefault(); onChange(!checked) }}
        className={clsx('grid size-[18px] place-items-center rounded-md border transition', checked ? 'border-accent bg-accent text-white' : 'border-line-strong bg-surface hover:border-accent')}>
        {checked && <svg viewBox="0 0 12 12" className="size-3"><path d="M2.5 6.2 5 8.5l4.5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}
      </span>
      {label && <span onClick={e => { e.preventDefault(); onChange(!checked) }}>{label}</span>}
    </label>
  )
}

/** Labelled range (two number inputs feel heavy; this is a single-thumb slider with value). */
export function Slider({ label, value, min, max, step = 1, onChange, format }: { label: ReactNode; value: number; min: number; max: number; step?: number; onChange: (v: number) => void; format?: (v: number) => string }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs"><span className="font-medium text-ink-2">{label}</span><span className="font-semibold text-ink">{format ? format(value) : value}</span></div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(Number(e.target.value))} className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-line accent-[var(--color-accent)]" />
    </div>
  )
}

export function Field({ label, children, hint }: { label: ReactNode; children: ReactNode; hint?: ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-ink-2">{label}</div>
      {children}
      {hint && <div className="mt-1 text-[11px] text-muted">{hint}</div>}
    </div>
  )
}

/* ---------- data display ---------- */

/** Risk level chip: tinted background + dot + label (never colour alone). */
export function LevelBadge({ level, value, size = 'md' }: { level: Level | string; value?: number | string; size?: 'sm' | 'md' }) {
  const c = LEVEL[level as Level] ?? { dot: '#8b93a1', bg: '#f1f2f4', ink: '#4b5563' }
  return (
    <span className={clsx('inline-flex items-center gap-1.5 rounded-full font-semibold whitespace-nowrap', size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs')} style={{ background: c.bg, color: c.ink }}>
      <span className="size-1.5 rounded-full" style={{ background: c.dot }} />
      {value !== undefined ? <><span className="tabular-nums">{value}</span><span className="opacity-70">· {level}</span></> : level}
    </span>
  )
}

/** Solid risk pill ("TRI 80 · CRITICAL"): level colour fill, dark ink on the yellow band so it stays readable. */
export function LevelPill({ level, children, className }: { level: Level | string; children: ReactNode; className?: string }) {
  const c = LEVEL[level as Level] ?? { dot: '#8b93a1' }
  return (
    <span className={clsx('inline-flex items-center rounded-full px-3 py-1 text-xs font-bold tracking-wide whitespace-nowrap uppercase', className)}
      style={{ background: c.dot, color: level === 'Medium' ? '#1b2420' : '#fff' }}>
      {children}
    </span>
  )
}

/** Neutral pill / tag. */
export function Tag({ children, tone = 'neutral', className }: { children: ReactNode; tone?: 'neutral' | 'accent' | 'warn' | 'bad' | 'good'; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold whitespace-nowrap',
      tone === 'neutral' && 'bg-sunken text-ink-2 ring-1 ring-line', tone === 'accent' && 'bg-accent-soft text-accent-strong',
      tone === 'warn' && 'bg-medium text-medium-ink', tone === 'bad' && 'bg-critical text-critical-ink', tone === 'good' && 'bg-low text-low-ink', className)}>
      {children}
    </span>
  )
}

/** KPI tile. */
export function Stat({ label, value, sub, icon, tone }: { label: ReactNode; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: 'accent' | 'bad' }) {
  return (
    <Card className="flex items-start gap-3.5">
      {icon && <div className={clsx('grid size-10 shrink-0 place-items-center rounded-2xl', tone === 'bad' ? 'bg-critical text-critical-ink' : 'bg-accent-soft text-accent')}>{icon}</div>}
      <div className="min-w-0">
        <div className="text-xs font-medium text-muted">{label}</div>
        <div className="mt-0.5 text-2xl font-bold tracking-tight text-ink tabular-nums">{value}</div>
        {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
      </div>
    </Card>
  )
}

/** Horizontal 0-100 meter with rounded ends, coloured by level. */
export function Meter({ value, max = 100, color }: { value: number; max?: number; color?: string }) {
  const lvl = value >= 75 ? 'Critical' : value >= 50 ? 'High' : value >= 25 ? 'Medium' : 'Low'
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken ring-1 ring-line/60">
      <div className="h-full rounded-full" style={{ width: `${Math.min(100, (value / max) * 100)}%`, background: color ?? LEVEL[lvl].dot }} />
    </div>
  )
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-[var(--radius-card)] border border-dashed border-line-strong bg-surface/60 px-6 py-14 text-center">
      {icon && <div className="mb-3 grid size-12 place-items-center rounded-2xl bg-sunken text-muted">{icon}</div>}
      <div className="font-semibold text-ink">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-ink-2">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return <div className="flex items-center gap-2 text-sm text-muted"><Loader2 className="size-4 animate-spin" />{label}</div>
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('rr-pulse rounded-2xl bg-sunken', className)} />
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return <div className={clsx('prose-rr', className)}><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: p => <a {...p} target="_blank" rel="noreferrer" /> }}>{children}</ReactMarkdown></div>
}

/** Recharts tooltip shell: <Tooltip content={<ChartTooltip />} /> or with a custom render. */
export function ChartTooltip({ active, payload, label, render }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-line bg-surface/95 px-3 py-2 text-xs shadow-[var(--shadow-pop)] backdrop-blur">
      {render ? render(payload, label) : (
        <>
          {label !== undefined && <div className="mb-1 font-semibold text-ink">{label}</div>}
          {payload.map((p: any) => (
            <div key={p.dataKey + p.name} className="flex items-center gap-2 text-ink-2">
              <span className="size-2 rounded-full" style={{ background: p.color || p.fill }} />
              <span>{p.name}</span><span className="ml-auto pl-3 font-semibold text-ink tabular-nums">{typeof p.value === 'number' ? Math.round(p.value * 10) / 10 : p.value}</span>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

/** Small legend row for charts with >= 2 series. */
export function Legend({ items }: { items: { label: ReactNode; color: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-2">
      {items.map((it, i) => <span key={i} className="inline-flex items-center gap-1.5"><span className="size-2.5 rounded-full" style={{ background: it.color }} />{it.label}</span>)}
    </div>
  )
}
