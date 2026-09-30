import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageList from './MessageList.vue'

describe('MessageList', () => {
  const messages = [
    { role: 'user', content: 'What is this about?', sources: null },
    {
      role: 'assistant',
      content: 'It is about **citations**.',
      sources: [
        { n: 1, path: 'sample-essay.txt', chunk_index: 0, text: 'chunk text', start_char: 0, end_char: 10 },
      ],
    },
  ]

  it('renders roles and sanitized markdown', () => {
    const wrapper = mount(MessageList, { props: { messages } })
    expect(wrapper.text()).toContain('You')
    expect(wrapper.text()).toContain('Assistant')
    expect(wrapper.find('.body strong').text()).toBe('citations')
  })

  it('sanitizes HTML in assistant content', () => {
    const evil = [{
      role: 'assistant',
      content: 'safe <img src=x onerror="alert(1)"> text',
      sources: [],
    }]
    const wrapper = mount(MessageList, { props: { messages: evil } })
    expect(wrapper.html()).not.toContain('onerror')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('renders citation chips and emits open-source', async () => {
    const wrapper = mount(MessageList, { props: { messages } })
    const chips = wrapper.findAll('.chip')
    expect(chips).toHaveLength(1)
    expect(chips[0].text()).toBe('[1]')
    await chips[0].trigger('click')
    expect(wrapper.emitted('open-source')[0][0].path).toBe('sample-essay.txt')
  })

  it('shows an empty state when there are no messages', () => {
    const wrapper = mount(MessageList, { props: { messages: [] } })
    expect(wrapper.text()).toContain('No messages yet')
  })
})
