export const eur = (x: number) =>
  Math.abs(x) >= 1e9 ? `€${(x / 1e9).toFixed(1)}bn` : Math.abs(x) >= 1e6 ? `€${(x / 1e6).toFixed(1)}M` : `€${(x / 1e3).toFixed(0)}k`

export const pct = (x: number, digits = 0) => `${(x <= 1 && x >= 0 && digits >= 0 ? x * 100 : x).toFixed(digits)}%`

/** "Financial_Health_Score" -> "Financial Health" */
export const label = (col: string) => col.replace('_Score', '').replace(/_/g, ' ')

export const num = (x: number, digits = 0) => x.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })

export const levelOf = (v: number) => (v >= 75 ? 'Critical' : v >= 50 ? 'High' : v >= 25 ? 'Medium' : 'Low')
