import { defineStore } from 'pinia'
import { get } from '../api/client'

export const useStatusStore = defineStore('status', {
  state: () => ({
    health: null,
    config: null,
  }),
  actions: {
    async refresh() {
      ;[this.health, this.config] = await Promise.all([
        get('/health'),
        get('/config'),
      ])
    },
  },
})
