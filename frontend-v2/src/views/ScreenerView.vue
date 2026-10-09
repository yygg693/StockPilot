<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
import { getStrategies, runScreener } from "@/api"

interface Strategy { id: string; name: string; desc: string }
interface Match { code: string; name: string; price: number; change_pct: number; pe: number; pb: number; reason: string }

const strategies = ref<Strategy[]>([])
const matches = ref<Match[]>([])
const selected = ref("oversold_bounce")
const universe = ref("hs300")
const loading = ref(false)
const scanned = ref(0)
const router = useRouter()
function goStock(code: string) { router.push("/stock/" + code) }

onMounted(async () => {
  try {
    const res: any = await getStrategies()
    strategies.value = res.data || []
  } catch {}
})

async function run() {
  loading.value = true
  matches.value = []
  try {
    const res: any = await runScreener(selected.value, universe.value)
    const d = res.data || {}
    matches.value = d.matches || []
    scanned.value = d.scanned || 0
  } catch (e: any) { alert(e.message) }
  finally { loading.value = false }
}

function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + v.toFixed(2) + "%" }
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">智能选股</h1>
      <p class="page-desc">多因子策略扫描，智能筛选优质标的</p>
    </div>

    <div class="controls card animate-in delay-1">
      <div class="control-group">
        <label>策略</label>
        <select v-model="selected" class="select">
          <option v-for="s in strategies" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>
      <div class="control-group">
        <label>股票池</label>
        <select v-model="universe" class="select">
          <option value="hs300">沪深300</option>
          <option value="zz500">中证500</option>
          <option value="zz1000">中证1000</option>
          <option value="all">全市场</option>
        </select>
      </div>
      <button class="btn btn-primary" v-liquid="{maxTilt: 6, scale: 1.04}" @click="run" :disabled="loading">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        {{ loading ? "扫描中..." : "开始扫描" }}
      </button>
    </div>

    <p v-if="scanned" class="scan-info animate-in delay-2">
      扫描 <strong>{{ scanned }}</strong> 只，命中 <strong class="accent-text">{{ matches.length }}</strong> 只
    </p>

    <div class="table-wrap animate-in delay-3" v-if="matches.length">
      <table>
        <thead>
          <tr><th>股票</th><th class="r">现价</th><th class="r">涨跌幅</th><th class="r">PE</th><th class="r">PB</th><th>命中理由</th></tr>
        </thead>
        <tbody>
          <tr v-for="m in matches" :key="m.code" class="clickable-row" @click="goStock(m.code)">
            <td><div class="cell-stock"><span class="cell-name">{{ m.name }}</span><span class="cell-code">{{ m.code }}</span></div></td>
            <td class="r mono" :class="valClass(m.change_pct)">{{ m.price?.toFixed(2) }}</td>
            <td class="r"><span class="pill" :class="m.change_pct >= 0 ? 'pill-up' : 'pill-down'">{{ fmtPct(m.change_pct || 0) }}</span></td>
            <td class="r mono">{{ m.pe?.toFixed(1) }}</td>
            <td class="r mono">{{ m.pb?.toFixed(2) }}</td>
            <td class="reason">{{ m.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading && scanned" class="card empty-state animate-in delay-3" v-liquid>没有符合条件的标的，换个策略试试</div>
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
.select {
  padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; outline: none; min-width: 150px;
  transition: all 0.2s;
}
.select:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

.scan-info { margin-bottom: 16px; font-size: 12.5px; color: var(--text-secondary); }
.scan-info strong { color: var(--text-primary); font-weight: 600; }
.accent-text { color: var(--accent) !important; }

.table-wrap {
  background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  overflow: hidden; transition: background var(--transition-theme), border-color var(--transition-theme);
}
table { width: 100%; border-collapse: collapse; }
thead th { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); text-align: left; padding: 11px 18px; border-bottom: 1px solid var(--border-subtle); }
thead th.r { text-align: right; }
tbody td { padding: 12px 18px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle); transition: background 0.12s; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--bg-hover); }
td.r { text-align: right; }
.mono { font-family: var(--font-mono); font-weight: 500; font-size: 12px; font-variant-numeric: tabular-nums; }
.cell-stock { display: flex; flex-direction: column; gap: 2px; }
.cell-name { font-weight: 600; font-size: 13px; color: var(--text-primary); }
.cell-code { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); }
.pill { display: inline-block; padding: 3px 9px; border-radius: 999px; font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
.pill-up { background: var(--up-dim); color: var(--up); }
.pill-down { background: var(--down-dim); color: var(--down); }
.reason { color: var(--text-secondary); font-size: 11.5px; }
.empty-state { display: flex; align-items: center; justify-content: center; min-height: 200px; color: var(--text-tertiary); font-size: 13px; }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); transition: all var(--transition-theme); }
.btn { font-family: var(--font-sans); font-size: 12.5px; font-weight: 600; padding: 10px 20px; border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all 0.18s ease; display: inline-flex; align-items: center; gap: 7px; }
.btn-primary { background: linear-gradient(135deg, var(--accent), #a8884a); color: #0a0c10; box-shadow: 0 4px 14px var(--accent-glow); }
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--accent-glow); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.clickable-row { cursor: pointer; transition: background 0.15s; }
.clickable-row:hover { background: var(--bg-hover); }
</style>
