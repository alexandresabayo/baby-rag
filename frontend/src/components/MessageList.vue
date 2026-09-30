<script setup>
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = defineProps({
  messages: { type: Array, required: true },
})

const emit = defineEmits(['open-source'])

function render(content) {
  return DOMPurify.sanitize(marked.parse(content || '', { async: false }), {
    FORBID_TAGS: ['img', 'style', 'iframe', 'form', 'script'],
  })
}

const hasMessages = computed(() => props.messages.length > 0)
</script>

<template>
  <div
    class="message-list"
    aria-live="polite"
  >
    <p
      v-if="!hasMessages"
      class="empty"
    >
      No messages yet. Ask a question about the files in your corpus.
    </p>
    <article
      v-for="(m, i) in messages"
      :key="i"
      :class="['msg', m.role]"
    >
      <p class="who">
        {{ m.role === 'user' ? 'You' : 'Assistant' }}
      </p>
      <div
        v-if="m.role === 'assistant'"
        class="body"
        v-html="render(m.content)"
      />
      <p
        v-else
        class="body"
      >
        {{ m.content }}
      </p>
      <div
        v-if="m.role === 'assistant' && m.sources?.length"
        class="citations"
      >
        <button
          v-for="s in m.sources"
          :key="s.n"
          class="chip"
          :aria-label="`Open source ${s.n}: ${s.path}`"
          @click="emit('open-source', s)"
        >
          [{{ s.n }}]
        </button>
      </div>
    </article>
  </div>
</template>

<style scoped>
.message-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  min-height: 40vh;
}

.empty {
  color: var(--muted);
}

.msg .who {
  font-family: var(--font-heading);
  font-size: 0.75rem;
  color: var(--muted);
  margin: 0;
}

.msg.assistant .body {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 0.6rem 0.9rem;
}

.citations {
  display: flex;
  gap: 0.35rem;
  margin-top: 0.35rem;
}

.chip {
  background: var(--accent);
  color: #fff;
  border-radius: 999px;
  padding: 0.05rem 0.5rem;
  font-size: 0.75rem;
}

.msg :deep(p) {
  margin: 0 0 0.5rem;
}

.msg :deep(p:last-child) {
  margin-bottom: 0;
}
</style>
