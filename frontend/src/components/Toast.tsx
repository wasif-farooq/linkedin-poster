import { useEffect } from 'react'
import { Icon } from './Icon'

interface ToastProps {
  title: string
  body?: string
  href?: string
  linkText?: string
  onClose: () => void
  timeoutMs?: number
}

export function Toast({ title, body, href, linkText = 'View post', onClose, timeoutMs = 10_000 }: ToastProps) {
  useEffect(() => {
    const id = window.setTimeout(onClose, timeoutMs)
    return () => window.clearTimeout(id)
  }, [onClose, timeoutMs])

  return (
    <div
      role="status"
      className="fixed inset-x-4 bottom-4 z-50 flex sm:inset-x-auto sm:right-8 sm:bottom-8 sm:w-95 items-start gap-3 rounded-[14px] bg-inverse px-4.5 py-4 text-on-inverse shadow-[0_16px_40px_rgba(26,25,22,0.3)]"
    >
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-success" aria-hidden="true">
        <Icon name="check" size={16} strokeWidth={2.6} className="text-card" />
      </span>
      <span className="flex grow flex-col gap-1">
        <span className="text-[15px] font-semibold">{title}</span>
        {(body || href) && (
          <span className="text-[13px] text-on-inverse-2">
            {body}{' '}
            {href && (
              <a href={href} target="_blank" rel="noreferrer" className="text-inverse-link">
                {linkText}
              </a>
            )}
          </span>
        )}
      </span>
      <button type="button" aria-label="Dismiss" onClick={onClose} className="text-on-inverse-2 hover:text-on-inverse">
        <Icon name="x" size={16} />
      </button>
    </div>
  )
}
