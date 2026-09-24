import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

export interface Resource<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
  reload: () => Promise<void>
  setData: (value: T) => void
}

/** Load async data on mount (and when `deps` change); ignores stale responses. */
export function useResource<T>(load: () => Promise<T>, deps: unknown[] = []): Resource<T> {
  const [data, setData] = useState<T>()
  const [error, setError] = useState<Error>()
  const [loading, setLoading] = useState(true)
  const request = useRef(0)
  const loadRef = useRef(load)
  useLayoutEffect(() => {
    loadRef.current = load
  })

  const reload = useCallback(async () => {
    const id = ++request.current
    setLoading(true)
    try {
      const value = await loadRef.current()
      if (id === request.current) {
        setData(value)
        setError(undefined)
      }
    } catch (err) {
      if (id === request.current) setError(err instanceof Error ? err : new Error(String(err)))
    } finally {
      if (id === request.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error, loading, reload, setData }
}
