<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { useStatusStore } from './stores/status'
import { onMounted, computed } from 'vue'

const status = useStatusStore()
onMounted(() => status.refresh().catch(() => {}))
const fake = computed(() => status.config?.fake_providers)
</script>

<template>
  <div class="app-shell">
    <nav class="app-nav">
      <RouterLink
        class="brand"
        to="/"
      >
        baby-rag
      </RouterLink>
      <RouterLink to="/">
        Chat
      </RouterLink>
      <RouterLink to="/corpus">
        Corpus
      </RouterLink>
      <RouterLink to="/settings">
        Settings
      </RouterLink>
      <span
        v-if="fake"
        class="fake-badge"
      >Fake providers</span>
    </nav>
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.fake-badge {
  margin-top: auto;
  font-family: var(--font-heading);
  font-size: 0.75rem;
  color: var(--text);
  background: var(--accent-2);
  border-radius: var(--radius);
  padding: 0.25rem 0.5rem;
  text-align: center;
}
</style>
