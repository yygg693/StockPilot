<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { getIndex, getBreadth, getWatchlist, getMarketSummary, getBriefing, getAlerts } from "@/api"
import { useStaleRefresh } from "@/composables/useStaleRefresh"

const indices = ref<any[]>([])
const breadth = ref<any>(null)
const watchlist = ref<any[]>([])
const loading = ref(true)
const router = useRouter()

const aiSummary = ref('')
const aiLoading = ref(false)
const aiError = ref('')

// Phase 2: Briefing & Alerts
const briefing = ref<any>(null)
const briefingLoading = ref(false)
const alerts = ref<any[]>([])
const alertsLoading = ref(false)

async function fetchBriefing() {
  briefingLoading.value = true
  try {
    const res: any = await getBriefing()
    briefing.value = res.data || null
  } catch (e: any) {
    briefing.value = { summary: "简报获取失败: " + e.message }
  } finally { briefingLoading.value = false }
}

async function fetchAlerts() {
  alertsLoading.value = true
  try {
    const res: any = await getAlerts()
    alerts.value = res.data || []
  } catch {} finally { alertsLoading.value = false }
}

async function fetchAISummary() {
  aiLoading.value = true
  aiError.value = ''
  try {
    const res: any = await getMarketSummary()
    const d = res?.data || res
    if (d?.summary) { aiSummary.value = d.summary }
    else { aiError.value = d?.error || 'AI 未返回内容' }
  } catch (e: any) {
    aiError.value = e.message || 'AI 请求失败'
  } finally {
    aiLoading.value = false
  }
}

function goStock(code: string) {
  const raw = code.replace(/^(sh|sz)/, '')
  const isFund = /^[023]/.test(raw) || (/^1/.test(raw) && !/^(15|16)/.test(raw))
  router.push(isFund ? "/fund/" + code : "/stock/" + code)
}

function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + v.toFixed(2) + "%" }
function fmtChange(v: number) { return (v > 0 ? "+" : "") + v.toFixed(2) }

async function load() {
  try {
    const [idxRes, brRes, wlRes] = await Promise.all([
      getIndex().catch(() => ({ data: [] })),
      getBreadth().catch(() => ({ data: null })),
      getWatchlist().catch(() => ({ data: [] })),
    ])
    indices.value = (idxRes as any).data || []
    breadth.value = (brRes as any).data || null
    watchlist.value = (wlRes as any).data || []
  } finally {
    loading.value = false
  }
  fetchAISummary()
  fetchBriefing()
  fetchAlerts()
}

// First visit loads immediately; returning to this cached view refreshes only
// when the data is older than 60s (instant switch, no stale-forever).
useStaleRefresh(load)
</script>

<template>
  <div class="dashboard">
    <!-- INDEX CARDS -->
    <div class="index-grid">
      <div v-for="(idx, i) in indices" :key="idx.code" class="index-card animate-in" v-liquid :class="'delay-' + (i + 1)">
        <div class="index-name">{{ idx.name }}</div>
        <div class="index-value" :class="valClass(idx.change_pct)">{{ idx.price?.toLocaleString("zh-CN", { minimumFractionDigits: 2 }) }}</div>
        <div class="index-change" :class="valClass(idx.change_pct)">
          {{ fmtChange(idx.change || 0) }} ({{ fmtPct(idx.change_pct || 0) }})
        </div>
        <svg class="index-spark" width="64" height="28" viewBox="0 0 64 28">
          <polyline v-if="idx.change_pct >= 0" points="0,22 8,20 16,21 24,16 32,18 40,12 48,14 56,8 64,6" fill="none" stroke="var(--up)" stroke-width="1.5" opacity="0.6"/>
          <polyline v-else points="0,8 8,10 16,9 24,14 32,12 40,16 48,15 56,20 64,22" fill="none" stroke="var(--down)" stroke-width="1.5" opacity="0.6"/>
        </svg>
      </div>
      <div v-if="!indices.length && loading" class="index-card placeholder animate-in delay-1">
        <span class="loading-text">加载中...</span>
      </div>
    </div>

    <!-- ALERTS STRIP -->
    <div v-if="alerts.length" class="alerts-strip animate-in delay-2">
      <div v-for="(a, i) in alerts" :key="i" class="alert-item" :class="a.level" @click="goStock(a.code)">
        <span class="alert-dot"></span>
        <span class="alert-msg">{{ a.message }}</span>
      </div>
    </div>

    <!-- AI BRIEFING -->
    <div class="briefing-card card animate-in delay-2" v-liquid>
      <div class="briefing-head">
        <div class="ai-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>
          AI 每日简报
        </div>
        <div class="briefing-meta" v-if="briefing?.date">{{ briefing.date }} {{ briefing.time }}</div>
        <button class="ai-refresh" @click="fetchBriefing" :disabled="briefingLoading" title="刷新简报">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
        </button>
      </div>
      <div v-if="briefingLoading" class="briefing-body" style="opacity:0.5">正在生成今日简报...</div>
      <div v-else-if="briefing?.summary" class="briefing-body">{{ briefing.summary }}</div>
      <div v-else class="briefing-body" style="opacity:0.5">点击刷新获取 AI 每日投资简报</div>
    </div>

    <!-- WATCHLIST TABLE -->
    <div class="section-head animate-in delay-3">
      <span class="section-title">自选股</span>
      <router-link class="section-link" to="/watchlist">管理 →</router-link>
    </div>
    <div class="table-wrap animate-in delay-4">
      <table v-if="watchlist.length">
        <thead>
          <tr>
            <th>股票</th>
            <th class="r">现价</th>
            <th class="r">涨跌幅</th>
            <th class="r">成交额</th>
            <th class="r">市盈率</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in watchlist" :key="s.code" class="clickable-row" @click="goStock(s.code)">
            <td><div class="cell-stock"><span class="cell-name">{{ s.name || s.code }}</span><span class="cell-code">{{ s.code }}</span></div></td>
            <td class="r mono" :class="valClass(s.change_pct)">{{ s.price?.toFixed(2) }}</td>
            <td class="r"><span class="pill" :class="s.change_pct >= 0 ? 'pill-up' : 'pill-down'">{{ fmtPct(s.change_pct || 0) }}</span></td>
            <td class="r mono">{{ s.amount ? (s.amount / 1e8).toFixed(1) + '亿' : '--' }}</td>
            <td class="r mono">{{ s.pe ? s.pe.toFixed(1) : '--' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-table">暂无自选股，去交易页面添加</div>
    </div>

    <!-- BOTTOM GRID -->
    <div class="bottom-grid animate-in delay-5">
      <!-- Market Breadth -->
      <div class="card" v-liquid>
        <div class="card-title">市场宽度</div>
        <div class="breadth-bar">
          <div class="breadth-seg breadth-up" :style="{ width: (breadth?.up_pct || 45) + '%' }"></div>
          <div class="breadth-seg breadth-flat" :style="{ width: (breadth?.flat_pct || 10) + '%' }"></div>
          <div class="breadth-seg breadth-down" :style="{ width: (breadth?.down_pct || 45) + '%' }"></div>
        </div>
        <div class="breadth-labels">
          <span class="val-up">↑ {{ breadth?.up_count || '--' }}</span>
          <span class="flat-label">— {{ breadth?.flat_count || '--' }}</span>
          <span class="val-down">↓ {{ breadth?.down_count || '--' }}</span>
        </div>
        <div class="breadth-stats">
          <div><div class="breadth-stat-label">涨停</div><div class="breadth-stat-val val-up">{{ breadth?.limit_up || '--' }}</div></div>
          <div><div class="breadth-stat-label">跌停</div><div class="breadth-stat-val val-down">{{ breadth?.limit_down || '--' }}</div></div>
          <div><div class="breadth-stat-label">北向净流入</div><div class="breadth-stat-val">{{ breadth?.north_flow ? (breadth.north_flow > 0 ? '+' : '') + breadth.north_flow.toFixed(1) + '亿' : '--' }}</div></div>
          <div><div class="breadth-stat-label">两市成交</div><div class="breadth-stat-val">{{ breadth?.total_amount ? (breadth.total_amount / 1e12).toFixed(2) + '万亿' : '--' }}</div></div>
        </div>
      </div>

      <!-- AI Market Summary -->
      <div class="card ai-card" v-liquid>
        <div class="ai-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>
          AI 市场速览
        </div>
        <div v-if="aiLoading" class="ai-text" style="opacity:0.5">正在分析市场数据...</div>
        <div v-else-if="aiError" class="ai-text">
          <span style="color:var(--down)">{{ aiError }}</span>
          <button class="ai-retry" @click="fetchAISummary">重试</button>
        </div>
        <div v-else-if="aiSummary" class="ai-text">{{ aiSummary }}</div>
        <div v-else class="ai-text" style="opacity:0.5">点击刷新获取 AI 市场分析</div>
        <button v-if="!aiLoading" class="ai-refresh" @click="fetchAISummary" title="刷新">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 4v6h6"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
        </button>
      </div>
    </div>

    <!-- ACTIONS -->
    <div class="actions-row animate-in delay-6">
      <router-link to="/screener" class="btn btn-primary" v-liquid="{maxTilt: 6, scale: 1.04}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        智能选股
      </router-link>
      <router-link to="/backtest" class="btn btn-secondary" v-liquid="{maxTilt: 6, scale: 1.04}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-9"/></svg>
        策略回测
      </router-link>
      <router-link to="/ai" class="btn btn-secondary" v-liquid="{maxTilt: 6, scale: 1.04}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>
        AI 分析
      </router-link>
    </div>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1200px; }

.index-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.index-card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  padding: 18px 20px; position: relative; overflow: hidden; transition: all 0.22s ease; cursor: default;
}
.index-card::after {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, var(--accent), transparent); opacity: 0; transition: opacity 0.3s;
}
.index-card:hover { border-color: var(--border-default); box-shadow: var(--shadow-card); transform: translateY(-2px); }
.index-card:hover::after { opacity: 1; }
.index-name { font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; }
.index-value { font-family: var(--font-mono); font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; margin-bottom: 6px; }
.index-change { font-family: var(--font-mono); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.index-spark { position: absolute; right: 16px; bottom: 14px; opacity: 0.5; }
.placeholder { display: flex; align-items: center; justify-content: center; min-height: 100px; }
.loading-text { color: var(--text-tertiary); font-size: 13px; }

.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.section-title { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.section-link { font-size: 11.5px; font-weight: 500; color: var(--accent); cursor: pointer; text-decoration: none; transition: color 0.15s; }
.section-link:hover { color: var(--accent-soft); }

.table-wrap {
  background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  overflow: hidden; margin-bottom: 24px; transition: background var(--transition-theme), border-color var(--transition-theme);
}
table { width: 100%; border-collapse: collapse; }
thead th {
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px;
  color: var(--text-tertiary); text-align: left; padding: 11px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
thead th.r { text-align: right; }
tbody td { padding: 12px 18px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle); transition: background 0.12s; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--bg-hover); }
tbody tr { cursor: pointer; }
td.r { text-align: right; }
td.mono, .mono { font-family: var(--font-mono); font-weight: 500; font-size: 12px; font-variant-numeric: tabular-nums; }
.cell-stock { display: flex; flex-direction: column; gap: 2px; }
.cell-name { font-weight: 600; font-size: 13px; color: var(--text-primary); }
.cell-code { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); }
.pill { display: inline-block; padding: 3px 9px; border-radius: 999px; font-family: var(--font-mono); font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums; }
.pill-up { background: var(--up-dim); color: var(--up); }
.pill-down { background: var(--down-dim); color: var(--down); }
.empty-table { padding: 32px; text-align: center; color: var(--text-tertiary); font-size: 13px; }

.bottom-grid { display: grid; grid-template-columns: 1fr 1.4fr; gap: 16px; margin-bottom: 24px; }
.card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  padding: 20px; transition: all var(--transition-theme);
}
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }

.breadth-bar { height: 10px; border-radius: 5px; overflow: hidden; display: flex; margin-bottom: 10px; background: var(--bg-overlay); }
.breadth-seg { transition: width 0.6s ease; }
.breadth-up { background: var(--up); border-radius: 5px 0 0 5px; }
.breadth-flat { background: var(--text-tertiary); opacity: 0.4; }
.breadth-down { background: var(--down); border-radius: 0 5px 5px 0; }
.breadth-labels { display: flex; justify-content: space-between; font-size: 11px; font-family: var(--font-mono); font-weight: 500; }
.flat-label { color: var(--text-tertiary); }
.breadth-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border-subtle); }
.breadth-stat-label { font-size: 10px; color: var(--text-tertiary); margin-bottom: 3px; }
.breadth-stat-val { font-family: var(--font-mono); font-size: 14px; font-weight: 600; }

.ai-card { position: relative; overflow: hidden; }
.ai-card::before {
  content: ''; position: absolute; top: -40px; right: -40px; width: 120px; height: 120px;
  background: radial-gradient(circle, var(--accent-glow), transparent 70%); border-radius: 50%; pointer-events: none;
}
.ai-badge {
  display: inline-flex; align-items: center; gap: 5px; background: var(--accent-dim); color: var(--accent);
  font-size: 10px; font-weight: 600; padding: 4px 10px; border-radius: 999px; margin-bottom: 12px; letter-spacing: 0.3px;
}
.ai-text { font-size: 12.5px; line-height: 1.8; color: var(--text-secondary); }
.ai-text strong { color: var(--text-primary); font-weight: 600; }
.ai-tags { display: flex; gap: 6px; margin-top: 14px; flex-wrap: wrap; }
.ai-tag { font-size: 10px; font-weight: 500; padding: 3px 9px; border-radius: 4px; background: var(--bg-overlay); color: var(--text-secondary); border: 1px solid var(--border-subtle); }
.ai-retry { margin-left: 8px; font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-default); background: var(--bg-elevated); color: var(--accent); cursor: pointer; }
.ai-retry:hover { border-color: var(--accent); }
.ai-refresh { position: absolute; top: 16px; right: 16px; background: none; border: none; color: var(--text-tertiary); cursor: pointer; padding: 4px; border-radius: 4px; transition: color 0.15s; }
.ai-refresh:hover { color: var(--accent); }

.actions-row { display: flex; gap: 12px; }
.btn {
  font-family: var(--font-sans); font-size: 12.5px; font-weight: 600; padding: 10px 20px;
  border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all 0.18s ease;
  display: inline-flex; align-items: center; gap: 7px; text-decoration: none;
}
.btn-primary { background: linear-gradient(135deg, var(--accent), #a8884a); color: #0a0c10; box-shadow: 0 4px 14px var(--accent-glow); }
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--accent-glow); }
.btn-secondary { background: var(--bg-elevated); color: var(--text-primary); border: 1px solid var(--border-default); }
.btn-secondary:hover { border-color: var(--accent); background: var(--accent-dim); color: var(--accent-soft); }

@media (max-width: 1100px) { .index-grid { grid-template-columns: repeat(2, 1fr); } .bottom-grid { grid-template-columns: 1fr; } }
@media (max-width: 860px) { .index-grid { grid-template-columns: 1fr; } }
.clickable-row { cursor: pointer; transition: background 0.15s; }
.clickable-row:hover { background: var(--bg-hover); }

/* Alerts Strip */
.alerts-strip { display: flex; gap: 12px; margin-bottom: 16px; overflow-x: auto; padding: 4px 0; }
.alert-item { display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-radius: var(--radius-sm); font-size: 12px; cursor: pointer; white-space: nowrap; transition: all 0.15s; border: 1px solid; }
.alert-item:hover { transform: translateY(-1px); }
.alert-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.alert-item.danger { background: rgba(240,72,72,0.08); border-color: rgba(240,72,72,0.2); color: var(--up); }
.alert-item.danger .alert-dot { background: var(--up); }
.alert-item.warning { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.2); color: #f59e0b; }
.alert-item.warning .alert-dot { background: #f59e0b; }
.alert-item.success { background: rgba(38,201,102,0.08); border-color: rgba(38,201,102,0.2); color: var(--down); }
.alert-item.success .alert-dot { background: var(--down); }
.alert-msg { font-weight: 500; }

/* Briefing Card */
.briefing-card { margin-bottom: 20px; position: relative; }
.briefing-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.briefing-meta { font-size: 11px; color: var(--text-tertiary); margin-left: auto; }
.briefing-body { font-size: 13px; line-height: 1.8; color: var(--text-secondary); white-space: pre-wrap; }
</style>
