import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '总览', icon: 'grid' },
  },
  {
    path: '/watchlist',
    name: 'watchlist',
    component: () => import('@/views/WatchlistView.vue'),
    meta: { title: '自选股', icon: 'star' },
  },
  {
    path: '/market',
    name: 'market',
    component: () => import('@/views/MarketView.vue'),
    meta: { title: '行情', icon: 'trending' },
  },
  {
    path: '/screener',
    name: 'screener',
    component: () => import('@/views/ScreenerView.vue'),
    meta: { title: '智能选股', icon: 'search' },
  },
  {
    path: '/backtest',
    name: 'backtest',
    component: () => import('@/views/BacktestView.vue'),
    meta: { title: '策略回测', icon: 'chart' },
  },
  {
    path: '/trade',
    name: 'trade',
    component: () => import('@/views/TradeView.vue'),
    meta: { title: '模拟盘', icon: 'wallet' },
  },
  {
    path: '/fund',
    name: 'fund',
    component: () => import('@/views/FundView.vue'),
    meta: { title: '选基金', icon: 'pie' },
  },
  {
    path: '/fund/:code',
    name: 'fund-detail',
    component: () => import('@/views/FundDetailView.vue'),
    meta: { title: '基金详情', icon: 'pie' },
  },
  {
    path: '/industry',
    name: 'industry',
    component: () => import('@/views/IndustryView.vue'),
    meta: { title: '行业扫描', icon: 'layers' },
  },
  {
    path: '/report',
    name: 'report',
    component: () => import('@/views/ReportView.vue'),
    meta: { title: '每日日报', icon: 'file' },
  },
  {
    path: '/ai',
    name: 'ai',
    component: () => import('@/views/AIView.vue'),
    meta: { title: 'AI 分析', icon: 'sparkles' },
  },
  {
    path: '/import',
    name: 'import',
    component: () => import('@/views/ImportView.vue'),
    meta: { title: '导入持仓', icon: 'upload' },
  },
  {
    path: '/stock/:code',
    name: 'stock-detail',
    component: () => import('@/views/StockDetailView.vue'),
    meta: { title: '个股详情', icon: 'candlestick' },
  },
  {
    path: '/suitability',
    name: 'suitability',
    component: () => import('@/views/SuitabilityView.vue'),
    meta: { title: '风险测评', icon: 'shield' },
  },
  {
    path: '/audit',
    name: 'audit',
    component: () => import('@/views/AuditView.vue'),
    meta: { title: '审计日志', icon: 'audit' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置', icon: 'settings' },
  },
]

// Use hash history for the packaged desktop app. WebView2 (pywebview) has a
// known race with history.pushState on <a href> navigation that breaks SPA
// routing in the packaged build (the dev server works fine because it ships a
// history fallback). Hash mode keeps every navigation strictly client-side and
// never triggers a server request, which is exactly what we want for a
// single-port localhost desktop app.
const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const title = (to.meta.title as string) || "StockPilot"
  document.title = title + " - StockPilot"

  // Auth guard: redirect to login when not authenticated, unless the route is public
  const token = localStorage.getItem('sp-token')
  if (!to.meta.public && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})

export default router
