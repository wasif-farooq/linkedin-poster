import { useState, type FormEvent } from 'react'
import type { TopicChoicePayload, TopicPickAnswer } from '../api/types'
import { Icon } from './Icon'

interface TopicPickerProps {
  payload: TopicChoicePayload
  busy: boolean
  onAnswer: (answer: TopicPickAnswer) => void
}

/** The Topic Scout's shortlist: pick one, ask for different ones, or write your own. */
export function TopicPicker({ payload, busy, onAnswer }: TopicPickerProps) {
  const [hint, setHint] = useState('')
  const [own, setOwn] = useState('')

  function submitOwn(e: FormEvent) {
    e.preventDefault()
    if (own.trim()) onAnswer({ topic: own.trim() })
  }

  return (
    <section
      aria-labelledby="topic-picker-h"
      className="flex max-w-180 flex-col gap-4 rounded-[14px] border border-review/40 bg-card px-5 py-4.5"
    >
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="topic-picker-h" className="m-0 font-display text-2xl font-normal">
          Pick a topic
        </h2>
        <span className="font-mono text-[11px] text-ink-3">
          {payload.options.length} options{payload.round > 1 && ` · round ${payload.round}`}
        </span>
      </div>

      <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
        {payload.options.map((o) => (
          <li
            key={o.id}
            className="flex flex-col gap-2 rounded-xl border border-line bg-card-soft px-4 py-3.5"
          >
            <div className="flex items-start gap-3">
              <span className="mt-0.5 font-mono text-xs text-ink-3" aria-hidden="true">
                {o.id + 1}
              </span>
              <div className="flex min-w-0 grow flex-col gap-1">
                <h3 className="m-0 text-[15px] leading-snug font-semibold">{o.topic}</h3>
                <p className="m-0 text-[13px] leading-normal text-body">{o.angle}</p>
                {o.why_now && (
                  <p className="m-0 text-xs leading-normal text-ink-2">
                    <span className="font-medium">Why now:</span> {o.why_now}
                  </p>
                )}
                {o.sources.length > 0 && (
                  <p className="m-0 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                    {o.sources.slice(0, 3).map((s) => (
                      <a
                        key={s.url}
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                        className="max-w-72 truncate text-accent-ink"
                      >
                        {s.title}
                      </a>
                    ))}
                  </p>
                )}
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => onAnswer({ choice: o.id })}
                aria-label={`Use topic ${o.id + 1}: ${o.topic}`}
                className="h-10 shrink-0 rounded-[10px] bg-accent px-3.5 text-sm font-semibold text-white hover:bg-accent-dark disabled:opacity-50"
              >
                Use this
              </button>
            </div>
          </li>
        ))}
      </ol>

      <div className="flex flex-col gap-2 border-t border-line pt-3.5">
        <label htmlFor="more-hint" className="text-[13px] font-medium">
          Not feeling these?
        </label>
        <div className="flex gap-2">
          <input
            id="more-hint"
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="Optional direction, e.g. “something about open source”"
            className="h-10 grow rounded-[10px] border border-line-strong bg-card px-3 text-sm text-ink placeholder:text-ink-3"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => onAnswer({ more: true, hint: hint.trim() || null })}
            className="flex h-10 items-center gap-1.5 rounded-[10px] border border-line-strong bg-card px-3.5 text-sm text-ink hover:bg-card-soft disabled:opacity-50"
          >
            <Icon name="history" size={16} />
            Show different topics
          </button>
        </div>
        <form onSubmit={submitOwn} className="flex gap-2">
          <label htmlFor="own-topic" className="sr-only">
            Your own topic
          </label>
          <input
            id="own-topic"
            value={own}
            onChange={(e) => setOwn(e.target.value)}
            placeholder="Or write your own topic…"
            maxLength={300}
            className="h-10 grow rounded-[10px] border border-line-strong bg-card px-3 text-sm text-ink placeholder:text-ink-3"
          />
          <button
            type="submit"
            disabled={busy || !own.trim()}
            className="h-10 rounded-[10px] border border-line-strong bg-card px-3.5 text-sm text-ink hover:bg-card-soft disabled:opacity-50"
          >
            Use my topic
          </button>
        </form>
      </div>
    </section>
  )
}
