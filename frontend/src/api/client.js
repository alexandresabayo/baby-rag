const BASE = import.meta.env.VITE_API_BASE || '/api'

async function jsonOrThrow(res) {
  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.error?.message || message
    } catch {
      /* keep default */
    }
    throw new Error(message)
  }
  return res.json()
}

export function get(path) {
  return fetch(`${BASE}${path}`).then(jsonOrThrow)
}

export function post(path, body) {
  return fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }).then(jsonOrThrow)
}

export function del(path) {
  return fetch(`${BASE}${path}`, { method: 'DELETE' }).then(jsonOrThrow)
}

/**
 * POST and stream an SSE response. onEvent(event, data) is called per event.
 * Returns an object with an abort() method.
 */
export function streamChat({ message, conversationId, topK }, onEvent) {
  const controller = new AbortController()
  const promise = (async () => {
    const res = await fetch(`${BASE}/chat`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        top_k: topK,
      }),
      signal: controller.signal,
    })
    if (!res.ok) {
      let message2 = `HTTP ${res.status}`
      try {
        const body = await res.json()
        message2 = body.error?.message || message2
      } catch {
        /* keep default */
      }
      throw new Error(message2)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop()
      for (const block of blocks) {
        const parsed = parseSseBlock(block)
        if (parsed) onEvent(parsed.event, parsed.data)
      }
    }
    const tail = parseSseBlock(buffer)
    if (tail) onEvent(tail.event, tail.data)
  })()
  return { abort: () => controller.abort(), promise }
}

export function parseSseBlock(block) {
  let event = null
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (event === null) return null
  let parsed = data
  try {
    parsed = JSON.parse(data)
  } catch {
    /* plain string token */
  }
  return { event, data: parsed }
}
