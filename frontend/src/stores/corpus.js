import { defineStore } from 'pinia'
import { get, post } from '../api/client'

export const useCorpusStore = defineStore('corpus', {
  state: () => ({
    documents: [],
    ingestStatus: { state: 'idle' },
    polling: null,
    error: null,
  }),
  actions: {
    async load() {
      this.documents = await get('/documents')
      this.ingestStatus = await get('/ingest/status')
    },
    async sync(force = false) {
      this.error = null
      try {
        await post('/ingest', { force })
        this.startPolling()
      } catch (err) {
        this.error = err.message
      }
    },
    startPolling() {
      this.stopPolling()
      this.polling = setInterval(async () => {
        this.ingestStatus = await get('/ingest/status')
        if (this.ingestStatus.state !== 'running') {
          this.stopPolling()
          this.documents = await get('/documents').catch(() => this.documents)
        }
      }, 1000)
    },
    stopPolling() {
      if (this.polling) {
        clearInterval(this.polling)
        this.polling = null
      }
    },
  },
})
