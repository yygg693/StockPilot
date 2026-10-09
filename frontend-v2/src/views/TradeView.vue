<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue"
import {
  getAccount,
  buyStock,
  sellStock,
  getTradeHistory,
  searchStock,
  getQuote,
  getStrategies,
  aiAutoBuy,
  aiAutoSell,
  confirmProposal,
  diagnosePortfolio,
  getSignals,
  getRiskStatus,
  autoExecute,
  resetAccount,
} from "@/api"
import ProposalConfirm from "@/components/ProposalConfirm.vue"

// ---- Account state ----
const account = ref<any>({
  cash: 1000000,
  initial_cash: 1000000,
  market_value: 0,
  total_assets: 1000000,
  total_cost: 0,
  total_pnl: 0,
  total_pnl_pct: 0,
  today_pnl: 0,
  position_count: 0,
  positions: [],
})
const positions = computed<any[]>(() => account.value.positions || [])
const history = ref<any[]>([])
const loading = ref(false)
const refreshing = ref(false)

// ---- Trade form ----
const side = ref<"buy" | "sell">("buy")
const form = ref({ code: "", name: "", qty: 100, price: 0 })
const submitting = ref(false)

// ---- Search autocomplete ----
const searchResults = ref<any[]>([])
const showSearch = ref(false)
const searchLoading = ref(false)
let searchTimer: any = null

// ---- AI auto-trade ----
const strategies = ref<any[]>([])
const aiStrategy = ref("oversold_bounce")
const aiUniverse = ref("hs300")
const aiTopN = ref(5)
const aiMaxPct = ref(0.2)
const aiStopLoss = ref(8)
const aiTakeProfit = ref(20)
const aiBuyLoading = ref(false)
const aiSellLoading = ref(false)
const aiResult = ref<any>(null)

// ---- Proposal Confirmation ----
const showProposal = ref(false)
const currentProposal = ref<any>(null)

async function handleConfirmProposal(id: string) {
  showProposal.value = false
  try {
    const res: any = await confirmProposal(id)
    aiResult.value = { type: "confirm", ...(res.data || res) }
    await load()
  } catch (e: any) {
    alert(e.message || "确认失败")
  }
}

function handleCancelProposal() {
  showProposal.value = false
  currentProposal.value = null
}

// ---- Portfolio Diagnosis ----
const diagnosis = ref<any>(null)
const diagLoading = ref(false)

async function runDiagnosis() {
  diagLoading.value = true
  diagnosis.value = null
  try {
    const res: any = await diagnosePortfolio()
    diagnosis.value = res.data || null
  } catch (e: any) {
    diagnosis.value = { diagnosis: '诊断失败: ' + e.message, scores: {} }
  } finally { diagLoading.value = false }
}

// ---- AI Signals & Auto Trade ----
const signals = ref<any[]>([])
const signalCommentary = ref('')
const signalsLoading = ref(false)
const riskStatus = ref<any>(null)
const autoLoading = ref(false)
const autoResult = ref<any>(null)

async function fetchSignals() {
  signalsLoading.value = true
  signals.value = []
  signalCommentary.value = ''
  try {
    const res: any = await getSignals()
    const d = res.data || {}
    signals.value = d.signals || []
    signalCommentary.value = d.commentary || ''
  } catch (e: any) {
    signalCommentary.value = '信号获取失败: ' + e.message
  } finally { signalsLoading.value = false }
}

async function fetchRiskStatus() {
  try {
    const res: any = await getRiskStatus()
    riskStatus.value = res.data || null
  } catch {}
}

async function runAutoTrade() {
  autoLoading.value = true
  autoResult.value = null
  try {
    const res: any = await autoExecute()
    const data = res.data || res
    if (data.proposal || data.proposal_id) {
      currentProposal.value = data.proposal || data
      showProposal.value = true
      autoResult.value = { message: "自动交易提案已生成，请确认后执行" }
    } else {
      autoResult.value = data
      refresh()
    }
  } catch (e: any) {
    autoResult.value = { message: '自动交易失败: ' + e.message, executed: [], skipped: [] }
  } finally { autoLoading.value = false }
}

function signalClass(s: string) {
  if (s.includes('buy')) return 'sig-buy'
  if (s.includes('sell')) return 'sig-sell'
  return 'sig-neutral'
}
function signalLabel(s: string) {
  const map: Record<string, string> = { strong_buy: '强烈买入', buy: '买入', strong_sell: '强烈卖出', sell: '卖出', neutral: '观望' }
  return map[s] || s
}

let refreshTimer: any = null

// ---- Helpers ----
function valClass(v: number) {
  return v > 0 ? "val-up" : v < 0 ? "val-down" : ""
}
function fmtPct(v: number) {
  return (v > 0 ? "+" : "") + (v || 0).toFixed(2) + "%"
}
function fmtMoney(v: number) {
  return (v || 0).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtSignedMoney(v: number) {
  return (v > 0 ? "+" : "") + fmtMoney(v)
}

// ---- Data loading ----
async function load() {
  loading.value = true
  try {
    const [accRes, histRes]: any[] = await Promise.all([
      getAccount().catch(() => ({ data: account.value })),
      getTradeHistory(20).catch(() => ({ data: [] })),
    ])
    account.value = accRes.data || account.value
    history.value = histRes.data || []
  } finally {
    loading.value = false
  }
}

async function refresh() {
  if (loading.value || submitting.value) return
  refreshing.value = true
  try {
    const accRes: any = await getAccount()
    account.value = accRes.data || account.value
  } catch {
    /* silent */
  } finally {
    refreshing.value = false
  }
}

async function handleResetAccount() {
  if (!confirm("确定重置模拟盘？将清空所有持仓和交易记录，恢复初始资金 1,000,000。")) return
  try {
    await resetAccount()
    await load()
    alert("模拟盘已重置")
  } catch (e: any) {
    alert(e.message || "重置失败")
  }
}

// ---- Search autocomplete ----
function onSearchInput() {
  const q = form.value.code.trim()
  if (searchTimer) clearTimeout(searchTimer)
  if (!q) {
    searchResults.value = []
    showSearch.value = false
    return
  }
  searchTimer = setTimeout(async () => {
    searchLoading.value = true
    try {
      const res: any = await searchStock(q)
      searchResults.value = res.data || []
      showSearch.value = true
    } catch {
      searchResults.value = []
    } finally {
      searchLoading.value = false
    }
  }, 300)
}

async function selectStock(s: any) {
  form.value.code = s.code
  form.value.name = s.name || ""
  showSearch.value = false
  searchResults.value = []
  await fillPrice(s.code, s.name)
}

async function fillPrice(code: string, name?: string) {
  try {
    const res: any = await getQuote(code)
    const q = res.data || {}
    if (q.price) form.value.price = Number(q.price)
    if (name === undefined || !form.value.name) form.value.name = q.name || form.value.name
  } catch {
    /* keep manual price */
  }
}

function onBlurSearch() {
  // delay to allow click on dropdown item
  setTimeout(() => {
    showSearch.value = false
  }, 180)
}

// ---- Quantity quick buttons ----
function setQty(n: number) {
  form.value.qty = n
}

function setFull() {
  if (side.value === "buy") {
    const price = Number(form.value.price) || 0
    if (price <= 0) return
    const maxQty = Math.floor(account.value.cash / price / 100) * 100
    form.value.qty = Math.max(0, maxQty)
  } else {
    const pos = positions.value.find((p) => p.code === form.value.code)
    if (pos) form.value.qty = Math.floor(pos.qty)
  }
}

// ---- Estimated amount ----
const estimated = computed(() => (Number(form.value.qty) || 0) * (Number(form.value.price) || 0))

// ---- Buy / Sell ----
function switchSide(s: "buy" | "sell") {
  side.value = s
}

async function submitTrade() {
  const code = form.value.code.trim()
  const price = Number(form.value.price)
  const qty = Number(form.value.qty)
  if (!code) return alert("请输入股票代码")
  if (!price || price <= 0) return alert("请输入有效价格")
  if (!qty || qty <= 0) return alert("请输入有效数量")

  if (side.value === "buy" && qty * price > account.value.cash + 1e-6) {
    return alert(`可用资金不足：需要 ${fmtMoney(qty * price)}，当前可用 ${fmtMoney(account.value.cash)}`)
  }

  submitting.value = true
  try {
    const payload = { code, name: form.value.name, qty, price }
    if (side.value === "buy") {
      await buyStock(payload)
    } else {
      await sellStock(payload)
    }
    form.value = { code: "", name: "", qty: 100, price: 0 }
    await load()
  } catch (e: any) {
    alert(e.message || "交易失败")
  } finally {
    submitting.value = false
  }
}

// Quick sell from a position row: prefill form & switch to sell side
async function quickSell(pos: any) {
  side.value = "sell"
  form.value.code = pos.code
  form.value.name = pos.name || ""
  form.value.qty = Math.floor(pos.qty)
  form.value.price = pos.price && pos.price > 0 ? pos.price : pos.cost
  // try to refresh live price
  await fillPrice(pos.code, pos.name)
  window.scrollTo({ top: 0, behavior: "smooth" })
}

// ---- AI auto-trade ----
async function runAiBuy() {
  aiBuyLoading.value = true
  aiResult.value = null
  try {
    const res: any = await aiAutoBuy({
      strategy: aiStrategy.value,
      universe: aiUniverse.value,
      top_n: aiTopN.value,
      max_position_pct: aiMaxPct.value,
    })
    const data = res.data || res
    // Check if backend returned a proposal (needs confirmation)
    if (data.proposal || data.proposal_id) {
      currentProposal.value = data.proposal || data
      showProposal.value = true
      aiResult.value = { type: "buy", message: "AI 建仓提案已生成，请确认后执行" }
    } else {
      aiResult.value = { type: "buy", ...data }
      await load()
    }
  } catch (e: any) {
    alert(e.message || "AI 建仓失败")
  } finally {
    aiBuyLoading.value = false
  }
}

async function runAiSell() {
  aiSellLoading.value = true
  aiResult.value = null
  try {
    const res: any = await aiAutoSell({
      stop_loss_pct: aiStopLoss.value,
      take_profit_pct: aiTakeProfit.value,
    })
    const data = res.data || res
    if (data.proposal || data.proposal_id) {
      currentProposal.value = data.proposal || data
      showProposal.value = true
      aiResult.value = { type: "sell", message: "AI 清仓提案已生成，请确认后执行" }
    } else {
      aiResult.value = { type: "sell", ...data }
      await load()
    }
  } catch (e: any) {
    alert(e.message || "AI 清仓失败")
  } finally {
    aiSellLoading.value = false
  }
}

onMounted(async () => {
  // Load core data first (fast, local DB)
  await load()
  try {
    const res: any = await getStrategies()
    strategies.value = res.data || []
  } catch {
    /* ignore */
  }
  // Defer AI-heavy calls so page renders immediately
  fetchRiskStatus()
  setTimeout(() => {
    fetchSignals()
    runDiagnosis()
  }, 1500)
  refreshTimer = setInterval(refresh, 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <div>
        <h1 class="page-title">模拟盘</h1>
        <p class="page-desc">虚拟资金模拟交易 · 实时行情计价 · AI 智能建仓与清仓</p>
      </div>
      <button class="btn-refresh" @click="refresh" :disabled="refreshing">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ spinning: refreshing }">
          <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
        刷新行情
      </button>
      <button class="btn-reset" @click="handleResetAccount">
        重置模拟盘
      </button>
    </div>

    <!-- Account Summary -->
    <div class="stat-grid animate-in delay-1">
      <div class="stat-card">
        <div class="stat-label">总资产</div>
        <div class="stat-value mono">{{ fmtMoney(account.total_assets) }}</div>
        <div class="stat-sub">初始资金 {{ fmtMoney(account.initial_cash) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">可用资金</div>
        <div class="stat-value mono">{{ fmtMoney(account.cash) }}</div>
        <div class="stat-sub">持仓市值 {{ fmtMoney(account.market_value) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">总盈亏</div>
        <div class="stat-value mono" :class="valClass(account.total_pnl)">{{ fmtSignedMoney(account.total_pnl) }}</div>
        <div class="stat-sub" :class="valClass(account.total_pnl)">{{ fmtPct(account.total_pnl_pct) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">今日盈亏</div>
        <div class="stat-value mono" :class="valClass(account.today_pnl)">{{ fmtSignedMoney(account.today_pnl) }}</div>
        <div class="stat-sub">持仓 {{ account.position_count }} 只</div>
      </div>
    </div>

    <!-- Portfolio Diagnosis -->
    <div class="diag-card card animate-in delay-1" v-liquid>
      <div class="diag-head">
        <div class="ai-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>
          AI 组合诊断
        </div>
        <button class="diag-btn" @click="runDiagnosis" :disabled="diagLoading">
          {{ diagLoading ? '诊断中...' : '开始诊断' }}
        </button>
      </div>
      <div v-if="diagnosis" class="diag-body">
        <div v-if="diagnosis.scores && Object.keys(diagnosis.scores).length" class="diag-scores">
          <div class="score-item">
            <div class="score-bar"><div class="score-fill" :style="{ width: diagnosis.scores.concentration + '%' }"></div></div>
            <span class="score-label">集中度 {{ diagnosis.scores.concentration }}</span>
          </div>
          <div class="score-item">
            <div class="score-bar"><div class="score-fill" :style="{ width: diagnosis.scores.diversification + '%' }"></div></div>
            <span class="score-label">分散度 {{ diagnosis.scores.diversification }}</span>
          </div>
          <div class="score-item">
            <div class="score-bar"><div class="score-fill" :style="{ width: diagnosis.scores.profitability + '%' }"></div></div>
            <span class="score-label">盈利性 {{ diagnosis.scores.profitability }}</span>
          </div>
        </div>
        <div class="diag-text">{{ diagnosis.diagnosis }}</div>
      </div>
      <div v-else-if="!diagLoading" class="diag-empty">点击「开始诊断」，AI 将分析你的持仓集中度、行业分布和配置建议</div>
    </div>

    <!-- AI Signals & Auto Trade -->
    <div class="signals-card card animate-in delay-2" v-liquid>
      <div class="signals-head">
        <div class="ai-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
          AI 交易信号
        </div>
        <div class="signals-actions">
          <button class="sig-btn" @click="fetchSignals" :disabled="signalsLoading">{{ signalsLoading ? '扫描中...' : '扫描信号' }}</button>
          <button class="sig-btn auto" @click="runAutoTrade" :disabled="autoLoading">{{ autoLoading ? '执行中...' : '一键自动交易' }}</button>
        </div>
      </div>

      <!-- Risk Status Bar -->
      <div v-if="riskStatus" class="risk-bar">
        <span class="risk-item">今日交易 {{ riskStatus.daily_trades }}/{{ riskStatus.max_daily_trades }}</span>
        <span class="risk-item">单只上限 {{ (riskStatus.max_position_pct * 100).toFixed(0) }}%</span>
        <span class="risk-item">止损 {{ riskStatus.stop_loss_pct }}%</span>
        <span class="risk-item">止盈 +{{ riskStatus.take_profit_pct }}%</span>
      </div>

      <!-- Signal List -->
      <div v-if="signals.length" class="signal-list">
        <div v-for="s in signals" :key="s.code" class="signal-item" @click="$router.push('/stock/' + s.code)">
          <div class="sig-id"><span class="sig-name">{{ s.name || s.code }}</span><span class="sig-code mono">{{ s.code }}</span></div>
          <span class="sig-price mono">{{ s.price?.toFixed(2) }}</span>
          <span class="sig-badge" :class="signalClass(s.signal)">{{ signalLabel(s.signal) }}</span>
          <span class="sig-reasons">{{ s.reasons?.join(', ') }}</span>
        </div>
      </div>
      <div v-else-if="!signalsLoading" class="sig-empty">点击「扫描信号」分析自选股技术面</div>

      <!-- AI Commentary -->
      <div v-if="signalCommentary" class="sig-commentary">{{ signalCommentary }}</div>

      <!-- Auto Trade Result -->
      <div v-if="autoResult" class="auto-result">
        <div class="auto-msg">{{ autoResult.message }}</div>
        <div v-if="autoResult.executed?.length" class="auto-executed">
          <div v-for="(e, i) in autoResult.executed" :key="i" class="auto-item success">
            {{ e.action === 'buy' ? '买入' : '卖出' }} {{ e.code }} {{ e.qty }}股 — {{ e.reason }}
          </div>
        </div>
        <div v-if="autoResult.skipped?.length" class="auto-skipped">
          <div v-for="(s, i) in autoResult.skipped" :key="i" class="auto-item warn">
            跳过 {{ s.code }} — {{ s.reason }}
          </div>
        </div>
      </div>
    </div>

    <div class="main-grid">
      <!-- Trade Form -->
      <div class="card animate-in delay-2" v-liquid>
        <div class="side-tabs">
          <button class="side-tab" :class="{ active: side === 'buy', 'tab-buy': side === 'buy' }" @click="switchSide('buy')">买入</button>
          <button class="side-tab" :class="{ active: side === 'sell', 'tab-sell': side === 'sell' }" @click="switchSide('sell')">卖出</button>
        </div>

        <div class="form-body">
          <div class="control-group search-wrap">
            <label>股票代码</label>
            <input
              v-model="form.code"
              class="input"
              placeholder="输入代码或名称，如 600519 / 茅台"
              autocomplete="off"
              @input="onSearchInput"
              @focus="onSearchInput"
              @blur="onBlurSearch"
            />
            <div v-if="showSearch && (searchResults.length || searchLoading)" class="search-dropdown">
              <div v-if="searchLoading" class="search-item disabled">搜索中...</div>
              <div
                v-for="s in searchResults"
                :key="s.code"
                class="search-item"
                @mousedown.prevent="selectStock(s)"
              >
                <span class="s-name">{{ s.name }}</span>
                <span class="s-code mono">{{ s.code }}</span>
              </div>
            </div>
          </div>

          <div class="control-group">
            <label>名称</label>
            <input v-model="form.name" class="input" placeholder="自动填充" />
          </div>

          <div class="control-group">
            <label>价格</label>
            <input v-model.number="form.price" type="number" step="0.01" class="input num-input" />
          </div>

          <div class="control-group qty-group">
            <label>数量（股）</label>
            <input v-model.number="form.qty" type="number" step="100" class="input num-input" />
            <div class="qty-shortcuts">
              <button class="chip" @click="setQty(100)">100股</button>
              <button class="chip" @click="setQty(500)">500股</button>
              <button class="chip" @click="setQty(1000)">1000股</button>
              <button class="chip" @click="setFull">全仓</button>
            </div>
          </div>

          <div class="estimate-row">
            <span class="estimate-label">{{ side === 'buy' ? '预计花费' : '预计回款' }}</span>
            <span class="estimate-value mono">¥ {{ fmtMoney(estimated) }}</span>
          </div>

          <button
            class="btn-trade"
            :class="side === 'buy' ? 'btn-buy' : 'btn-sell-big'"
            :disabled="submitting"
            @click="submitTrade"
          >
            {{ submitting ? '提交中...' : (side === 'buy' ? '确认买入' : '确认卖出') }}
          </button>
        </div>
      </div>

      <!-- AI Auto-trade -->
      <div class="card ai-card animate-in delay-3" v-liquid>
        <div class="card-title">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2a3 3 0 0 0-3 3v1H7a3 3 0 0 0 0 6h1v1H7a3 3 0 0 0 0 6h2v1a3 3 0 0 0 6 0v-1h2a3 3 0 0 0 0-6h-1v-1h1a3 3 0 0 0 0-6h-2V5a3 3 0 0 0-3-3z" />
          </svg>
          AI 智能交易
        </div>

        <div class="ai-controls">
          <div class="control-group">
            <label>建仓策略</label>
            <select v-model="aiStrategy" class="select">
              <option v-for="s in strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
          <div class="control-group">
            <label>股票池</label>
            <select v-model="aiUniverse" class="select">
              <option value="hs300">沪深300</option>
              <option value="zz500">中证500</option>
              <option value="zz1000">中证1000</option>
              <option value="all">全市场</option>
            </select>
          </div>
          <div class="control-group">
            <label>建仓只数</label>
            <input v-model.number="aiTopN" type="number" min="1" max="20" class="input num-input" />
          </div>
          <div class="control-group">
            <label>单票上限</label>
            <select v-model.number="aiMaxPct" class="select">
              <option :value="0.1">10%</option>
              <option :value="0.2">20%</option>
              <option :value="0.3">30%</option>
            </select>
          </div>
        </div>

        <button class="btn-ai btn-ai-buy" @click="runAiBuy" :disabled="aiBuyLoading || aiSellLoading">
          {{ aiBuyLoading ? 'AI 建仓中...' : 'AI 智能建仓' }}
        </button>

        <div class="ai-divider"></div>

        <div class="ai-controls">
          <div class="control-group">
            <label>止损线</label>
            <div class="pct-input"><input v-model.number="aiStopLoss" type="number" min="0" max="50" class="input num-input" /><span>%</span></div>
          </div>
          <div class="control-group">
            <label>止盈线</label>
            <div class="pct-input"><input v-model.number="aiTakeProfit" type="number" min="0" max="200" class="input num-input" /><span>%</span></div>
          </div>
        </div>

        <button class="btn-ai btn-ai-sell" @click="runAiSell" :disabled="aiBuyLoading || aiSellLoading">
          {{ aiSellLoading ? 'AI 清仓中...' : 'AI 智能清仓' }}
        </button>

        <div v-if="aiResult" class="ai-result" :class="aiResult.type === 'buy' ? 'res-buy' : 'res-sell'">
          <div class="ai-result-msg">{{ aiResult.message }}</div>
          <template v-if="aiResult.type === 'buy' && aiResult.bought && aiResult.bought.length">
            <div v-for="b in aiResult.bought" :key="b.code" class="ai-result-item">
              <span class="mono">{{ b.code }}</span>
              <span class="ai-r-name">{{ b.name }}</span>
              <span class="mono">{{ b.qty }}股 @ {{ b.price }}</span>
            </div>
          </template>
          <template v-else-if="aiResult.type === 'sell' && aiResult.sold && aiResult.sold.length">
            <div v-for="s in aiResult.sold" :key="s.code" class="ai-result-item">
              <span class="mono">{{ s.code }}</span>
              <span class="ai-r-name">{{ s.name }}</span>
              <span class="mono" :class="valClass(s.pnl)">{{ s.reason }} {{ fmtSignedMoney(s.pnl) }}</span>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Positions -->
    <div class="card animate-in delay-4" v-liquid>
      <div class="card-title">当前持仓</div>
      <div class="table-scroll">
        <table v-if="positions.length" class="data-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th class="r">数量</th>
              <th class="r">成本价</th>
              <th class="r">现价</th>
              <th class="r">市值</th>
              <th class="r">盈亏</th>
              <th class="r">盈亏%</th>
              <th class="r">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in positions" :key="p.id" class="clickable-row" @click="$router.push(p.type === 'fund' ? '/fund/' + p.code : '/stock/' + p.code)">
              <td class="mono">{{ p.code }}</td>
              <td>{{ p.name || p.code }}</td>
              <td class="r mono">{{ Math.floor(p.qty) }}</td>
              <td class="r mono">{{ (p.cost || 0).toFixed(2) }}</td>
              <td class="r mono" :class="valClass(p.change_pct)">{{ (p.price || 0).toFixed(2) }}</td>
              <td class="r mono">{{ fmtMoney(p.market_value) }}</td>
              <td class="r mono" :class="valClass(p.pnl)">{{ fmtSignedMoney(p.pnl) }}</td>
              <td class="r">
                <span class="pill" :class="p.pnl >= 0 ? 'pill-up' : 'pill-down'">{{ fmtPct(p.pnl_pct) }}</span>
              </td>
              <td class="r"><button class="btn-sell" @click="quickSell(p)">卖出</button></td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty">暂无持仓，可通过买入或 AI 智能建仓开始</div>
      </div>
    </div>

    <!-- Trade History -->
    <div class="card animate-in delay-5" v-liquid v-if="history.length">
      <div class="card-title">交易记录</div>
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>代码</th>
              <th>名称</th>
              <th>方向</th>
              <th class="r">数量</th>
              <th class="r">价格</th>
              <th class="r">金额</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in history" :key="h.id">
              <td class="mono">{{ h.created_at }}</td>
              <td class="mono">{{ h.code }}</td>
              <td>{{ h.name || h.code }}</td>
              <td>
                <span class="pill" :class="h.action === 'buy' ? 'pill-up' : 'pill-down'">
                  {{ h.action === 'buy' ? '买入' : '卖出' }}
                </span>
              </td>
              <td class="r mono">{{ Math.floor(h.qty) }}</td>
              <td class="r mono">{{ (h.price || 0).toFixed(2) }}</td>
              <td class="r mono">{{ fmtMoney(h.amount) }}</td>
              <td class="note-cell">{{ h.note || '--' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Proposal Confirmation Dialog -->
    <ProposalConfirm
      :visible="showProposal"
      :proposal="currentProposal"
      @confirm="handleConfirmProposal"
      @cancel="handleCancelProposal"
    />
  </div>
</template>

<style scoped>
.page { max-width: 1200px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; gap: 16px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.btn-refresh {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
  border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-secondary); font-size: 12px; font-weight: 500;
  cursor: pointer; transition: all 0.18s; font-family: var(--font-sans); white-space: nowrap;
}
.btn-refresh:hover { border-color: var(--accent); color: var(--accent); }
.btn-refresh:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-reset {
  display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px;
  border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-secondary); font-size: 12px; font-weight: 500;
  cursor: pointer; transition: all 0.18s; font-family: var(--font-sans); white-space: nowrap;
}
.btn-reset:hover { border-color: var(--down); color: var(--down); }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Stat cards */
.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md); padding: 18px 20px; transition: all var(--transition-theme);
}
.stat-card:hover { border-color: var(--border-default); }
.stat-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); margin-bottom: 10px; }
.stat-value { font-size: 22px; font-weight: 700; color: var(--text-primary); line-height: 1.1; }
.stat-sub { font-size: 11px; color: var(--text-tertiary); margin-top: 8px; }

/* Layout */
.main-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }

.card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md); padding: 20px; transition: all var(--transition-theme); margin-bottom: 20px;
}
.card-title { display: flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 600; margin-bottom: 16px; color: var(--text-primary); }

/* Side tabs */
.side-tabs { display: flex; gap: 8px; margin-bottom: 18px; }
.side-tab {
  flex: 1; padding: 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-secondary); font-size: 13px; font-weight: 600;
  cursor: pointer; transition: all 0.18s; font-family: var(--font-sans);
}
.side-tab.tab-buy { background: var(--up-dim); border-color: var(--up); color: var(--up); }
.side-tab.tab-sell { background: var(--down-dim); border-color: var(--down); color: var(--down); }

/* Form */
.form-body { display: flex; flex-direction: column; gap: 14px; }
.control-group { display: flex; flex-direction: column; gap: 6px; position: relative; }
.control-group label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); }
.input {
  padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; outline: none; width: 100%;
  transition: all 0.2s; font-family: var(--font-sans);
}
.input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.num-input { font-family: var(--font-mono); }
.select {
  padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; outline: none; width: 100%; transition: all 0.2s;
}
.select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

/* Search dropdown */
.search-dropdown {
  position: absolute; top: 100%; left: 0; right: 0; z-index: 30; margin-top: 4px;
  background: var(--bg-elevated); border: 1px solid var(--border-default);
  border-radius: var(--radius-sm); box-shadow: var(--shadow-elevated); overflow: hidden; max-height: 240px; overflow-y: auto;
}
.search-item { display: flex; align-items: center; justify-content: space-between; padding: 9px 14px; cursor: pointer; transition: background 0.12s; }
.search-item:hover { background: var(--bg-hover); }
.search-item.disabled { color: var(--text-tertiary); cursor: default; font-size: 12px; }
.s-name { font-size: 12.5px; color: var(--text-primary); }
.s-code { font-size: 11px; color: var(--text-tertiary); }

/* Qty shortcuts */
.qty-shortcuts { display: flex; gap: 6px; margin-top: 8px; }
.chip {
  flex: 1; padding: 5px 0; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: transparent; color: var(--text-secondary); font-size: 11px; font-weight: 500;
  cursor: pointer; transition: all 0.15s; font-family: var(--font-sans);
}
.chip:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }

/* Estimate */
.estimate-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; background: var(--bg-overlay); border-radius: var(--radius-sm); }
.estimate-label { font-size: 11px; color: var(--text-tertiary); }
.estimate-value { font-size: 15px; font-weight: 700; color: var(--text-primary); }

/* Trade button */
.btn-trade {
  padding: 12px; border-radius: var(--radius-sm); border: none; font-weight: 700; font-size: 14px;
  cursor: pointer; transition: all 0.18s; font-family: var(--font-sans); color: #fff;
}
.btn-buy { background: var(--up); }
.btn-buy:hover { opacity: 0.9; transform: translateY(-1px); }
.btn-sell-big { background: var(--down); }
.btn-sell-big:hover { opacity: 0.9; transform: translateY(-1px); }
.btn-trade:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

/* AI card */
.ai-controls { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }
.pct-input { display: flex; align-items: center; gap: 6px; }
.pct-input span { color: var(--text-tertiary); font-size: 12px; }
.btn-ai {
  width: 100%; padding: 11px; border-radius: var(--radius-sm); border: none; font-weight: 700; font-size: 13px;
  cursor: pointer; transition: all 0.18s; font-family: var(--font-sans); display: inline-flex; align-items: center; justify-content: center; gap: 7px;
}
.btn-ai-buy { background: linear-gradient(135deg, var(--accent), #a8884a); color: #0a0c10; box-shadow: 0 4px 14px var(--accent-glow); }
.btn-ai-buy:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--accent-glow); }
.btn-ai-sell { background: var(--bg-overlay); border: 1px solid var(--down); color: var(--down); }
.btn-ai-sell:hover { background: var(--down-dim); }
.btn-ai:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.ai-divider { height: 1px; background: var(--border-subtle); margin: 16px 0; }

.ai-result { margin-top: 14px; padding: 12px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }
.ai-result.res-buy { background: var(--accent-dim); border-color: var(--accent); }
.ai-result.res-sell { background: var(--down-dim); border-color: var(--down); }
.ai-result-msg { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.ai-result-item { display: flex; align-items: center; gap: 10px; font-size: 11.5px; color: var(--text-secondary); padding: 4px 0; }
.ai-r-name { flex: 1; color: var(--text-primary); }

/* Tables */
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
.data-table th.r { text-align: right; }
.data-table td { padding: 11px 14px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle); white-space: nowrap; }
.data-table tr:last-child td { border-bottom: none; }
.data-table tr:hover td { background: var(--bg-hover); }
.data-table .r { text-align: right; }
.mono { font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums; }
.note-cell { color: var(--text-tertiary); font-size: 11px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }

.pill { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; font-family: var(--font-mono); }
.pill-up { background: var(--up-dim); color: var(--up); }
.pill-down { background: var(--down-dim); color: var(--down); }

.btn-sell {
  padding: 4px 12px; border-radius: var(--radius-sm); border: 1px solid var(--down);
  background: transparent; color: var(--down); font-size: 11px; font-weight: 500; cursor: pointer; transition: all 0.15s;
}
.btn-sell:hover { background: var(--down-dim); }

.empty { color: var(--text-tertiary); font-size: 13px; padding: 24px 0; text-align: center; }

@media (max-width: 900px) {
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .main-grid { grid-template-columns: 1fr; }
}

/* Diagnosis Card */
.diag-card { margin-bottom: 20px; }
.diag-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.diag-btn { padding: 6px 14px; border-radius: var(--radius-sm); border: 1px solid var(--accent); background: var(--accent-dim); color: var(--accent); font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.diag-btn:hover:not(:disabled) { background: var(--accent); color: #111; }
.diag-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.diag-scores { display: flex; gap: 16px; margin-bottom: 14px; }
.score-item { flex: 1; }
.score-bar { height: 4px; background: var(--bg-overlay); border-radius: 2px; overflow: hidden; margin-bottom: 4px; }
.score-fill { height: 100%; background: var(--accent); border-radius: 2px; transition: width 0.6s ease; }
.score-label { font-size: 10px; color: var(--text-tertiary); }
.diag-text { font-size: 13px; line-height: 1.8; color: var(--text-secondary); white-space: pre-wrap; }
.diag-empty { font-size: 12px; color: var(--text-tertiary); padding: 8px 0; }

/* Signals Card */
.signals-card { margin-bottom: 20px; }
.signals-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.signals-actions { display: flex; gap: 8px; }
.sig-btn { padding: 6px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 11px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.sig-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.sig-btn.auto { border-color: var(--accent); background: var(--accent-dim); color: var(--accent); }
.sig-btn.auto:hover:not(:disabled) { background: var(--accent); color: #111; }
.sig-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.risk-bar { display: flex; gap: 16px; padding: 8px 12px; background: var(--bg-overlay); border-radius: var(--radius-sm); margin-bottom: 12px; }
.risk-item { font-size: 10px; color: var(--text-tertiary); }
.signal-list { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.signal-item { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.15s; }
.signal-item:hover { background: var(--bg-hover); }
.sig-id { display: flex; flex-direction: column; gap: 1px; width: 90px; }
.sig-name { font-size: 12px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sig-code { font-size: 10px; color: var(--text-tertiary); }
.sig-price { font-size: 12px; color: var(--text-secondary); width: 60px; }
.sig-badge { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 3px; }
.sig-badge.sig-buy { background: rgba(240,72,72,0.1); color: var(--up); }
.sig-badge.sig-sell { background: rgba(38,201,102,0.1); color: var(--down); }
.sig-badge.sig-neutral { background: var(--bg-overlay); color: var(--text-tertiary); }
.sig-reasons { font-size: 11px; color: var(--text-tertiary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sig-empty { font-size: 12px; color: var(--text-tertiary); padding: 8px 0; }
.clickable-row { cursor: pointer; }
.clickable-row:hover td { background: var(--bg-hover); }
.sig-commentary { font-size: 12px; line-height: 1.7; color: var(--text-secondary); padding: 10px 12px; background: var(--bg-overlay); border-radius: var(--radius-sm); margin-top: 8px; white-space: pre-wrap; }
.auto-result { margin-top: 12px; padding: 12px; background: var(--bg-overlay); border-radius: var(--radius-sm); }
.auto-msg { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.auto-item { font-size: 11px; padding: 4px 0; }
.auto-item.success { color: var(--up); }
.auto-item.warn { color: #f59e0b; }
</style>
