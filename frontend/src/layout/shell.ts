import { useOutletContext } from 'react-router'
import type { LinkedInStatus, ThreadSummary } from '../api/types'

/** Shared state the shell hands to every page (via <Outlet context>). */
export interface ShellContext {
  threads: ThreadSummary[]
  reloadThreads: () => Promise<void>
  linkedin: LinkedInStatus | undefined
  reloadLinkedIn: () => Promise<void>
}

export function useShell(): ShellContext {
  return useOutletContext<ShellContext>()
}
