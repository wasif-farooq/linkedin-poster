import type { ThreadStatus } from '../api/types'

const styles: Record<ThreadStatus, { label: string; className: string }> = {
  choose_topic: { label: 'Pick a topic', className: 'bg-review-soft text-review' },
  needs_review: { label: 'Needs review', className: 'bg-review-soft text-review' },
  confirm_publish: { label: 'Confirm publish', className: 'bg-review-soft text-review' },
  published: { label: 'Published', className: 'bg-success-soft text-success' },
  shared: { label: 'Shared', className: 'bg-success-soft text-success' },
  approved: { label: 'Approved', className: 'bg-success-soft text-success' },
  draft: { label: 'Draft', className: 'bg-line text-ink-2' },
  new: { label: 'New', className: 'bg-paper-2 text-ink-3' },
}

export function StatusPill({ status }: { status: ThreadStatus }) {
  const { label, className } = styles[status]
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${className}`}>
      {label}
    </span>
  )
}
