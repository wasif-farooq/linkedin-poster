// Mirrors the Python API (app/api/server.py, app/services/threads.py).

export type ThreadStatus =
  | 'choose_topic'
  | 'needs_review'
  | 'confirm_publish'
  | 'published'
  | 'shared'
  | 'approved'
  | 'draft'
  | 'new'

export interface ThreadSummary {
  id: string
  title: string
  status: ThreadStatus
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Topic {
  topic: string
  angle?: string
  why_now?: string
  audience?: string
  source_urls?: string[]
  source_titles?: string[]
  runner_up_ids?: number[]
}

export interface Source {
  id: number
  title: string
  url: string
  origin: 'scout' | 'search'
  content: string
  published: string | null
  full_text: boolean
}

export interface CitedPoint {
  point: string
  source_ids: number[]
}

export interface ResearchBrief {
  topic: string
  angle: string
  summary: string
  key_points: CitedPoint[]
  stats: { fact: string; source_ids: number[] }[]
  counterpoints: CitedPoint[]
  sources: Source[]
  queries: string[]
}

export interface Draft {
  text: string
  hashtags: string[]
  source_ids: number[]
  full_text: string
  chars: number
}

export type ScoreName = 'hook' | 'insight' | 'accuracy' | 'clarity' | 'tone'

export interface Critique {
  scores: Record<ScoreName, number>
  issues: string[]
  suggestions: string[]
  verdict: 'pass' | 'revise'
  rule_errors: string[]
  rule_warnings: string[]
}

export interface PublishResult {
  status: 'published' | 'dry_run' | 'already_published' | 'cancelled' | 'share_ready' | 'shared'
  urn: string | null
  url: string | null
}

export interface ReviewPayload {
  type: 'review'
  post: string
  chars: number
  critic_verdict: 'pass' | 'revise' | null
  critic_scores: Record<ScoreName, number> | null
  critic_issues: string[]
  rule_errors: string[]
  can_approve: boolean
}

export interface PublishConfirmPayload {
  type: 'publish_confirm'
  post: string
  chars: number
  account: string
}

export interface TopicOptionView {
  id: number
  topic: string
  angle: string
  why_now: string
  audience: string
  sources: { title: string; url: string }[]
}

export interface TopicChoicePayload {
  type: 'topic_choice'
  options: TopicOptionView[]
  round: number
}

export type PendingDecision = ReviewPayload | PublishConfirmPayload | TopicChoicePayload

export interface ThreadSnapshot {
  id: string
  title: string
  status: ThreadStatus
  niche: string | null
  auto_topic: boolean
  messages: ChatMessage[]
  topic: Topic | null
  research_brief: ResearchBrief | null
  draft: Draft | null
  critique: Critique | null
  revision_count: number
  approved: boolean
  final_post: string | null
  publish_result: PublishResult | null
  activity: string[]
  last_error: string | null
  pending: PendingDecision | null
}

export interface Usage {
  calls: number
  input_tokens: number
  output_tokens: number
  rate_limit_retries: number
  searches: number
  search_cache_hits: number
}

export type ReviewAnswer =
  | { action: 'approve' }
  | { action: 'reject' }
  | { action: 'edit'; text: string }
  | { action: 'revise'; text: string }

export type TopicPickAnswer =
  | { choice: number }
  | { more: true; hint?: string | null }
  | { topic: string }
  | { cancel: true }

export type ResumeAnswer = ReviewAnswer | { confirm: boolean } | TopicPickAnswer

// Server-Sent Events emitted by a run.
export type RunEvent =
  | { event: 'start'; data: { thread_id: string } }
  | {
      event: 'step'
      data: {
        node: string
        plan?: string[]
        reply?: string | null
        next?: string
        activity?: string[]
        error?: string
      }
    }
  | { event: 'interrupt'; data: PendingDecision }
  | { event: 'error'; data: { message: string } }
  | { event: 'done'; data: { thread: ThreadSnapshot; usage: Usage } }

export interface HistoryPost {
  id: number
  created_at: string
  status: 'published' | 'dry_run' | 'shared'
  topic: string
  text: string
  urn: string | null
  url: string | null
  source_urls: string[]
}

export interface DoctorCheck {
  name: string
  status: 'ok' | 'warn' | 'fail'
  detail: string
}

export interface LinkedInStatus {
  configured: boolean
  connected: boolean
  name?: string
  author_urn?: string
  days_left?: number
  error?: string
  auth_flow: { running: boolean; authorize_url: string | null; error: string | null }
}

export interface AppSettings {
  default_model: string
  role_models: Record<string, string>
  fallback_models: string[]
  limits: Record<string, number>
  linkedin_version: string
  publish_dry_run: boolean
  publish_mode: 'share' | 'api'
}
