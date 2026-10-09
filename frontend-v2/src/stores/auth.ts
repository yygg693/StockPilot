import { ref, computed } from 'vue'
import api from '@/api'

interface UserInfo {
  username: string
  display_name: string
  role: string
}

const token = ref<string | null>(localStorage.getItem('sp-token'))
const user = ref<UserInfo | null>(null)

export function useAuthStore() {
  const isLoggedIn = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const res: any = await api.post('/auth/login', { username, password })
    const data = res.data || res
    token.value = data.token
    localStorage.setItem('sp-token', data.token)
    if (data.user) {
      user.value = data.user
    } else {
      await fetchUser()
    }
  }

  async function register(username: string, password: string, displayName?: string) {
    await api.post('/auth/register', {
      username,
      password,
      display_name: displayName || username,
    })
    await login(username, password)
  }

  async function fetchUser() {
    try {
      const res: any = await api.get('/auth/me')
      const d = res.data || res
      user.value = {
        username: d.username,
        display_name: d.display_name || d.username,
        role: d.role || 'user',
      }
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('sp-token')
  }

  return { token, user, isLoggedIn, login, register, fetchUser, logout }
}
