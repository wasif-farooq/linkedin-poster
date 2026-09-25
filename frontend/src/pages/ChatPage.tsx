import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router'
import { api } from '../api/client'
import type {
  ChatMessage,
  PublishConfirmPayload,
  ThreadSnapshot,
  TopicChoicePayload,
  TopicPickAnswer,
} from '../api/types'
import { Composer } from '../components/Composer'
import { DraftPanel } from '../components/DraftPanel'
import { PublishDialog } from '../components/PublishDialog'
import { RunCard } from '../components/RunCard'
import { StatusPill } from '../components/StatusPill'
import { Toast } from '../components/Toast'
import { TopicPicker } from '../components/TopicPicker'
import { useAutoTopic, useDryRun } from '../hooks/useLocalStorage'
import { useMediaQuery, XL } from '../hooks/useMediaQuery'
import { useThreadRun, type ThreadRun } from '../hooks/useThreadRun'
import { useShell } from '../layout/shell'
import { formatTokens } from '../lib/post'

const STARTERS = [
  'Find a trending AI topic and draft a post',
  'Find a software engineering topic and draft a post',
]
const EDITS = ['Make it shorter', 'Punchier hook', 'Show me the sources', 'Use the runner-up']

export function ChatPage() {
  const { threadId } = useParams()
  // key: a fresh workspace (and run state) per conversation
  return threadId ? <Conversation key={threadId} threadId={threadId} /> : <StartConversation />
}

function StartConversation() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  async function start(text: string) {
    try {
      const { id } = await api.createThread()
      navigate(`/chat/${id}`, { state: { initialMessage: text } })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <main className="flex grow flex-col items-center justify-center gap-6 overflow-y-auto p-5 sm:p-10">
      <div className="flex max-w-xl flex-col items-center gap-3 text-center">
        <h1 className="m-0 font-display text-4xl leading-none sm:text-5xl">Chat with the Manager</h1>
        <p className="text-ink-2">
          Ask for a post and the team finds a topic, researches it, writes it and gets it reviewed.
          Nothing is published until you approve it.
        </p>
      </div>
      <div className="w-full max-w-2xl">
        <Composer running={false} onSend={start} suggestions={STARTERS} autoFocus />
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger">
            {error}
          </p>
        )}
      </div>
    </main>
  )
}

function Conversation({ threadId }: { threadId: string }) {
  const { reloadThreads, linkedin, publishMode } = useShell()
  const [toast, setToast] = useState<{ title: string; body?: string; href?: string } | null>(null)
  const run = useThreadRun(threadId, ({ before, after }) => {
    void reloadThreads()
    // Toast only for a publish that happened in this run.
    const was = before?.publish_result?.status
    const now = after?.publish_result?.status
    if (now === was) return
    if (now === 'published') {
      setToast({ title: 'Published to LinkedIn', body: 'Your post is live.', href: after?.publish_result?.url ?? undefined })
    } else if (now === 'dry_run') {
      setToast({ title: 'Dry run recorded', body: 'Saved to history — nothing was posted.' })
    }
  })
  const [dryRun, setDryRun] = useDryRun()
  const [autoTopic, setAutoTopic] = useAutoTopic()
  const [publishDismissed, setPublishDismissed] = useState(false)
  // Narrow screens show the chat or the draft panel, not both side by side.
  const wide = useMediaQuery(XL)
  const [view, setView] = useState<'chat' | 'draft'>('chat')
  const location = useLocation()
  const navigate = useNavigate()
  const { thread } = run

  // First message typed on the start screen.
  const initialSent = useRef(false)
  const initialMessage = (location.state as { initialMessage?: string } | null)?.initialMessage
  useEffect(() => {
    if (!initialMessage || initialSent.current || !thread) return
    initialSent.current = true
    navigate(location.pathname, { replace: true, state: null })
    void run.send(initialMessage, { dryRun, autoTopic })
  }, [initialMessage, thread, navigate, location.pathname, run, dryRun, autoTopic])

  const sendText = (text: string) => {
    setPublishDismissed(false)
    setView('chat')
    void run.send(text, { dryRun, autoTopic })
  }

  if (run.loadError) {
    return <p className="p-7 text-danger">Couldn’t load this conversation: {run.loadError.message}</p>
  }
  if (!thread) return <p className="p-7 text-ink-3">Loading…</p>

  const pending = thread.pending
  const showPublishDialog = pending?.type === 'publish_confirm' && !publishDismissed && !run.running

  const showChat = wide || view === 'chat'
  const showDraft = wide || view === 'draft'

  return (
    <div className="flex min-h-0 grow flex-col xl:flex-row">
      {!wide && <ViewSwitch view={view} onChange={setView} hasDraft={thread.draft !== null} />}
      <main className={`min-h-0 min-w-0 grow flex-col ${showChat ? 'flex' : 'hidden'}`}>
        <header className="flex min-h-16 shrink-0 flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-4 py-3 sm:px-7">
          <div className="flex min-w-0 items-center gap-3">
            <h1 className="m-0 truncate font-display text-[22px] font-normal sm:text-[26px]">{thread.title}</h1>
            <StatusPill status={thread.status} />
            {thread.niche && (
              <span className="shrink-0 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-medium text-accent-ink">
                {thread.niche}
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-4 sm:gap-5">
            <label
              className="flex cursor-pointer items-center gap-2.5 text-[13px] text-ink-2"
              title="On: the Topic Scout picks the best topic. Off: you choose from its shortlist."
            >
              <input
                type="checkbox"
                checked={autoTopic}
                onChange={(e) => setAutoTopic(e.target.checked)}
                className="size-4.5 accent-accent"
              />
              Auto-pick topic
            </label>
            <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-ink-2">
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                className="size-4.5 accent-accent"
              />
              Dry run
            </label>
          </div>
        </header>

        <Transcript
          thread={thread}
          run={run}
          onPickTopic={(answer) => void run.resume(answer, dryRun)}
        />

        <div className="flex flex-col gap-2.5 px-4 pb-4 sm:px-7 sm:pb-5">
          {run.error && (
            <div role="alert" className="flex items-start justify-between gap-3 rounded-[10px] bg-danger-soft px-4 py-3 text-sm text-danger">
              <span>{run.error}</span>
              <button type="button" onClick={run.clearError} className="font-medium underline">
                Dismiss
              </button>
            </div>
          )}
          {pending?.type === 'publish_confirm' && publishDismissed && !run.running && (
            <button
              type="button"
              onClick={() => setPublishDismissed(false)}
              className="self-start rounded-full bg-review-soft px-3.5 py-1.5 text-[13px] font-medium text-review"
            >
              A publish confirmation is waiting — open it
            </button>
          )}
          <Composer
            running={run.running}
            onSend={sendText}
            onStop={run.stop}
            suggestions={thread.draft ? EDITS : STARTERS}
          />
          {run.usage && (
            <span className="font-mono text-[11px] text-ink-3">
              last turn · LLM calls {run.usage.calls} · tokens {formatTokens(run.usage.input_tokens)} in /{' '}
              {formatTokens(run.usage.output_tokens)} out · searches {run.usage.searches} (+{run.usage.search_cache_hits} cached)
              {dryRun && ' · dry run'}
            </span>
          )}
        </div>
      </main>

      {showDraft && (
        <DraftPanel
          thread={thread}
          author={linkedin?.connected ? (linkedin.name ?? 'You') : 'You'}
          running={run.running}
          publishMode={publishMode}
          onPublish={() => sendText('post it')}
          onShared={(articleUrl) => {
            // LinkedIn opened in a new tab from the click itself; record it here.
            api
              .markShared(thread.id, articleUrl)
              .then((snapshot) => {
                run.replaceThread(snapshot)
                void reloadThreads()
                setToast({ title: 'Opened on LinkedIn', body: 'Review the post there and press Post.' })
              })
              .catch(() => undefined)
          }}
          onRequestReview={() => sendText('let me review it')}
          onOpenPublishConfirm={() => setPublishDismissed(false)}
          onThreadUpdated={run.replaceThread}
        />
      )}

      {showPublishDialog && (
        <PublishDialog
          payload={pending as PublishConfirmPayload}
          busy={run.running}
          onDecide={(confirm) => void run.resume({ confirm }, dryRun)}
          onLater={() => setPublishDismissed(true)}
        />
      )}
      {toast && <Toast {...toast} onClose={() => setToast(null)} />}
    </div>
  )
}

/** Narrow screens: switch between the conversation and the draft panel. */
function ViewSwitch({
  view,
  onChange,
  hasDraft,
}: {
  view: 'chat' | 'draft'
  onChange: (view: 'chat' | 'draft') => void
  hasDraft: boolean
}) {
  const tabs = [
    { id: 'chat', label: 'Chat' },
    { id: 'draft', label: 'Draft' },
  ] as const
  return (
    <div role="tablist" aria-label="Show" className="flex shrink-0 gap-1 border-b border-line px-3 pt-2">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={view === t.id}
          onClick={() => onChange(t.id)}
          className={`flex h-10 grow items-center justify-center gap-2 border-b-2 text-sm ${
            view === t.id ? 'border-accent font-semibold text-ink' : 'border-transparent text-ink-2'
          }`}
        >
          {t.label}
          {t.id === 'draft' && hasDraft && <span className="size-1.5 rounded-full bg-accent" aria-label="(ready)" />}
        </button>
      ))}
    </div>
  )
}

/** Messages, with the agent checklist placed after the user message that started the work. */
function Transcript({
  thread,
  run,
  onPickTopic,
}: {
  thread: ThreadSnapshot
  run: ThreadRun
  onPickTopic: (answer: TopicPickAnswer) => void
}) {
  const bottom = useRef<HTMLDivElement>(null)
  const { live, pendingText } = run
  const messages: ChatMessage[] = pendingText
    ? [...thread.messages, { role: 'user', content: pendingText }]
    : thread.messages

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, live?.lines.length, live?.current, thread.pending?.type])

  const lastUser = messages.map((m) => m.role).lastIndexOf('user')
  const pending = thread.pending
  const card = live ? (
    <RunCard
      lines={live.lines}
      plan={live.plan}
      current={live.current}
      running
      startedAt={live.startedAt}
    />
  ) : thread.activity.length > 0 ? (
    <RunCard
      lines={thread.activity}
      running={false}
      waitingFor={
        pending
          ? ({ topic_choice: 'topic', review: 'review', publish_confirm: 'publish' } as const)[pending.type]
          : null
      }
      reviewHref={`/chat/${thread.id}/review`}
    />
  ) : null

  return (
    <section aria-label="Conversation" className="flex min-h-0 grow flex-col gap-5 overflow-y-auto px-4 pt-5 pb-3 sm:px-7 sm:pt-7">
      {messages.length === 0 && !live && (
        <p className="text-sm text-ink-3">Say what you’d like — the Manager takes it from there.</p>
      )}
      {messages.map((m, i) => (
        <div key={i} className="contents">
          <Message message={m} />
          {i === lastUser && card}
        </div>
      ))}
      {lastUser === -1 && card}
      {/* Hidden once answered: the live checklist above takes over while the run continues. */}
      {pending?.type === 'topic_choice' && !live && (
        <TopicPicker payload={pending as TopicChoicePayload} busy={run.running} onAnswer={onPickTopic} />
      )}
      {!live && messages.length > 0 && messages[messages.length - 1].role === 'user' && !thread.pending && (
        <p role="status" className="m-0 max-w-160 rounded-[10px] border border-dashed border-line-strong px-4 py-3 text-[13px] text-ink-2">
          This turn was interrupted before the Manager replied (stopped, or the page was reloaded mid-run). Your work
          up to that point is saved — send your message again to continue.
        </p>
      )}
      <div ref={bottom} />
    </section>
  )
}

function Message({ message }: { message: ChatMessage }) {
  if (message.role === 'user') {
    return (
      <p className="m-0 max-w-130 self-end rounded-[14px_14px_4px_14px] bg-inverse px-4 py-3 text-sm leading-normal whitespace-pre-line text-on-inverse">
        {message.content}
      </p>
    )
  }
  return (
    <div className="flex max-w-160 gap-3">
      <span
        className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent font-display text-lg text-white"
        aria-hidden="true"
      >
        M
      </span>
      <p className="m-0 rounded-[4px_14px_14px_14px] border border-line bg-card px-4 py-3 text-sm leading-[1.55] whitespace-pre-line">
        <span className="sr-only">Manager: </span>
        {message.content}
      </p>
    </div>
  )
}
