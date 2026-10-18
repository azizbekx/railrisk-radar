// Buyer quotes helpers shared by the compare page (price vs risk) and the agent team brief.
import type { Meta, PartType } from './types'

/** Exact price, e.g. 1050 -> "€1,050" (format.eur abbreviates to k/M, which hides quote differences). */
export const price = (x: number) => `€${x.toLocaleString('en-US', { maximumFractionDigits: 2 })}`

/** Deterministic demo quote (EUR 800-1,200, rounded to 10) from a hash of the supplier id. Not real data. */
export function demoQuote(id: string): number {
  let h = 2166136261
  for (let i = 0; i < id.length; i++) { h ^= id.charCodeAt(i); h = Math.imul(h, 16777619) }
  return 800 + (Math.abs(h) % 41) * 10
}

/** One-line description of the component type and entered quotes, appended to the agent team's buying context. */
export function quoteLine(partType: PartType, meta: Meta | null, quotes: Record<string, number>, ids: string[]): string {
  const pt = meta?.part_types[partType]
  const q = ids.filter(i => quotes[i] > 0).map(i => `${i} ${price(quotes[i])}`)
  if (!pt && !q.length) return ''
  return [pt ? `Component: ${pt.label} (${pt.examples}).` : '', q.length ? `Buyer quotes: ${q.join(', ')}.` : ''].filter(Boolean).join(' ')
}
