<script setup>
import { useStatusStore } from '../stores/status'
import { onMounted, ref } from 'vue'

const status = useStatusStore()
const error = ref(null)
onMounted(() => status.refresh().catch((e) => (error.value = e.message)))

function fmt(value) {
  return value === true ? 'yes' : value === false ? 'no' : String(value)
}
</script>

<template>
  <div>
    <h1>Settings &amp; status</h1>
    <p
      v-if="error"
      class="error"
      role="alert"
    >
      {{ error }}
    </p>

    <section
      v-if="status.health"
      aria-label="Health checks"
    >
      <h2>Health</h2>
      <ul class="health">
        <li :class="status.health.sqlite.ok ? 'ok' : 'failed'">
          SQLite — {{ status.health.sqlite.chunks }} chunks
        </li>
        <li :class="status.health.chroma.ok ? 'ok' : 'failed'">
          ChromaDB — {{ status.health.chroma.chunks }} chunks
        </li>
        <li :class="status.health.counts_match ? 'ok' : 'failed'">
          Chunk counts match — {{ fmt(status.health.counts_match) }}
        </li>
        <li :class="status.health.embedding_meta_ok ? 'ok' : 'failed'">
          Embedding model matches — {{ fmt(status.health.embedding_meta_ok) }}
          <span v-if="status.health.embedding_meta_message">
            {{ status.health.embedding_meta_message }}
          </span>
        </li>
      </ul>
    </section>

    <section
      v-if="status.config"
      aria-label="Effective configuration"
    >
      <h2>Configuration</h2>
      <table>
        <tbody>
          <tr
            v-for="(value, key) in status.config"
            :key="key"
          >
            <th>{{ key }}</th>
            <td>{{ fmt(value) }}</td>
          </tr>
        </tbody>
      </table>
      <p
        v-if="status.config.fake_providers"
        class="badge"
      >
        FAKE PROVIDERS — running with deterministic offline fakes.
      </p>
    </section>
  </div>
</template>

<style scoped>
.health {
  list-style: none;
  padding: 0;
  font-family: var(--font-heading);
  font-size: 0.9rem;
}

.health li.ok::before { content: '✓ '; color: var(--accent-3); }
.health li.failed::before { content: '⚠ '; }

table {
  border-collapse: collapse;
  font-size: 0.85rem;
}

th,
td {
  text-align: left;
  padding: 0.25rem 0.75rem 0.25rem 0;
  border-bottom: 1px solid var(--surface);
}

th {
  font-family: var(--font-heading);
  font-weight: 600;
  font-size: 0.8rem;
  white-space: nowrap;
}

.badge {
  display: inline-block;
  background: var(--accent-2);
  color: var(--text);
  border-radius: var(--radius);
  padding: 0.25rem 0.6rem;
  font-family: var(--font-heading);
  font-size: 0.8rem;
}

.error { color: var(--accent); }
</style>
