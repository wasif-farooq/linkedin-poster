import { useState } from 'react'
import { api } from '../api/client'
import type { ThreadSnapshot } from '../api/types'
import { Icon } from './Icon'

interface ImageCardProps {
  thread: ThreadSnapshot
  running: boolean
  onUpdated: (thread: ThreadSnapshot) => void
}

/** Make, remake or drop the image that goes with the post (on request only). */
export function ImageCard({ thread, running, onUpdated }: ImageCardProps) {
  const [direction, setDirection] = useState('')
  const [busy, setBusy] = useState<'generate' | 'remove' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const image = thread.image
  const blocked = thread.pending !== null
  const disabled = running || busy !== null || blocked

  async function act(kind: 'generate' | 'remove') {
    setBusy(kind)
    setError(null)
    try {
      onUpdated(kind === 'generate' ? await api.generateImage(thread.id, direction.trim()) : await api.removeImage(thread.id))
      if (kind === 'generate') setDirection('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(null)
    }
  }

  const button =
    'flex h-9 items-center gap-1.5 rounded-lg border border-line-strong bg-card px-3 text-[13px] text-ink no-underline hover:bg-card-soft disabled:cursor-not-allowed disabled:opacity-50'

  return (
    <section aria-label="Post image" className="flex flex-col gap-2.5 rounded-xl border border-line bg-card px-4.5 py-4">
      <div className="flex items-center justify-between">
        <h3 className="eyebrow">Image</h3>
        {image && <span className="text-[11px] text-ink-3">{image.provider}</span>}
      </div>
      {!image && <p className="m-0 text-[13px] text-ink-2">Text-only for now. Posts with an image tend to stand out more in the feed.</p>}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (!disabled) void act('generate')
        }}
      >
        <input
          type="text"
          value={direction}
          onChange={(e) => setDirection(e.target.value)}
          maxLength={500}
          placeholder="Style (optional): photo, isometric, dark…"
          aria-label="Image style"
          disabled={disabled}
          className="h-9 min-w-0 grow rounded-lg border border-line-strong bg-card-soft px-3 text-[13px] text-ink placeholder:text-ink-3 disabled:opacity-50"
        />
        <button type="submit" disabled={disabled} className={`${button} shrink-0 border-accent bg-accent font-semibold text-white hover:bg-accent-dark`}>
          {busy === 'generate' ? (
            <span className="size-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden="true" />
          ) : (
            <Icon name="image" size={15} strokeWidth={2} />
          )}
          {image ? 'New image' : 'Generate'}
        </button>
      </form>

      {image && (
        <div className="flex gap-2">
          <a href={image.url} download={`linkedin-post-image.${image.file.split('.').pop()}`} className={button}>
            <Icon name="download" size={15} strokeWidth={2} />
            Download
          </a>
          <button type="button" disabled={disabled} onClick={() => void act('remove')} className={button}>
            <Icon name="x" size={15} strokeWidth={2} />
            Remove
          </button>
        </div>
      )}

      {busy === 'generate' && (
        <p role="status" className="m-0 text-xs text-ink-3">
          Making the image. This can take up to a minute.
        </p>
      )}
      {blocked && !running && <p className="m-0 text-xs text-ink-3">Answer the pending question first.</p>}
      {error && (
        <p role="alert" className="m-0 text-xs text-danger">
          {error}
        </p>
      )}
    </section>
  )
}
