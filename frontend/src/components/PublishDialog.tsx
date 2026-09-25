import { useEffect, useRef } from 'react'
import type { PublishConfirmPayload } from '../api/types'
import { Icon } from './Icon'

interface PublishDialogProps {
  payload: PublishConfirmPayload
  busy: boolean
  onDecide: (confirm: boolean) => void
  onLater: () => void // Escape / close: leave the confirmation pending
}

/** The final gate before a public post. Native <dialog>: focus trap, Escape and backdrop for free. */
export function PublishDialog({ payload, busy, onDecide, onLater }: PublishDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    return () => dialog?.close()
  }, [])

  return (
    <dialog
      ref={ref}
      aria-labelledby="publish-title"
      onCancel={(e) => {
        e.preventDefault()
        if (!busy) onLater()
      }}
      className="m-auto max-h-[calc(100dvh-32px)] w-145 max-w-[calc(100vw-32px)] overflow-y-auto rounded-[18px] bg-card-soft p-0 text-ink shadow-[0_24px_64px_rgba(26,25,22,0.35)] backdrop:bg-black/60"
    >
      <div className="flex flex-col gap-2 px-5 pt-6 pb-2 sm:px-8 sm:pt-7">
        <span className="flex size-11 items-center justify-center rounded-xl bg-accent-soft text-accent-ink" aria-hidden="true">
          <Icon name="send" size={22} strokeWidth={2} />
        </span>
        <h2 id="publish-title" className="m-0 font-display text-[28px] leading-tight sm:text-[34px] font-normal">
          Publish to LinkedIn?
        </h2>
        <p className="m-0 text-[15px] text-ink-2">
          This posts publicly as <strong className="font-semibold text-ink">{payload.account || 'you'}</strong>.
          It can’t be undone from here.
        </p>
      </div>

      <div className="relative mx-5 mt-4 sm:mx-8 max-h-48 overflow-hidden rounded-xl border border-line bg-card px-4.5 py-4">
        <p className="m-0 text-sm leading-[1.55] whitespace-pre-line">{payload.post}</p>
        <div className="absolute inset-x-0 bottom-0 h-14 bg-linear-to-b from-card/0 to-card" aria-hidden="true" />
      </div>
      {payload.image && (
        <div className="mx-5 mt-3 sm:mx-8">
          <img
            src={payload.image}
            alt="The image posted with it"
            className="block aspect-[1.91] w-full rounded-xl border border-line object-cover"
          />
        </div>
      )}

      <ul className="mx-5 mt-4 flex list-none sm:mx-8 flex-col gap-2 p-0 text-sm">
        {['Approved by you', 'Not posted before (history checked)', 'Special characters escaped so nothing gets cut off'].map(
          (text) => (
            <li key={text} className="flex items-center gap-2.5">
              <Icon name="check" size={16} strokeWidth={2.4} className="text-success" />
              {text}
            </li>
          ),
        )}
      </ul>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-4.5 sm:px-8">
        <span className="font-mono text-[11px] text-ink-3">
          public · {payload.chars.toLocaleString()} chars{payload.image ? ' · with image' : ''}
        </span>
        <div className="flex gap-2.5">
          <button
            type="button"
            autoFocus
            disabled={busy}
            onClick={() => onDecide(false)}
            className="h-12 rounded-[10px] border border-line-strong bg-card px-5.5 text-[15px] hover:bg-card-soft disabled:opacity-50"
          >
            Not now
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onDecide(true)}
            className="flex h-12 items-center gap-2 rounded-[10px] bg-inverse px-6 text-[15px] font-semibold text-on-inverse hover:opacity-90 disabled:opacity-50"
          >
            {busy && <span className="size-3.5 animate-spin rounded-full border-2 border-on-inverse border-t-transparent" aria-hidden="true" />}
            {busy ? 'Publishing…' : 'Publish now'}
          </button>
        </div>
      </div>
    </dialog>
  )
}
