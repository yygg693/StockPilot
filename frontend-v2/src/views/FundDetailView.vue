<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from "vue"
import { useRoute, useRouter } from "vue-router"
import echarts from "@/echarts"
import { getFundDetail, buyStock, sellStock, getAccount, addWatch, removeWatch, getWatchlist } from "@/api"
import AIPanel from "@/components/AIPanel.vue"
import { useTradingHours } from "@/composables/useTradingHours"

const { fundSameDay, fundStatusText } = useTradingHours()

const route = useRoute()
const router = useRouter()
const code = computed(() => route.params.code as string)

const fund = ref<any>({
  code: code.value,
  name: code.value,
  nav: 0,
  return_1m: 0,
  return_3m: 0,
  return_6m: 0,
  return_1y: 0,
  return_ytd: 0,
  type: '',
})

const loading = ref(true)
const chartEl = ref<HTMLDivElement>()
const scaleChartEl = ref<HTMLDivElement>()
let chart: any = null
let scaleChart: any = null


// Trade
const showTradeModal = ref(false)
const tradeSide = ref<"buy" | "sell">("buy")
const tradeAmount = ref(1000)
const tradeLoading = ref(false)
const tradeMsg = ref("")
const accountCash = ref(0)

// Watchlist
const inWatchlist = ref(false)


function openTrade(side: "buy" | "sell") {
  tradeSide.value = side
  tradeAmount.value = 1000
  tradeMsg.value = ""
  showTradeModal.value = true
  loadAccount()
}

async function loadAccount() {
  try {
    const res: any = await getAccount()
    accountCash.value = res.data?.cash || 0
  } catch {}
}

async function confirmTrade() {
  if (tradeAmount.value <= 0) return
  tradeLoading.value = true
  tradeMsg.value = ""
  try {
    const payload = { code: code.value, name: fund.value.name || "", asset_type: "fund", qty: 1, price: tradeAmount.value }
    const fn = tradeSide.value === "buy" ? buyStock : sellStock
    await fn(payload)
    tradeMsg.value = tradeSide.value === "buy"
      ? `申购成功：${tradeAmount.value}元`
      : `赎回成功：${tradeAmount.value}元`
    loadAccount()
  } catch (e: any) {
    tradeMsg.value = e.message || "交易失败"
  } finally { tradeLoading.value = false }
}

async function toggleWatch() {
  try {
    if (inWatchlist.value) { await removeWatch(code.value); inWatchlist.value = false }
    else { await addWatch(code.value, fund.value.name || ""); inWatchlist.value = true }
  } catch (e: any) { alert(e.message) }
}

async function checkWatchlist() {
  try {
    const res: any = await getWatchlist()
    inWatchlist.value = (res.data || []).some((it: any) => it.code === code.value)
  } catch {}
}


function fmtRet(v: number) { return v ? ((v > 0 ? "+" : "") + v.toFixed(2) + "%") : "--" }
function retClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }

function getNavHistory(): [string, number][] {
  const history = fund.value.nav_history
  if (history && history.length > 0) {
    return history.map((p: [number, number]) => {
      const d = new Date(p[0])
      return [(d.getMonth() + 1) + '/' + d.getDate(), p[1]] as [string, number]
    })
  }
  return []
}

function renderChart() {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  const data = getNavHistory()
  if (!data.length) return
  const isUp = (fund.value.return_1y || 0) >= 0
  const color = isUp ? '#f04848' : '#26c966'
  chart.setOption({
    grid: { top: 20, right: 16, bottom: 28, left: 50 },
    xAxis: { type: 'category', data: data.map(d => d[0]), axisLine: { lineStyle: { color: 'rgba(255,255,255,0.08)' } }, axisLabel: { color: '#565f6e', fontSize: 10 }, axisTick: { show: false } },
    yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }, axisLabel: { color: '#565f6e', fontSize: 10 } },
    tooltip: { trigger: 'axis', backgroundColor: '#1e2430', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#f2f4f7', fontSize: 11 }, formatter: (p: any) => p[0]?.name + '<br/>净值: ' + p[0]?.value },
    series: [{ type: 'line', data: data.map(d => d[1]), smooth: true, symbol: 'none', lineStyle: { color, width: 2 }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: color + '30' }, { offset: 1, color: color + '05' }] } } }]
  })
}

function renderScaleChart() {
  if (!scaleChartEl.value || !fund.value.scale_history?.length) return
  scaleChart = echarts.init(scaleChartEl.value)
  const sh = fund.value.scale_history
  scaleChart.setOption({
    grid: { top: 20, right: 16, bottom: 28, left: 50 },
    xAxis: { type: 'category', data: sh.map((s: any) => s.date), axisLabel: { color: '#565f6e', fontSize: 10 }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: '#565f6e', fontSize: 10, formatter: '{value}亿' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } } },
    tooltip: { trigger: 'axis', backgroundColor: '#1e2430', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#f2f4f7', fontSize: 11 } },
    series: [{ type: 'bar', data: sh.map((s: any) => s.scale), itemStyle: { color: 'rgba(201,169,98,0.6)', borderRadius: [3, 3, 0, 0] } }]
  })
}

// AI Context
const aiContext = computed(() => {
  const f = fund.value
  let ctx = `fund|${code.value}|${f.name}\n`
  ctx += `最新净值: ${f.nav}, 近1月: ${f.return_1m}%, 近3月: ${f.return_3m}%, 近6月: ${f.return_6m}%, 近1年: ${f.return_1y}%\n`
  if (f.manager) ctx += `基金经理: ${f.manager}, 从业: ${f.manager_work_time}, 管理规模: ${f.manager_fund_size}\n`
  if (f.scale) ctx += `基金规模: ${f.scale}亿\n`
  if (f.top_holdings?.length) ctx += `重仓股: ${f.top_holdings.map((h: any) => h.name + '(' + h.code + ')').join(', ')}\n`
  if (f.performance_scores?.categories) ctx += `五维评分(均分${f.performance_scores.average}): ${f.performance_scores.categories.join('/')}\n`
  ctx += `请以基金投资顾问身份回答，给出专业、实用的建议。`
  return ctx
})

async function loadFund() {
  loading.value = true
  fund.value = { code: code.value, name: code.value, nav: 0, return_1m: 0, return_3m: 0, return_6m: 0, return_1y: 0, return_ytd: 0, type: '' }
  try {
    const res: any = await getFundDetail(code.value)
    const d = res.data
    if (d) {
      fund.value = { ...fund.value, ...d }
    }
  } catch (e) { /* ignore */ }
  finally { loading.value = false }
  await nextTick()
  renderChart()
  renderScaleChart()
}

onMounted(() => {
  checkWatchlist()
  loadFund()
})

// Reload when navigating to a different fund
watch(code, (newCode, oldCode) => {
  if (newCode !== oldCode) {
    loadFund()
    checkWatchlist()
  }
})
</script>

<template>
  <div class="fund-page">
    <div class="fund-main">
      <!-- Header -->
      <div class="fd-header animate-in">
        <button class="back-btn" v-liquid="{maxTilt: 5, scale: 1.06}" @click="router.back()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M19 12H5"/><path d="M12 19l-7-7 7-7"/></svg>
          返回
        </button>
        <div class="fd-title-block">
          <h1 class="fd-name">{{ fund.name }}</h1>
          <span class="fd-code">{{ fund.code }}</span>
          <span v-if="fund.type" class="fd-type-tag">{{ fund.type }}</span>
        </div>
        <div class="fd-actions">
          <button class="btn-act" :class="{ watched: inWatchlist }" v-liquid="{maxTilt:5,scale:1.06}" @click="toggleWatch">{{ inWatchlist ? '✓ 已自选' : '+ 自选' }}</button>
          <button class="btn-act buy" v-liquid="{maxTilt:5,scale:1.06}" @click="openTrade('buy')">买入</button>
          <button class="btn-act sell" v-liquid="{maxTilt:5,scale:1.06}" @click="openTrade('sell')">卖出</button>
        </div>
      </div>

      <!-- NAV + Performance -->
      <div class="fd-top-grid animate-in delay-1">
        <div class="fd-nav-card" v-liquid>
          <div class="nav-label">最新净值</div>
          <div class="nav-value">{{ fund.nav ? fund.nav.toFixed(4) : '--' }}</div>
          <div class="nav-subs">
            <span v-if="fund.manager">{{ fund.manager }}</span>
            <span v-if="fund.manager_star" class="star">{{ '★'.repeat(fund.manager_star) }}</span>
            <span v-if="fund.scale">{{ fund.scale }}亿</span>
          </div>
          <div class="nav-subs" v-if="fund.fee_discount">
            <span>申购费 {{ fund.fee_discount }}%</span>
            <span v-if="fund.fee_min_purchase">起购 {{ fund.fee_min_purchase }}元</span>
          </div>
        </div>
        <div class="fd-perf-card" v-liquid>
          <div class="perf-title">阶段收益</div>
          <div class="perf-grid-mini">
            <div><span class="pg-label">近1月</span><span class="pg-val" :class="retClass(fund.return_1m)">{{ fmtRet(fund.return_1m) }}</span></div>
            <div><span class="pg-label">近3月</span><span class="pg-val" :class="retClass(fund.return_3m)">{{ fmtRet(fund.return_3m) }}</span></div>
            <div><span class="pg-label">近6月</span><span class="pg-val" :class="retClass(fund.return_6m)">{{ fmtRet(fund.return_6m) }}</span></div>
            <div><span class="pg-label">近1年</span><span class="pg-val" :class="retClass(fund.return_1y)">{{ fmtRet(fund.return_1y) }}</span></div>
            <div><span class="pg-label">今年来</span><span class="pg-val" :class="retClass(fund.return_ytd)">{{ fmtRet(fund.return_ytd) }}</span></div>
          </div>
        </div>
      </div>

      <!-- NAV Chart -->
      <div class="fd-section-title animate-in delay-2">净值走势</div>
      <div class="fd-chart-card animate-in delay-2" v-liquid>
        <div ref="chartEl" class="fd-chart"></div>
      </div>

      <!-- Performance Scores -->
      <div v-if="fund.performance_scores?.categories" class="animate-in delay-3">
        <div class="fd-section-title">五维评分 <span class="score-avg">{{ fund.performance_scores.average }}分</span></div>
        <div class="fd-scores" v-liquid>
          <div class="score-item" v-for="(cat, i) in fund.performance_scores.categories" :key="cat">
            <div class="score-bar-track">
              <div class="score-bar-fill" :style="{ width: (fund.performance_scores.scores?.[i] || 50) + '%' }"></div>
            </div>
            <span class="score-label">{{ cat }}</span>
            <span class="score-num">{{ fund.performance_scores.scores?.[i] || '--' }}</span>
          </div>
        </div>
      </div>

      <!-- Asset Allocation -->
      <div v-if="fund.asset_allocation?.series?.length" class="animate-in delay-3">
        <div class="fd-section-title">资产配置</div>
        <div class="fd-allocation" v-liquid>
          <div class="alloc-item" v-for="s in fund.asset_allocation.series" :key="s.name">
            <span class="alloc-name">{{ s.name }}</span>
            <div class="alloc-bar-track">
              <div class="alloc-bar-fill" :style="{ width: Math.min(s.data?.[0] || 0, 100) + '%' }"></div>
            </div>
            <span class="alloc-val">{{ s.data?.[0]?.toFixed(1) || '0' }}%</span>
          </div>
          <div class="alloc-periods" v-if="fund.asset_allocation.categories?.length">
            报告期: {{ fund.asset_allocation.categories.join(' / ') }}
          </div>
        </div>
      </div>

      <!-- Top Holdings -->
      <div v-if="fund.top_holdings?.length" class="animate-in delay-4">
        <div class="fd-section-title">重仓股</div>
        <div class="fd-holdings" v-liquid>
          <div class="holding-chip" v-for="(h, i) in fund.top_holdings" :key="h.code"
            @click="router.push('/stock/' + (h.market === '1' ? 'sh' : 'sz') + h.code)">
            <span class="holding-rank">{{ Number(i) + 1 }}</span>
            <span class="holding-name">{{ h.name || h.code }}</span>
            <span class="holding-code">{{ h.code }}</span>
            <span v-if="h.change_pct" class="holding-chg" :class="h.change_pct > 0 ? 'val-up' : 'val-down'">{{ h.change_pct > 0 ? '+' : '' }}{{ h.change_pct.toFixed(2) }}%</span>
          </div>
        </div>
      </div>

      <!-- Scale History -->
      <div v-if="fund.scale_history?.length" class="animate-in delay-4">
        <div class="fd-section-title">规模变动</div>
        <div class="fd-chart-card" v-liquid>
          <div ref="scaleChartEl" class="fd-chart-sm"></div>
        </div>
      </div>

      <!-- Manager Info -->
      <div v-if="fund.manager" class="animate-in delay-5">
        <div class="fd-section-title">基金经理</div>
        <div class="fd-manager" v-liquid>
          <div class="mgr-avatar">{{ fund.manager[0] }}</div>
          <div class="mgr-info">
            <div class="mgr-name">{{ fund.manager }} <span class="mgr-star" v-if="fund.manager_star">{{ '★'.repeat(fund.manager_star) }}</span></div>
            <div class="mgr-meta">从业 {{ fund.manager_work_time }} | 管理 {{ fund.manager_fund_size }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- AI Chat Panel -->
    <div class="ai-side animate-in delay-2">
      <AIPanel :context="aiContext" :asset-code="code" :asset-name="fund.name" default-question="这只基金值得买入吗？" :orb-size="180" />
    </div>

    <!-- Trade Modal -->
    <Teleport to="body">
      <div v-if="showTradeModal" class="modal-overlay" @click.self="showTradeModal = false">
        <div class="trade-modal">
          <div class="trade-modal-head">
            <h3 :class="tradeSide === 'buy' ? 'val-up' : 'val-down'">{{ tradeSide === 'buy' ? '申购' : '赎回' }} {{ fund.name }}</h3>
            <button class="modal-close" @click="showTradeModal = false">&times;</button>
          </div>
          <div class="trade-modal-body">
            <div class="trade-info-row"><span class="tl">最新净值</span><span class="tv mono">{{ fund.nav ? fund.nav.toFixed(4) : '--' }}</span></div>
            <div class="trade-info-row"><span class="tl">可用资金</span><span class="tv mono">{{ accountCash.toLocaleString() }}元</span></div>
            <div class="fund-time-notice" :class="{ warn: !fundSameDay }">{{ fundStatusText }}</div>
            <div class="trade-field">
              <span class="tl">{{ tradeSide === 'buy' ? '申购金额(元)' : '赎回金额(元)' }}</span>
              <input class="trade-input" type="number" v-model.number="tradeAmount" min="0" step="100" />
            </div>
            <div class="trade-quick">
              <button @click="tradeAmount = 1000">1000</button>
              <button @click="tradeAmount = 5000">5000</button>
              <button @click="tradeAmount = 10000">1万</button>
              <button @click="tradeAmount = tradeSide === 'buy' ? Math.floor(accountCash) : accountCash">全部</button>
            </div>
            <div v-if="tradeMsg" class="trade-msg" :class="tradeMsg.includes('成功') ? 'success' : 'error'">{{ tradeMsg }}</div>
            <button class="trade-confirm" :class="tradeSide" :disabled="tradeLoading || tradeAmount <= 0" @click="confirmTrade">
              {{ tradeLoading ? '处理中...' : (tradeSide === 'buy' ? '确认申购' : '确认赎回') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.fund-page { display: grid; grid-template-columns: 1fr 320px; gap: 20px; align-items: start; }
.fund-main { min-width: 0; }

.fd-header { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.back-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: var(--bg-elevated); color: var(--text-secondary); font-size: 12px; font-weight: 500; cursor: pointer; position: relative; overflow: hidden; }
.back-btn:hover { border-color: var(--accent); color: var(--accent); }
.fd-title-block { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.fd-name { font-size: 18px; font-weight: 700; color: var(--text-primary); }
.fd-code { font-size: 11px; color: var(--text-tertiary); font-family: var(--font-mono); }
.fd-type-tag { font-size: 10px; padding: 3px 8px; border-radius: 4px; background: var(--accent-dim); color: var(--accent); font-weight: 600; }

.fd-top-grid { display: grid; grid-template-columns: 1fr 1.2fr; gap: 14px; margin-bottom: 24px; }
.fd-nav-card, .fd-perf-card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; position: relative; overflow: hidden; }
.nav-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-tertiary); margin-bottom: 6px; }
.nav-value { font-family: var(--font-mono); font-size: 30px; font-weight: 700; color: var(--text-primary); margin-bottom: 8px; }
.nav-subs { display: flex; gap: 12px; font-size: 11px; color: var(--text-secondary); margin-top: 4px; }
.star { color: var(--accent); }
.perf-title { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: var(--text-tertiary); margin-bottom: 12px; }
.perf-grid-mini { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.pg-label { display: block; font-size: 10px; color: var(--text-tertiary); margin-bottom: 3px; }
.pg-val { font-family: var(--font-mono); font-size: 14px; font-weight: 700; }

.fd-section-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; margin-top: 6px; }
.score-avg { font-size: 11px; color: var(--accent); font-weight: 500; margin-left: 6px; }

.fd-chart-card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px; margin-bottom: 24px; position: relative; overflow: hidden; }
.fd-chart { width: 100%; height: 220px; }
.fd-chart-sm { width: 100%; height: 160px; }

.fd-scores { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px; margin-bottom: 24px; position: relative; overflow: hidden; }
.score-item { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.score-item:last-child { margin-bottom: 0; }
.score-bar-track { flex: 1; height: 6px; background: var(--bg-overlay); border-radius: 3px; overflow: hidden; }
.score-bar-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width 0.6s ease; }
.score-label { font-size: 11px; color: var(--text-secondary); width: 56px; }
.score-num { font-size: 11px; font-family: var(--font-mono); color: var(--text-primary); width: 24px; text-align: right; }

.fd-allocation { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px; margin-bottom: 24px; position: relative; overflow: hidden; }
.alloc-item { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.alloc-name { font-size: 11px; color: var(--text-secondary); width: 70px; }
.alloc-bar-track { flex: 1; height: 8px; background: var(--bg-overlay); border-radius: 4px; overflow: hidden; }
.alloc-bar-fill { height: 100%; background: var(--accent); border-radius: 4px; opacity: 0.7; }
.alloc-val { font-size: 11px; font-family: var(--font-mono); width: 44px; text-align: right; }
.alloc-periods { font-size: 10px; color: var(--text-tertiary); margin-top: 8px; }

.fd-holdings { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 16px; margin-bottom: 24px; display: flex; flex-wrap: wrap; gap: 8px; position: relative; overflow: hidden; }
.holding-chip { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 6px; background: var(--bg-overlay); border: 1px solid var(--border-subtle); cursor: pointer; transition: all 0.15s; }
.holding-chip:hover { border-color: var(--accent); background: var(--accent-dim); }
.holding-rank { font-size: 10px; font-weight: 700; color: var(--accent); }
.holding-name { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.holding-code { font-size: 10px; font-family: var(--font-mono); color: var(--text-tertiary); }
.holding-chg { font-size: 10px; font-family: var(--font-mono); font-weight: 600; }

.fd-manager { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px; margin-bottom: 24px; display: flex; align-items: center; gap: 14px; position: relative; overflow: hidden; }
.mgr-avatar { width: 44px; height: 44px; border-radius: 50%; background: var(--accent-dim); color: var(--accent); display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700; }
.mgr-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.mgr-star { color: var(--accent); font-size: 12px; }
.mgr-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 3px; }


.fd-actions { display: flex; gap: 8px; margin-left: auto; }
.btn-act { padding: 7px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 12px; font-weight: 500; cursor: pointer; position: relative; overflow: hidden; }
.btn-act:hover { border-color: var(--accent); color: var(--accent); }
.btn-act.watched { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.btn-act.buy { border-color: var(--up); color: var(--up); }
.btn-act.buy:hover { background: var(--up-dim); }
.btn-act.sell { border-color: var(--down); color: var(--down); }
.btn-act.sell:hover { background: var(--down-dim); }

.orb-wrap { display: flex; flex-direction: column; align-items: center; padding: 10px 0 4px; cursor: pointer; position: relative; }
.orb-canvas { width: 180px; height: 180px; }
.orb-hint { font-size: 10px; color: var(--text-tertiary); margin-top: -8px; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.trade-modal { background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-lg); width: 360px; overflow: hidden; }
.trade-modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.trade-modal-head h3 { font-size: 15px; font-weight: 700; }
.modal-close { background: none; border: none; color: var(--text-tertiary); font-size: 20px; cursor: pointer; }
.trade-modal-body { padding: 20px; }
.trade-info-row { display: flex; justify-content: space-between; margin-bottom: 12px; }
.tl { font-size: 12px; color: var(--text-tertiary); }
.tv { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.trade-field { margin-bottom: 12px; }
.trade-field .tl { display: block; margin-bottom: 6px; }
.trade-input { width: 100%; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--border-default); background: var(--bg-elevated); color: var(--text-primary); font-size: 14px; outline: none; }
.trade-input:focus { border-color: var(--accent); }
.trade-quick { display: flex; gap: 8px; margin-bottom: 16px; }
.trade-quick button { flex: 1; padding: 6px; border-radius: 6px; border: 1px solid var(--border-default); background: var(--bg-elevated); color: var(--text-secondary); font-size: 11px; cursor: pointer; }
.trade-quick button:hover { border-color: var(--accent); color: var(--accent); }
.trade-msg { font-size: 12px; margin-bottom: 12px; padding: 8px 12px; border-radius: 6px; }
.trade-msg.success { background: var(--down-dim); color: var(--down); }
.trade-msg.error { background: var(--up-dim); color: var(--up); }
.fund-time-notice { font-size: 11px; padding: 8px 12px; border-radius: 6px; background: rgba(38,201,102,0.08); color: var(--down); margin-bottom: 12px; }
.fund-time-notice.warn { background: rgba(255,180,50,0.1); color: #ffb432; }
.trade-confirm { width: 100%; padding: 12px; border-radius: 8px; border: none; font-size: 13px; font-weight: 600; cursor: pointer; }
.trade-confirm.buy { background: var(--up); color: #fff; }
.trade-confirm.sell { background: var(--down); color: #fff; }
.trade-confirm:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 1000px) { .fund-page { grid-template-columns: 1fr; } .ai-panel { height: 400px; position: static; } }
.ai-side { width: 320px; flex-shrink: 0; position: sticky; top: 0; height: calc(100vh - 96px); max-height: 740px; }
</style>
