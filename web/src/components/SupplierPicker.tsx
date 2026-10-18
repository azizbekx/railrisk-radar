// Search-as-you-type supplier picker (GET /api/lookup); selecting a hit calls onSelect with its id.
import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { get } from '../lib/api'
import type { SupplierRow } from '../lib/types'
import { Input, LevelBadge } from './ui'

export function SupplierPicker({ onSelect, placeholder = 'Search supplier by ID or name…' }: { onSelect: (id: string) => void; placeholder?: string }) {
  const [q, setQ] = useState('')
  const [results, setResults] = useState<SupplierRow[]>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!q.trim()) return
    const t = setTimeout(() => get<SupplierRow[]>(`/lookup?q=${encodeURIComponent(q)}`).then(setResults).catch(() => setResults([])), 200)
    return () => clearTimeout(t)
  }, [q])

  return (
    <div className="relative w-full max-w-sm">
      <Input
        icon={<Search className="size-4" />}
        placeholder={placeholder}
        value={q}
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && q.trim() && results.length > 0 && (
        <div className="absolute z-20 mt-1.5 w-full overflow-hidden rounded-2xl border border-line bg-surface py-1 shadow-[var(--shadow-pop)]">
          {results.map(r => (
            <button
              key={r.id}
              onMouseDown={() => { onSelect(r.id); setQ(''); setOpen(false) }}
              className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition hover:bg-sunken"
            >
              <span className="min-w-0 truncate"><span className="font-semibold text-ink">{r.id}</span> <span className="text-ink-2">{r.name}</span></span>
              <LevelBadge level={r.level} value={r.tri} size="sm" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
