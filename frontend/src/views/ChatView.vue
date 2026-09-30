<script setup>
import { onMounted, ref } from 'vue'
import { useChatStore } from '../stores/chat'
import MessageList from '../components/MessageList.vue'

const store = useChatStore()
const draft = ref('')
const panelSource = ref(null)

onMounted(() => store.loadConversations().catch((e) => (store.error = e.message)))

function send() {
  if (!draft.value.trim()) return
  const text = draft.value
  draft.value = ''
  store.sendMessage(text)
}

function openSource(source) {
  panelSource.value = source
}
</script>

<template>
  <div class="chat-layout">
    <aside class="conv-list">
      <button @click="store.newConversation()">
        New chat
      </button>
      <ul>
        <li
          v-for="c in store.conversations"
          :key="c.id"
          :class="{ active: c.id === store.activeId }"
        >
          <button
            class="link"
            @click="store.openConversation(c.id)"
          >
            {{ c.title }}
          </button>
          <button
            class="small danger"
            :aria-label="`Delete conversation ${c.title}`"
            @click="store.deleteConversation(c.id)"
          >
            ×
          </button>
        </li>
      </ul>
    </aside>

    <section class="chat-main">
      <MessageList
        :messages="store.messages"
        @open-source="openSource"
      />
      <p
        v-if="store.error"
        class="error"
        role="alert"
      >
        {{ store.error }}
      </p>
      <div class="composer">
        <textarea
          v-model="draft"
          rows="2"
          placeholder="Ask something about your corpus…"
          @keydown.enter.exact.prevent="send"
        />
        <button
          v-if="!store.streaming"
          :disabled="!draft.trim()"
          @click="send"
        >
          Send
        </button>
        <button
          v-else
          class="secondary"
          @click="store.stop()"
        >
          Stop
        </button>
      </div>
    </section>

    <aside
      v-if="panelSource"
      class="source-panel"
      aria-label="Cited passage"
    >
      <header>
        <strong>{{ panelSource.path }}</strong>
        <button
          class="small"
          aria-label="Close source panel"
          @click="panelSource = null"
        >
          ×
        </button>
      </header>
      <pre>{{ panelSource.text }}</pre>
      <p class="meta">
        chunk {{ panelSource.chunk_index + 1 }} · chars
        {{ panelSource.start_char }}–{{ panelSource.end_char }}
      </p>
    </aside>
  </div>
</template>

<style scoped>
.chat-layout {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 1rem;
}

.chat-layout:has(.source-panel) {
  grid-template-columns: 180px 1fr 260px;
}

.conv-list ul {
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
}

.conv-list li {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.conv-list li.active .link {
  color: var(--accent);
  font-weight: 700;
}

.conv-list .link {
  flex: 1;
  background: none;
  border: none;
  color: var(--text);
  text-align: left;
  padding: 0.3rem 0.4rem;
  font-family: var(--font-body);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

button.small {
  padding: 0.1rem 0.35rem;
  font-size: 0.8rem;
}

button.danger {
  background: transparent;
  color: var(--muted);
  border: none;
}

.composer {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
  margin-top: 1rem;
}

.composer textarea {
  flex: 1;
  resize: vertical;
}

.error {
  color: var(--accent);
}

.source-panel {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 0.75rem;
  font-size: 0.85rem;
  align-self: start;
  max-height: 70vh;
  overflow: auto;
}

.source-panel header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.source-panel pre {
  white-space: pre-wrap;
  font-family: var(--font-body);
  margin: 0.5rem 0;
}

.source-panel .meta {
  color: var(--muted);
  font-size: 0.75rem;
  margin: 0;
}

@media (max-width: 720px) {
  .chat-layout,
  .chat-layout:has(.source-panel) {
    grid-template-columns: 1fr;
  }
}
</style>
