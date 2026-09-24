import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router'
import { api } from '../api/client'
import { useResource } from '../hooks/useResource'
import { Sidebar } from './Sidebar'
import type { ShellContext } from './shell'

export function AppShell() {
  const threads = useResource(api.threads)
  const linkedin = useResource(api.linkedin)
  const health = useResource(api.health)
  const settings = useResource(api.settings)
  const publishMode = settings.data?.publish_mode ?? 'share'
  const location = useLocation()

  // Keep the conversation list fresh as the user moves around.
  const { reload } = threads
  useEffect(() => {
    void reload()
  }, [location.pathname, reload])

  const context: ShellContext = {
    threads: threads.data ?? [],
    reloadThreads: threads.reload,
    linkedin: linkedin.data,
    reloadLinkedIn: linkedin.reload,
    publishMode,
  }

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar
        threads={threads.data ?? []}
        threadsError={threads.error}
        linkedin={publishMode === 'api' ? linkedin.data : undefined}
      />
      <div className="flex min-w-0 grow flex-col">
        {health.error && <OfflineBanner onRetry={health.reload} />}
        <Outlet context={context} />
      </div>
    </div>
  )
}

function OfflineBanner({ onRetry }: { onRetry: () => Promise<void> }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-4 border-b border-review/20 bg-review-soft px-7 py-3 text-sm text-review"
    >
      <span>
        Can’t reach the API. Start it with{' '}
        <code className="font-mono text-[13px]">uv run linkedin-poster serve</code>
      </span>
      <button
        type="button"
        onClick={() => void onRetry()}
        className="h-9 rounded-lg border border-review/30 bg-card px-3 font-medium hover:bg-card-soft"
      >
        Retry
      </button>
    </div>
  )
}
