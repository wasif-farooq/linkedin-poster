import type { RunEvent } from './types'

/**
 * Parse a text/event-stream body (from fetch — EventSource can't POST).
 * Handles events split across network chunks and CRLF line endings.
 */
export async function readEventStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: RunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      if (signal?.aborted) break
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const parsed = parseEvent(buffer.slice(0, boundary))
        if (parsed) onEvent(parsed)
        buffer = buffer.slice(boundary + 2)
        boundary = buffer.indexOf('\n\n')
      }
    }
    const tail = parseEvent(buffer.trim())
    if (tail) onEvent(tail)
  } finally {
    reader.releaseLock()
  }
}

export function parseEvent(block: string): RunEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (!data.length) return null
  try {
    return { event, data: JSON.parse(data.join('\n')) } as RunEvent
  } catch {
    return null
  }
}
