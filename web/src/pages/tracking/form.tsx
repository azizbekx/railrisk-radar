// "Add supplier" form for the live tracking portfolio.
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, CardHeader, Field, Input, Select } from '../../components/ui'
import { post } from '../../lib/api'
import { useApp } from '../../lib/store'
import type { Criticality, NewSupplier, TrackedSupplier } from './types'

export function AddSupplier({ onAdded, onCancel }: { onAdded: () => void; onCancel: () => void }) {
  const notify = useApp(s => s.notify)
  const [f, setF] = useState({ name: '', website: '', country: '', category: '', criticality: 'Medium' as Criticality, dataset_id: '', relationship: '', source: '' })
  const [busy, setBusy] = useState(false)
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF(v => ({ ...v, [k]: e.target.value }))

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!f.name.trim()) { notify('Enter the supplier name', 'warn'); return }
    const body: NewSupplier = { name: f.name.trim(), criticality: f.criticality }
    for (const k of ['website', 'country', 'category', 'relationship', 'source'] as const) if (f[k].trim()) body[k] = f[k].trim()
    if (f.dataset_id.trim()) body.dataset_id = f.dataset_id.trim().toUpperCase()
    setBusy(true)
    try {
      const s = await post<TrackedSupplier>('/tracking/suppliers', body)
      notify(`Now tracking ${s.name}. Run the agents to build its history.`)
      onAdded()
    } catch (e: any) { notify(String(e?.message || e), 'warn') } finally { setBusy(false) }
  }

  return (
    <Card className="mb-6">
      <CardHeader title="Add a supplier to track" subtitle="Use the real company name, the worker agent searches the web for it. Link a dataset ID to start from its dataset risk profile." />
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Field label="Company name *"><Input value={f.name} onChange={set('name')} placeholder="e.g. Knorr-Bremse" autoFocus /></Field>
        <Field label="Website"><Input value={f.website} onChange={set('website')} placeholder="knorr-bremse.com" /></Field>
        <Field label="Country"><Input value={f.country} onChange={set('country')} placeholder="Germany" /></Field>
        <Field label="Category"><Input value={f.category} onChange={set('category')} placeholder="Braking systems" /></Field>
        <Field label="Criticality" hint="Weights the supplier in the portfolio score (High 3, Medium 2, Low 1)">
          <Select value={f.criticality} onChange={set('criticality')}><option>High</option><option>Medium</option><option>Low</option></Select>
        </Field>
        <Field label="Dataset ID (optional)" hint="e.g. SUPP_00012"><Input value={f.dataset_id} onChange={set('dataset_id')} placeholder="SUPP_00012" /></Field>
        <Field label="What they supply us" hint="Helps the worker agent tell this company from namesakes"><Input value={f.relationship} onChange={set('relationship')} placeholder="Brakes for Velaro trains" /></Field>
        <Field label="Source (optional)" hint="Contract, press release or award that documents the relationship"><Input value={f.source} onChange={set('source')} placeholder="https://…" /></Field>
        <div className="flex items-center justify-end gap-2 sm:col-span-2 xl:col-span-3">
          <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button type="submit" variant="primary" icon={<Plus className="size-4" />} loading={busy}>Add supplier</Button>
        </div>
      </form>
    </Card>
  )
}
