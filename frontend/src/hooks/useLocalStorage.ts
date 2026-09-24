import { useCallback, useState } from 'react'

/** A per-browser preference. Storage can be unavailable (private mode), so it degrades to memory. */
export function useLocalStorage<T>(key: string, initial: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = window.localStorage.getItem(key)
      return raw === null ? initial : (JSON.parse(raw) as T)
    } catch {
      return initial
    }
  })
  const update = useCallback(
    (next: T) => {
      setValue(next)
      try {
        window.localStorage.setItem(key, JSON.stringify(next))
      } catch {
        // storage blocked: keep the in-memory value
      }
    },
    [key],
  )
  return [value, update]
}

export function useDryRun(): [boolean, (value: boolean) => void] {
  return useLocalStorage('poster.dryRun', false)
}
