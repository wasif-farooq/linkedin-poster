import { useSyncExternalStore } from 'react'

/** Whether a CSS media query matches, kept in sync as the window resizes. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const list = window.matchMedia(query)
      list.addEventListener('change', onChange)
      return () => list.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
  )
}

// Tailwind's default breakpoints, for layout decisions that CSS alone can't make.
export const LG = '(min-width: 64rem)'
export const XL = '(min-width: 80rem)'
