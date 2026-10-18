// One shortlist toggle used on every page: adds the supplier, or removes it when already shortlisted.
import { Check, Plus, Star } from 'lucide-react'
import { useApp } from '../lib/store'
import { Button, clsx } from './ui'

/** variant 'button': labelled pill (profile header, alternatives). 'icon': compact round toggle for table rows. */
export function ShortlistButton({ id, variant = 'button', size = 'md', className }: {
  id: string; variant?: 'button' | 'icon'; size?: 'sm' | 'md' | 'lg'; className?: string
}) {
  const on = useApp(s => s.shortlist.includes(id))
  const add = useApp(s => s.addToShortlist)
  const remove = useApp(s => s.removeFromShortlist)
  const toggle = () => (on ? remove(id) : add([id]))

  if (variant === 'icon') {
    return (
      <button onClick={toggle} title={on ? 'Remove from shortlist' : 'Add to shortlist'}
        className={clsx('grid size-6 place-items-center rounded-full text-muted hover:bg-accent-soft hover:text-accent-strong', className)}>
        {on ? <Star className="size-3.5 fill-current text-accent" /> : <Plus className="size-3.5" />}
      </button>
    )
  }
  return (
    <Button size={size} variant={on ? 'secondary' : 'primary'} onClick={toggle}
      icon={on ? <Star className="size-4 fill-current text-accent" /> : <Plus className="size-4" />}
      className={clsx('group', className)}>
      {on ? (
        <>
          <span className="group-hover:hidden"><Check className="mr-1 inline size-3.5" />{size === 'sm' ? 'Listed' : 'On shortlist'}</span>
          <span className="hidden group-hover:inline">{size === 'sm' ? 'Remove' : 'Remove from shortlist'}</span>
        </>
      ) : 'Shortlist'}
    </Button>
  )
}
