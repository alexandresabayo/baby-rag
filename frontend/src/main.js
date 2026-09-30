import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import '@fontsource/lora/400.css'
import '@fontsource/lora/700.css'
import '@fontsource/poppins/400.css'
import '@fontsource/poppins/600.css'
import '@fontsource/poppins/700.css'
import './styles/theme.css'

createApp(App).use(createPinia()).use(router).mount('#app')
