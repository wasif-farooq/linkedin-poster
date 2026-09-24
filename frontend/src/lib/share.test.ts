import { describe, expect, it } from 'vitest'
import { composeUrl, shareText } from './share'

// Same cases as tests/unit/test_share.py — the two builders must agree.
const POST = 'Hook line.\n\nBody (with parens) & more.\n\n#AI #Agents'

describe('shareText', () => {
  it('puts the article on its own line before the hashtags', () => {
    expect(shareText(POST, 'https://src.dev/a')).toBe(
      'Hook line.\n\nBody (with parens) & more.\n\nhttps://src.dev/a\n\n#AI #Agents',
    )
    expect(shareText('No tags here', 'https://src.dev/a')).toBe('No tags here\n\nhttps://src.dev/a')
    expect(shareText(POST)).toBe(POST)
  })
})

describe('composeUrl', () => {
  it('round-trips the text exactly', () => {
    const url = new URL(composeUrl(POST))
    expect(`${url.origin}${url.pathname}`).toBe('https://www.linkedin.com/feed/')
    expect(url.searchParams.get('shareActive')).toBe('true')
    expect(url.searchParams.get('text')).toBe(POST)
    expect(url.search).not.toContain('+') // spaces as %20
  })
})
