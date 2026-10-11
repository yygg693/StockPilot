<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { getWatchlist, addWatch, removeWatch, searchStock } from "@/api"
import { useStaleRefresh } from "@/composables/useStaleRefresh"

const router = useRouter()
const watchlist = ref<any[]>([])
const searchQ = ref("")
const searchResults = ref<any[]>([])
const showSearch = ref(false)
const loading = ref(true)

function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + (v || 0).toFixed(2) + "%" }
function goStock(code: string) {
  const raw = code.replace(/^(sh|sz)/, '')
  const isFund = /^[023]/.test(raw) || (/^1/.test(raw) && !/^(15|16)/.test(raw))
  router.push(isFund ? `/fund/${code}` : `/stock/${code}`)
}

async function load() {
  try {
    const res: any = await getWatchlist()
    watchlist.value = res.data || []
  } finally { loading.value = false }
}

async function doSearch() {
  if (!searchQ.value) { searchResults.value = []; return }
  try {
    const res: any = await searchStock(searchQ.value)
    searchResults.value = (res.data || []).slice(0, 6)
    showSearch.value = true
  } catch { searchResults.value = [] }
}

async function doAdd(item: any) {
  try {
    await addWatch(item.code, item.name)
    searchQ.value = ""
    searchResults.value = []
    showSearch.value = false
    await load()
  } catch (e: any) { alert(e.message) }
}

async function doRemove(code: string) {
  try {
    await removeWatch(code)
    await load()
  } catch (e: any) { alert(e.message) }
}

function delayHideSearch() {
  setTimeout(() => { showSearch.value = false }, 200)
}

// Load on first visit; refresh on return only when older than 60s. Manual
// load() calls (after add/remove) still work and reset the staleness timer.
useStaleRefresh(load)
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">自选股</h1>
      <p class="page-desc">管理你关注的股票</p>
    </div>

    <!-- Add Stock -->
    <div class="card add-card animate-in delay-1" v-liquid>
      <div class="add-row">
        <div class="search-wrap">
          <input v-model="searchQ" class="input" placeholder="输入股票代码或名称搜索..." @input="doSearch" @blur="delayHideSearch" />
          <div v-if="showSearch && searchResults.length" class="search-dropdown">
            <div v-for="item in searchResults" :key="item.code" class="search-item" @mousedown="doAdd(item)">
              <span class="si-name">{{ item.name }}</span>
              <span class="si-code">{{ item.code }}</span>
              <span class="si-add">+ 添加</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Watchlist Table -->
    <div class="table-wrap animate-in delay-2">
      <table v-if="watchlist.length">
        <thead><tr><th>股票</th><th class="r">现价</th><th class="r">涨跌幅</th><th class="r">成交额</th><th class="r">操作</th></tr></thead>
        <tbody>
          <tr v-for="s in watchlist" :key="s.code" @click="goStock(s.code)">
            <td><div class="cell-stock"><span class="cell-name">{{ s.name || s.code }}</span><span class="cell-code">{{ s.code }}</span></div></td>
            <td class="r mono" :class="valClass(s.change_pct)">{{ s.price ? s.price.toFixed(2) : '--' }}</td>
            <td class="r"><span class="pill" :class="(s.change_pct||0) >= 0 ? 'pill-up' : 'pill-down'">{{ fmtPct(s.change_pct || 0) }}</span></td>
            <td class="r mono">{{ s.amount ? (s.amount / 1e4).toFixed(0) + '万' : '--' }}</td>
            <td class="r"><button class="btn-remove" @click.stop="doRemove(s.code)">移除</button></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-table">暂无自选股，搜索添加你关注的股票</div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1000px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; }
.add-card { margin-bottom: 20px; }
.add-row { display: flex; gap: 12px; }
.search-wrap { position: relative; flex: 1; }
.input { width: 100%; padding: 10px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: var(--bg-overlay); color: var(--text-primary); font-size: 13px; outline: none; transition: all 0.2s; }
.input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.search-dropdown { position: absolute; top: calc(100% + 6px); left: 0; right: 0; background: var(--bg-elevated); border: 1px solid var(--border-default); border-radius: var(--radius-md); box-shadow: var(--shadow-elevated); z-index: 100; overflow: hidden; }
.search-item { display: flex; align-items: center; gap: 10px; padding: 10px 14px; cursor: pointer; transition: background 0.12s; }
.search-item:hover { background: var(--bg-hover); }
.si-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.si-code { font-size: 11px; font-family: var(--font-mono); color: var(--text-tertiary); }
.si-add { margin-left: auto; font-size: 11px; color: var(--accent); font-weight: 600; }

.table-wrap { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
table { width: 100%; border-collapse: collapse; }
thead th { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); text-align: left; padding: 11px 18px; border-bottom: 1px solid var(--border-subtle); }
thead th.r { text-align: right; }
tbody td { padding: 12px 18px; font-size: 12.5px; border-bottom: 1px solid var(--border-subtle); transition: background 0.12s; }
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
.btn-remove { padding: 4px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: transparent; color: var(--text-tertiary); font-size: 11px; cursor: pointer; transition: all 0.15s; }
.btn-remove:hover { border-color: var(--up); color: var(--up); background: var(--up-dim); }
.empty-table { padding: 40px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
</style>
