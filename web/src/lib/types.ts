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

export type PartType = 'safety_critical' | 'standard' | 'budget'

/** core/dataset.py PART_TYPES: risk gate, lens and price weight per kind of component. */
export interface PartTypeMeta {
  label: string
  examples: string
  lens: string
  price_weight: number
  gate: { scores: string[]; max: number; tri_max: number }
  why: string
  /** suppliers (of 10,000) the gate hides */
  gate_hidden: number
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
  part_types: Record<PartType, PartTypeMeta>
  summary: { suppliers: number; avg_tri: number; critical: number; high: number; po_volume: number }
  means: Record<string, number>
  tri_check: number
  keys: { llm: boolean; provider: string; tavily: boolean }
  model: string | null
}
