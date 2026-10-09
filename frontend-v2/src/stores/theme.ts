import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(true)

  function initTheme() {
    const saved = localStorage.getItem('sp-theme')
    if (saved) {
      isDark.value = saved === 'dark'
    }
    // 无保存值时默认暗色（Obsidian设计）
    applyTheme()
  }

  function toggle() {
    isDark.value = !isDark.value
    applyTheme()
    localStorage.setItem('sp-theme', isDark.value ? 'dark' : 'light')
  }

  function applyTheme() {
    document.documentElement.setAttribute(
      'data-theme',
      isDark.value ? 'dark' : 'light'
    )
  }

  return { isDark, initTheme, toggle }
})
