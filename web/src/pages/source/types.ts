// Shapes returned by api/routes/sourcing.py (logic in core/sourcing.py).
import type { Level, PartType } from '../../lib/types'
import type { TeamReport } from '../team/charts'

export interface CatalogItem { label: string; part_type: PartType; unit_eur: number; lead_weeks: number; certs: string[] }

export interface Parsed {
  component: string; quantity: number | null; need_by_weeks: number | null; target_unit_price: number | null
  notes: string; parsed_by: 'agent' | 'keywords'
}

export type Dim = 'price' | 'quality' | 'delivery' | 'lead_time' | 'risk'

/** One supplier's simulated RFQ answer with its dataset facts and offer score (0-100, lower = better). */
export interface Offer {
  id: string; name: string; rank: number; score: number
  unit_price: number; total: number; lead_weeks: number; warranty_years: number; certs: string[]
  late: boolean; over_budget: boolean
  tri: number; level: Level; risk_index: number; quality_risk: number
  delivery: number; confirmation: number; change_rate: number; reliability: number
  sourcing: string; complexity: string
  pts: Record<Dim, number>
}

export interface Pick {
  id: string; rank: number; role: string; why: string; pros: string[]; cons: string[]; watch: string
  final_score: number; team_score: number; area_index: Record<string, number>
  red_flags: { area: string; issue: string }[]; specialist_picks: string[]
  drivers: { label: string; value: number; level: Level }[]
  strengths: { label: string; value: number; level: Level }[]
}

export interface Signal { title: string; url: string; date: string; severity: number; impact: string; areas: string[] }

export interface SourcingResult {
  brief: {
    component: string; label: string; part_type: PartType; part_label: string; certs: string[]
    quantity: number; need_by_weeks: number | null; target_unit_price: number | null; notes: string
  }
  context: string; lens: string; weights: Record<Dim, number>
  funnel: { stage: string; label: string; count: number }[]
  longlist: Offer[]; finalists: string[]
  final_score: Record<string, number>; team_score: Record<string, number>
  area_weights: Record<string, number>; area_index: Record<string, Record<string, number>>
  analyst: { summary: string; reasons: Record<string, string>; passed_over: { id: string; reason: string }[]; reasoning: string }
  reports: Record<string, Omit<TeamReport, 'chart' | 'brief'> & { error?: string }>
  market: { summary: string; signals: Signal[]; advice: string; sources: { title: string; url: string; date: string }[]; error?: string }
  top: Pick[]; not_chosen: { id: string; reason: string; final_score: number }[]
  summary: string; memo: string; model: string; seconds: number; created_at: string; simulated: string
}

export const DIM_LABEL: Record<Dim, string> = { price: 'Price', risk: 'Risk', quality: 'Quality', delivery: 'Delivery', lead_time: 'Lead time' }
