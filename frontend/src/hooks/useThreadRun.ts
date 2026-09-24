import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { ResumeAnswer, RunEvent, ThreadSnapshot, Usage } from '../api/types'
import { useResource } from './useResource'

/** Progress of the run that is streaming right now. */
export interface LiveRun {
  kind: 'message' | 'resume'
  plan: string[]
  managerNote: string | null
  lines: string[] // activity lines produced by this run
  current: string | null // agent working now, or "manager"
  startedAt: number
}

export interface ThreadRun {
  thread: ThreadSnapshot | undefined
  loadError: Error | undefined
  live: LiveRun | null
  running: boolean
  pendingText: string | null // the user's message while its turn runs
  error: string | null
  usage: Usage | null
  send: (text: string, options: { dryRun: boolean; autoTopic: boolean }) => Promise<void>
  resume: (answer: ResumeAnswer, dryRun: boolean) => Promise<void>
  stop: () => void
  clearError: () => void
  replaceThread: (thread: ThreadSnapshot) => void
}

export interface RunOutcome {
  before: ThreadSnapshot | undefined
  after: ThreadSnapshot | undefined
}

/**
 * One conversation: its saved state plus any run streaming for it.
 * Mount it per conversation (key by thread id) so transient run state never leaks across threads.
 */
export function useThreadRun(
  threadId: string,
  onSettled?: (outcome: RunOutcome) => void,
): ThreadRun {
  const snapshot = useResource(() => api.thread(threadId), [threadId])
  const [live, setLive] = useState<LiveRun | null>(null)
  const [pendingText, setPendingText] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const settledRef = useRef(onSettled)
  useEffect(() => {
    settledRef.current = onSettled
  })

  const { data: current, setData, reload } = snapshot
  const currentRef = useRef(current)
  useEffect(() => {
    currentRef.current = current
  })
  const execute = useCallback(
    async (
      kind: LiveRun['kind'],
      start: (onEvent: (e: RunEvent) => void, signal: AbortSignal) => Promise<void>,
    ) => {
      const controller = new AbortController()
      abortRef.current = controller
      setError(null)
      setLive({
        kind,
        plan: [],
        managerNote: null,
        lines: [],
        current: kind === 'message' ? 'manager' : null,
        startedAt: Date.now(),
      })
      let finished = false
      const before = currentRef.current
      let after: ThreadSnapshot | undefined

      const onEvent = (e: RunEvent) => {
        switch (e.event) {
          case 'step': {
            const { node, plan, reply, next, activity } = e.data
            setLive((run) => {
              if (!run) return run
              const updated = { ...run }
              if (activity?.length) updated.lines = [...run.lines, ...activity]
              if (node === 'manager') {
                if (plan?.length) {
                  updated.plan = plan
                  updated.managerNote = reply ?? null
                }
                updated.current = null
              } else if (node === 'dispatch') {
                updated.current = next ?? null
              } else if (node !== 'begin_turn') {
                updated.current = null
              }
              return updated
            })
            break
          }
          case 'error':
            setError(e.data.message)
            break
          case 'done':
            finished = true
            after = e.data.thread
            setData(e.data.thread)
            setUsage(e.data.usage)
            break
          default:
            break // 'start'; 'interrupt' also arrives in done.thread.pending
        }
      }

      try {
        await start(onEvent, controller.signal)
      } catch (err) {
        setError(err instanceof ApiError || err instanceof Error ? err.message : String(err))
      } finally {
        abortRef.current = null
        setLive(null)
        setPendingText(null)
        if (!finished) await reload() // stopped or failed: show what was saved
        settledRef.current?.({ before, after })
      }
    },
    [setData, reload],
  )

  const send = useCallback(
    async (text: string, options: { dryRun: boolean; autoTopic: boolean }) => {
      setPendingText(text)
      await execute('message', (onEvent, signal) =>
        api.sendMessage(threadId, text, options, onEvent, signal),
      )
    },
    [execute, threadId],
  )

  const resume = useCallback(
    (answer: ResumeAnswer, dryRun: boolean) =>
      execute('resume', (onEvent, signal) => api.resume(threadId, answer, dryRun, onEvent, signal)),
    [execute, threadId],
  )

  return {
    thread: snapshot.data,
    loadError: snapshot.error,
    live,
    running: live !== null,
    pendingText,
    error,
    usage,
    send,
    resume,
    stop: () => abortRef.current?.abort(),
    clearError: () => setError(null),
    replaceThread: setData,
  }
}
