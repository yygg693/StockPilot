<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import api, { getAIConfig, saveAIConfig, getAIModels } from "@/api"

// --- State ---
const apiKey = ref("")
const baseUrl = ref("https://api.deepseek.com")
// Currently recommended DeepSeek API models (deepseek-chat/-reasoner were
// retired on 2026-07-24). Used as the default and as a fallback when the
// provider model list can't be fetched (e.g. no key / offline).
const RECOMMENDED_MODELS = ["deepseek-v4-flash", "deepseek-v4-pro"]
const model = ref("deepseek-v4-flash")
const modelList = ref<string[]>([...RECOMMENDED_MODELS])
const modelsLoading = ref(false)

async function fetchModels() {
  modelsLoading.value = true
  try {
    const res: any = await getAIModels()
    const fetched = (res.data?.models || []).filter(Boolean)
    if (fetched.length) {
      modelList.value = fetched
      if (!modelList.value.includes(model.value)) {
        model.value = modelList.value[0]
      }
    } else {
      // Provider list unavailable — keep the recommended models so the
      // dropdown is never empty or stuck on a placeholder.
      modelList.value = [...RECOMMENDED_MODELS]
    }
  } catch {
    modelList.value = [...RECOMMENDED_MODELS]
  } finally { modelsLoading.value = false }
}
const showKey = ref(false)
const hasSavedKey = ref(false)

// Connection test
const testing = ref(false)
const testResult = ref<"idle" | "success" | "fail">("idle")
const testMsg = ref("")
const showKeyHint = ref(false)
const KEY_REGEN_URL = "https://platform.deepseek.com/api_keys"

// Save
const saving = ref(false)
const showToast = ref(false)
const toastMsg = ref("")

// Server config status
const serverConfig = ref<any>(null)

// --- Computed ---
const maskedKey = computed(() => {
  const k = apiKey.value
  if (!k) return ""
  if (k.length <= 8) return "****" + k.slice(-4)
  return k.slice(0, 4) + "****" + k.slice(-4)
})

// --- Methods ---
function toggleShowKey() {
  showKey.value = !showKey.value
}

function onKeyInput(e: Event) {
  const target = e.target as HTMLInputElement
  apiKey.value = target.value
  hasSavedKey.value = false
}

async function testConnection() {
  if (!apiKey.value) {
    testResult.value = "fail"
    testMsg.value = "\u8bf7\u5148\u8f93\u5165 API Key"
    showKeyHint.value = false
    return
  }
  testing.value = true
  testResult.value = "idle"
  testMsg.value = ""
  showKeyHint.value = false
  try {
    const res: any = await api.post("/config/ai/test", {
      api_key: apiKey.value,
      base_url: baseUrl.value,
      model: model.value,
    })
    // The test endpoint returns HTTP 200 with { data: { success, message, status } }.
    const d = res?.data || {}
    testResult.value = d.success ? "success" : "fail"
    testMsg.value = d.message || (d.success ? "\u8fde\u63a5\u6210\u529f" : "\u8fde\u63a5\u5931\u8d25")
    // Surface the "regenerate key" hint only on auth failures (401/403).
    showKeyHint.value = d.success === false && (d.status === 401 || d.status === 403)
  } catch (e: any) {
    testResult.value = "fail"
    testMsg.value = e?.message || "\u8fde\u63a5\u5931\u8d25"
    showKeyHint.value = false
  } finally {
    testing.value = false
  }
}

// Open the DeepSeek key-management page. In the packaged desktop app we route
// through the pywebview JS bridge so the OS default browser actually opens;
// in the dev browser we fall back to window.open.
function openKeyUrl(e: Event) {
  e.preventDefault()
  const wv: any = (window as any).pywebview
  if (wv && wv.api && typeof wv.api.open_external === "function") {
    wv.api.open_external(KEY_REGEN_URL)
  } else {
    window.open(KEY_REGEN_URL, "_blank", "noopener,noreferrer")
  }
}

async function saveConfig() {
  saving.value = true
  try {
    // Persist to the backend so AI analysis can actually use the key.
    // The key itself is never written to disk or localStorage: it is kept in
    // backend memory or the STOCKPILOT_AI_API_KEY environment variable.
    const res: any = await saveAIConfig({
      api_key: apiKey.value,
      base_url: baseUrl.value,
      model: model.value,
    })
    if (apiKey.value) {
      hasSavedKey.value = true
    }
    localStorage.setItem("sp-ai-base-url", baseUrl.value)
    localStorage.setItem("sp-ai-model", model.value)
    // Reflect the freshly saved state in the status badge.
    serverConfig.value = res?.data || res || serverConfig.value || {}
    toastMsg.value = "\u914d\u7f6e\u5df2\u4fdd\u5b58"
    showToast.value = true
    setTimeout(() => { showToast.value = false }, 2500)
    // Re-fetch authoritative server state.
    try {
      const cfg: any = await getAIConfig()
      serverConfig.value = cfg?.data || cfg || {}
    } catch {
      // ignore refresh failure; we already have the save response
    }
  } catch (e: any) {
    toastMsg.value = e?.message || "\u4fdd\u5b58\u5931\u8d25"
    showToast.value = true
    setTimeout(() => { showToast.value = false }, 2500)
  } finally {
    saving.value = false
  }
}

function loadConfig() {
  // API key is never persisted to localStorage; it comes from the
  // STOCKPILOT_AI_API_KEY env var or is entered at runtime.
  const savedUrl = localStorage.getItem("sp-ai-base-url")
  if (savedUrl) baseUrl.value = savedUrl
  const savedModel = localStorage.getItem("sp-ai-model")
  if (savedModel) model.value = savedModel
}

// --- Lifecycle ---
onMounted(async () => {
  loadConfig()
  fetchModels()
  try {
    const res: any = await getAIConfig()
    serverConfig.value = res?.data || res || {}
  } catch {
    // ignore
  }
})
</script>

<template>
  <div class="page">
    <!-- Page Header -->
    <div class="page-head animate-in">
      <h1 class="page-title">设置</h1>
      <p class="page-desc">配置 AI 密钥、模型参数与连接状态</p>
    </div>

    <!-- AI Key Configuration Card -->
    <div class="card animate-in delay-1" v-liquid>
      <div class="card-header">
        <span class="card-title">AI 密钥配置</span>
        <span
          v-if="serverConfig"
          class="status-badge"
          :class="serverConfig.api_key_set ? 'on' : 'off'"
        >
          {{ serverConfig.api_key_set ? "已连接" : "未配置" }}
        </span>
      </div>

      <!-- API Key Field -->
      <div class="field-group">
        <label class="field-label">API Key</label>
        <div class="key-input-row">
          <div class="input-wrap key-wrap">
            <input
              v-if="showKey"
              v-model="apiKey"
              type="text"
              class="input mono"
              placeholder="sk-..."
              autocomplete="off"
              spellcheck="false"
            />
            <input
              v-else
              :value="hasSavedKey ? maskedKey : apiKey"
              @input="onKeyInput"
              @focus="hasSavedKey = false"
              type="text"
              class="input mono"
              placeholder="sk-..."
              autocomplete="off"
              spellcheck="false"
            />
            <button class="eye-btn" @click="toggleShowKey" :title="showKey ? 'Hide' : 'Show'">
              <svg v-if="!showKey" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
              <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"/>
                <line x1="1" y1="1" x2="23" y2="23"/>
              </svg>
            </button>
          </div>
        </div>
        <p class="field-hint">密钥会以设备绑定的加密方式保存在本机配置文件（data/ai_config.json）中，仅本机可读、重启后仍有效；也可改用环境变量 STOCKPILOT_AI_API_KEY 配置</p>
      </div>

      <!-- Base URL Field -->
      <div class="field-group">
        <label class="field-label">Base URL</label>
        <input
          v-model="baseUrl"
          type="text"
          class="input"
          placeholder="https://api.deepseek.com"
          spellcheck="false"
        />
      </div>

      <!-- Model Field -->
      <div class="field-group">
        <label class="field-label">模型</label>
        <div style="display:flex;gap:8px;align-items:center">
          <select v-model="model" class="model-select">
            <option v-for="m in modelList" :key="m" :value="m">{{ m }}</option>
          </select>
          <button class="fetch-btn" @click="fetchModels" :disabled="modelsLoading">
            {{ modelsLoading ? '获取中...' : '获取模型' }}
          </button>
        </div>
        <p class="field-hint">推荐 deepseek-v4-flash（通用）或 deepseek-v4-pro（推理）；旧模型 deepseek-chat / deepseek-reasoner 已于 2026-07-24 退役，请勿使用</p>
      </div>

      <!-- Actions -->
      <div class="actions-row">
        <button class="btn btn-secondary" v-liquid="{maxTilt: 6, scale: 1.04}" @click="testConnection" :disabled="testing">
          <span v-if="testing" class="spinner"></span>
          <span v-else>测试连接</span>
        </button>
        <button class="btn btn-primary" v-liquid="{maxTilt: 6, scale: 1.04}" @click="saveConfig" :disabled="saving">
          保存配置
        </button>
      </div>

      <!-- Test Result -->
      <div v-if="testResult !== 'idle'" class="test-result" :class="testResult">
        <span class="test-icon">{{ testResult === "success" ? "\u2713" : "\u2717" }}</span>
        <span class="test-msg">{{ testMsg }}</span>
      </div>
      <a v-if="showKeyHint" class="key-hint" :href="KEY_REGEN_URL" target="_blank" rel="noopener noreferrer" @click="openKeyUrl">
        前往 DeepSeek 平台重新生成 API Key &nearr;
      </a>
    </div>

    <!-- About Card -->
    <div class="card animate-in delay-2" v-liquid>
      <div class="card-header">
        <span class="card-title">关于</span>
      </div>
      <div class="about-row">
        <span class="about-label">版本</span>
        <span class="about-value mono">StockPilot v2.0.0</span>
      </div>
      <div class="about-row">
        <span class="about-label">技术栈</span>
        <span class="about-value">FastAPI + Vue 3 + ECharts</span>
      </div>
      <div class="about-row">
        <span class="about-label">数据源</span>
        <span class="about-value">腾讯财经 / 东方财富</span>
      </div>
    </div>

    <!-- Toast -->
    <Transition name="toast">
      <div v-if="showToast" class="toast">
        <span class="toast-icon">&#10003;</span>
        {{ toastMsg }}
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.page {
  max-width: 680px;
}

.page-head {
  margin-bottom: 28px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
}
.page-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  margin: 0;
}

/* Card */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 24px;
  margin-bottom: 16px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Status badge */
.status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
}
.status-badge.on {
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
}
.status-badge.off {
  background: rgba(251, 191, 36, 0.12);
  color: #fbbf24;
}

/* Fields */
.field-group {
  margin-bottom: 18px;
}
.field-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 7px;
}
.field-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  margin: 6px 0 0;
  line-height: 1.5;
}

.input {
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}
.input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.input::placeholder {
  color: var(--text-tertiary);
}
.mono {
  font-family: var(--font-mono);
}

/* Key input with eye toggle */
.key-input-row {
  display: flex;
  gap: 8px;
}
.input-wrap {
  position: relative;
  flex: 1;
}
.key-wrap .input {
  padding-right: 40px;
}
.eye-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: color 0.15s;
}
.eye-btn:hover {
  color: var(--text-secondary);
}

/* Actions */
.actions-row {
  display: flex;
  gap: 10px;
  margin-top: 22px;
}
.btn {
  padding: 9px 18px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--accent);
  color: #0a0c10;
  border-color: var(--accent);
}
.btn-primary:hover:not(:disabled) {
  opacity: 0.88;
}
.btn-secondary {
  background: transparent;
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}
.btn-secondary:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

/* Spinner */
.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Test result */
.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: var(--radius-sm);
  font-size: 12.5px;
}
.test-result.success {
  background: rgba(52, 211, 153, 0.08);
  border: 1px solid rgba(52, 211, 153, 0.2);
  color: #34d399;
}
.test-result.fail {
  background: rgba(248, 113, 113, 0.08);
  border: 1px solid rgba(248, 113, 113, 0.2);
  color: #f87171;
}
.test-icon {
  font-weight: 700;
  font-size: 14px;
}
.test-msg {
  color: inherit;
}

/* Key regeneration hint (auth failure) */
.key-hint {
  display: inline-block;
  margin-top: 10px;
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  border: 1px solid var(--accent);
  padding: 7px 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s;
}
.key-hint:hover {
  background: var(--accent-dim, rgba(56, 189, 248, 0.12));
}

/* About */
.about-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.about-row:last-child {
  border-bottom: none;
}
.about-label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-secondary);
}
.about-value {
  font-size: 12.5px;
  color: var(--text-primary);
}

/* Toast */
.toast {
  position: fixed;
  bottom: 32px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg-surface);
  border: 1px solid rgba(52, 211, 153, 0.3);
  color: #34d399;
  padding: 10px 20px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 1000;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}
.toast-icon {
  font-weight: 700;
}
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}

/* Animations */
.animate-in {
  animation: fadeUp 0.35s ease both;
}
.delay-1 { animation-delay: 0.06s; }
.delay-2 { animation-delay: 0.12s; }
@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.fetch-btn { margin-left: 8px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border-default); background: transparent; color: var(--accent); font-size: 10px; cursor: pointer; }
.fetch-btn:hover:not(:disabled) { background: var(--accent-dim); }
.fetch-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.model-select { width: 100%; padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-default); background: var(--bg-overlay); color: var(--text-primary); font-size: 13px; outline: none; cursor: pointer; }
.model-select:focus { border-color: var(--accent); }
</style>
