<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAuditLogs } from '@/api'

const logs = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)
const actionFilter = ref('')

const actionTypes = ['', 'buy', 'sell', 'ai_auto_execute', 'ai_auto_sell', 'config_save', 'watchlist_add', 'watchlist_remove']

async function load() {
  loading.value = true
  try {
    const params: any = { limit: 50, offset: (page.value - 1) * 50 }
    if (actionFilter.value) params.action = actionFilter.value
    const res: any = await getAuditLogs(params)
    logs.value = res.items || res.logs || res
    total.value = res.total || logs.value.length
  } catch (e: any) {
    // API not available
  } finally {
    loading.value = false
  }
}

onMounted(load)

function fmtTime(ts: string): string {
  return new Date(ts).toLocaleString('zh-CN')
}

const actionLabels: Record<string, string> = {
  buy: '买入', sell: '卖出',
  ai_auto_execute: 'AI自动建仓', ai_auto_sell: 'AI自动清仓',
  config_save: '配置保存',
  watchlist_add: '添加自选', watchlist_remove: '移除自选',
}
</script>

<template>
  <div class="audit-page">
    <h2>操作审计日志</h2>
    <div class="toolbar">
      <select v-model="actionFilter" @change="load" class="filter-select">
        <option value="">全部操作</option>
        <option v-for="a in actionTypes.slice(1)" :key="a" :value="a">{{ actionLabels[a] || a }}</option>
      </select>
      <button @click="load" class="btn-refresh">刷新</button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="logs.length === 0" class="empty">暂无审计记录</div>
    <table v-else class="audit-table">
      <thead>
        <tr>
          <th>时间</th>
          <th>操作</th>
          <th>目标</th>
          <th>用户</th>
          <th>IP</th>
          <th>详情</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="log in logs" :key="log.id">
          <td class="col-time">{{ fmtTime(log.timestamp) }}</td>
          <td><span class="action-tag">{{ actionLabels[log.action] || log.action }}</span></td>
          <td>{{ log.target || '-' }}</td>
          <td>{{ log.user_id || '-' }}</td>
          <td class="col-ip">{{ log.ip_address || '-' }}</td>
          <td class="col-detail">{{ log.detail || '-' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.audit-page { }
h2 { font-size: 22px; font-weight: 700; color: var(--text-primary); margin-bottom: 16px; }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.filter-select {
  padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 13px;
}
.btn-refresh {
  padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-secondary); cursor: pointer; font-size: 13px;
}
.btn-refresh:hover { background: var(--bg-elevated); }
.loading, .empty { text-align: center; padding: 40px; color: var(--text-tertiary); }
.audit-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.audit-table th {
  text-align: left; padding: 10px 12px; border-bottom: 2px solid var(--border-subtle);
  color: var(--text-tertiary); font-weight: 600; font-size: 12px;
}
.audit-table td {
  padding: 8px 12px; border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.col-time { font-family: var(--font-mono); font-size: 12px; white-space: nowrap; }
.col-ip { font-family: var(--font-mono); font-size: 12px; }
.col-detail { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-tag {
  padding: 2px 8px; border-radius: 4px; background: var(--accent-dim);
  color: var(--accent-soft); font-size: 12px; font-weight: 500;
}
</style>
