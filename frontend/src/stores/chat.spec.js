import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from './chat'

vi.mock('../api/client', () => {
  let onEvent = () => {}
  return {
    get: vi.fn(async (path) => {
      if (path === '/conversations') return [{ id: 'c1', title: 'T', created_at: '' }]
      if (path.startsWith('/conversations/')) {
        return {
          id: 'c1',
          title: 'T',
          messages: [
            { role: 'user', content: 'hi', sources: null },
            { role: 'assistant', content: 'answer [1]', sources: [{ n: 1, path: 'a.txt' }] },
          ],
        }
      }
      return {}
    }),
    del: vi.fn(async () => ({ status: 'deleted' })),
    streamChat: vi.fn((_body, cb) => {
      onEvent = cb
      return {
        abort: vi.fn(),
        promise: Promise.resolve(),
      }
    }),
    __emit: (e, d) => onEvent(e, d),
  }
})

describe('chat store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads conversations', async () => {
    const store = useChatStore()
    await store.loadConversations()
    expect(store.conversations).toHaveLength(1)
    expect(store.conversations[0].id).toBe('c1')
  })

  it('opens a conversation with messages', async () => {
    const store = useChatStore()
    await store.openConversation('c1')
    expect(store.messages).toHaveLength(2)
    expect(store.messages[1].sources[0].path).toBe('a.txt')
  })

  it('sends a message and accumulates tokens', async () => {
    const store = useChatStore()
    const { __emit } = await import('../api/client')
    store.sendMessage('question?')
    __emit('sources', [{ n: 1, path: 'a.txt' }])
    __emit('token', 'Hello')
    __emit('token', ' world')
    __emit('done', { message_id: 1, conversation_id: 'c9' })
    await Promise.resolve()
    expect(store.messages.at(-2).content).toBe('question?')
    const assistant = store.messages.at(-1)
    expect(assistant.content).toBe('Hello world')
    expect(assistant.sources[0].path).toBe('a.txt')
    expect(store.activeId).toBe('c9')
  })

  it('captures error events', async () => {
    const store = useChatStore()
    const { __emit } = await import('../api/client')
    store.sendMessage('q')
    __emit('error', { message: 'boom' })
    await Promise.resolve()
    expect(store.error).toBe('boom')
  })
})
