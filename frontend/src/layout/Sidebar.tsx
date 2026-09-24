import { NavLink, useMatch, useNavigate } from 'react-router'
import { api } from '../api/client'
import type { LinkedInStatus, ThreadSummary } from '../api/types'
import { Icon, type IconName } from '../components/Icon'
import { StatusPill } from '../components/StatusPill'
import { useTheme } from '../hooks/useTheme'

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/chat', label: 'Chat', icon: 'chat' },
  { to: '/history', label: 'History', icon: 'history' },
  { to: '/settings', label: 'Health & settings', icon: 'pulse' },
]

interface SidebarProps {
  threads: ThreadSummary[]
  threadsError: Error | undefined
  linkedin: LinkedInStatus | undefined
}

export function Sidebar({ threads, threadsError, linkedin }: SidebarProps) {
  const navigate = useNavigate()
  const threadId = useMatch('/chat/:threadId')?.params.threadId
  const [theme, toggleTheme] = useTheme()

  async function newConversation() {
    try {
      const { id } = await api.createThread()
      navigate(`/chat/${id}`)
    } catch {
      navigate('/chat')
    }
  }

  return (
    <aside className="flex w-66 shrink-0 flex-col border-r border-line bg-paper-2">
      <div className="flex items-center justify-between px-5 pt-5 pb-3">
        <span className="flex items-baseline gap-2">
          <span className="font-display text-3xl leading-none">Poster</span>
          <span className="font-mono text-[11px] text-ink-3">v0.1</span>
        </span>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Light theme' : 'Dark theme'}
          className="flex size-9 items-center justify-center rounded-lg text-ink-2 hover:bg-card hover:text-ink"
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
      </div>

      <nav aria-label="Main" className="flex flex-col gap-0.5 px-3">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex h-10 items-center gap-2.5 rounded-lg px-3 text-sm no-underline ${
                isActive
                  ? 'bg-card font-medium text-ink shadow-[0_1px_0_var(--color-line)]'
                  : 'text-ink-2 hover:bg-card/60'
              }`
            }
          >
            <Icon name={item.icon} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="flex items-center justify-between px-5 pt-5 pb-2">
        <h2 className="eyebrow">Conversations</h2>
        <button
          type="button"
          onClick={newConversation}
          aria-label="New conversation"
          className="flex size-8 items-center justify-center rounded-lg border border-line-strong bg-card text-ink hover:bg-card-soft"
        >
          <Icon name="plus" size={16} strokeWidth={2} />
        </button>
      </div>

      <ul className="flex min-h-0 grow flex-col gap-0.5 overflow-y-auto px-3 pb-3">
        {threadsError && (
          <li className="px-3 py-2 text-xs text-ink-3">Couldn’t load conversations.</li>
        )}
        {!threadsError && threads.length === 0 && (
          <li className="px-3 py-2 text-xs text-ink-3">No conversations yet.</li>
        )}
        {threads.map((t) => (
          <li key={t.id}>
            <NavLink
              to={`/chat/${t.id}`}
              aria-current={t.id === threadId ? 'page' : undefined}
              className={`flex flex-col gap-1.5 rounded-lg px-3 py-2.5 text-ink no-underline ${
                t.id === threadId ? 'bg-accent-soft' : 'hover:bg-card/60'
              }`}
            >
              <span className="line-clamp-2 text-[13px] leading-snug font-medium">{t.title}</span>
              <span className="flex items-center gap-2">
                <StatusPill status={t.status} />
                <span className="font-mono text-[11px] text-ink-3">{t.id}</span>
              </span>
            </NavLink>
          </li>
        ))}
      </ul>

      <LinkedInCard linkedin={linkedin} />
    </aside>
  )
}

function LinkedInCard({ linkedin }: { linkedin: LinkedInStatus | undefined }) {
  if (!linkedin) return null
  const connected = linkedin.connected
  const expiring = connected && (linkedin.days_left ?? 0) < 7
  return (
    <NavLink
      to="/settings"
      className="m-3 flex flex-col gap-1 rounded-xl border border-line bg-card p-3.5 text-ink no-underline hover:bg-card-soft"
    >
      <span className="flex items-center gap-2 text-[13px] font-medium">
        <span
          className={`size-2 rounded-full ${connected && !expiring ? 'bg-success' : 'bg-review'}`}
          aria-hidden="true"
        />
        {connected ? 'LinkedIn connected' : 'LinkedIn not connected'}
      </span>
      <span className="text-xs text-ink-2">
        {connected
          ? `as ${linkedin.name} · token expires in ${linkedin.days_left} days`
          : 'Connect to publish posts'}
      </span>
    </NavLink>
  )
}
