// Formatting and domain helpers for the live tracking page.
import { SERIES } from '../../lib/chart'
import type { Area } from './types'


export const AREAS: Area[] = ['Financial', 'Operations & Quality', 'Compliance & ESG', 'Geopolitics & Reputation']
export const AREA_SHORT: Record<Area, string> = { Financial: 'Financial', 'Operations & Quality': 'Ops & Quality', 'Compliance & ESG': 'Compliance & ESG', 'Geopolitics & Reputation': 'Geopolitics' }
export const AREA_COLOR = Object.fromEntries(AREAS.map((a, i) => [a, SERIES[i]])) as Record<Area, string>

const r1 = (x: number) => Math.round(x * 10) / 10
export const n1 = (x: number) => String(r1(x))
/** Signed, 1 decimal max: +3.2 / −1.5 / 0 */
export const signed = (x: number) => { const r = r1(x); return r > 0 ? `+${r}` : r < 0 ? `−${Math.abs(r)}` : '0' }

/** Accepts "YYYY-MM-DD", "YYYY-MM-DD HH:MM" or ISO. Treated as UTC. */
const toDate = (s: string) => {
  const t = s.includes(' ') ? s.replace(' ', 'T') : s
  return new Date(/T/.test(t) ? (/[zZ]|[+-]\d\d:?\d\d$/.test(t) ? t : `${t}Z`) : `${t}T00:00:00Z`)
}
export const fmtDate = (s: string, year = false) => {
  const d = toDate(s)
  return isNaN(+d) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: year ? 'numeric' : undefined, timeZone: 'UTC' })
}
export const fmtDateTime = (s?: string | null) => {
  if (!s) return 'never'
  const d = toDate(s)
  return isNaN(+d) ? s : `${fmtDate(s)}, ${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })} UTC`
}

/** Padded y-domain (multiples of 5, clamped to 0-100) around the given values. */
export function domainOf(values: number[], pad = 4): [number, number] {
  if (!values.length) return [0, 100]
  const lo = Math.max(0, Math.floor((Math.min(...values) - pad) / 5) * 5)
  const hi = Math.min(100, Math.ceil((Math.max(...values) + pad) / 5) * 5)
  return hi - lo < 10 ? [lo, Math.min(100, lo + 10)] : [lo, hi]
}
