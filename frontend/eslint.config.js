import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'].map((config) => ({
    ...config,
    rules: Object.fromEntries(
      Object.entries(config.rules || {}).map(([rule, level]) => [
        rule,
        rule.startsWith('vue/') && level === 'error' && !rule.startsWith('vue/no-') ? 'warn' : level,
      ]),
    ),
  })),
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        AbortController: 'readonly',
        FileReader: 'readonly',
        URL: 'readonly',
        TextDecoder: 'readonly',
        TextEncoder: 'readonly',
        Request: 'readonly',
        Response: 'readonly',
        Headers: 'readonly',
        URLSearchParams: 'readonly',
        FormData: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'error',
    },
  },
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
]
