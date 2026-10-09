<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue"
import { useRoute } from "vue-router"
import echarts from "@/echarts"
import { runBacktest, getKline } from "@/api"

const route = useRoute()
const code = ref((route.query.code as string) || "sh600519")
const strategy = ref("ma_cross")
const days = ref(250)
const loading = ref(false)
const result = ref<any>(null)
const chartEl = ref<HTMLDivElement>()
let chart: any = null

const strategyOptions = [
  { id: "ma_cross", name: "均线金叉 (MA5/MA20)" },
  { id: "bollinger", name: "布林带均值回归" },
  { id: "momentum", name: "20日动量" },
]

async function run() {
  loading.value = true
  result.value = null
  try {
    const [btRes, klRes]: any[] = await Promise.all([
      runBacktest(code.value, strategy.value, days.value),
      getKline(code.value, "day", days.value).catch(() => ({ data: [] })),
    ])
    result.value = btRes.data
    renderChart(klRes.data || [])
  } catch (e: any) { alert(e.message) }
  finally { loading.value = false }
}

function renderChart(klines: any[]) {
  if (!chartEl.value || !klines.length) return
  if (!chart) chart = echarts.init(chartEl.value)
  const dates = klines.map((k: any) => k.date)
  const ohlc = klines.map((k: any) => [k.open, k.close, k.low, k.high])
  const volumes = klines.map((k: any) => k.volume)
  const cs = getComputedStyle(document.documentElement)
  const upColor = cs.getPropertyValue("--up").trim() || "#f04848"
  const downColor = cs.getPropertyValue("--down").trim() || "#26c966"
  const textColor = cs.getPropertyValue("--text-tertiary").trim() || "#565f6e"
  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    grid: [
      { left: 60, right: 20, top: 20, height: "55%" },
      { left: 60, right: 20, top: "72%", height: "18%" },
    ],
    xAxis: [
      { type: "category", data: dates, gridIndex: 0, axisLabel: { color: textColor, fontSize: 10 } },
      { type: "category", data: dates, gridIndex: 1, show: false },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitLine: { lineStyle: { color: "rgba(107,114,128,0.08)" } }, axisLabel: { color: textColor, fontSize: 10 } },
      { scale: true, gridIndex: 1, show: false },
    ],
    series: [
      { type: "candlestick", data: ohlc, itemStyle: { color: upColor, color0: downColor, borderColor: upColor, borderColor0: downColor } },
      { type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: "rgba(201,169,98,0.35)" } },
    ],
    dataZoom: [{ type: "inside", xAxisIndex: [0, 1], start: 60, end: 100 }],
  })
}

function onResize() { chart?.resize() }
onMounted(() => window.addEventListener("resize", onResize))
onUnmounted(() => window.removeEventListener("resize", onResize))
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">策略回测</h1>
      <p class="page-desc">基于历史K线数据，验证策略有效性</p>
    </div>

    <div class="controls card animate-in delay-1">
      <div class="control-group">
        <label>股票代码</label>
        <input v-model="code" class="input" placeholder="sh600519" />
      </div>
      <div class="control-group">
        <label>策略</label>
        <select v-model="strategy" class="select">
          <option v-for="s in strategyOptions" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="control-group">
        <label>回测天数</label>
        <select v-model="days" class="select">
          <option :value="120">120天</option>
          <option :value="250">250天</option>
          <option :value="500">500天</option>
        </select>
      </div>
      <button class="btn btn-primary" v-liquid="{maxTilt: 6, scale: 1.04}" @click="run" :disabled="loading">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-9"/></svg>
        {{ loading ? "回测中..." : "开始回测" }}
      </button>
    </div>

    <div class="card chart-card animate-in delay-2" v-liquid><div ref="chartEl" class="chart"></div></div>

    <div v-if="result" class="summary-grid animate-in delay-3">
      <div class="card stat" v-liquid>
        <div class="stat-label">总交易</div>
        <div class="stat-value tnum">{{ result.summary?.total_trades }}</div>
      </div>
      <div class="card stat" v-liquid>
        <div class="stat-label">胜率</div>
        <div class="stat-value tnum" :class="(result.summary?.win_rate || 0) >= 50 ? 'val-up' : 'val-down'">{{ result.summary?.win_rate }}%</div>
      </div>
      <div class="card stat" v-liquid>
        <div class="stat-label">策略收益</div>
        <div class="stat-value tnum" :class="(result.summary?.total_return || 0) >= 0 ? 'val-up' : 'val-down'">{{ result.summary?.total_return }}%</div>
      </div>
      <div class="card stat" v-liquid>
        <div class="stat-label">买入持有</div>
        <div class="stat-value tnum" :class="(result.summary?.buy_hold_return || 0) >= 0 ? 'val-up' : 'val-down'">{{ result.summary?.buy_hold_return }}%</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.controls { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; padding: 20px; }
.control-group { display: flex; flex-direction: column; gap: 6px; }
.control-group label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); }
.input, .select {
  padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; outline: none; min-width: 130px;
  transition: all 0.2s; font-family: var(--font-sans);
}
.input:focus, .select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); transition: all var(--transition-theme); }
.chart-card { margin-bottom: 20px; padding: 16px; }
.chart { width: 100%; height: 380px; }

.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.stat { text-align: center; padding: 18px 12px; }
.stat-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); margin-bottom: 8px; }
.stat-value { font-size: 22px; font-weight: 700; }
.tnum { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.val-up { color: var(--up); }
.val-down { color: var(--down); }

.btn { font-family: var(--font-sans); font-size: 12.5px; font-weight: 600; padding: 10px 20px; border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all 0.18s ease; display: inline-flex; align-items: center; gap: 7px; }
.btn-primary { background: linear-gradient(135deg, var(--accent), #a8884a); color: #0a0c10; box-shadow: 0 4px 14px var(--accent-glow); }
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--accent-glow); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

@media (max-width: 900px) { .summary-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
