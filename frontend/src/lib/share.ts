// "Share on LinkedIn" links — mirrors app/tools/linkedin/share.py (keep the two in sync).
import type { ThreadSnapshot } from '../api/types'

/** The post, with the source article on its own line before the hashtags (link preview card). */
export function shareText(post: string, articleUrl?: string | null): string {
  const text = post.trim()
  if (!articleUrl) return text
  const lines = text.split('\n')
  const last = lines[lines.length - 1]?.trim() ?? ''
  if (last && last.split(/\s+/).every((w) => w.startsWith('#'))) {
    const body = lines.slice(0, -1).join('\n').trimEnd()
    return `${body}\n\n${articleUrl}\n\n${last}`
  }
  return `${text}\n\n${articleUrl}`
}

/** LinkedIn's composer, pre-filled. The person presses Post on LinkedIn. */
export function composeUrl(text: string): string {
  return `https://www.linkedin.com/feed/?shareActive=true&text=${encodeURIComponent(text)}`
}

/** The article to attach: the Scout's pick first, then the research brief's first source. */
export function articleUrlFor(thread: ThreadSnapshot): string | null {
  return thread.topic?.source_urls?.[0] ?? thread.research_brief?.sources[0]?.url ?? null
}
