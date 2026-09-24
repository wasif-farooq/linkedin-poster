import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { AGENT_LABELS, isAgent, parseActivity } from '../lib/post'
import { Icon } from './Icon'

interface RunCardProps {
  lines: string[]
  plan?: string[]
  current?: string | null // agent working now, or "manager"
  running: boolean
  startedAt?: number
  waitingFor?: 'topic' | 'review' | 'publish' | null
  reviewHref?: string
}

/** The Manager's plan as a live checklist (design: "Manager's plan" card). */
export function RunCard({
  lines,
  plan = [],
  current,
  running,
  startedAt,
  waitingFor,
  reviewHref,
}: RunCardProps) {
  const items = parseActivity(lines)
  const elapsed = useElapsed(running ? startedAt : undefined)
  const agentsDone = new Set(items.filter((i) => i.agent).map((i) => i.agent)).size

  return (
    <section
      aria-label="Agent progress"
      aria-live="polite"
      className="flex max-w-160 flex-col gap-3.5 rounded-[14px] border border-line bg-card px-5 py-4.5"
    >
      <div className="flex items-center justify-between gap-4">
        <h2 className="eyebrow">Manager’s plan</h2>
        <span className="font-mono text-[11px] text-ink-3">
          {agentsDone} {agentsDone === 1 ? 'agent' : 'agents'}
          {elapsed !== null && ` · ${formatElapsed(elapsed)}`}
        </span>
      </div>

      {plan.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-xs text-ink-2">
          {plan.map((step, i) => (
            <span key={`${step}-${i}`} className="flex items-center gap-1.5">
              {i > 0 && <span aria-hidden="true">→</span>}
              <span className="rounded-full bg-paper-2 px-2 py-0.5">
                {isAgent(step) ? AGENT_LABELS[step] : step}
              </span>
            </span>
          ))}
        </p>
      )}

      <ol className="flex flex-col gap-3">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-3">
            {item.agent ? (
              <Badge tone={item.failed ? 'fail' : 'done'} />
            ) : (
              <span className="flex size-6 shrink-0 items-center justify-center" aria-hidden="true">
                <span className="size-1.5 rounded-full bg-ink-3" />
              </span>
            )}
            <span className="flex flex-col gap-0.5">
              {item.label && <span className="text-sm font-medium">{item.label}</span>}
              <span className={`text-[13px] ${item.failed ? 'text-danger' : 'text-ink-2'}`}>
                {item.failed ? 'Failed — the Manager will explain' : item.detail}
              </span>
            </span>
          </li>
        ))}

        {running && current && (
          <li className="flex items-start gap-3">
            <Badge tone="working" />
            <span className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">
                {current === 'manager' ? 'Manager' : isAgent(current) ? AGENT_LABELS[current] : current}
              </span>
              <span className="text-[13px] text-ink-2">
                {current === 'manager' ? 'Thinking…' : 'Working…'}
              </span>
            </span>
          </li>
        )}

        {!running && waitingFor && (
          <li className="flex items-start gap-3">
            <Badge tone="waiting" />
            <span className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">
                {{ topic: 'Your pick', review: 'Your review', publish: 'Publish confirmation' }[waitingFor]}
              </span>
              {waitingFor === 'review' && reviewHref ? (
                <Link to={reviewHref} className="text-[13px] font-medium text-review">
                  Waiting for you — review the draft
                </Link>
              ) : (
                <span className="text-[13px] text-review">
                  {waitingFor === 'topic' ? 'Waiting for you — choose a topic below' : 'Waiting for you'}
                </span>
              )}
            </span>
          </li>
        )}
      </ol>
    </section>
  )
}

function Badge({ tone }: { tone: 'done' | 'fail' | 'working' | 'waiting' }) {
  const styles = {
    done: 'bg-success-soft text-success',
    fail: 'bg-danger-soft text-danger',
    working: 'bg-accent-soft text-accent-ink',
    waiting: 'bg-review-soft text-review',
  }[tone]
  return (
    <span
      className={`flex size-6 shrink-0 items-center justify-center rounded-full ${styles}`}
      aria-hidden="true"
    >
      {tone === 'done' && <Icon name="check" size={14} strokeWidth={2.4} />}
      {tone === 'fail' && <Icon name="x" size={14} strokeWidth={2.4} />}
      {tone === 'waiting' && <Icon name="clock" size={14} strokeWidth={2.2} />}
      {tone === 'working' && (
        <span className="size-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      )}
    </span>
  )
}

function useElapsed(since: number | undefined): number | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (since === undefined) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [since])
  return since === undefined ? null : Math.max(0, Math.round((now - since) / 1000))
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
  return m ? `${m}m ${String(seconds % 60).padStart(2, '0')}s` : `${seconds}s`
}
