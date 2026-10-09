import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/obsidian.css'
import { vLiquid } from './composables/useLiquidGlass'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.directive('liquid', vLiquid)
app.mount('#app')
