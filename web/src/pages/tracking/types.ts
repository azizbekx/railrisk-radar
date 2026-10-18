// Live tracking contract (api/tracking.py ⇄ web). Keys must match the backend exactly.
import type { Level } from '../../lib/types'

export type Area = 'Financial' | 'Operations & Quality' | 'Compliance & ESG' | 'Geopolitics & Reputation'
export type Criticality = 'High' | 'Medium' | 'Low'
export type Direction = 'rising' | 'stable' | 'falling'

export interface NewSupplier { name: string; website?: string; country?: string; category?: string; criticality?: Criticality; dataset_id?: string; relationship?: string; source?: string }

export interface TrackEvent {
  id: string; date: string; title: string; url: string; source: string
  area: Area; severity: number; impact: number; summary: string; found_at: string
}

export interface Outlook { direction: Direction; delta_30d: number; confidence: 'high' | 'medium' | 'low'; reason: string; disruption_prob_90d: number }
export interface Point { date: string; score: number }
export interface ForecastPoint { date: string; score: number; low: number; high: number }

export interface TrackedSupplier {
  id: string
  name: string; website: string; country: string; category: string
  criticality: Criticality; dataset_id: string | null; added_at: string
  relationship: string               // what they supply us
  source: string                     // link documenting the supply relationship
  status: 'pending' | 'ok' | 'error'
  last_checked: string | null
  score: number | null; level: Level | null
  delta_1d: number | null; delta_7d: number | null
  areas: Record<Area, number> | null
  baseline: Record<Area, number> | null
  series: Point[]
  forecast: ForecastPoint[]
  trend: Direction | null; slope_per_week: number | null
  outlook: Outlook | null
  latest_event: TrackEvent | null
  events_30d: number
  note: string
  error: string | null
}

export interface SupplierDetail extends TrackedSupplier {
  area_series: ({ date: string } & Record<Area, number>)[]
  events: TrackEvent[]
  signals: string[]
  sources_checked: number
}

export interface LeaderBrief {
  created_at: string; model: string
  headline: string
  summary_md: string
  portfolio: { score: number; level: Level; delta_7d: number; series: Point[]; forecast: ForecastPoint[] }
  watchlist: { id: string; name: string; reason: string; action: string; predicted_level: Level }[]
}

export interface RunInfo { started_at: string; finished_at: string | null; trigger: 'manual' | 'schedule'; suppliers: number; new_events: number; errors: number }

export interface Portfolio {
  suppliers: TrackedSupplier[]
  leader: LeaderBrief | null
  runs: RunInfo[]
  schedule: { enabled: boolean; hour_utc: number; next_run: string | null; last_run: string | null }
  running: boolean
  keys: { llm: boolean; tavily: boolean }
}
