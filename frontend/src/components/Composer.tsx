import { useState, type FormEvent, type KeyboardEvent } from 'react'
import { Icon } from './Icon'

interface ComposerProps {
  running: boolean
  onSend: (text: string) => void
  onStop?: () => void
  suggestions?: string[]
  placeholder?: string
  autoFocus?: boolean
}

export function Composer({
  running,
  onSend,
  onStop,
  suggestions = [],
  placeholder = 'Ask the Manager… e.g. “write about LangGraph 1.0”',
  autoFocus,
}: ComposerProps) {
  const [text, setText] = useState('')

  function submit(e?: FormEvent) {
    e?.preventDefault()
    const value = text.trim()
    if (!value || running) return
    onSend(value)
    setText('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={running}
              onClick={() => onSend(s)}
              className="h-8 rounded-full border border-line-strong bg-card px-3.5 text-[13px] text-ink hover:bg-card-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <form
        onSubmit={submit}
        className="flex items-end gap-2.5 rounded-[14px] border border-line-strong bg-card py-2.5 pr-2.5 pl-4 focus-within:border-accent"
      >
        <label htmlFor="composer" className="sr-only">
          Message the Manager
        </label>
        <textarea
          id="composer"
          rows={2}
          value={text}
          autoFocus={autoFocus}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          maxLength={4000}
          className="grow resize-none border-0 bg-transparent text-sm leading-normal text-ink outline-none placeholder:text-ink-3"
        />
        {running && onStop ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop"
            className="flex size-11 items-center justify-center rounded-[10px] border border-line-strong bg-card text-ink hover:bg-card-soft"
          >
            <span className="size-3.5 rounded-sm bg-ink" aria-hidden="true" />
          </button>
        ) : (
          <button
            type="submit"
            aria-label="Send"
            disabled={running || !text.trim()}
            className="flex size-11 items-center justify-center rounded-[10px] bg-accent text-white hover:bg-accent-dark disabled:opacity-40"
          >
            <Icon name="arrowRight" strokeWidth={2} />
          </button>
        )}
      </form>
    </div>
  )
}
