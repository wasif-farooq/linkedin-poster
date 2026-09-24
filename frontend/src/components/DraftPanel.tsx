import { useState } from 'react'
import { Link } from 'react-router'
import type { ResearchBrief, ThreadSnapshot } from '../api/types'
import { Icon } from './Icon'
import { PostPreview } from './PostPreview'
import { ScoreBars, VerdictPill } from './Scores'
import { ShareActions } from './ShareActions'

type Tab = 'draft' | 'research' | 'sources'

interface DraftPanelProps {
  thread: ThreadSnapshot
  author: string
  running: boolean
  publishMode: 'share' | 'api'
  onPublish: () => void
  onShared: (articleUrl: string | null) => void
  onRequestReview: () => void
  onOpenPublishConfirm: () => void
}

export function DraftPanel({
  thread,
  author,
  running,
  publishMode,
  onPublish,
  onShared,
  onRequestReview,
  onOpenPublishConfirm,
}: DraftPanelProps) {
  const [tab, setTab] = useState<Tab>('draft')
  const brief = thread.research_brief
  const tabs: { id: Tab; label: string }[] = [
    { id: 'draft', label: 'Draft' },
    { id: 'research', label: 'Research' },
    { id: 'sources', label: brief ? `Sources (${brief.sources.length})` : 'Sources' },
  ]

  return (
    <aside
      aria-label="Current draft"
      className="flex w-113 shrink-0 flex-col border-l border-line bg-card-soft"
    >
      <div role="tablist" aria-label="Draft panel" className="flex h-16 shrink-0 items-end gap-1 border-b border-line px-5">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`h-11 border-b-2 px-3.5 text-sm ${
              tab === t.id ? 'border-accent font-semibold text-ink' : 'border-transparent text-ink-2 hover:text-ink'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`panel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="flex min-h-0 grow flex-col gap-4 overflow-y-auto p-5"
      >
        {tab === 'draft' && <DraftTab thread={thread} author={author} />}
        {tab === 'research' && <ResearchTab brief={brief} />}
        {tab === 'sources' && <SourcesTab brief={brief} />}
      </div>

      {thread.draft && (
        <DraftActions
          thread={thread}
          running={running}
          publishMode={publishMode}
          onPublish={onPublish}
          onShared={onShared}
          onRequestReview={onRequestReview}
          onOpenPublishConfirm={onOpenPublishConfirm}
        />
      )}
    </aside>
  )
}

function DraftTab({ thread, author }: { thread: ThreadSnapshot; author: string }) {
  const { draft, critique } = thread
  if (!draft) {
    return (
      <p className="text-sm text-ink-3">
        No draft yet. Ask the Manager for a post and it will appear here.
      </p>
    )
  }
  return (
    <>
      <PostPreview
        text={draft.full_text}
        author={author}
        subtitle={`${thread.approved ? 'Approved' : 'Draft preview'} · ${draft.chars.toLocaleString()} characters`}
      />
      {critique && (
        <section className="flex flex-col gap-2.5 rounded-xl border border-line bg-card px-4.5 py-4">
          <div className="flex items-center justify-between">
            <h3 className="eyebrow">Critic</h3>
            <VerdictPill verdict={critique.verdict} />
          </div>
          <ScoreBars scores={critique.scores} />
        </section>
      )}
    </>
  )
}

function DraftActions({
  thread,
  running,
  publishMode,
  onPublish,
  onShared,
  onRequestReview,
  onOpenPublishConfirm,
}: Omit<DraftPanelProps, 'author'>) {
  const primary =
    'flex h-12 items-center justify-center gap-2 rounded-[10px] bg-accent text-[15px] font-semibold text-white no-underline hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-50'
  const status = thread.status
  const result = thread.publish_result

  return (
    <div className="flex flex-col gap-2.5 border-t border-line px-5 pt-4 pb-5">
      {status === 'needs_review' && (
        <>
          <StatusLine tone="review" icon="clock" text="Waiting for your review" />
          <Link to={`/chat/${thread.id}/review`} className={primary}>
            Review draft
          </Link>
        </>
      )}
      {status === 'confirm_publish' && (
        <>
          <StatusLine tone="review" icon="clock" text="Waiting for your publish confirmation" />
          <button type="button" className={primary} onClick={onOpenPublishConfirm}>
            Confirm publishing
          </button>
        </>
      )}
      {publishMode === 'share' && (status === 'approved' || status === 'shared') && (
        <ShareActions thread={thread} onShared={onShared} />
      )}
      {publishMode === 'api' && status === 'approved' && (
        <>
          <StatusLine
            tone="success"
            icon="check"
            text={result?.status === 'dry_run' ? 'Approved · dry run recorded' : 'Approved by you'}
          />
          <button type="button" className={primary} disabled={running} onClick={onPublish}>
            <Icon name="send" size={16} strokeWidth={2} />
            Publish to LinkedIn
          </button>
        </>
      )}
      {status === 'published' && (
        <StatusLine
          tone="success"
          icon="check"
          text="Published to LinkedIn"
          href={result?.url ?? undefined}
        />
      )}
      {status === 'draft' && (
        <>
          <StatusLine tone="neutral" icon="pen" text="Not approved yet" />
          <button type="button" className={primary} disabled={running} onClick={onRequestReview}>
            Review &amp; approve
          </button>
        </>
      )}
    </div>
  )
}

function StatusLine({
  tone,
  icon,
  text,
  href,
}: {
  tone: 'review' | 'success' | 'neutral'
  icon: 'clock' | 'check' | 'pen'
  text: string
  href?: string
}) {
  const color = { review: 'text-review', success: 'text-success', neutral: 'text-ink-2' }[tone]
  return (
    <span className={`flex items-center gap-2 text-[13px] font-medium ${color}`}>
      <Icon name={icon} size={16} strokeWidth={2} />
      {text}
      {href && (
        <a href={href} target="_blank" rel="noreferrer" className="ml-auto font-medium">
          View post
        </a>
      )}
    </span>
  )
}

function ResearchTab({ brief }: { brief: ResearchBrief | null }) {
  if (!brief) return <p className="text-sm text-ink-3">No research yet.</p>
  return (
    <>
      <section className="flex flex-col gap-2">
        <h3 className="eyebrow">Summary</h3>
        <p className="m-0 text-sm leading-relaxed">{brief.summary}</p>
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="eyebrow">Key points</h3>
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {brief.key_points.map((kp, i) => (
            <li key={i} className="flex gap-2 rounded-[10px] border border-line bg-card px-3 py-2.5 text-[13px] leading-snug">
              <span className="grow">{kp.point}</span>
              <Cites ids={kp.source_ids} />
            </li>
          ))}
        </ul>
      </section>
      {brief.counterpoints.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="eyebrow">Counterpoints</h3>
          {brief.counterpoints.map((c, i) => (
            <p key={i} className="m-0 rounded-[10px] bg-review-soft px-3 py-2.5 text-[13px] leading-snug text-body">
              {c.point}
            </p>
          ))}
        </section>
      )}
    </>
  )
}

function SourcesTab({ brief }: { brief: ResearchBrief | null }) {
  if (!brief) return <p className="text-sm text-ink-3">No sources yet.</p>
  return (
    <ol className="m-0 flex list-none flex-col gap-2 p-0">
      {brief.sources.map((s) => (
        <li key={s.id} className="flex gap-3 rounded-[10px] border border-line bg-card px-3.5 py-3">
          <span className="w-4 shrink-0 font-mono text-xs text-accent-ink">{s.id}</span>
          <span className="flex min-w-0 flex-col gap-1">
            <a href={s.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-ink no-underline hover:underline">
              {s.title}
            </a>
            <span className="flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
              {hostname(s.url)}
              <span
                className={`rounded-full px-2 text-[11px] ${
                  s.origin === 'scout' ? 'bg-success-soft text-success' : 'bg-paper-2 text-ink-2'
                }`}
              >
                {s.origin === 'scout' ? 'from scout' : 'search'} · {s.full_text ? 'full text' : 'snippet'}
              </span>
            </span>
          </span>
        </li>
      ))}
    </ol>
  )
}

export function Cites({ ids }: { ids: number[] }) {
  if (!ids.length) return null
  return (
    <span className="flex shrink-0 gap-1" aria-label={`Sources ${ids.join(', ')}`}>
      {ids.map((id) => (
        <span key={id} className="rounded-md bg-accent-soft px-1.5 py-0.5 font-mono text-[11px] text-accent-ink">
          {id}
        </span>
      ))}
    </span>
  )
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}
