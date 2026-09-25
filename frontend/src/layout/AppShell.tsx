import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router'
import { api } from '../api/client'
import { Icon } from '../components/Icon'
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
  const [navOpen, setNavOpen] = useState(false) // the sidebar drawer on narrow screens

  // Keep the conversation list fresh as the user moves around.
  const { reload } = threads
  useEffect(() => {
    void reload()
  }, [location.pathname, reload])

  useEffect(() => {
    if (!navOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setNavOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navOpen])

  const context: ShellContext = {
    threads: threads.data ?? [],
    reloadThreads: threads.reload,
    linkedin: linkedin.data,
    reloadLinkedIn: linkedin.reload,
    publishMode,
  }

  return (
    <div className="flex h-full overflow-hidden">
      {navOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" aria-hidden="true" onClick={() => setNavOpen(false)} />
      )}
      <Sidebar
        open={navOpen}
        onClose={() => setNavOpen(false)}
        threads={threads.data ?? []}
        threadsError={threads.error}
        linkedin={publishMode === 'api' ? linkedin.data : undefined}
      />
      <div className="flex min-w-0 grow flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b border-line bg-paper-2 px-2 lg:hidden">
          <button
            type="button"
            onClick={() => setNavOpen(true)}
            aria-label="Open menu"
            aria-expanded={navOpen}
            className="flex size-10 items-center justify-center rounded-lg text-ink hover:bg-card"
          >
            <Icon name="menu" size={20} />
          </button>
          <span className="font-display text-2xl leading-none">Poster</span>
        </header>
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
      className="flex items-center justify-between gap-4 border-b border-review/20 bg-review-soft px-4 py-3 text-sm text-review sm:px-7"
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
