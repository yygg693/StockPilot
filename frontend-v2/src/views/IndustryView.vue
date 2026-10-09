<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
import { getSectors, getSectorStocks } from "@/api"

const router = useRouter()
const sectors = ref<any[]>([])
const selectedSector = ref("")
const sectorStocks = ref<any[]>([])
const loading = ref(true)
const loadingStocks = ref(false)

function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + (v || 0).toFixed(2) + "%" }
function goStock(code: string) { router.push(`/stock/${code}`) }

async function selectSector(code: string) {
  selectedSector.value = code
  loadingStocks.value = true
  sectorStocks.value = []
  try {
    const res: any = await getSectorStocks(code, 20)
    sectorStocks.value = res.data || []
  } catch {} finally { loadingStocks.value = false }
}

onMounted(async () => {
  try {
    const res: any = await getSectors()
    sectors.value = res.data || []
  } finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">行业扫描</h1>
      <p class="page-desc">板块轮动、行业涨跌幅一览</p>
    </div>

    <!-- Sector Grid -->
    <div class="sector-grid animate-in delay-1">
      <div v-for="s in sectors" :key="s.code" class="sector-card" :class="{ active: selectedSector === s.code }" @click="selectSector(s.code)">
        <div class="sector-name">{{ s.name }}</div>
        <div class="sector-pct" :class="valClass(s.change_pct)">{{ fmtPct(s.change_pct) }}</div>
      </div>
    </div>

    <!-- Sector Stocks -->
    <div v-if="selectedSector" class="table-wrap animate-in delay-2">
      <table v-if="sectorStocks.length">
        <thead><tr><th>股票</th><th class="r">现价</th><th class="r">涨跌幅</th><th class="r">成交额</th><th class="r">振幅</th></tr></thead>
        <tbody>
          <tr v-for="s in sectorStocks" :key="s.code" @click="goStock(s.code)">
            <td><div class="cell-stock"><span class="cell-name">{{ s.name }}</span><span class="cell-code">{{ s.code }}</span></div></td>
            <td class="r mono" :class="valClass(s.change_pct)">{{ s.price?.toFixed(2) }}</td>
            <td class="r"><span class="pill" :class="(s.change_pct||0) >= 0 ? 'pill-up' : 'pill-down'">{{ fmtPct(s.change_pct) }}</span></td>
            <td class="r mono">{{ s.amount ? (s.amount / 1e8).toFixed(2) + '亿' : '--' }}</td>
            <td class="r mono">{{ s.amplitude ? s.amplitude.toFixed(2) + '%' : '--' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-table">{{ loadingStocks ? '加载中...' : '点击板块查看成分股' }}</div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.sector-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-bottom: 24px; }
.sector-card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px 16px; cursor: pointer; transition: all 0.18s; text-align: center; }
.sector-card:hover { border-color: var(--border-default); transform: translateY(-1px); }
.sector-card.active { border-color: var(--accent); background: var(--accent-dim); }
.sector-name { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px; }
.sector-pct { font-family: var(--font-mono); font-size: 14px; font-weight: 700; }

.table-wrap { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
thead th { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); text-align: left; padding: 11px 18px; border-bottom: 1px solid var(--border-subtle); }
thead th.r { text-align: right; }
tbody td { padding: 12px 18px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle); }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--bg-hover); }
tbody tr { cursor: pointer; }
td.r { text-align: right; }
.mono { font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums; }
.cell-stock { display: flex; flex-direction: column; gap: 2px; }
.cell-name { font-weight: 600; font-size: 13px; color: var(--text-primary); }
.cell-code { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); }
.pill { display: inline-block; padding: 3px 9px; border-radius: 999px; font-family: var(--font-mono); font-size: 11px; font-weight: 600; }
.pill-up { background: var(--up-dim); color: var(--up); }
.pill-down { background: var(--down-dim); color: var(--down); }
.val-up { color: var(--up); }
.val-down { color: var(--down); }
.empty-table { padding: 40px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
</style>
