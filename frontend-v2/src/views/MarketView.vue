<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
import { getTopMovers, getIndex } from "@/api"

const router = useRouter()
const indices = ref<any[]>([])
const gainers = ref<any[]>([])
const losers = ref<any[]>([])
const loading = ref(true)

function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + (v || 0).toFixed(2) + "%" }
function goStock(code: string) { router.push(`/stock/${code}`) }

onMounted(async () => {
  try {
    const [idxRes, upRes, downRes] = await Promise.all([
      getIndex().catch(() => ({ data: [] })),
      getTopMovers("up", 10).catch(() => ({ data: [] })),
      getTopMovers("down", 10).catch(() => ({ data: [] })),
    ])
    indices.value = (idxRes as any).data || []
    gainers.value = (upRes as any).data || []
    losers.value = (downRes as any).data || []
  } finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">市场行情</h1>
      <p class="page-desc">实时指数、涨跌幅榜</p>
    </div>

    <!-- Index Cards -->
    <div class="index-grid animate-in delay-1">
      <div v-for="idx in indices" :key="idx.code" class="index-card">
        <div class="index-name">{{ idx.name }}</div>
        <div class="index-value" :class="valClass(idx.change_pct)">{{ idx.price?.toLocaleString("zh-CN", { minimumFractionDigits: 2 }) }}</div>
        <div class="index-change" :class="valClass(idx.change_pct)">{{ fmtPct(idx.change_pct) }}</div>
      </div>
    </div>

    <!-- Top Movers -->
    <div class="movers-grid animate-in delay-2">
      <div class="card">
        <div class="card-title">涨幅榜</div>
        <div class="mover-list">
          <div v-for="(s, i) in gainers" :key="s.code" class="mover-item" @click="goStock(s.code)">
            <span class="mover-rank">{{ i + 1 }}</span>
            <div class="mover-info"><span class="mover-name">{{ s.name }}</span><span class="mover-code">{{ s.code }}</span></div>
            <span class="mover-pct val-up">{{ fmtPct(s.change_pct) }}</span>
          </div>
          <div v-if="!gainers.length" class="empty">加载中...</div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">跌幅榜</div>
        <div class="mover-list">
          <div v-for="(s, i) in losers" :key="s.code" class="mover-item" @click="goStock(s.code)">
            <span class="mover-rank">{{ i + 1 }}</span>
            <div class="mover-info"><span class="mover-name">{{ s.name }}</span><span class="mover-code">{{ s.code }}</span></div>
            <span class="mover-pct val-down">{{ fmtPct(s.change_pct) }}</span>
          </div>
          <div v-if="!losers.length" class="empty">加载中...</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.index-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.index-card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px 20px; transition: all 0.22s; }
.index-card:hover { border-color: var(--border-default); box-shadow: var(--shadow-card); transform: translateY(-2px); }
.index-name { font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; }
.index-value { font-family: var(--font-mono); font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; margin-bottom: 4px; }
.index-change { font-family: var(--font-mono); font-size: 12px; font-weight: 600; }

.movers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; }
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 14px; color: var(--text-primary); }
.mover-list { display: flex; flex-direction: column; gap: 2px; }
.mover-item { display: flex; align-items: center; gap: 12px; padding: 8px 10px; border-radius: var(--radius-sm); cursor: pointer; transition: background 0.12s; }
.mover-item:hover { background: var(--bg-hover); }
.mover-rank { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); width: 18px; text-align: center; }
.mover-info { flex: 1; display: flex; flex-direction: column; gap: 1px; }
.mover-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.mover-code { font-size: 10px; font-family: var(--font-mono); color: var(--text-tertiary); }
.mover-pct { font-family: var(--font-mono); font-size: 13px; font-weight: 600; }
.val-up { color: var(--up); }
.val-down { color: var(--down); }
.empty { color: var(--text-tertiary); font-size: 12px; padding: 16px 0; text-align: center; }
@media (max-width: 900px) { .movers-grid { grid-template-columns: 1fr; } .index-grid { grid-template-columns: 1fr; } }
</style>
