// Chart theme (dataviz reference palette, light mode). Use these instead of raw hex in charts.
// Rules: categorical hues in fixed order by entity (never by rank); thin marks; 4px rounded bar ends;
// recessive grid; text in ink tokens, never series colours; a legend for >= 2 series; hover tooltip on every chart.

export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']

/** Stable colour per supplier: index in the given ordered id list (e.g. the shortlist order). */
export const seriesColor = (ids: string[], id: string) => SERIES[Math.max(0, ids.indexOf(id)) % SERIES.length]

/** Sequential blue ramp (100 -> 700) for magnitude, e.g. heatmaps of risk scores. */
export const SEQ = ['#cde2fb', '#b7d3f6', '#9ec5f4', '#86b6ef', '#6da7ec', '#5598e7', '#3987e5', '#2a78d6', '#256abf', '#1c5cab', '#184f95', '#104281', '#0d366b']

/** Risk-level status colours (dot / mark) and soft chip pairs. Always pair with a text label. */
export const LEVEL = {
  Low: { dot: '#22a447', bg: '#e6f5eb', ink: '#1c6b3a' },
  Medium: { dot: '#e9a514', bg: '#fdf3d6', ink: '#87600a' },
  High: { dot: '#ec835a', bg: '#fde8dd', ink: '#a4461b' },
  Critical: { dot: '#d03b3b', bg: '#fbe2e2', ink: '#a42828' },
} as const

/** Diverging around a midpoint (e.g. points vs dataset average): blue = lower risk, red = higher risk. */
export const DIVERGE = { better: '#2a78d6', worse: '#e34948', neutral: '#d9d8d3' }

export const INK = { primary: '#111827', secondary: '#4b5563', muted: '#8b93a1', grid: '#eef0f3', axis: '#d5d9e0' }

/** Spread into recharts axes: <XAxis {...axisProps} /> */
export const axisProps = {
  tick: { fill: INK.muted, fontSize: 11 },
  axisLine: false,
  tickLine: false,
} as const

export const gridProps = { stroke: INK.grid, strokeDasharray: '0', vertical: false } as const

/** Bar radius for horizontal bars (rounded data end) and vertical bars. */
export const BAR_RADIUS_H: [number, number, number, number] = [0, 4, 4, 0]
export const BAR_RADIUS_V: [number, number, number, number] = [4, 4, 0, 0]

/** Interpolate the sequential ramp for a 0-100 risk score. */
export const seqColor = (v: number) => SEQ[Math.min(SEQ.length - 1, Math.max(0, Math.round((v / 100) * (SEQ.length - 1))))]
