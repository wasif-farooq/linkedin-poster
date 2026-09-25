import type { PostImage } from '../api/types'
import { foldPost } from '../lib/post'

interface PostPreviewProps {
  text: string
  author: string
  subtitle: string
  size?: 'md' | 'lg'
  image?: PostImage | null
}

/** A post as readers will see it, with the "…see more" fold marked and its image below. */
export function PostPreview({ text, author, subtitle, size = 'md', image }: PostPreviewProps) {
  const [before, after] = foldPost(text)
  const large = size === 'lg'
  const body = large ? 'text-[15px] leading-relaxed' : 'text-sm leading-[1.55]'
  const initials = author
    .split(/\s+/)
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <article
      className={`flex flex-col gap-3 rounded-xl border border-line bg-card ${
        large ? 'gap-3.5 rounded-[14px] px-5 py-5 sm:px-8 sm:py-7' : 'p-4 sm:p-4.5'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span
          className={`flex shrink-0 items-center justify-center rounded-full bg-avatar font-semibold ${
            large ? 'size-12' : 'size-10 text-sm'
          }`}
          aria-hidden="true"
        >
          {initials || 'ME'}
        </span>
        <span className="flex flex-col">
          <span className={`font-semibold ${large ? 'text-[15px]' : 'text-sm'}`}>{author}</span>
          <span className="text-xs text-ink-3">{subtitle}</span>
        </span>
      </div>
      <p className={`m-0 whitespace-pre-line ${body}`}>{before}</p>
      {after && (
        <>
          <div className="flex items-center gap-2" aria-hidden="true">
            <span className="h-px grow border-t border-dashed border-line-strong" />
            <span className="text-[11px] text-ink-3">
              {large ? 'readers see this much before “…see more”' : '“…see more” fold'}
            </span>
            <span className="h-px grow border-t border-dashed border-line-strong" />
          </div>
          <p className={`m-0 whitespace-pre-line text-body ${body}`}>{after}</p>
        </>
      )}
      {image && (
        <img
          src={image.url}
          alt={image.alt_text}
          className={`block aspect-[1.91] w-full rounded-lg border border-line bg-paper-2 object-cover ${large ? 'mt-1' : ''}`}
        />
      )}
    </article>
  )
}
