export type Level = 'Low' | 'Medium' | 'High' | 'Critical'

/** Compact supplier row (api/common.py row). lens_index only when lens weights were sent. */
export interface SupplierRow {
  id: string
  name: string
  tri: number
  level: Level
  tri_percentile: number
  sourcing: 'Low' | 'Medium' | 'High'
  complexity: 'Simple' | 'Moderate' | 'Complex'
  delivery: number
  confirmation: number
  change: number
  po: number
  lens_index?: number
  /** Highest single score (explore rows only). */
  worst_label?: string
  worst_value?: number
}

export interface ScoreMeta { key: string; label: string; weight: number; group: string }

export interface Meta {
  scores: ScoreMeta[]
  groups: Record<string, string[]>
  ops: string[]
  higher_is_better: string[]
  categorical: Record<string, string[]>
  levels: Level[]
  lenses: Record<string, Record<string, number>>
  summary: { suppliers: number; avg_tri: number; critical: number; high: number; po_volume: number }
  means: Record<string, number>
  tri_check: number
  keys: { llm: boolean; provider: string; tavily: boolean }
  model: string | null
}
