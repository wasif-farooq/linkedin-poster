import { useCallback, useState } from 'react'

export type Theme = 'dark' | 'light'
const KEY = 'poster.theme'

/** Dark by default. index.html applies the saved theme before first paint; this keeps it in sync. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === 'light' ? 'light' : 'dark',
  )
  const toggle = useCallback(() => {
    setTheme((current) => {
      const next: Theme = current === 'dark' ? 'light' : 'dark'
      document.documentElement.dataset.theme = next
      try {
        window.localStorage.setItem(KEY, next)
      } catch {
        // storage blocked: the choice lasts for this page only
      }
      return next
    })
  }, [])
  return [theme, toggle]
}
