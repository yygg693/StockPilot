<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  getSuitabilityQuestions,
  submitSuitability,
  getSuitabilityProfile,
  getProductGrades,
  getRiskWarnings,
} from '@/api'

// ---- State ----
const questions = ref<any[]>([])
const riskLevels = ref<Record<string, any>>({})
const selectedOptions = ref<number[]>([]) // index of selected option per question
const profile = ref<any>(null)
const productGrades = ref<Record<string, any>>({})
const warnings = ref<any[]>([])
const loading = ref(false)
const submitted = ref(false)
const loadingProfile = ref(true)

// ---- Risk level meta ----
const levelColors: Record<string, string> = {
  C1: '#22c55e', C2: '#84cc16', C3: '#f5c842', C4: '#f97316', C5: '#ef4444',
}
const levelOrder = ['C1', 'C2', 'C3', 'C4', 'C5']
const gradeOrder = ['R1', 'R2', 'R3', 'R4', 'R5']

// ---- Computed ----
const answeredCount = computed(() => selectedOptions.value.filter((a) => a >= 0).length)
const progressPct = computed(() => {
  if (!questions.value.length) return 0
  return Math.round((answeredCount.value / questions.value.length) * 100)
})
const allAnswered = computed(() => {
  return questions.value.length > 0 && answeredCount.value === questions.value.length
})

// ---- Helpers ----
function fmtLevelName(level: string): string {
  return riskLevels.value[level]?.name || level
}
function fmtGradeName(grade: string): string {
  return productGrades.value[grade]?.name || grade
}
function fmtGradeDesc(grade: string): string {
  return productGrades.value[grade]?.desc || ''
}

// Check if a product grade is allowed for the investor's risk level
function isGradeAllowed(grade: string): boolean {
  if (!profile.value) return true
  const maxGrade = profile.value.max_product_grade || 'R5'
  const maxNum = parseInt(maxGrade[1])
  const gradeNum = parseInt(grade[1])
  return gradeNum <= maxNum
}

// ---- Data loading ----
async function loadQuestionnaire() {
  try {
    const res: any = await getSuitabilityQuestions()
    const d = res.data || res
    questions.value = d.questions || []
    riskLevels.value = d.risk_levels || {}
    selectedOptions.value = new Array(questions.value.length).fill(-1)
  } catch (e: any) {
    console.error('Failed to load questionnaire:', e.message)
  }
}

async function loadProfile() {
  loadingProfile.value = true
  try {
    const res: any = await getSuitabilityProfile()
    const d = res.data || res
    if (d.assessed) {
      profile.value = d
    }
  } catch {
    // not assessed yet
  } finally {
    loadingProfile.value = false
  }
}

async function loadGrades() {
  try {
    const res: any = await getProductGrades()
    productGrades.value = res.data || res || {}
  } catch {
    // ignore
  }
}

async function loadWarnings() {
  try {
    const res: any = await getRiskWarnings()
    warnings.value = (res.data || res || []).filter((w: any) => w.level !== 'info')
  } catch {
    // ignore
  }
}

// ---- Submit ----
async function submit() {
  if (!allAnswered.value) return
  loading.value = true
  try {
    // Convert selected option indices to scores
    const scores = questions.value.map((q, i) => {
      const optIdx = selectedOptions.value[i]
      return q.options[optIdx]?.score ?? 0
    })
    const res: any = await submitSuitability(scores)
    profile.value = res.data || res
    submitted.value = true
    await loadWarnings()
  } catch (e: any) {
    alert(e.message || '提交失败')
  } finally {
    loading.value = false
  }
}

function retake() {
  submitted.value = false
  selectedOptions.value = new Array(questions.value.length).fill(-1)
}

// ---- Warning severity ----
function warningClass(level: string): string {
  if (level === 'critical') return 'warn-critical'
  if (level === 'danger') return 'warn-danger'
  if (level === 'warning') return 'warn-warning'
  return 'warn-info'
}
function warningIcon(level: string): string {
  if (level === 'critical' || level === 'danger') return '!'
  if (level === 'warning') return '~'
  return 'i'
}

// ---- Init ----
onMounted(async () => {
  await Promise.all([loadQuestionnaire(), loadProfile(), loadGrades()])
  if (profile.value) {
    await loadWarnings()
  }
})
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <div>
        <h1 class="page-title">风险测评</h1>
        <p class="page-desc">根据监管要求完成风险承受能力评估，系统将匹配适合您的投资产品</p>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loadingProfile" class="card loading-card">
      <div class="loading-spinner"></div>
      <p>加载中...</p>
    </div>

    <!-- Result view (after submit or existing profile) -->
    <template v-else-if="profile && submitted">
      <div class="result-section animate-in delay-1">
        <!-- Risk level card -->
        <div class="card result-card">
          <div class="result-badge">
            <div class="result-level-tag" :style="{ background: levelColors[profile.risk_level] }">
              {{ profile.risk_level }}
            </div>
            <div class="result-level-name">{{ profile.level_name }}</div>
          </div>
          <div class="result-score">
            <span class="score-label">测评得分</span>
            <span class="score-value mono">{{ profile.score }}</span>
            <span class="score-max">/ 40</span>
          </div>
          <p class="result-desc">{{ profile.level_desc }}</p>
          <p class="result-time mono">评估时间：{{ profile.assessed_at }}</p>

          <!-- Risk level scale visualization -->
          <div class="level-scale">
            <div
              v-for="lv in levelOrder"
              :key="lv"
              class="level-step"
              :class="{
                active: lv === profile.risk_level,
                passed: levelOrder.indexOf(lv) <= levelOrder.indexOf(profile.risk_level),
              }"
            >
              <div class="step-dot" :style="{ background: levelColors[lv] }"></div>
              <span class="step-label">{{ lv }}</span>
              <span class="step-name">{{ fmtLevelName(lv) }}</span>
            </div>
          </div>
        </div>

        <!-- Product grade matching -->
        <div class="card animate-in delay-2">
          <div class="card-title">产品风险等级匹配</div>
          <p class="section-desc">您的风险等级 {{ profile.risk_level }} 可投资以下产品：</p>
          <div class="grade-grid">
            <div
              v-for="grade in gradeOrder"
              :key="grade"
              class="grade-item"
              :class="{ allowed: isGradeAllowed(grade), disallowed: !isGradeAllowed(grade) }"
            >
              <div class="grade-header">
                <span class="grade-tag">{{ grade }}</span>
                <span class="grade-name">{{ fmtGradeName(grade) }}</span>
              </div>
              <p class="grade-desc">{{ fmtGradeDesc(grade) }}</p>
              <div class="grade-status">
                <span v-if="isGradeAllowed(grade)" class="status-ok">可投资</span>
                <span v-else class="status-no">超出风险等级</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Risk warnings -->
        <div v-if="warnings.length" class="card animate-in delay-3">
          <div class="card-title">风险提示</div>
          <div class="warning-list">
            <div
              v-for="(w, i) in warnings"
              :key="i"
              class="warning-item"
              :class="warningClass(w.level)"
            >
              <span class="warn-icon">{{ warningIcon(w.level) }}</span>
              <div class="warn-content">
                <div class="warn-title">{{ w.title }}</div>
                <div class="warn-message">{{ w.message }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Retake button -->
        <div class="action-row">
          <button class="btn-retake" @click="retake">重新测评</button>
        </div>
      </div>
    </template>

    <!-- Questionnaire view -->
    <template v-else>
      <!-- Existing profile banner -->
      <div v-if="profile" class="card existing-banner animate-in delay-1">
        <div class="banner-left">
          <span class="banner-label">当前评级</span>
          <span class="banner-level" :style="{ color: levelColors[profile.risk_level] }">
            {{ profile.risk_level }} - {{ profile.level_name }}
          </span>
          <span class="banner-score">得分 {{ profile.score }}</span>
        </div>
        <span class="banner-hint">重新测评将覆盖当前结果</span>
      </div>

      <!-- Progress bar -->
      <div class="progress-bar-wrap animate-in delay-1">
        <div class="progress-info">
          <span>已完成 {{ answeredCount }} / {{ questions.length }} 题</span>
          <span class="progress-pct mono">{{ progressPct }}%</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
        </div>
      </div>

      <!-- Questions -->
      <div class="questionnaire animate-in delay-2">
        <div
          v-for="(q, i) in questions"
          :key="i"
          class="question-card"
          :class="{ answered: selectedOptions[i] >= 0 }"
        >
          <div class="q-header">
            <span class="q-number">{{ i + 1 }}</span>
            <span class="q-title">{{ q.question }}</span>
          </div>
          <div class="q-options">
            <label
              v-for="(opt, j) in q.options"
              :key="j"
              class="q-option"
              :class="{ selected: selectedOptions[i] === j }"
            >
              <input
                type="radio"
                :name="'q' + i"
                :checked="selectedOptions[i] === j"
                @change="selectedOptions[i] = Number(j)"
              />
              <span class="opt-radio"></span>
              <span class="opt-label">{{ opt.label }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Submit -->
      <div class="submit-row animate-in delay-3">
        <button
          class="btn-submit"
          :disabled="loading || !allAnswered"
          @click="submit"
        >
          {{ loading ? '提交中...' : '提交测评' }}
        </button>
        <p v-if="!allAnswered" class="submit-hint">请完成所有题目后提交</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page { max-width: 760px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

/* Loading */
.loading-card { text-align: center; padding: 48px 20px; }
.loading-spinner {
  width: 32px; height: 32px; border: 3px solid var(--border-subtle);
  border-top-color: var(--accent); border-radius: 50%; margin: 0 auto 12px;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Card */
.card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md); padding: 20px; margin-bottom: 20px;
  transition: all var(--transition-theme);
}
.card-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 12px; }
.section-desc { font-size: 12px; color: var(--text-tertiary); margin-bottom: 16px; }

/* Existing profile banner */
.existing-banner {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--accent-dim); border-color: var(--accent);
}
.banner-left { display: flex; align-items: center; gap: 12px; }
.banner-label { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }
.banner-level { font-size: 16px; font-weight: 700; }
.banner-score { font-size: 12px; color: var(--text-secondary); }
.banner-hint { font-size: 11px; color: var(--text-tertiary); }

/* Progress bar */
.progress-bar-wrap { margin-bottom: 20px; }
.progress-info {
  display: flex; justify-content: space-between; font-size: 11px;
  color: var(--text-tertiary); margin-bottom: 6px;
}
.progress-pct { font-weight: 600; color: var(--accent); }
.progress-track {
  height: 4px; background: var(--bg-overlay); border-radius: 2px; overflow: hidden;
}
.progress-fill {
  height: 100%; background: var(--accent); border-radius: 2px;
  transition: width 0.3s ease;
}

/* Questions */
.questionnaire { display: flex; flex-direction: column; gap: 16px; }
.question-card {
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md); padding: 18px 20px; transition: all 0.2s;
}
.question-card.answered { border-color: var(--accent); border-left: 3px solid var(--accent); }
.q-header { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 14px; }
.q-number {
  flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%;
  background: var(--accent-dim); color: var(--accent); font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.q-title { font-size: 13.5px; font-weight: 600; color: var(--text-primary); line-height: 1.5; }
.q-options { display: flex; flex-direction: column; gap: 6px; }
.q-option {
  display: flex; align-items: center; gap: 10px; padding: 9px 14px;
  border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);
  cursor: pointer; transition: all 0.15s; font-size: 12.5px; color: var(--text-secondary);
}
.q-option:hover { border-color: var(--accent); background: var(--accent-dim); }
.q-option.selected {
  border-color: var(--accent); background: var(--accent-dim); color: var(--text-primary);
}
.q-option input { display: none; }
.opt-radio {
  flex-shrink: 0; width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid var(--border-default); transition: all 0.15s; position: relative;
}
.q-option.selected .opt-radio {
  border-color: var(--accent); background: var(--accent);
}
.q-option.selected .opt-radio::after {
  content: ''; position: absolute; top: 3px; left: 3px;
  width: 6px; height: 6px; border-radius: 50%; background: #fff;
}
.opt-label { flex: 1; }

/* Submit */
.submit-row { text-align: center; margin-top: 24px; }
.btn-submit {
  padding: 12px 40px; border: none; border-radius: var(--radius-sm);
  background: var(--accent); color: #0a0c10; font-size: 14px; font-weight: 700;
  cursor: pointer; transition: all 0.18s; font-family: var(--font-sans);
}
.btn-submit:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 14px var(--accent-glow); }
.btn-submit:disabled { opacity: 0.4; cursor: not-allowed; }
.submit-hint { font-size: 11px; color: var(--text-tertiary); margin-top: 10px; }

/* Result */
.result-section { }
.result-card { text-align: center; padding: 32px 24px; }
.result-badge { margin-bottom: 20px; }
.result-level-tag {
  display: inline-block; padding: 6px 20px; border-radius: var(--radius-sm);
  color: #fff; font-size: 18px; font-weight: 700; letter-spacing: 1px;
}
.result-level-name { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-top: 10px; }
.result-score { display: flex; align-items: baseline; justify-content: center; gap: 6px; margin: 16px 0; }
.score-label { font-size: 12px; color: var(--text-tertiary); }
.score-value { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.score-max { font-size: 14px; color: var(--text-tertiary); }
.result-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.6; max-width: 480px; margin: 0 auto 8px; }
.result-time { font-size: 11px; color: var(--text-tertiary); }

/* Level scale */
.level-scale {
  display: flex; justify-content: space-between; margin-top: 28px; padding-top: 24px;
  border-top: 1px solid var(--border-subtle);
}
.level-step {
  display: flex; flex-direction: column; align-items: center; gap: 4px; opacity: 0.3; transition: opacity 0.3s;
}
.level-step.passed { opacity: 0.6; }
.level-step.active { opacity: 1; }
.step-dot {
  width: 12px; height: 12px; border-radius: 50%; transition: transform 0.2s;
}
.level-step.active .step-dot { transform: scale(1.4); box-shadow: 0 0 0 4px var(--bg-surface), 0 0 0 5px currentColor; }
.step-label { font-size: 11px; font-weight: 700; color: var(--text-secondary); }
.step-name { font-size: 9px; color: var(--text-tertiary); }

/* Product grades */
.grade-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.grade-item {
  padding: 14px 16px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);
  transition: all 0.2s;
}
.grade-item.allowed { border-color: var(--border-default); background: var(--bg-surface); }
.grade-item.disallowed { opacity: 0.5; background: var(--bg-overlay); }
.grade-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.grade-tag {
  padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 700;
  background: var(--accent-dim); color: var(--accent);
}
.grade-name { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.grade-desc { font-size: 11px; color: var(--text-tertiary); margin-bottom: 8px; }
.grade-status { font-size: 10px; font-weight: 600; }
.status-ok { color: var(--up); }
.status-no { color: var(--down); }

/* Warnings */
.warning-list { display: flex; flex-direction: column; gap: 10px; }
.warning-item {
  display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px;
  border-radius: var(--radius-sm); border: 1px solid var(--border-subtle);
}
.warn-icon {
  flex-shrink: 0; width: 20px; height: 20px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; color: #fff;
}
.warn-critical { border-color: #ef4444; background: rgba(239,68,68,0.06); }
.warn-critical .warn-icon { background: #ef4444; }
.warn-danger { border-color: #f97316; background: rgba(249,115,22,0.06); }
.warn-danger .warn-icon { background: #f97316; }
.warn-warning { border-color: #f5c842; background: rgba(245,200,66,0.06); }
.warn-warning .warn-icon { background: #f5c842; color: #333; }
.warn-info { border-color: var(--border-default); }
.warn-info .warn-icon { background: var(--text-tertiary); }
.warn-title { font-size: 12px; font-weight: 600; color: var(--text-primary); margin-bottom: 2px; }
.warn-message { font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; }

/* Retake */
.action-row { text-align: center; margin-top: 8px; }
.btn-retake {
  padding: 10px 28px; border: 1px solid var(--border-default); border-radius: var(--radius-sm);
  background: var(--bg-overlay); color: var(--text-secondary); font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.15s; font-family: var(--font-sans);
}
.btn-retake:hover { border-color: var(--accent); color: var(--accent); }

.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
</style>
