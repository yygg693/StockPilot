<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useThemeStore } from "@/stores/theme"
import { useAuthStore } from "@/stores/auth"
import ParticleCanvas from "@/components/ParticleCanvas.vue"
import SearchAutocomplete from "@/components/SearchAutocomplete.vue"

const router = useRouter()
const route = useRoute()
const theme = useThemeStore()
const auth = useAuthStore()
const userInfo = computed(() => auth.user.value)
const searchCode = ref("")
const clock = ref("")
const marketStatus = ref({ text: "", state: "closed" })
let timer: number

onMounted(async () => {
  if (auth.isLoggedIn && !auth.user) {
    await auth.fetchUser()
  }
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}

function getMarketStatus(): { text: string; state: string } {
  const now = new Date()
  const day = now.getDay() // 0=Sun, 6=Sat
  const h = now.getHours()
  const m = now.getMinutes()
  const t = h * 60 + m // minutes since midnight

  // Weekend
  if (day === 0 || day === 6) {
    return { text: "\u5468\u672b\u4f11\u5e02", state: "closed" }
  }
  // Before 9:15
  if (t < 9 * 60 + 15) {
    return { text: "\u76d8\u524d", state: "pre" }
  }
  // 9:15 - 9:25 集合竞价
  if (t < 9 * 60 + 25) {
    return { text: "\u96c6\u5408\u7ade\u4ef7", state: "auction" }
  }
  // 9:25 - 9:30 等待开盘
  if (t < 9 * 60 + 30) {
    return { text: "\u5f85\u5f00\u76d8", state: "pre" }
  }
  // 9:30 - 11:30 上午连续竞价
  if (t < 11 * 60 + 30) {
    return { text: "\u4ea4\u6613\u4e2d", state: "open" }
  }
  // 11:30 - 13:00 午间休市
  if (t < 13 * 60) {
    return { text: "\u5348\u95f4\u4f11\u5e02", state: "noon" }
  }
  // 13:00 - 15:00 下午连续竞价
  if (t < 15 * 60) {
    return { text: "\u4ea4\u6613\u4e2d", state: "open" }
  }
  // After 15:00
  return { text: "\u5df2\u6536\u76d8", state: "closed" }
}

function onStockSelect(item: any) {
  const raw = item.code.replace(/^(sh|sz)/, '')
  const isFund = /^[023]/.test(raw) || (/^1/.test(raw) && !/^(15|16)/.test(raw))
  router.push({ path: (isFund ? "/fund/" : "/stock/") + item.code })
}

function tick() {
  const now = new Date()
  const days = ["\u5468\u65e5", "\u5468\u4e00", "\u5468\u4e8c", "\u5468\u4e09", "\u5468\u56db", "\u5468\u4e94", "\u5468\u516d"]
  const dateStr = now.getFullYear() + "-" + String(now.getMonth() + 1).padStart(2, "0") + "-" + String(now.getDate()).padStart(2, "0")
  clock.value = dateStr + " " + days[now.getDay()] + " " + now.toLocaleTimeString("zh-CN", { hour12: false })
  marketStatus.value = getMarketStatus()
}

onMounted(() => { tick(); timer = window.setInterval(tick, 1000) })
onUnmounted(() => clearInterval(timer))

const navTop = [
  { path: "/", label: "总览", icon: "grid" },
  { path: "/watchlist", label: "自选股", icon: "star" },
  { path: "/market", label: "行情", icon: "trending" },
]
const navStrategy = [
  { path: "/screener", label: "智能选股", icon: "search" },
  { path: "/backtest", label: "策略回测", icon: "chart" },
  { path: "/trade", label: "模拟盘", icon: "wallet" },
  { path: "/import", label: "导入持仓", icon: "upload" },
  { path: "/fund", label: "选基金", icon: "pie" },
]
const navResearch = [
  { path: "/industry", label: "行业扫描", icon: "layers" },
  { path: "/report", label: "每日日报", icon: "file" },
  { path: "/ai", label: "AI 分析", icon: "cpu" },
]
const navCompliance = [
  { path: "/suitability", label: "风险测评", icon: "shield" },
  { path: "/audit", label: "审计日志", icon: "audit" },
]
</script>

<template>
  <ParticleCanvas />
  <div class="app">
    <aside class="sidebar">
      <div class="logo-area">
        <div class="logo">Stock<em>Pilot</em></div>
        <div class="logo-sub">Investment Intelligence</div>
        <div class="logo-line"></div>
      </div>
      <div class="nav-section">
        <router-link
          v-for="item in navTop"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
        >
          <svg v-if="item.icon === 'grid'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
          <svg v-else-if="item.icon === 'star'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
          <svg v-else-if="item.icon === 'trending'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
          <svg v-else-if="item.icon === 'search'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <svg v-else-if="item.icon === 'chart'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-9"/></svg>
          <svg v-else-if="item.icon === 'wallet'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3h-8l-2 4h12l-2-4z"/></svg>
          <svg v-else-if="item.icon === 'pie'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
          <svg v-else-if="item.icon === 'layers'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
          <svg v-else-if="item.icon === 'file'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></svg>
          <span>{{ item.label }}</span>
        </router-link>

        <div class="nav-label">策略工具</div>
        <router-link
          v-for="item in navStrategy"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
        >
          <svg v-if="item.icon === 'search'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <svg v-else-if="item.icon === 'chart'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-9"/></svg>
          <svg v-else-if="item.icon === 'wallet'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3h-8l-2 4h12l-2-4z"/></svg>
          <svg v-else-if="item.icon === 'upload'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
          <span>{{ item.label }}</span>
        </router-link>

        <div class="nav-label">研究</div>
        <router-link
          v-for="item in navResearch"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
        >
          <svg v-if="item.icon === 'layers'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
          <svg v-else-if="item.icon === 'file'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/></svg>
          <span>{{ item.label }}</span>
        </router-link>

        <div class="nav-label">合规管理</div>
        <router-link
          v-for="item in navCompliance"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
        >
          <svg v-if="item.icon === 'shield'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span>{{ item.label }}</span>
        </router-link>
      </div>
      <div class="sidebar-footer">
        <div v-if="userInfo" class="user-info">
          <div class="user-avatar">{{ userInfo.display_name?.charAt(0) || userInfo.username?.charAt(0) || 'U' }}</div>
          <div class="user-detail">
            <div class="user-name">{{ userInfo.display_name || userInfo.username }}</div>
            <div class="user-role">{{ userInfo.role || 'user' }}</div>
          </div>
          <button class="btn-logout" @click="handleLogout" title="退出登录">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
        <router-link v-else to="/login" class="nav-item">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          <span>登录</span>
        </router-link>
        <router-link to="/settings" class="nav-item" :class="{ active: route.path === '/settings' }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span>设置</span>
        </router-link>
      </div>
    </aside>

    <div class="main">
      <header class="topbar">
        <div class="search-box">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-tertiary)" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <SearchAutocomplete v-model="searchCode" @select="onStockSelect" />
          <span class="search-kbd">&#8984;K</span>
        </div>
        <div class="topbar-right">
          <div class="market-badge" :class="'status-' + marketStatus.state">
            <span class="market-dot"></span>
            {{ marketStatus.text }}
          </div>
          <span class="clock">{{ clock }}</span>
          <div class="theme-toggle" @click="theme.toggle()" title="切换主题">
            <div class="theme-toggle-knob">
              <svg v-if="theme.isDark" viewBox="0 0 24 24" fill="currentColor"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
              <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
            </div>
          </div>
        </div>
      </header>
      <div class="content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<style scoped>
.app { display: flex; height: 100vh; position: relative; z-index: 1; }

.sidebar {
  width: 232px; background: var(--bg-surface); border-right: 1px solid var(--border-subtle);
  display: flex; flex-direction: column; padding: 24px 0 16px; flex-shrink: 0;
  transition: background var(--transition-theme), border-color var(--transition-theme);
  overflow-y: auto;
}
.logo-area { padding: 0 24px 20px; border-bottom: 1px solid var(--border-subtle); margin-bottom: 12px; }
.logo { font-family: var(--font-serif); font-size: 20px; font-weight: 700; letter-spacing: -0.3px; color: var(--text-primary); transition: color var(--transition-theme); }
.logo em { font-style: italic; color: var(--accent); }
.logo-sub { font-size: 10px; font-weight: 500; letter-spacing: 1.5px; text-transform: uppercase; color: var(--text-tertiary); margin-top: 4px; }
.logo-line { width: 36px; height: 2px; margin-top: 10px; background: linear-gradient(90deg, var(--accent), transparent); border-radius: 1px; }

.nav-section { padding: 0 12px; flex: 1; }
.nav-item {
  display: flex; align-items: center; gap: 11px; padding: 9px 12px; border-radius: var(--radius-sm);
  font-size: 13px; font-weight: 500; color: var(--text-secondary); cursor: pointer;
  position: relative; transition: all 0.18s ease; user-select: none; text-decoration: none;
}
.nav-item:hover { background: var(--bg-overlay); color: var(--text-primary); }
.nav-item.active { background: var(--accent-dim); color: var(--accent-soft); }
.nav-item.active::before {
  content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 3px; height: 18px; border-radius: 2px; background: var(--accent);
  box-shadow: 0 0 8px var(--accent-glow);
}
.nav-label {
  font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 1.2px;
  color: var(--text-tertiary); padding: 12px 12px 6px; transition: color var(--transition-theme);
}
.nav-item svg { width: 17px; height: 17px; flex-shrink: 0; opacity: 0.65; transition: opacity 0.18s; }
.nav-item:hover svg, .nav-item.active svg { opacity: 1; }

.sidebar-footer { margin-top: auto; padding: 12px 12px 0; border-top: 1px solid var(--border-subtle); }
.user-info {
  display: flex; align-items: center; gap: 10px; padding: 8px 12px; margin-bottom: 4px;
  border-radius: var(--radius-sm); background: var(--bg-overlay);
}
.user-avatar {
  width: 32px; height: 32px; border-radius: 50%; background: var(--accent);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600; flex-shrink: 0;
}
.user-detail { flex: 1; min-width: 0; }
.user-name { font-size: 13px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-role { font-size: 11px; color: var(--text-tertiary); }
.btn-logout {
  width: 28px; height: 28px; border: none; border-radius: 6px; cursor: pointer;
  background: transparent; color: var(--text-tertiary); display: flex; align-items: center; justify-content: center;
}
.btn-logout:hover { background: var(--bg-elevated); color: var(--down); }

.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

.topbar {
  height: 56px; border-bottom: 1px solid var(--border-subtle); display: flex; align-items: center;
  padding: 0 28px; gap: 16px; flex-shrink: 0; background: var(--bg-surface);
  transition: background var(--transition-theme), border-color var(--transition-theme);
}
.search-box {
  display: flex; align-items: center; gap: 9px; background: var(--bg-overlay);
  border: 1px solid var(--border-subtle); border-radius: var(--radius-sm);
  padding: 8px 14px; width: 280px; transition: all 0.2s ease;
}
.search-box:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); background: var(--bg-elevated); }
.search-box svg { flex-shrink: 0; }
.search-kbd { font-family: var(--font-mono); font-size: 10px; color: var(--text-tertiary); border: 1px solid var(--border-default); border-radius: 4px; padding: 2px 5px; flex-shrink: 0; }

.topbar-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.market-badge { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; color: var(--text-secondary); }
.market-dot { width: 7px; height: 7px; border-radius: 50%; background: #6b7280; }
.status-open .market-dot { background: var(--down); animation: pulse-dot 2s ease-in-out infinite; }
.status-auction .market-dot { background: #f5c842; animation: pulse-dot 1.5s ease-in-out infinite; }
.status-pre .market-dot, .status-noon .market-dot { background: #f5c842; }
.status-closed .market-dot { background: #6b7280; }
.clock { font-family: var(--font-mono); font-size: 12px; font-weight: 500; color: var(--text-secondary); letter-spacing: 0.3px; }

.theme-toggle {
  position: relative; width: 52px; height: 28px; border-radius: 14px;
  background: var(--bg-overlay); border: 1px solid var(--border-default);
  cursor: pointer; transition: all 0.3s ease; display: flex; align-items: center; padding: 0 4px;
}
.theme-toggle:hover { border-color: var(--accent); }
.theme-toggle-knob {
  width: 20px; height: 20px; border-radius: 50%; background: var(--accent);
  box-shadow: 0 2px 6px var(--accent-glow);
  transition: transform 0.35s cubic-bezier(0.68, -0.15, 0.27, 1.15);
  display: flex; align-items: center; justify-content: center;
}
[data-theme="light"] .theme-toggle-knob { transform: translateX(23px); }
.theme-toggle-knob svg { width: 11px; height: 11px; color: var(--bg-base); }

.content { flex: 1; overflow-y: auto; padding: 24px 28px; scroll-behavior: smooth; }
.content::-webkit-scrollbar { width: 5px; }
.content::-webkit-scrollbar-track { background: transparent; }
.content::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 3px; }

@media (max-width: 860px) { .sidebar { display: none; } }
</style>
