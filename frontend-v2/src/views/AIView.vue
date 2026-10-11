<script setup lang="ts">
import { ref } from "vue"
import { analyzeStock } from "@/api"

const code = ref("")
const name = ref("")
const loading = ref(false)
const result = ref<any>(null)

async function analyze() {
  if (!code.value) return
  loading.value = true
  result.value = null
  try {
    const res: any = await analyzeStock(code.value, name.value)
    result.value = res.data
  } catch (e: any) { alert(e.message) }
  finally { loading.value = false }
}

const roleLabels: Record<string, string> = {
  analyst: "基本面分析师",
  trader: "技术面交易员",
  risk: "风控专家",
}
const roleIcons: Record<string, string> = {
  analyst: "M3 3v18h18M7 16l4-8 4 4 5-9",
  trader: "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z",
  risk: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
}
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">AI 多角色分析</h1>
      <p class="page-desc">多角色并行分析，综合基本面、技术面与风控视角</p>
    </div>

    <div class="compliance-banner">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 9v4M12 17h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>
      <span>本工具为个人学习用途，所有 AI 分析仅为公开数据的整理与信息呈现，<strong>不构成投资建议，也不提供确定性买卖指令</strong>。投资决策由您独立做出，盈亏自负。</span>
    </div>

    <div class="card input-card animate-in delay-1" v-liquid>
      <div class="form-row">
        <div class="control-group">
          <label>股票代码</label>
          <input v-model="code" class="input" placeholder="sh600519" />
        </div>
        <div class="control-group">
          <label>名称 (可选)</label>
          <input v-model="name" class="input" placeholder="贵州茅台" />
        </div>
        <button class="btn btn-primary" v-liquid="{maxTilt: 6, scale: 1.04}" @click="analyze" :disabled="loading || !code">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/></svg>
          {{ loading ? "分析中..." : "开始分析" }}
        </button>
      </div>
    </div>

    <div v-if="result" class="results">
      <div class="role-grid animate-in delay-2">
        <div v-for="(text, role) in result.analyses" :key="role" class="card role-card" v-liquid>
          <div class="role-header">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round"><path :d="roleIcons[role as string] || roleIcons.analyst"/></svg>
            <span class="role-title">{{ roleLabels[role as string] || role }}</span>
          </div>
          <p class="role-text">{{ text }}</p>
        </div>
      </div>
      <div class="card summary-card animate-in delay-3" v-liquid>
        <div class="ai-badge">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
          AI 综合梳理
        </div>
        <p class="role-text summary-text">{{ result.summary }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1200px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; transition: all var(--transition-theme); }
.input-card { margin-bottom: 20px; }
.form-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
.control-group { display: flex; flex-direction: column; gap: 6px; }
.control-group label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.7px; color: var(--text-tertiary); }
.input {
  padding: 9px 14px; border-radius: var(--radius-sm); border: 1px solid var(--border-default);
  background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; outline: none; min-width: 160px;
  transition: all 0.2s; font-family: var(--font-sans);
}
.input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

.role-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 16px; }
.role-card { position: relative; }
.role-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.role-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.role-text { font-size: 12.5px; line-height: 1.8; color: var(--text-secondary); white-space: pre-wrap; }

.summary-card { position: relative; overflow: hidden; border-color: var(--accent-dim); }
.summary-card::before {
  content: ''; position: absolute; top: -40px; right: -40px; width: 120px; height: 120px;
  background: radial-gradient(circle, var(--accent-glow), transparent 70%); border-radius: 50%; pointer-events: none;
}
.ai-badge {
  display: inline-flex; align-items: center; gap: 5px; background: var(--accent-dim); color: var(--accent);
  font-size: 10px; font-weight: 600; padding: 4px 10px; border-radius: 999px; margin-bottom: 12px; letter-spacing: 0.3px;
}
.summary-text { color: var(--text-primary); }

.btn { font-family: var(--font-sans); font-size: 12.5px; font-weight: 600; padding: 10px 20px; border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all 0.18s ease; display: inline-flex; align-items: center; gap: 7px; }
.btn-primary { background: linear-gradient(135deg, var(--accent), #a8884a); color: #0a0c10; box-shadow: 0 4px 14px var(--accent-glow); }
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--accent-glow); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

.compliance-banner {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(230, 162, 60, 0.12); border: 1px solid rgba(230, 162, 60, 0.42);
  border-radius: var(--radius-md); padding: 12px 16px; margin-bottom: 20px;
  font-size: 12px; line-height: 1.7; color: var(--text-secondary);
}
.compliance-banner svg { flex-shrink: 0; margin-top: 1px; color: #e6a23c; }
.compliance-banner strong { color: var(--text-primary); }
</style>
