import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import type { ReviewAnswer, ReviewPayload } from '../api/types'
import { Icon } from '../components/Icon'
import { PostPreview } from '../components/PostPreview'
import { RunCard } from '../components/RunCard'
import { ScoreTiles, VerdictPill } from '../components/Scores'
import { useDryRun } from '../hooks/useLocalStorage'
import { useResource } from '../hooks/useResource'
import { useThreadRun } from '../hooks/useThreadRun'

const MAX_CHARS = 3000

type Mode = 'view' | 'edit' | 'revise'

export function ReviewPage() {
  const { threadId = '' } = useParams()
  return <Review key={threadId} threadId={threadId} />
}

function Review({ threadId }: { threadId: string }) {
  const run = useThreadRun(threadId)
  const settings = useResource(api.settings)
  const linkedin = useResource(api.linkedin)
  const [dryRun] = useDryRun()
  const navigate = useNavigate()
  // Mode belongs to the draft it was chosen for: a new draft (after a revision) starts in view.
  const [modeFor, setModeFor] = useState<{ post: string | undefined; mode: Mode }>({ post: undefined, mode: 'view' })
  const [editText, setEditText] = useState('')
  const [feedback, setFeedback] = useState('')
  const { thread } = run
  const review = thread?.pending?.type === 'review' ? (thread.pending as ReviewPayload) : null

  // Once nothing is waiting for review (approved, rejected, or now a publish confirmation), go back.
  useEffect(() => {
    if (thread && !review && !run.running) navigate(`/chat/${threadId}`, { replace: true })
  }, [thread, review, run.running, navigate, threadId])

  const post = review?.post
  const mode: Mode = modeFor.post === post ? modeFor.mode : 'view'
  const setMode = (next: Mode) => setModeFor({ post, mode: next })

  if (run.loadError) {
    return <p className="p-8 text-danger">Couldn’t load this conversation: {run.loadError.message}</p>
  }
  if (!thread || !review) return <p className="p-8 text-ink-3">Loading…</p>

  const critique = thread.critique
  const author = linkedin.data?.connected ? (linkedin.data.name ?? 'You') : 'You'
  const decide = (answer: ReviewAnswer) => void run.resume(answer, dryRun)
  const editChars = editText.length
  const busy = run.running

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-line bg-card-soft px-8">
        <div className="flex items-center gap-4">
          <Link
            to={`/chat/${threadId}`}
            aria-label="Back to chat"
            className="flex size-10 items-center justify-center rounded-[10px] border border-line-strong bg-card text-ink"
          >
            <Icon name="arrowLeft" strokeWidth={2} />
          </Link>
          <h1 className="m-0 font-display text-[28px] font-normal">Review draft</h1>
          <span className="rounded-full bg-review-soft px-2.5 py-1 text-xs font-semibold text-review">
            Needs your decision
          </span>
        </div>
        <span className="font-mono text-xs text-ink-3">
          thread {threadId}
          {thread.revision_count > 0 && ` · revision ${thread.revision_count}`}
        </span>
      </header>

      <div className="flex min-h-0 grow gap-8 px-8 py-7">
        <section aria-label="Post" className="flex min-w-0 grow flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <h2 className="eyebrow">{mode === 'edit' ? 'Edit the post' : 'Post as it will appear'}</h2>
            <span className={`font-mono text-xs ${(mode === 'edit' ? editChars : review.chars) > MAX_CHARS ? 'text-danger' : 'text-ink-2'}`}>
              {(mode === 'edit' ? editChars : review.chars).toLocaleString()} / {MAX_CHARS.toLocaleString()} characters
            </span>
          </div>
          {mode === 'edit' ? (
            <>
              <label htmlFor="edit-post" className="sr-only">
                Post text
              </label>
              <textarea
                id="edit-post"
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                className="min-h-0 grow resize-none rounded-[14px] border border-accent bg-card px-8 py-7 text-[15px] leading-relaxed text-ink outline-none"
              />
              <p className="m-0 text-xs text-ink-2">
                Keep hashtags on the last line. Plain text only — LinkedIn doesn’t render markdown. Your version is approved as
                soon as you save it.
              </p>
            </>
          ) : (
            <div className="min-h-0 grow overflow-y-auto">
              <PostPreview text={review.post} author={author} subtitle="Public post" size="lg" />
            </div>
          )}
        </section>

        <aside aria-label="Critic findings" className="flex w-105 shrink-0 flex-col gap-4 overflow-y-auto">
          {run.live && (
            <RunCard lines={run.live.lines} current={run.live.current} running startedAt={run.live.startedAt} />
          )}
          {run.error && (
            <p role="alert" className="m-0 rounded-[10px] bg-danger-soft px-4 py-3 text-sm text-danger">
              {run.error}
            </p>
          )}

          {critique && (
            <section className="flex flex-col gap-3 rounded-[14px] border border-line bg-card px-5 py-4.5">
              <div className="flex items-center justify-between">
                <h2 className="eyebrow">Critic verdict</h2>
                <VerdictPill verdict={critique.verdict} bar={settings.data?.limits.critic_min_score} />
              </div>
              <ScoreTiles scores={critique.scores} />
              {critique.issues.length > 0 && (
                <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px] leading-normal text-body">
                  {critique.issues.slice(0, 3).map((issue, i) => (
                    <li key={i} className="rounded-lg border border-line bg-card-soft px-3 py-2.5">
                      {issue}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          <RuleChecks errors={review.rule_errors} warnings={critique?.rule_warnings ?? []} />

          {mode === 'revise' && (
            <section className="flex flex-col gap-2.5 rounded-[14px] border border-accent bg-card px-5 py-4">
              <label htmlFor="revise" className="text-sm font-semibold">
                What should the Writer change?
              </label>
              <textarea
                id="revise"
                rows={3}
                autoFocus
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="e.g. give the unknown biological function its own line in the hook"
                className="resize-none rounded-[10px] border border-line-strong px-3 py-2.5 text-sm leading-normal text-ink"
              />
              <span className="text-xs text-ink-2">
                The Writer revises, the Critic re-checks, and the draft comes back here.
              </span>
            </section>
          )}
        </aside>
      </div>

      <footer className="flex h-21 shrink-0 items-center justify-between border-t border-line bg-card-soft px-8">
        <div className="flex gap-2.5">
          {mode === 'view' && (
            <>
              <SecondaryButton
                disabled={busy}
                onClick={() => {
                  setEditText(review.post)
                  setMode('edit')
                }}
              >
                <Icon name="pen" size={16} strokeWidth={2} />
                Edit myself
              </SecondaryButton>
              <SecondaryButton disabled={busy} onClick={() => setMode('revise')}>
                Ask for a revision
              </SecondaryButton>
              <button
                type="button"
                disabled={busy}
                onClick={() => decide({ action: 'reject' })}
                className="h-12 rounded-[10px] border border-danger/30 bg-card px-5 text-[15px] text-danger hover:bg-danger-soft disabled:opacity-50"
              >
                Reject
              </button>
            </>
          )}
          {mode !== 'view' && (
            <SecondaryButton disabled={busy} onClick={() => setMode('view')}>
              Cancel
            </SecondaryButton>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          {mode === 'view' && (
            <>
              <Link to={`/chat/${threadId}`} className="flex h-12 items-center px-4 text-[15px] text-ink-2 no-underline">
                Decide later
              </Link>
              <PrimaryButton
                disabled={busy || !review.can_approve}
                title={review.can_approve ? undefined : 'Fix the rule errors first (edit or revise)'}
                onClick={() => decide({ action: 'approve' })}
              >
                <Icon name="check" strokeWidth={2.4} />
                Approve
              </PrimaryButton>
            </>
          )}
          {mode === 'edit' && (
            <PrimaryButton
              disabled={busy || !editText.trim() || editText.trim() === review.post.trim()}
              onClick={() => decide({ action: 'edit', text: editText })}
            >
              Save &amp; approve
            </PrimaryButton>
          )}
          {mode === 'revise' && (
            <PrimaryButton
              disabled={busy || !feedback.trim()}
              onClick={() => {
                decide({ action: 'revise', text: feedback.trim() })
                setFeedback('')
              }}
            >
              {busy ? 'Revising…' : 'Send revision'}
            </PrimaryButton>
          )}
        </div>
      </footer>
    </div>
  )
}

function RuleChecks({ errors, warnings }: { errors: string[]; warnings: string[] }) {
  return (
    <section className="flex flex-col gap-2.5 rounded-[14px] border border-line bg-card px-5 py-4.5">
      <h2 className="eyebrow">Rule checks</h2>
      <ul className="m-0 flex list-none flex-col gap-2 p-0 text-[13px]">
        {errors.map((e) => (
          <li key={e} className="flex items-start gap-2.5 text-danger">
            <Icon name="x" size={16} strokeWidth={2.4} className="mt-0.5 shrink-0" />
            {e}
          </li>
        ))}
        {warnings.map((w) => (
          <li key={w} className="flex items-start gap-2.5 text-review">
            <Icon name="alert" size={16} strokeWidth={2.2} className="mt-0.5 shrink-0" />
            {w}
          </li>
        ))}
        {errors.length === 0 && (
          <li className="flex items-center gap-2.5">
            <Icon name="check" size={16} strokeWidth={2.4} className="text-success" />
            Under 3,000 characters, no markdown{warnings.length === 0 && ', formatting looks good'}
          </li>
        )}
      </ul>
    </section>
  )
}

function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className="flex h-12 items-center gap-2 rounded-[10px] bg-accent px-7 text-[15px] font-semibold text-white hover:bg-accent-dark disabled:cursor-not-allowed disabled:opacity-50"
    />
  )
}

function SecondaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...props}
      className="flex h-12 items-center gap-2 rounded-[10px] border border-line-strong bg-card px-5 text-[15px] text-ink hover:bg-card-soft disabled:opacity-50"
    />
  )
}
