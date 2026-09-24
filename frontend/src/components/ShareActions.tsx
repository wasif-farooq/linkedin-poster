import { useState } from 'react'
import type { ThreadSnapshot } from '../api/types'
import { articleUrlFor, composeUrl, shareText } from '../lib/share'
import { Icon } from './Icon'

interface ShareActionsProps {
  thread: ThreadSnapshot
  onShared: (articleUrl: string | null) => void
}

/**
 * Publishing without connecting LinkedIn: a real link that opens LinkedIn's composer with
 * the post filled in. The person presses Post there — the app itself never posts.
 */
export function ShareActions({ thread, onShared }: ShareActionsProps) {
  const article = articleUrlFor(thread)
  const [includeLink, setIncludeLink] = useState(article !== null)
  const [copied, setCopied] = useState(false)
  const post = thread.final_post ?? thread.draft?.full_text ?? ''
  const articleUrl = includeLink ? article : null
  const text = shareText(post, articleUrl)
  const shared = thread.status === 'shared'

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      <span className="flex items-center gap-2 text-[13px] font-medium text-success">
        <Icon name="check" size={16} strokeWidth={2} />
        {shared ? 'Shared — opened on LinkedIn' : 'Approved by you'}
      </span>

      {article && (
        <label className="flex cursor-pointer items-start gap-2 text-[13px] text-ink-2">
          <input
            type="checkbox"
            checked={includeLink}
            onChange={(e) => setIncludeLink(e.target.checked)}
            className="mt-0.5 size-4 shrink-0 accent-accent"
          />
          <span>
            Include the source article link{' '}
            <span className="text-ink-3">(LinkedIn shows a preview card for it)</span>
          </span>
        </label>
      )}

      <div className="flex gap-2">
        <a
          href={composeUrl(text)}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => onShared(articleUrl)}
          className="flex h-12 grow items-center justify-center gap-2 rounded-[10px] bg-accent text-[15px] font-semibold text-white no-underline hover:bg-accent-dark"
        >
          <Icon name="send" size={16} strokeWidth={2} />
          {shared ? 'Share again' : 'Share on LinkedIn'}
        </a>
        <button
          type="button"
          onClick={() => void copy()}
          className="h-12 rounded-[10px] border border-line-strong bg-card px-4 text-sm text-ink hover:bg-card-soft"
        >
          {copied ? 'Copied' : 'Copy text'}
        </button>
      </div>
      <p className="m-0 text-xs text-ink-3">
        Opens LinkedIn with this post filled in — review it there and press Post. If the text doesn’t appear, use Copy
        text and paste it.
      </p>
    </div>
  )
}
