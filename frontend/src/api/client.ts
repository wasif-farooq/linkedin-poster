import type {
  AppSettings,
  DoctorCheck,
  HistoryPost,
  LinkedInStatus,
  ResumeAnswer,
  RunEvent,
  ThreadSnapshot,
  ThreadSummary,
} from './types'
import { readEventStream } from './sse'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'Can’t reach the API. Is `uv run linkedin-poster serve` running?')
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  return (await response.json()) as T
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg: string }) => d.msg).join('; ')
  } catch {
    // not JSON
  }
  return `Request failed (${response.status})`
}

/** POST that answers with a Server-Sent Events stream; calls onEvent for each event. */
async function stream(
  path: string,
  body: unknown,
  onEvent: (event: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    })
  } catch {
    if (signal?.aborted) return
    throw new ApiError(0, 'Can’t reach the API. Is `uv run linkedin-poster serve` running?')
  }
  if (!response.ok || !response.body) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  await readEventStream(response.body, onEvent, signal)
}

export const api = {
  health: () => request<{ ok: boolean; busy: boolean }>('/api/health'),

  threads: () => request<ThreadSummary[]>('/api/threads'),
  createThread: (niche?: string) =>
    request<{ id: string }>('/api/threads', {
      method: 'POST',
      body: JSON.stringify({ niche: niche || null }),
    }),
  thread: (id: string) => request<ThreadSnapshot>(`/api/threads/${encodeURIComponent(id)}`),

  sendMessage: (
    id: string,
    text: string,
    dryRun: boolean,
    onEvent: (e: RunEvent) => void,
    signal?: AbortSignal,
  ) =>
    stream(
      `/api/threads/${encodeURIComponent(id)}/messages`,
      { text, dry_run: dryRun },
      onEvent,
      signal,
    ),
  resume: (
    id: string,
    answer: ResumeAnswer,
    dryRun: boolean,
    onEvent: (e: RunEvent) => void,
    signal?: AbortSignal,
  ) =>
    stream(
      `/api/threads/${encodeURIComponent(id)}/resume`,
      { answer, dry_run: dryRun },
      onEvent,
      signal,
    ),

  markShared: (id: string, articleUrl: string | null) =>
    request<ThreadSnapshot>(`/api/threads/${encodeURIComponent(id)}/shared`, {
      method: 'POST',
      body: JSON.stringify({ article_url: articleUrl }),
    }),

  history: (includeDryRuns = true) =>
    request<HistoryPost[]>(`/api/history?include_dry_runs=${includeDryRuns}`),
  doctor: () => request<DoctorCheck[]>('/api/doctor'),
  linkedin: () => request<LinkedInStatus>('/api/linkedin'),
  connectLinkedIn: () =>
    request<LinkedInStatus['auth_flow']>('/api/linkedin/connect', { method: 'POST' }),
  settings: () => request<AppSettings>('/api/settings'),
  voice: () => request<{ text: string }>('/api/voice'),
  saveVoice: (text: string) =>
    request<{ text: string }>('/api/voice', { method: 'PUT', body: JSON.stringify({ text }) }),
}
