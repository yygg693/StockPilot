<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const displayName = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (mode.value === 'login') {
      await auth.login(username.value, password.value)
    } else {
      await auth.register(username.value, password.value, displayName.value)
    }
    const redirect = (router.currentRoute.value.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    error.value = e.message || '操作失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="logo">Stock<em>Pilot</em></div>
        <div class="subtitle">Investment Intelligence Platform</div>
      </div>

      <div class="tab-switch">
        <button :class="{ active: mode === 'login' }" @click="mode = 'login'">登录</button>
        <button :class="{ active: mode === 'register' }" @click="mode = 'register'">注册</button>
      </div>

      <form @submit.prevent="submit" class="login-form">
        <div class="field">
          <label>用户名</label>
          <input v-model="username" type="text" placeholder="请输入用户名" required autocomplete="username" />
        </div>
        <div class="field">
          <label>密码</label>
          <input v-model="password" type="password" placeholder="请输入密码" required autocomplete="current-password" />
        </div>
        <div v-if="mode === 'register'" class="field">
          <label>显示名称（可选）</label>
          <input v-model="displayName" type="text" placeholder="用于界面显示" />
        </div>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <button type="submit" class="submit-btn" :disabled="loading">
          {{ loading ? '处理中...' : (mode === 'login' ? '登 录' : '注 册') }}
        </button>
      </form>

      <div class="login-footer">
        <span v-if="mode === 'login'">还没有账号？</span>
        <a v-if="mode === 'login'" @click="mode = 'register'">立即注册</a>
        <span v-if="mode === 'register'">已有账号？</span>
        <a v-if="mode === 'register'" @click="mode = 'login'">去登录</a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  display: flex; align-items: center; justify-content: center;
  height: 100vh; background: var(--bg-base);
}
.login-card {
  width: 400px; padding: 40px 36px; border-radius: 16px;
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  box-shadow: 0 8px 32px rgba(0,0,0,0.12);
}
.login-header { text-align: center; margin-bottom: 28px; }
.logo {
  font-family: var(--font-serif); font-size: 28px; font-weight: 700;
  color: var(--text-primary);
}
.logo em { font-style: italic; color: var(--accent); }
.subtitle {
  font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
  color: var(--text-tertiary); margin-top: 6px;
}
.tab-switch {
  display: flex; gap: 0; margin-bottom: 24px;
  border-radius: 8px; overflow: hidden; border: 1px solid var(--border-default);
}
.tab-switch button {
  flex: 1; padding: 10px; border: none; background: var(--bg-overlay);
  color: var(--text-secondary); font-size: 14px; font-weight: 500; cursor: pointer;
  transition: all 0.2s;
}
.tab-switch button.active {
  background: var(--accent); color: #fff;
}
.login-form { display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12px; font-weight: 500; color: var(--text-secondary); }
.field input {
  padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 14px;
  transition: all 0.2s;
}
.field input:focus {
  outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.error-msg {
  color: var(--down); font-size: 13px; padding: 8px 12px;
  background: rgba(239,68,68,0.08); border-radius: 8px;
}
.submit-btn {
  margin-top: 8px; padding: 12px; border: none; border-radius: 8px;
  background: var(--accent); color: #fff; font-size: 15px; font-weight: 600;
  cursor: pointer; transition: all 0.2s;
}
.submit-btn:hover { opacity: 0.9; }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.login-footer {
  margin-top: 20px; text-align: center; font-size: 13px;
  color: var(--text-tertiary);
}
.login-footer a {
  color: var(--accent); cursor: pointer; margin-left: 4px;
}
</style>
