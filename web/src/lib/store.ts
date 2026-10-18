// Global app state: current page, shortlist (max 20, persisted per browser), risk lens, selected profile.
import { create } from 'zustand'
import type { Meta } from './types'

export type Page = 'explore' | 'compare' | 'team' | 'profile' | 'chat' | 'research' | 'tracking'
export const MAX_SHORTLIST = 20
export const OFFICIAL_LENS = 'Dataset TRI (official)'
/** The jury's example shortlist (same as views/compare.py). */
export const JURY_EXAMPLE = ['SUPP_00012', 'SUPP_00450', 'SUPP_00731', 'SUPP_00018']

const load = <T,>(k: string, fallback: T): T => {
  try { const v = localStorage.getItem(k); return v ? (JSON.parse(v) as T) : fallback } catch { return fallback }
}
const save = (k: string, v: unknown) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* private mode */ } }

const initialPage = (): Page => {
  const h = window.location.hash.replace('#/', '').split('/')[0] as Page
  return ['explore', 'compare', 'team', 'profile', 'chat', 'research', 'tracking'].includes(h) ? h : 'explore'
}

interface State {
  meta: Meta | null
  setMeta: (m: Meta) => void

  page: Page
  go: (p: Page) => void

  shortlist: string[]
  /** Adds ids keeping order and the cap. Returns how many were added and skipped. */
  addToShortlist: (ids: string[]) => { added: string[]; skipped: string[] }
  removeFromShortlist: (id: string) => void
  setShortlist: (ids: string[]) => void

  lensName: string
  customWeights: Record<string, number> | null
  setLens: (name: string) => void
  setCustomWeights: (w: Record<string, number>) => void

  profileId: string | null
  openProfile: (id: string) => void

  toast: { id: number; text: string; tone?: 'ok' | 'warn' } | null
  notify: (text: string, tone?: 'ok' | 'warn') => void
}

export const useApp = create<State>((set, get) => ({
  meta: null,
  setMeta: meta => set({ meta }),

  page: initialPage(),
  go: page => { window.location.hash = `#/${page}`; set({ page }) },

  shortlist: load<string[]>('rr.shortlist', []),
  addToShortlist: ids => {
    const sl = [...get().shortlist]
    const added: string[] = [], skipped: string[] = []
    for (const id of ids) {
      if (sl.includes(id)) continue
      if (sl.length >= MAX_SHORTLIST) { skipped.push(id); continue }
      sl.push(id); added.push(id)
    }
    save('rr.shortlist', sl)
    set({ shortlist: sl })
    if (added.length) get().notify(`Added ${added.length} to shortlist (${sl.length}/${MAX_SHORTLIST})`)
    if (skipped.length) get().notify(`Shortlist is full. Skipped ${skipped.length}.`, 'warn')
    return { added, skipped }
  },
  removeFromShortlist: id => {
    const sl = get().shortlist.filter(x => x !== id)
    save('rr.shortlist', sl); set({ shortlist: sl })
  },
  setShortlist: ids => {
    const sl = [...new Set(ids)].slice(0, MAX_SHORTLIST)
    save('rr.shortlist', sl); set({ shortlist: sl })
  },

  lensName: load<string>('rr.lens', OFFICIAL_LENS),
  customWeights: load<Record<string, number> | null>('rr.customWeights', null),
  setLens: lensName => { save('rr.lens', lensName); set({ lensName }) },
  setCustomWeights: w => { save('rr.customWeights', w); set({ customWeights: w }) },

  profileId: load<string | null>('rr.profile', null),
  openProfile: id => { save('rr.profile', id); set({ profileId: id }); get().go('profile') },

  toast: null,
  notify: (text, tone = 'ok') => set({ toast: { id: Date.now(), text, tone } }),
}))

/** Active lens weights (normalised server-side). Official lens returns null so requests use the dataset TRI. */
export function useLens(): { name: string; weights: Record<string, number> | null; isOfficial: boolean; label: string } {
  const { lensName, customWeights, meta } = useApp()
  if (lensName === 'Custom') return { name: lensName, weights: customWeights ?? meta?.lenses[OFFICIAL_LENS] ?? null, isOfficial: false, label: 'Lens index' }
  const isOfficial = lensName === OFFICIAL_LENS || !meta?.lenses[lensName]
  return { name: lensName, weights: isOfficial ? null : meta!.lenses[lensName], isOfficial, label: isOfficial ? 'TRI' : 'Lens index' }
}
