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
      className="fixed right-8 bottom-8 z-50 flex w-95 items-start gap-3 rounded-[14px] bg-ink px-4.5 py-4 text-card-soft shadow-[0_16px_40px_rgba(26,25,22,0.3)]"
    >
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-success" aria-hidden="true">
        <Icon name="check" size={16} strokeWidth={2.6} className="text-white" />
      </span>
      <span className="flex grow flex-col gap-1">
        <span className="text-[15px] font-semibold">{title}</span>
        {(body || href) && (
          <span className="text-[13px] text-[#d9d4c8]">
            {body}{' '}
            {href && (
              <a href={href} target="_blank" rel="noreferrer" className="text-[#9fd9d2]">
                {linkText}
              </a>
            )}
          </span>
        )}
      </span>
      <button type="button" aria-label="Dismiss" onClick={onClose} className="text-[#d9d4c8] hover:text-white">
        <Icon name="x" size={16} />
      </button>
    </div>
  )
}
