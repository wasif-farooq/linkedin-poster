import { describe, expect, it } from 'vitest'
import { FOLD_CHARS, foldPost, formatTokens, parseActivity } from './post'

describe('foldPost', () => {
  it('keeps a short post whole', () => {
    expect(foldPost('Short hook.\n\nBody.')).toEqual(['Short hook.\n\nBody.', ''])
  })

  it('folds after three non-empty lines', () => {
    const text = 'One.\n\nTwo.\n\nThree.\n\nFour.\n\nFive.'
    expect(foldPost(text)).toEqual(['One.\n\nTwo.\n\nThree.', 'Four.\n\nFive.'])
  })

  it('folds at the character limit on a line boundary', () => {
    const first = 'a'.repeat(150)
    const second = 'b'.repeat(100)
    const [before, after] = foldPost(`${first}\n${second}`)
    expect(before).toBe(first)
    expect(after).toBe(second)
  })

  it('cuts a single very long first line at a word boundary', () => {
    const line = 'word '.repeat(80).trim()
    const [before, after] = foldPost(line)
    expect(before.length).toBeLessThanOrEqual(FOLD_CHARS)
    expect(before.endsWith('word')).toBe(true)
    expect(`${before} ${after}`).toBe(line)
  })
})

describe('parseActivity', () => {
  it('maps agent lines and notes', () => {
    expect(
      parseActivity([
        "topic_scout: picked 'Agents as config'",
        'critic: revise (lowest: hook 6)',
        'auto-revision 1/2 queued',
        'researcher: FAILED',
        'human_review: APPROVED',
      ]),
    ).toEqual([
      { agent: 'topic_scout', label: 'Topic Scout', detail: "Picked 'Agents as config'", failed: false },
      { agent: 'critic', label: 'Critic', detail: 'Revise (lowest: hook 6)', failed: false },
      { agent: null, label: '', detail: 'Auto-revision 1/2 queued', failed: false },
      { agent: 'researcher', label: 'Researcher', detail: 'FAILED', failed: true },
      { agent: 'human_review', label: 'Your review', detail: 'APPROVED', failed: false },
    ])
  })
})

describe('formatTokens', () => {
  it('abbreviates thousands', () => {
    expect(formatTokens(950)).toBe('950')
    expect(formatTokens(17899)).toBe('17.9k')
  })
})
