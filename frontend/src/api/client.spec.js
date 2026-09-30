import { describe, expect, it } from 'vitest'
import { parseSseBlock } from './client'

describe('parseSseBlock', () => {
  it('parses a sources event with JSON data', () => {
    const block = 'event: sources\ndata: [{"n":1,"path":"a.txt"}]'
    const parsed = parseSseBlock(block)
    expect(parsed.event).toBe('sources')
    expect(parsed.data[0].path).toBe('a.txt')
  })

  it('parses a token event with plain text data', () => {
    const block = 'event: token\ndata: Hello '
    const parsed = parseSseBlock(block)
    expect(parsed.event).toBe('token')
    expect(parsed.data).toBe('Hello ')
  })

  it('parses a done event', () => {
    const block = 'event: done\ndata: {"message_id":3,"conversation_id":"x"}'
    const parsed = parseSseBlock(block)
    expect(parsed.event).toBe('done')
    expect(parsed.data.conversation_id).toBe('x')
  })

  it('returns null for an empty block', () => {
    expect(parseSseBlock('')).toBeNull()
  })

  it('handles multiline data', () => {
    const block = 'event: token\ndata: line1\ndata: line2'
    const parsed = parseSseBlock(block)
    expect(parsed.event).toBe('token')
    expect(parsed.data).toBe('line1line2')
  })

  it('ignores comment lines', () => {
    const block = ': ping\nevent: token\ndata: x'
    expect(parseSseBlock(block).data).toBe('x')
  })
})
