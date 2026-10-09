<script setup lang="ts">
import { ref } from "vue"
import { importManual, importText, importImage, clearPortfolio } from "@/api"

const tab = ref<"manual" | "text" | "image">("manual")
const loading = ref(false)
const result = ref<any>(null)
const error = ref("")

// Manual entry
const manualRows = ref([{ code: "", name: "", qty: "", cost: "", type: "stock" }])
const manualCash = ref("")

function addRow() {
  manualRows.value.push({ code: "", name: "", qty: "", cost: "", type: "stock" })
}
function removeRow(i: number) {
  manualRows.value.splice(i, 1)
}

async function submitManual() {
  const positions = manualRows.value
    .filter((r) => r.code && r.qty && r.cost)
    .map((r) => ({
      code: r.code.trim(),
      name: r.name.trim(),
      qty: parseFloat(r.qty),
      cost: parseFloat(r.cost),
      asset_type: r.type,
    }))
  if (!positions.length) { error.value = "请至少填写一条完整持仓"; return }
  loading.value = true; error.value = ""; result.value = null
  try {
    const cash = manualCash.value ? parseFloat(manualCash.value) : undefined
    const res: any = await importManual({ positions, cash })
    result.value = res.data || res
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

// Text paste
const pasteText = ref("")
const pasteCash = ref("")

async function submitText() {
  if (!pasteText.value.trim()) { error.value = "请粘贴持仓文本"; return }
  loading.value = true; error.value = ""; result.value = null
  try {
    const cash = pasteCash.value ? parseFloat(pasteCash.value) : undefined
    const res: any = await importText({ text: pasteText.value, cash })
    result.value = res.data || res
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

// Image upload
const imagePreview = ref("")
const imageBase64 = ref("")
const imageCash = ref("")

function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const dataUrl = reader.result as string
    imagePreview.value = dataUrl
    imageBase64.value = dataUrl.split(",")[1] || ""
  }
  reader.readAsDataURL(file)
}

async function submitImage() {
  if (!imageBase64.value) { error.value = "请先选择截图文件"; return }
  loading.value = true; error.value = ""; result.value = null
  try {
    const cash = imageCash.value ? parseFloat(imageCash.value) : undefined
    const res: any = await importImage({ image_base64: imageBase64.value, cash })
    result.value = res.data || res
  } catch (e: any) { error.value = e.message }
  finally { loading.value = false }
}

// Clear
async function doClear() {
  if (!confirm("确定清空所有持仓数据？清空后可重新导入。")) return
  try {
    await clearPortfolio()
    result.value = { ok: true, message: "已清空，可重新导入" }
  } catch (e: any) { error.value = e.message }
}
</script>

<template>
  <div class="page">
    <div class="page-head animate-in">
      <h1 class="page-title">导入持仓</h1>
      <p class="page-desc">从蚂蚁财富、券商APP等导入真实持仓，AI将基于此进行诊断和模拟操作</p>
    </div>

    <!-- Tabs -->
    <div class="tabs animate-in delay-1">
      <button :class="{ active: tab === 'manual' }" @click="tab = 'manual'">手动录入</button>
      <button :class="{ active: tab === 'text' }" @click="tab = 'text'">文本粘贴</button>
      <button :class="{ active: tab === 'image' }" @click="tab = 'image'">截图识别</button>
    </div>

    <!-- Manual -->
    <div v-if="tab === 'manual'" class="card animate-in delay-2">
      <div class="card-title">逐条添加持仓</div>
      <div class="manual-rows">
        <div v-for="(row, i) in manualRows" :key="i" class="manual-row">
          <input v-model="row.code" placeholder="代码 如600519" class="input code-input" />
          <input v-model="row.name" placeholder="名称（可选）" class="input name-input" />
          <input v-model="row.qty" placeholder="数量/份额" class="input num-input" type="number" />
          <input v-model="row.cost" placeholder="成本价" class="input num-input" type="number" step="0.001" />
          <select v-model="row.type" class="select type-select">
            <option value="stock">股票</option>
            <option value="fund">基金</option>
          </select>
          <button class="btn-icon" @click="removeRow(i)" v-if="manualRows.length > 1" title="删除">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
      <div class="manual-footer">
        <button class="btn btn-ghost" @click="addRow">+ 添加一行</button>
        <div class="cash-field">
          <label>可用余额（可选）</label>
          <input v-model="manualCash" placeholder="如 50000" class="input num-input" type="number" />
        </div>
        <button class="btn btn-primary" @click="submitManual" :disabled="loading">{{ loading ? "导入中..." : "确认导入" }}</button>
      </div>
    </div>

    <!-- Text -->
    <div v-if="tab === 'text'" class="card animate-in delay-2">
      <div class="card-title">粘贴持仓文本</div>
      <p class="hint">从蚂蚁财富/同花顺/券商APP复制持仓信息粘贴到下方，系统自动识别代码、数量、成本。</p>
      <textarea v-model="pasteText" class="textarea" rows="8" placeholder="示例：&#10;贵州茅台 600519&#10;持有 100股 成本1800.00&#10;&#10;招商中证白酒 161725&#10;份额: 5000 成本净值: 1.234"></textarea>
      <div class="manual-footer">
        <div class="cash-field">
          <label>可用余额（可选）</label>
          <input v-model="pasteCash" placeholder="如 50000" class="input num-input" type="number" />
        </div>
        <button class="btn btn-primary" @click="submitText" :disabled="loading">{{ loading ? "识别中..." : "识别并导入" }}</button>
      </div>
    </div>

    <!-- Image -->
    <div v-if="tab === 'image'" class="card animate-in delay-2">
      <div class="card-title">截图识别（AI视觉）</div>
      <p class="hint">截取蚂蚁财富/券商APP的持仓页面，上传后AI自动提取持仓数据。</p>
      <div class="image-area">
        <label class="upload-label">
          <input type="file" accept="image/*" @change="onFileChange" hidden />
          <div v-if="!imagePreview" class="upload-placeholder">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
            <span>点击选择截图</span>
          </div>
          <img v-else :src="imagePreview" class="preview-img" />
        </label>
      </div>
      <div class="manual-footer">
        <div class="cash-field">
          <label>可用余额（可选）</label>
          <input v-model="imageCash" placeholder="如 50000" class="input num-input" type="number" />
        </div>
        <button class="btn btn-primary" @click="submitImage" :disabled="loading || !imageBase64">{{ loading ? "AI识别中..." : "识别并导入" }}</button>
      </div>
    </div>

    <!-- Result -->
    <div v-if="result" class="result-card animate-in" :class="result.ok ? 'result-ok' : 'result-fail'">
      {{ result.message }}
      <span v-if="result.imported" class="result-count">（{{ result.imported }} 条）</span>
    </div>
    <div v-if="error" class="result-card result-fail animate-in">{{ error }}</div>

    <!-- Danger zone -->
    <div class="card danger-zone animate-in delay-3">
      <span class="danger-text">清空所有持仓数据（重新导入前使用）</span>
      <button class="btn btn-danger" @click="doClear">清空持仓</button>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 800px; }
.page-head { margin-bottom: 24px; }
.page-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 4px; }
.page-desc { font-size: 12.5px; color: var(--text-tertiary); }

.tabs { display: flex; gap: 4px; margin-bottom: 16px; background: var(--bg-overlay); border-radius: var(--radius-sm); padding: 4px; }
.tabs button { flex: 1; padding: 9px 16px; border: none; border-radius: var(--radius-sm); font-size: 12.5px; font-weight: 600; cursor: pointer; background: transparent; color: var(--text-secondary); transition: all 0.18s; }
.tabs button.active { background: var(--bg-surface); color: var(--accent); box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
.tabs button:hover:not(.active) { color: var(--text-primary); }

.card { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 20px; margin-bottom: 16px; }
.card-title { font-size: 13px; font-weight: 600; margin-bottom: 14px; color: var(--text-primary); }
.hint { font-size: 11.5px; color: var(--text-tertiary); margin-bottom: 12px; line-height: 1.6; }

.manual-rows { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
.manual-row { display: flex; gap: 8px; align-items: center; }
.input { padding: 8px 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; outline: none; transition: border-color 0.2s; }
.input:focus { border-color: var(--accent); }
.code-input { width: 100px; font-family: var(--font-mono); }
.name-input { flex: 1; min-width: 80px; }
.num-input { width: 90px; font-family: var(--font-mono); }
.type-select { padding: 8px 10px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-overlay); color: var(--text-primary); font-size: 12px; }
.btn-icon { background: none; border: none; cursor: pointer; color: var(--text-tertiary); padding: 4px; border-radius: 4px; }
.btn-icon:hover { color: var(--down); background: var(--down-dim); }

.manual-footer { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.cash-field { display: flex; align-items: center; gap: 8px; margin-left: auto; }
.cash-field label { font-size: 11px; color: var(--text-tertiary); white-space: nowrap; }

.textarea { width: 100%; padding: 12px; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-overlay); color: var(--text-primary); font-size: 12.5px; font-family: var(--font-mono); line-height: 1.7; resize: vertical; outline: none; }
.textarea:focus { border-color: var(--accent); }

.image-area { margin-bottom: 14px; }
.upload-label { cursor: pointer; display: block; }
.upload-placeholder { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 40px; border: 2px dashed var(--border-default); border-radius: var(--radius-md); color: var(--text-tertiary); font-size: 12.5px; transition: border-color 0.2s; }
.upload-placeholder:hover { border-color: var(--accent); color: var(--accent); }
.preview-img { max-width: 100%; max-height: 300px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); }

.btn { font-size: 12.5px; font-weight: 600; padding: 9px 18px; border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all 0.18s; }
.btn-primary { background: linear-gradient(135deg, var(--accent), #a8884a); color: #0a0c10; }
.btn-primary:hover { transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.btn-ghost { background: transparent; border: 1px solid var(--border-default); color: var(--text-secondary); }
.btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
.btn-danger { background: var(--down-dim); color: var(--down); font-size: 11.5px; padding: 7px 14px; }
.btn-danger:hover { background: var(--down); color: #fff; }

.result-card { padding: 12px 16px; border-radius: var(--radius-sm); font-size: 12.5px; margin-bottom: 12px; }
.result-ok { background: var(--up-dim); color: var(--up); border: 1px solid var(--up); }
.result-fail { background: var(--down-dim); color: var(--down); border: 1px solid var(--down); }
.result-count { font-weight: 600; }

.danger-zone { display: flex; align-items: center; justify-content: space-between; border-color: var(--down-dim); }
.danger-text { font-size: 11.5px; color: var(--text-tertiary); }
</style>
