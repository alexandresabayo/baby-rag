<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useCorpusStore } from '../stores/corpus'

const store = useCorpusStore()
onMounted(() => store.load().then(() => {
  if (store.ingestStatus.state === 'running') store.startPolling()
}).catch((e) => (store.error = e.message)))
onUnmounted(() => store.stopPolling())
</script>

<template>
  <div>
    <h1>Corpus</h1>
    <p
      v-if="store.error"
      class="error"
      role="alert"
    >
      {{ store.error }}
    </p>
    <div class="actions">
      <button @click="store.sync(false)">
        Sync corpus
      </button>
      <button
        class="secondary"
        @click="store.sync(true)"
      >
        Force re-index
      </button>
      <span
        v-if="store.ingestStatus.state === 'running'"
        class="progress"
      >
        {{ store.ingestStatus.done }}/{{ store.ingestStatus.total }} files
      </span>
    </div>
    <table v-if="store.documents.length">
      <thead>
        <tr>
          <th>Path</th><th>Status</th><th>Chunks</th><th>Indexed</th><th>Error</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="d in store.documents"
          :key="d.id"
        >
          <td>{{ d.path }}</td>
          <td :class="d.status === 'indexed' ? 'ok' : 'failed'">
            {{ d.status === 'indexed' ? '✓ indexed' : '⚠ failed' }}
          </td>
          <td>{{ d.n_chunks }}</td>
          <td>{{ d.indexed_at }}</td>
          <td>{{ d.error }}</td>
        </tr>
      </tbody>
    </table>
    <p
      v-else
      class="empty"
    >
      No documents indexed yet. Put .txt files in the corpus folder and sync.
    </p>
  </div>
</template>

<style scoped>
.actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.progress {
  color: var(--accent-2);
  font-family: var(--font-heading);
  font-size: 0.85rem;
}

table {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.9rem;
}

th,
td {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid var(--muted);
}

th {
  font-family: var(--font-heading);
  font-size: 0.8rem;
}

td.ok { color: var(--accent-3); }
td.failed { color: var(--accent); }

.empty { color: var(--muted); }
.error { color: var(--accent); }
</style>
