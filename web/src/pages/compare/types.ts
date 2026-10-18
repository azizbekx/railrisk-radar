// Shared shapes for the compare page + sub-components. Mirrors api/routes/compare.py's response.
import type { Level, SupplierRow } from '../../lib/types'

export interface RankRow {
  rank: number
  id: string
  name: string
  tri: number
  level: Level
  lens_index: number | null
  critical_scores: number
  worst_label: string
  worst_value: number
  best_at: string[]
  delivery: number
  confirmation: number
  change: number
  po: number
  sourcing: string
  complexity: string
}

export interface ColumnStat {
  values: Record<string, number>
  lowest_risk: string | null
  highest_risk: string | null
  tied: boolean
}

export interface CompareResp {
  ids: string[]
  lens_label: 'TRI' | 'Lens index'
  rows: SupplierRow[]
  ranking: RankRow[]
  scores: Record<string, Record<string, number>>
  levels: Record<string, Record<string, Level>>
  score_order: string[]
  families: Record<string, string[]>
  tri_composition: Record<string, Record<string, number>>
  means: Record<string, number>
  columns: Record<string, ColumnStat>
}

/** Scores grouped by risk family, in a fixed display order (matches the TRI composition legend). */
export const familyOrder = (families: Record<string, string[]>) => Object.values(families).flat()
