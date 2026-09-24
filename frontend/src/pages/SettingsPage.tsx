import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { api } from '../api/client'
import { useShell } from '../layout/shell'

// Phase 11 builds the full Health & settings screen. This first piece covers how posts reach
// LinkedIn: share links (default, nothing to connect) or, in API mode, connecting LinkedIn.
export function SettingsPage() {
  const { linkedin, reloadLinkedIn, publishMode } = useShell()
  const [params, setParams] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const result = params.get('linkedin')
  const reason = params.get('reason')

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      const flow = await api.connectLinkedIn()
      if (flow.authorize_url) {
        window.location.assign(flow.authorize_url) // LinkedIn → /api/linkedin/callback → back here
        return
      }
      setError(flow.error ?? 'Could not start the LinkedIn sign-in.')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
      void reloadLinkedIn()
    }
  }

  return (
    <main className="flex grow flex-col gap-6 overflow-y-auto p-10">
      <h1 className="m-0 font-display text-[40px] leading-none font-normal">Health &amp; settings</h1>

      {result === 'connected' && (
        <p role="status" className="m-0 max-w-xl rounded-[10px] bg-success-soft px-4 py-3 text-sm text-success">
          LinkedIn connected.{' '}
          <button type="button" className="underline" onClick={() => setParams({})}>
            Dismiss
          </button>
        </p>
      )}
      {result === 'error' && (
        <p role="alert" className="m-0 max-w-xl rounded-[10px] bg-danger-soft px-4 py-3 text-sm text-danger">
          LinkedIn sign-in failed{reason ? `: ${reason}` : '.'}
        </p>
      )}

      {publishMode === 'share' && (
        <section
          aria-labelledby="share-h"
          className="flex max-w-xl flex-col gap-3 rounded-[14px] border border-line bg-card px-5.5 py-5"
        >
          <h2 id="share-h" className="eyebrow m-0">
            Posting to LinkedIn
          </h2>
          <p className="m-0 text-sm leading-relaxed">
            Approved posts are shared with a <strong className="font-semibold">Share on LinkedIn</strong> link: it
            opens LinkedIn with the post (and optionally the source article) filled in, and you press Post there. No
            LinkedIn app, sign-in or stored token is needed, and this site can never post on its own.
          </p>
        </section>
      )}

      {publishMode === 'api' && (
      <section
        aria-labelledby="li-h"
        className="flex max-w-xl flex-col gap-4 rounded-[14px] border border-line bg-card px-5.5 py-5"
      >
        <h2 id="li-h" className="eyebrow m-0">
          LinkedIn
        </h2>
        {linkedin?.connected ? (
          <p className="m-0 text-sm">
            Connected as <strong className="font-semibold">{linkedin.name}</strong> · token expires in{' '}
            {linkedin.days_left} days.
          </p>
        ) : (
          <p className="m-0 text-sm text-ink-2">
            Not connected. Connect to publish posts — you’ll approve access on LinkedIn and come back here.
          </p>
        )}
        {error && (
          <p role="alert" className="m-0 text-sm text-danger">
            {error}
          </p>
        )}
        <button
          type="button"
          onClick={() => void connect()}
          disabled={busy}
          className="h-11 self-start rounded-[10px] bg-accent px-4.5 text-sm font-semibold text-white hover:bg-accent-dark disabled:opacity-50"
        >
          {linkedin?.connected ? 'Reconnect' : 'Connect LinkedIn'}
        </button>
      </section>
      )}

      <p className="m-0 text-sm text-ink-3">System health, models, limits and your voice guide arrive in Phase 11.</p>
    </main>
  )
}
