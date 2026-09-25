// Pure helpers for rendering posts and agent activity (unit-tested in post.test.ts).

/** LinkedIn shows roughly this much (or 3 lines) before "…see more". */
export const FOLD_CHARS = 210
export const FOLD_LINES = 3

/** Split a post into what shows before "…see more" and the rest. */
export function foldPost(text: string): [before: string, after: string] {
  const lines = text.split('\n')
  let before = ''
  let visibleLines = 0
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const candidate = before ? `${before}\n${line}` : line
    if (line.trim()) visibleLines++
    if (candidate.length > FOLD_CHARS || visibleLines > FOLD_LINES) {
      if (!before) {
        // A single long first line: cut at a word boundary.
        const cut = line.slice(0, FOLD_CHARS)
        const at = cut.lastIndexOf(' ') > 0 ? cut.lastIndexOf(' ') : FOLD_CHARS
        return [line.slice(0, at), text.slice(at).trimStart()]
      }
      return [before.replace(/\n+$/, ''), lines.slice(i).join('\n').replace(/^\n+/, '')]
    }
    before = candidate
  }
  return [text, '']
}

export type AgentKey =
  | 'topic_scout'
  | 'topic_pick'
  | 'researcher'
  | 'writer'
  | 'critic'
  | 'illustrator'
  | 'human_review'
  | 'publisher'

export const AGENT_LABELS: Record<AgentKey, string> = {
  topic_scout: 'Topic Scout',
  topic_pick: 'Your pick',
  researcher: 'Researcher',
  writer: 'Writer',
  critic: 'Critic',
  illustrator: 'Illustrator',
  human_review: 'Your review',
  publisher: 'Publisher',
}

export function isAgent(name: string | undefined): name is AgentKey {
  return !!name && name in AGENT_LABELS
}

export interface ActivityItem {
  agent: AgentKey | null // null = a note such as "auto-revision 1/2 queued"
  label: string
  detail: string
  failed: boolean
}

/** Turn backend activity lines ("writer: wrote the draft (~1785 chars)") into display items. */
export function parseActivity(lines: string[]): ActivityItem[] {
  return lines.map((line) => {
    const colon = line.indexOf(':')
    const name = colon > 0 ? line.slice(0, colon) : ''
    if (isAgent(name)) {
      const detail = line.slice(colon + 1).trim()
      return {
        agent: name,
        label: AGENT_LABELS[name],
        detail: capitalize(detail),
        failed: detail === 'FAILED',
      }
    }
    return { agent: null, label: '', detail: capitalize(line), failed: false }
  })
}

function capitalize(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}

export function formatTokens(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}
