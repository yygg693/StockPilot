<script setup lang="ts">
import { ref, onMounted } from "vue"
import { useRouter } from "vue-router"
import { screenFunds } from "@/api"

const router = useRouter()
const funds = ref<any[]>([])
const fundType = ref("all")
const loading = ref(false)
const total = ref(0)

function showDetail(f: any) {
  router.push({
    path: "/fund/" + f.code,
    query: {
      name: f.name,
      nav: f.nav,
      return_1m: f.return_1m,
      return_3m: f.return_3m,
      return_6m: f.return_6m,
      return_1y: f.return_1y,
      return_ytd: f.return_ytd,
      type: f.type,
    }
  })
}

const typeOptions = [
  { id: "all", name: "全部" },
  { id: "stock", name: "股票型" },
  { id: "mixed", name: "混合型" },
  { id: "bond", name: "债券型" },
  { id: "index", name: "指数型" },
]

async function load() {
  loading.value = true
  try {
    const res: any = await screenFunds(fundType.value, "return_1y", 20)
    const d = res.data || {}
    funds.value = d.funds || []
    total.value = d.total || 0
  } catch (e: any) { alert(e.message) }
  finally { loading.value = false }
}

function fmtRet(v: number) { return v ? ((v > 0 ? "+" : "") + v.toFixed(2) + "%") : "--" }
function retClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">选基金</h1>
      <p class="page-desc">按类型和业绩筛选基金</p>
    </div>

    <div class="controls card animate-in delay-1">
      <div class="type-tabs">
        <button v-for="t in typeOptions" :key="t.id" class="tab" :class="{ active: fundType === t.id }" @click="fundType = t.id; load()">{{ t.name }}</button>
      </div>
    </div>

    <div class="table-wrap animate-in delay-2">
      <table v-if="funds.length">
        <thead><tr><th>基金</th><th class="r">净值</th><th class="r">近1月</th><th class="r">近3月</th><th class="r">近6月</th><th class="r">近1年</th></tr></thead>
        <tbody>
          <tr v-for="f in funds" :key="f.code" class="clickable-row" @click="showDetail(f)">
            <td><div class="cell-stock"><span class="cell-name">{{ f.name }}</span><span class="cell-code">{{ f.code }}</span></div></td>
            <td class="r mono">{{ f.nav ? f.nav.toFixed(4) : '--' }}</td>
            <td class="r mono" :class="retClass(f.return_1m)">{{ fmtRet(f.return_1m) }}</td>
            <td class="r mono" :class="retClass(f.return_3m)">{{ fmtRet(f.return_3m) }}</td>
            <td class="r mono" :class="retClass(f.return_6m)">{{ fmtRet(f.return_6m) }}</td>
            <td class="r mono" :class="retClass(f.return_1y)">{{ fmtRet(f.return_1y) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-table">{{ loading ? '加载中...' : '暂无数据' }}</div>
    </div>

  </div>
</template>

<style scoped>
.page { max-width: 1000px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }
.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 16px 20px; margin-bottom: 20px; }
.type-tabs { display: flex; gap: 8px; }
.tab { padding: 7px 16px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-secondary); font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.tab:hover { border-color: var(--accent); color: var(--accent); }
.tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); font-weight: 600; }

.table-wrap { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
thead th { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); text-align: left; padding: 11px 18px; border-bottom: 1px solid var(--border-subtle); }
thead th.r { text-align: right; }
tbody td { padding: 12px 18px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle); }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--bg-hover); }
td.r { text-align: right; }
.mono { font-family: var(--font-mono); font-size: 12px; font-variant-numeric: tabular-nums; }
.cell-stock { display: flex; flex-direction: column; gap: 2px; }
.cell-name { font-weight: 600; font-size: 13px; color: var(--text-primary); }
.cell-code { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); }
.val-up { color: var(--up); }
.val-down { color: var(--down); }
.empty-table { padding: 40px; text-align: center; color: var(--text-tertiary); font-size: 13px; }

.clickable-row { cursor: pointer; transition: background 0.15s; }
.clickable-row:hover td { background: var(--bg-hover); }
</style>
