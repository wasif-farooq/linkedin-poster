import { describe, expect, it } from 'vitest'
import { parseEvent, readEventStream } from './sse'
import type { RunEvent } from './types'

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<RunEvent[]> {
  const events: RunEvent[] = []
  await readEventStream(stream, (e) => events.push(e))
  return events
}

describe('readEventStream', () => {
  it('parses consecutive events', async () => {
    const events = await collect(
      streamOf(
        'event: start\ndata: {"thread_id": "t1"}\n\n',
        'event: step\ndata: {"node": "manager", "plan": ["writer"]}\n\n',
      ),
    )
    expect(events).toEqual([
      { event: 'start', data: { thread_id: 't1' } },
      { event: 'step', data: { node: 'manager', plan: ['writer'] } },
    ])
  })

  it('reassembles an event split across chunks (and multi-byte characters)', async () => {
    const events = await collect(
      streamOf('event: error\nda', 'ta: {"message": "Can’t re', 'ach"}\n', '\n'),
    )
    expect(events).toEqual([{ event: 'error', data: { message: 'Can’t reach' } }])
  })

  it('handles CRLF line endings and a final event without a trailing blank line', async () => {
    const events = await collect(streamOf('event: start\r\ndata: {"thread_id": "x"}\r\n\r\nevent: done\ndata: {"ok": 1}'))
    expect(events.map((e) => e.event)).toEqual(['start', 'done'])
  })
})

describe('parseEvent', () => {
  it('ignores blocks without data or with invalid JSON', () => {
    expect(parseEvent('event: ping')).toBeNull()
    expect(parseEvent('event: step\ndata: {not json')).toBeNull()
  })
})
