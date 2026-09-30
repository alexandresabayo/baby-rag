import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'
import CorpusView from '../views/CorpusView.vue'
import SettingsView from '../views/SettingsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/corpus', name: 'corpus', component: CorpusView },
    { path: '/settings', name: 'settings', component: SettingsView },
  ],
})

export default router
