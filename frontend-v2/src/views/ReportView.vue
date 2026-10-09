<script setup lang="ts">
import { ref, onMounted } from "vue"
import { getDailyReport } from "@/api"

const report = ref<any>(null)
const loading = ref(true)

function valClass(v: number) { return v > 0 ? "val-up" : v < 0 ? "val-down" : "" }
function fmtPct(v: number) { return (v > 0 ? "+" : "") + (v || 0).toFixed(2) + "%" }

onMounted(async () => {
  try {
    const res: any = await getDailyReport()
    report.value = res.data || null
  } catch (e: any) { alert(e.message) }
  finally { loading.value = false }
})
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">每日日报</h1>
      <p class="page-desc">{{ report?.date }} 市场综述</p>
    </div>

    <div v-if="loading" class="card loading-card animate-in delay-1" v-liquid>生成日报中...</div>

    <template v-else-if="report">
      <!-- Summary -->
      <div class="card summary-card animate-in delay-1" v-liquid>
        <div class="card-title">市场概览</div>
        <p class="summary-text">{{ report.summary || '暂无数据' }}</p>
      </div>

      <!-- AI Summary -->
      <div v-if="report.ai_summary" class="card ai-card animate-in delay-2" v-liquid>
        <div class="ai-badge">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          AI 点评
        </div>
        <p class="ai-text">{{ report.ai_summary }}</p>
      </div>

      <!-- Index Performance -->
      <div class="card animate-in delay-3" v-liquid v-if="report.indices?.length">
        <div class="card-title">指数表现</div>
        <div class="index-row">
          <div v-for="idx in report.indices" :key="idx.code" class="index-item">
            <span class="idx-name">{{ idx.name }}</span>
            <span class="idx-val mono" :class="valClass(idx.change_pct)">{{ idx.price?.toFixed(2) }}</span>
            <span class="idx-pct mono" :class="valClass(idx.change_pct)">{{ fmtPct(idx.change_pct) }}</span>
          </div>
        </div>
      </div>

      <!-- Top Gainers & Losers -->
      <div class="movers-grid animate-in delay-4">
        <div class="card" v-liquid v-if="report.top_gainers?.length">
          <div class="card-title">今日领涨</div>
          <div class="gainer-list">
            <div v-for="s in report.top_gainers" :key="s.code" class="gainer-item">
              <span class="g-name">{{ s.name }}</span>
              <span class="g-code mono">{{ s.code }}</span>
              <span class="g-pct mono val-up">+{{ (s.change_pct || 0).toFixed(2) }}%</span>
            </div>
          </div>
        </div>
        <div class="card" v-liquid v-if="report.top_losers?.length">
          <div class="card-title">今日领跌</div>
          <div class="gainer-list">
            <div v-for="s in report.top_losers" :key="s.code" class="gainer-item">
              <span class="g-name">{{ s.name }}</span>
              <span class="g-code mono">{{ s.code }}</span>
              <span class="g-pct mono val-down">{{ (s.change_pct || 0).toFixed(2) }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Financial News -->
      <div class="card animate-in delay-5" v-if="report.news?.length">
        <div class="card-title">财经要闻</div>
        <div class="news-list">
          <a v-for="(n, i) in report.news" :key="i" :href="n.url" target="_blank" rel="noopener" class="news-item" :class="{ 'news-hot': (report.key_news_indices || []).includes(i) }">
            <span class="news-dot"></span>
            <div class="news-body">
              <span class="news-title"><em v-if="(report.key_news_indices || []).includes(i)" class="hot-tag">重要</em>{{ n.title }}</span>
              <span class="news-meta">{{ n.source }} · {{ n.time }}</span>
            </div>
          </a>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 900px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; margin-bottom: 16px; }
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 12px; color: var(--text-primary); }
.loading-card { text-align: center; color: var(--text-tertiary); padding: 40px; }

.summary-text { font-size: 14px; line-height: 1.8; color: var(--text-secondary); }

.ai-card { position: relative; overflow: hidden; border-color: var(--accent-dim); }
.ai-card::before { content: ''; position: absolute; top: -40px; right: -40px; width: 120px; height: 120px; background: radial-gradient(circle, var(--accent-glow), transparent 70%); border-radius: 50%; pointer-events: none; }
.ai-badge { display: inline-flex; align-items: center; gap: 5px; background: var(--accent-dim); color: var(--accent); font-size: 10px; font-weight: 600; padding: 4px 10px; border-radius: 999px; margin-bottom: 12px; }
.ai-text { font-size: 13px; line-height: 1.9; color: var(--text-secondary); white-space: pre-wrap; }

.index-row { display: flex; flex-direction: column; gap: 10px; }
.index-item { display: flex; align-items: center; gap: 16px; }
.idx-name { font-size: 13px; font-weight: 500; color: var(--text-primary); width: 80px; }
.idx-val { font-size: 14px; font-weight: 600; flex: 1; }
.idx-pct { font-size: 13px; font-weight: 600; }

.gainer-list { display: flex; flex-direction: column; gap: 6px; }
.gainer-item { display: flex; align-items: center; gap: 12px; padding: 6px 0; }
.g-name { font-size: 13px; font-weight: 500; color: var(--text-primary); flex: 1; }
.g-code { font-size: 11px; color: var(--text-tertiary); }
.g-pct { font-size: 13px; font-weight: 600; }

.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.val-up { color: var(--up); }
.val-down { color: var(--down); }

.movers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.movers-grid .card { margin-bottom: 0; }
@media (max-width: 700px) { .movers-grid { grid-template-columns: 1fr; } }

.news-list { display: flex; flex-direction: column; }
.news-item { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--border-subtle); text-decoration: none; transition: background 0.15s; }
.news-item:last-child { border-bottom: none; }
.news-item:hover { background: var(--bg-hover); margin: 0 -12px; padding: 12px; border-radius: var(--radius-sm); }
.news-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); margin-top: 6px; flex-shrink: 0; }
.news-body { display: flex; flex-direction: column; gap: 4px; }
.news-title { font-size: 13px; font-weight: 500; color: var(--text-primary); line-height: 1.5; }
.news-item:hover .news-title { color: var(--accent-soft); }
.news-meta { font-size: 11px; color: var(--text-tertiary); }
.news-hot .news-dot { background: var(--down); box-shadow: 0 0 6px var(--down); }
.news-hot .news-title { font-weight: 600; }
.hot-tag { font-style: normal; font-size: 10px; font-weight: 600; color: var(--down); background: var(--down-dim); padding: 1px 6px; border-radius: 3px; margin-right: 6px; vertical-align: middle; }
</style>
