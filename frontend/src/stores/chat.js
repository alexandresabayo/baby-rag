import { defineStore } from 'pinia'
import { del, get, streamChat } from '../api/client'

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversations: [],
    activeId: null,
    messages: [],
    streaming: false,
    error: null,
    activeStream: null,
  }),
  actions: {
    async loadConversations() {
      this.conversations = await get('/conversations')
    },
    async openConversation(id) {
      this.activeId = id
      this.error = null
      if (!id) {
        this.messages = []
        return
      }
      const detail = await get(`/conversations/${id}`)
      this.messages = detail.messages
    },
    newConversation() {
      this.activeId = null
      this.messages = []
      this.error = null
    },
    async deleteConversation(id) {
      await del(`/conversations/${id}`)
      await this.loadConversations()
      if (this.activeId === id) this.newConversation()
    },
    sendMessage(text) {
      if (!text.trim() || this.streaming) return
      this.error = null
      this.streaming = true
      this.messages.push({ role: 'user', content: text, sources: null })
      const assistant = { role: 'assistant', content: '', sources: [] }
      this.messages.push(assistant)

      const { abort, promise } = streamChat(
        { message: text, conversationId: this.activeId },
        (event, data) => {
          if (event === 'sources') assistant.sources = data
          else if (event === 'token') assistant.content += data
          else if (event === 'error') this.error = data.message
          else if (event === 'done') this.activeId = data.conversation_id
        },
      )
      this.activeStream = { abort }
      promise
        .catch((err) => {
          if (err.name !== 'AbortError') this.error = err.message
        })
        .finally(() => {
          this.streaming = false
          this.activeStream = null
          this.loadConversations().catch(() => {})
        })
    },
    stop() {
      this.activeStream?.abort()
    },
  },
})
