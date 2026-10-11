import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import api from './api'
import { useAuthStore } from './stores/auth'
import './assets/obsidian.css'
import { vLiquid } from './composables/useLiquidGlass'

async function bootstrap() {
  const auth = useAuthStore()
  if (!auth.isLoggedIn.value) {
    try {
      // Desktop / local mode: when the backend runs with auth disabled (the
      // default for the packaged desktop app), /auth/me returns an anonymous
      // admin WITHOUT requiring a token. Provision a local session token so the
      // route guard doesn't bounce the user to /login on every launch. When auth
      // is actually enabled (production), this throws and we stay on /login.
      const res: any = await api.get('/auth/me')
      const d = res?.data ?? res
      if (d && d.username) {
        auth.token.value = 'desktop-local-session'
        localStorage.setItem('sp-token', 'desktop-local-session')
        auth.user.value = {
          username: d.username,
          display_name: d.display_name || d.username,
          role: d.role || 'admin',
        }
      }
    } catch {
      // auth enabled (production) -> keep on /login
    }
  } else {
    await auth.fetchUser()
  }
}

bootstrap().finally(() => {
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.directive('liquid', vLiquid)
  app.mount('#app')
})
