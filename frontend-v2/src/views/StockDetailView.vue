<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue"
import { useRoute, useRouter } from "vue-router"
import echarts from "@/echarts"
import { getQuote, getKline, getMinuteKline, getRealtime, addWatch, removeWatch, getWatchlist, buyStock, sellStock, getAccount } from "@/api"
import AIPanel from "@/components/AIPanel.vue"
import { useTradingHours } from "@/composables/useTradingHours"

const { canTradeStock, stockStatusText } = useTradingHours()

const route = useRoute()
const router = useRouter()
const code = computed(() => route.params.code as string)

function goBack() {
  if (window.history.length > 2) {
    router.back()
  } else {
    router.push('/')
  }
}
const quote = ref<any>(null)
const klines = ref<any[]>([])
const realtimeData = ref<any>(null)
const loading = ref(true)
const chartEl = ref<HTMLDivElement>()
let chart: any = null

const period = ref('day')
const periodOptions = [
  { label: "\u5206\u65f6", value: "realtime" },
  { label: "1\u5206", value: "m1" },
  { label: "5\u5206", value: "m5" },
  { label: "15\u5206", value: "m15" },
  { label: "30\u5206", value: "m30" },
  { label: "60\u5206", value: "m60" },
  { label: "\u65e5K", value: "day" },
  { label: "\u5468K", value: "week" },
  { label: "\u6708K", value: "month" },
]

const inWatchlist = ref(false)

// Trade modal
const showTradeModal = ref(false)
const tradeSide = ref<"buy" | "sell">("buy")
const tradeQty = ref(100)
const tradeLoading = ref(false)
const tradeMsg = ref("")
const accountCash = ref(0)
const holdingQty = ref(0)

function openTrade(side: "buy" | "sell") {
  tradeSide.value = side
  tradeQty.value = 100
  tradeMsg.value = ""
  showTradeModal.value = true
  loadAccount()
}

async function loadAccount() {
  try {
    const res: any = await getAccount()
    accountCash.value = res.data?.cash || 0
    const positions = res.data?.positions || []
    const pos = positions.find((p: any) => p.code === code.value)
    holdingQty.value = pos ? pos.qty : 0
  } catch {}
}

function setQty(q: number) { tradeQty.value = q }
function setMaxQty() {
  if (!quote.value?.price) return
  if (tradeSide.value === "buy") {
    tradeQty.value = Math.floor(accountCash.value / quote.value.price / 100) * 100
  } else {
    tradeQty.value = holdingQty.value
  }
}

async function confirmTrade() {
  if (!quote.value?.price || tradeQty.value <= 0) return
  tradeLoading.value = true
  tradeMsg.value = ""
  try {
    const payload = { code: code.value, name: quote.value.name || "", asset_type: "stock", qty: tradeQty.value, price: quote.value.price }
    const fn = tradeSide.value === "buy" ? buyStock : sellStock
    await fn(payload)
    tradeMsg.value = tradeSide.value === "buy"
      ? `\u4e70\u5165\u6210\u529f\uff1a${tradeQty.value}\u80a1 @ ${quote.value.price.toFixed(2)}`
      : `\u5356\u51fa\u6210\u529f\uff1a${tradeQty.value}\u80a1 @ ${quote.value.price.toFixed(2)}`
    loadAccount()
  } catch (e: any) {
    tradeMsg.value = e.message || "\u4ea4\u6613\u5931\u8d25"
  } finally { tradeLoading.value = false }
}

// AI Context
const aiContext = computed(() => {
  const name = quote.value?.name || code.value
  let ctx = `stock|${code.value}|${name}\n`
  if (quote.value) {
    ctx += `当前价: ${quote.value.price}, 涨跌: ${quote.value.change_pct}%\n`
    ctx += `今开: ${quote.value.open}, 最高: ${quote.value.high}, 最低: ${quote.value.low}\n`
    ctx += `成交量: ${quote.value.volume}, 成交额: ${quote.value.amount}\n`
    ctx += `换手率: ${quote.value.turnover}%, 市盈率: ${quote.value.pe}, 市净率: ${quote.value.pb}\n`
  }
  ctx += `请以专业股票投资顾问身份回答，给出实用建议。`
  return ctx
})


// Chart functions
function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + (v || 0).toFixed(2) + "%" }

function calcMA(data: number[], n: number): (number | null)[] {
  const result: (number | null)[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < n - 1) { result.push(null); continue }
    let sum = 0
    for (let j = 0; j < n; j++) sum += data[i - j]
    result.push(+(sum / n).toFixed(2))
  }
  return result
}

function calcEMA(data: number[], n: number): number[] {
  const result: number[] = []
  const k = 2 / (n + 1)
  for (let i = 0; i < data.length; i++) {
    if (i === 0) result.push(data[0])
    else result.push(data[i] * k + result[i - 1] * (1 - k))
  }
  return result
}

function calcMACD(closes: number[]) {
  const ema12 = calcEMA(closes, 12)
  const ema26 = calcEMA(closes, 26)
  const dif = closes.map((_, i) => +(ema12[i] - ema26[i]).toFixed(4))
  const dea = calcEMA(dif, 9).map(v => +v.toFixed(4))
  const histogram = dif.map((d, i) => +((d - dea[i]) * 2).toFixed(4))
  return { dif, dea, histogram }
}

async function load() {
  loading.value = true
  quote.value = null
  klines.value = []
  try {
    const [qRes, kRes]: any[] = await Promise.all([
      getQuote(code.value).catch(() => ({ data: null })),
      getKline(code.value, period.value, 120).catch(() => ({ data: [] })),
    ])
    quote.value = qRes.data || null
    klines.value = kRes.data || []
    renderChart()
  } finally { loading.value = false }
}

async function changePeriod(p: string) {
  period.value = p
  if (p === "realtime") {
    try {
      const res: any = await getRealtime(code.value)
      realtimeData.value = res.data || {}
      renderRealtimeChart()
    } catch {}
    return
  }
  const isMinute = p.startsWith("m")
  try {
    const res: any = isMinute ? await getMinuteKline(code.value, p, 120) : await getKline(code.value, p, 120)
    klines.value = res.data || []
    renderChart()
  } catch {}
}

function renderRealtimeChart() {
  if (!chartEl.value) return
  if (!chart) chart = echarts.init(chartEl.value)
  const d = realtimeData.value
  if (!d?.minutes?.length) return
  const times = d.minutes.map((m: any) => m.time)
  const prices = d.minutes.map((m: any) => m.price)
  const volumes = d.minutes.map((m: any) => m.volume)
  const prevClose = d.prev_close || prices[0]
  const cs = getComputedStyle(document.documentElement)
  const accent = cs.getPropertyValue("--accent").trim() || "#c9a962"

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    grid: [{ left: 60, right: 20, top: 24, height: "60%" }, { left: 60, right: 20, top: "72%", height: "20%" }],
    xAxis: [
      { type: "category", data: times, gridIndex: 0, axisLabel: { color: "#6b7280", fontSize: 10, interval: 59 }, boundaryGap: false },
      { type: "category", data: times, gridIndex: 1, show: false, boundaryGap: false },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "rgba(107,114,128,0.08)" } }, axisLabel: { color: "#6b7280", fontSize: 10 } },
      { scale: true, gridIndex: 1, show: false },
    ],
    series: [
      { name: "\u4ef7\u683c", type: "line", data: prices, xAxisIndex: 0, yAxisIndex: 0, showSymbol: false, lineStyle: { width: 1.5, color: accent }, areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: "rgba(201,169,98,0.2)" }, { offset: 1, color: "rgba(201,169,98,0.01)" }] } }, markLine: { silent: true, symbol: "none", lineStyle: { type: "dashed", color: "#6b7280", width: 1 }, data: [{ yAxis: prevClose }], label: { formatter: prevClose.toFixed(2), color: "#6b7280", fontSize: 10 } } },
      { name: "\u6210\u4ea4\u91cf", type: "bar", data: volumes.map((v: number, i: number) => ({ value: v, itemStyle: { color: prices[i] >= prevClose ? "rgba(240,72,72,0.35)" : "rgba(38,201,102,0.35)" } })), xAxisIndex: 1, yAxisIndex: 1 },
    ],
  }, true)
}

function renderChart() {
  if (!chartEl.value || !klines.value.length) return
  if (!chart) chart = echarts.init(chartEl.value)
  const dates = klines.value.map((k: any) => k.date)
  const ohlc = klines.value.map((k: any) => [k.open, k.close, k.low, k.high])
  const volumes = klines.value.map((k: any) => k.volume)
  const closes = klines.value.map((k: any) => k.close)
  const ma5 = calcMA(closes, 5), ma10 = calcMA(closes, 10), ma20 = calcMA(closes, 20), ma60 = calcMA(closes, 60)
  const { dif, dea, histogram } = calcMACD(closes)
  const cs = getComputedStyle(document.documentElement)
  const upColor = cs.getPropertyValue("--up").trim() || "#f04848"
  const downColor = cs.getPropertyValue("--down").trim() || "#26c966"

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    legend: { data: ["MA5", "MA10", "MA20", "MA60"], top: 0, left: 60, textStyle: { color: "#6b7280", fontSize: 10 }, itemWidth: 14, itemHeight: 2 },
    grid: [{ left: 60, right: 20, top: 24, height: "46%" }, { left: 60, right: 20, top: "58%", height: "13%" }, { left: 60, right: 20, top: "76%", height: "13%" }],
    xAxis: [
      { type: "category", data: dates, gridIndex: 0, axisLabel: { color: "#6b7280", fontSize: 10 }, boundaryGap: true },
      { type: "category", data: dates, gridIndex: 1, show: false, boundaryGap: true },
      { type: "category", data: dates, gridIndex: 2, axisLabel: { color: "#6b7280", fontSize: 10 }, boundaryGap: true },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "rgba(107,114,128,0.08)" } }, axisLabel: { color: "#6b7280", fontSize: 10 } },
      { scale: true, gridIndex: 1, show: false },
      { scale: true, gridIndex: 2, splitLine: { lineStyle: { color: "rgba(107,114,128,0.08)" } }, axisLabel: { color: "#6b7280", fontSize: 10 } },
    ],
    series: [
      { type: "candlestick", data: ohlc, xAxisIndex: 0, yAxisIndex: 0, itemStyle: { color: upColor, color0: downColor, borderColor: upColor, borderColor0: downColor } },
      { name: "MA5", type: "line", data: ma5, xAxisIndex: 0, yAxisIndex: 0, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#f5c842" } },
      { name: "MA10", type: "line", data: ma10, xAxisIndex: 0, yAxisIndex: 0, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#42a5f5" } },
      { name: "MA20", type: "line", data: ma20, xAxisIndex: 0, yAxisIndex: 0, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#ab47bc" } },
      { name: "MA60", type: "line", data: ma60, xAxisIndex: 0, yAxisIndex: 0, smooth: true, showSymbol: false, lineStyle: { width: 1, color: "#66bb6a" } },
      { type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: "rgba(201,169,98,0.35)" } },
      { name: "DIF", type: "line", data: dif, xAxisIndex: 2, yAxisIndex: 2, showSymbol: false, lineStyle: { width: 1, color: "#f5c842" } },
      { name: "DEA", type: "line", data: dea, xAxisIndex: 2, yAxisIndex: 2, showSymbol: false, lineStyle: { width: 1, color: "#42a5f5" } },
      { name: "MACD", type: "bar", data: histogram.map(v => ({ value: v, itemStyle: { color: v >= 0 ? upColor : downColor } })), xAxisIndex: 2, yAxisIndex: 2 },
    ],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1, 2], start: 50, end: 100 }],
  }, true)
}

async function checkWatchlist() {
  try {
    const res: any = await getWatchlist()
    inWatchlist.value = (res.data || []).some((it: any) => it.code === code.value)
  } catch {}
}

async function toggleWatch() {
  try {
    if (inWatchlist.value) { await removeWatch(code.value); inWatchlist.value = false }
    else { await addWatch(code.value, quote.value?.name || ""); inWatchlist.value = true }
  } catch (e: any) { alert(e.message) }
}

function onResize() { chart?.resize() }
onMounted(() => { load(); checkWatchlist(); window.addEventListener("resize", onResize) })
onUnmounted(() => { window.removeEventListener("resize", onResize) })

// Reload when navigating to a different stock
watch(code, (newCode, oldCode) => {
  if (newCode !== oldCode) {
    period.value = 'day'
    realtimeData.value = null
    load()
    checkWatchlist()
  }
})
</script>

<template>
  <div class="stock-detail-layout">
    <!-- Left: Market Data -->
    <div class="left-panel">
      <div class="detail-head animate-in">
        <button class="back-btn" v-liquid="{maxTilt:5,scale:1.06}" @click="goBack">&#8592; &#36820;&#22238;</button>
        <div class="head-info">
          <h1 class="stock-name">{{ quote?.name || code }}</h1>
          <span class="stock-code mono">{{ code }}</span>
        </div>
        <div class="head-actions">
          <span class="market-status" :class="{ open: canTradeStock }">{{ stockStatusText }}</span>
          <button class="btn-action" :class="{ watched: inWatchlist }" v-liquid="{maxTilt:5,scale:1.06}" @click="toggleWatch">{{ inWatchlist ? "&#10003; &#24050;&#33258;&#36873;" : "+ &#33258;&#36873;" }}</button>
          <button class="btn-action buy-btn" :disabled="!canTradeStock" v-liquid="{maxTilt:5,scale:1.06}" @click="openTrade('buy')">&#20080;&#20837;</button>
          <button class="btn-action sell-btn" :disabled="!canTradeStock" v-liquid="{maxTilt:5,scale:1.06}" @click="openTrade('sell')">&#21334;&#20986;</button>
        </div>
      </div>

      <!-- Quote Card -->
      <div class="quote-card card animate-in delay-1" v-liquid v-if="quote">
        <div class="quote-main">
          <span class="quote-price" :class="valClass(quote.change_pct)">{{ quote.price?.toFixed(2) }}</span>
          <span class="quote-change" :class="valClass(quote.change_pct)">{{ quote.change > 0 ? '+' : '' }}{{ quote.change?.toFixed(2) }}  {{ fmtPct(quote.change_pct) }}</span>
        </div>
        <div class="quote-grid">
          <div class="q-item"><span class="q-label">今开</span><span class="q-val mono">{{ quote.open?.toFixed(2) }}</span></div>
          <div class="q-item"><span class="q-label">昨收</span><span class="q-val mono">{{ quote.prev_close?.toFixed(2) }}</span></div>
          <div class="q-item"><span class="q-label">最高</span><span class="q-val mono val-up">{{ quote.high?.toFixed(2) }}</span></div>
          <div class="q-item"><span class="q-label">最低</span><span class="q-val mono val-down">{{ quote.low?.toFixed(2) }}</span></div>
          <div class="q-item"><span class="q-label">成交量</span><span class="q-val mono">{{ quote.volume ? (quote.volume / 1e4).toFixed(1) + '万手' : '--' }}</span></div>
          <div class="q-item"><span class="q-label">成交额</span><span class="q-val mono">{{ quote.amount ? (quote.amount / 1e4).toFixed(1) + '亿' : '--' }}</span></div>
          <div class="q-item"><span class="q-label">换手率</span><span class="q-val mono">{{ quote.turnover ? quote.turnover.toFixed(2) + '%' : '--' }}</span></div>
          <div class="q-item"><span class="q-label">量比</span><span class="q-val mono">{{ quote.volume_ratio ? quote.volume_ratio.toFixed(2) : '--' }}</span></div>
          <div class="q-item"><span class="q-label">振幅</span><span class="q-val mono">{{ quote.amplitude ? quote.amplitude.toFixed(2) + '%' : '--' }}</span></div>
          <div class="q-item"><span class="q-label">均价</span><span class="q-val mono">{{ quote.avg_price ? quote.avg_price.toFixed(2) : '--' }}</span></div>
          <div class="q-item"><span class="q-label">市盈率(动)</span><span class="q-val mono">{{ quote.pe_dynamic ? quote.pe_dynamic.toFixed(1) : (quote.pe ? quote.pe.toFixed(1) : '--') }}</span></div>
          <div class="q-item"><span class="q-label">市盈率(静)</span><span class="q-val mono">{{ quote.pe ? quote.pe.toFixed(1) : '--' }}</span></div>
          <div class="q-item"><span class="q-label">市净率</span><span class="q-val mono">{{ quote.pb ? quote.pb.toFixed(2) : '--' }}</span></div>
          <div class="q-item"><span class="q-label">总市值</span><span class="q-val mono">{{ quote.market_cap ? quote.market_cap.toFixed(0) + '亿' : '--' }}</span></div>
          <div class="q-item"><span class="q-label">流通市值</span><span class="q-val mono">{{ quote.float_cap ? quote.float_cap.toFixed(0) + '亿' : '--' }}</span></div>
          <div class="q-item"><span class="q-label">涨停</span><span class="q-val mono val-up">{{ quote.limit_up ? quote.limit_up.toFixed(2) : '--' }}</span></div>
          <div class="q-item"><span class="q-label">跌停</span><span class="q-val mono val-down">{{ quote.limit_down ? quote.limit_down.toFixed(2) : '--' }}</span></div>
          <div class="q-item"><span class="q-label">外盘</span><span class="q-val mono val-up">{{ quote.outer_vol ? (quote.outer_vol / 1e4).toFixed(1) + '万' : '--' }}</span></div>
        </div>
      </div>

      <!-- K-line Chart -->
      <div class="card chart-card animate-in delay-2" v-liquid>
        <div class="period-selector">
          <button v-for="opt in periodOptions" :key="opt.value" class="period-btn" :class="{ active: period === opt.value }" @click="changePeriod(opt.value)">{{ opt.label }}</button>
        </div>
        <div ref="chartEl" class="chart"></div>
      </div>
    </div>

    <!-- Right: AI Chat Panel -->
    <div class="right-panel animate-in delay-2">
      <AIPanel :context="aiContext" :asset-code="code" :asset-name="quote?.name" default-question="综合分析这只股票" />
    </div>

    <!-- Trade Modal -->
    <Teleport to="body">
      <div v-if="showTradeModal" class="modal-overlay" @click.self="showTradeModal = false">
        <div class="trade-modal">
          <div class="trade-modal-head">
            <h3 :class="tradeSide === 'buy' ? 'val-up' : 'val-down'">{{ tradeSide === 'buy' ? '&#20080;&#20837;' : '&#21334;&#20986;' }} {{ quote?.name || code }}</h3>
            <button class="modal-close" @click="showTradeModal = false">&times;</button>
          </div>
          <div class="trade-modal-body">
            <div class="trade-info-row"><span class="trade-label">&#24403;&#21069;&#20215;</span><span class="trade-val mono">{{ quote?.price?.toFixed(2) }}</span></div>
            <div class="trade-info-row"><span class="trade-label">&#21487;&#29992;&#36164;&#37329;</span><span class="trade-val mono">{{ accountCash.toLocaleString() }}</span></div>
            <div class="trade-info-row"><span class="trade-label">&#24403;&#21069;&#25345;&#20179;</span><span class="trade-val mono">{{ holdingQty }} &#32929;</span></div>
            <div class="trade-field">
              <span class="trade-label">&#25968;&#37327;&#65288;&#32929;&#65289;</span>
              <input v-model.number="tradeQty" type="number" min="100" step="100" class="trade-input mono" />
            </div>
            <div class="trade-quick-btns">
              <button @click="setQty(100)">100&#32929;</button>
              <button @click="setQty(500)">500&#32929;</button>
              <button @click="setQty(1000)">1000&#32929;</button>
              <button @click="setMaxQty">&#20840;&#20179;</button>
            </div>
            <div class="trade-info-row total"><span class="trade-label">&#39044;&#35745;&#37329;&#39069;</span><span class="trade-val mono accent">{{ quote?.price ? (quote.price * tradeQty).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '--' }}</span></div>
            <div v-if="tradeMsg" class="trade-msg" :class="tradeMsg.includes('\u6210\u529f') ? 'success' : 'error'">{{ tradeMsg }}</div>
            <button class="trade-confirm" :class="tradeSide" :disabled="tradeLoading || tradeQty <= 0" @click="confirmTrade">{{ tradeLoading ? '&#22788;&#29702;&#20013;...' : (tradeSide === 'buy' ? '&#30830;&#35748;&#20080;&#20837;' : '&#30830;&#35748;&#21334;&#20986;') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.stock-detail-layout { display: flex; gap: 16px; align-items: flex-start; }
.left-panel { flex: 1; min-width: 0; }
.right-panel { width: 320px; flex-shrink: 0; position: sticky; top: 0; margin-top: -24px; height: calc(100vh - 96px); max-height: 740px; }

.detail-head { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.back-btn { padding: 6px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: all 0.15s; }
.back-btn:hover { border-color: var(--accent); color: var(--accent); }
.head-info { flex: 1; }
.stock-name { font-size: 20px; font-weight: 700; color: var(--text-primary); }
.stock-code { font-size: 12px; color: var(--text-tertiary); margin-left: 10px; }
.head-actions { display: flex; gap: 8px; }
.btn-action { padding: 7px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.btn-action:hover { border-color: var(--accent); color: var(--accent); }
.btn-action.watched { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
.buy-btn { border-color: var(--up); color: var(--up); }
.buy-btn:hover { background: rgba(240,72,72,0.1); }
.sell-btn { border-color: var(--down); color: var(--down); }
.sell-btn:hover { background: rgba(38,201,102,0.1); }
.btn-action:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-action:disabled:hover { background: transparent; }
.market-status { font-size: 11px; color: var(--text-tertiary); padding: 7px 0; white-space: nowrap; }
.market-status.open { color: var(--down); font-weight: 600; }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; margin-bottom: 16px; }
.quote-card { display: flex; gap: 32px; align-items: flex-start; flex-wrap: wrap; }
.quote-main { display: flex; flex-direction: column; gap: 4px; }
.quote-price { font-family: var(--font-mono); font-size: 32px; font-weight: 700; font-variant-numeric: tabular-nums; }
.quote-change { font-family: var(--font-mono); font-size: 14px; font-weight: 600; }
.quote-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; flex: 1; }
.q-item { display: flex; flex-direction: column; gap: 3px; }
.q-label { font-size: 10px; color: var(--text-tertiary); }
.q-val { font-size: 13px; font-weight: 500; color: var(--text-primary); }

.chart-card { padding: 16px; }
.period-selector { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.period-btn { padding: 4px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 11px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.period-btn:hover { border-color: var(--accent); color: var(--accent); }
.period-btn.active { background: var(--accent); border-color: var(--accent); color: #0a0c10; font-weight: 600; }
.chart { width: 100%; height: 420px; }


/* Trade Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.trade-modal { background: var(--bg-surface); border: 1px solid var(--border-default); border-radius: var(--radius-md); width: 380px; max-width: 90vw; }
.trade-modal-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border-subtle); }
.trade-modal-head h3 { font-size: 15px; font-weight: 600; margin: 0; }
.modal-close { background: none; border: none; color: var(--text-tertiary); font-size: 20px; cursor: pointer; line-height: 1; }
.modal-close:hover { color: var(--text-primary); }
.trade-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.trade-info-row { display: flex; justify-content: space-between; align-items: center; }
.trade-info-row.total { border-top: 1px solid var(--border-subtle); padding-top: 12px; }
.trade-label { font-size: 12px; color: var(--text-tertiary); }
.trade-val { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.trade-val.accent { color: var(--accent); font-size: 16px; }
.trade-field { display: flex; flex-direction: column; gap: 6px; }
.trade-input { width: 100%; padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: var(--bg-overlay); color: var(--text-primary); font-size: 15px; outline: none; }
.trade-input:focus { border-color: var(--accent); }
.trade-quick-btns { display: flex; gap: 8px; }
.trade-quick-btns button { flex: 1; padding: 6px 0; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 11px; cursor: pointer; transition: all 0.15s; }
.trade-quick-btns button:hover { border-color: var(--accent); color: var(--accent); }
.trade-msg { font-size: 12px; padding: 8px 12px; border-radius: var(--radius-sm); }
.trade-msg.success { background: rgba(38,201,102,0.1); color: var(--down); }
.trade-msg.error { background: rgba(240,72,72,0.1); color: var(--up); }
.trade-confirm { width: 100%; padding: 12px; border-radius: var(--radius-sm); border: none; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.trade-confirm.buy { background: var(--up); color: #fff; }
.trade-confirm.sell { background: var(--down); color: #fff; }
.trade-confirm:disabled { opacity: 0.5; cursor: not-allowed; }
.trade-confirm:hover:not(:disabled) { filter: brightness(1.1); }

.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.val-up { color: var(--up); }
.val-down { color: var(--down); }

@media (max-width: 1000px) {
  .stock-detail-layout { flex-direction: column; }
  .right-panel { width: 100%; position: static; }
  .ai-panel { height: 400px; }
  .quote-grid { grid-template-columns: repeat(3, 1fr); }
}
</style>
