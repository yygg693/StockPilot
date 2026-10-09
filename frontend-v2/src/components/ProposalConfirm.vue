<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  proposal: any
}>()
const emit = defineEmits<{
  confirm: [id: string]
  cancel: []
}>()

const countdown = ref(300)
let timer: number | undefined

watch(() => props.visible, (v) => {
  if (v) {
    countdown.value = 300
    timer = window.setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        clearInterval(timer)
        emit('cancel')
      }
    }, 1000)
  } else if (timer) {
    clearInterval(timer)
  }
})

function fmtTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${String(sec).padStart(2, '0')}`
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible && proposal" class="modal-overlay" @click.self="emit('cancel')">
      <div class="modal-card">
        <div class="modal-header">
          <h3>交易提案确认</h3>
          <span class="countdown" :class="{ urgent: countdown < 60 }">
            剩余 {{ fmtTime(countdown) }}
          </span>
        </div>

        <div class="modal-body">
          <div class="proposal-summary">
            <div class="prop-row">
              <span class="prop-label">操作类型</span>
              <span class="prop-value" :class="proposal.type === 'buy' ? 'buy' : 'sell'">
                {{ proposal.type === 'buy' ? '买入' : '卖出' }}
              </span>
            </div>
            <div class="prop-row">
              <span class="prop-label">标的</span>
              <span class="prop-value">{{ proposal.code }} {{ proposal.name || '' }}</span>
            </div>
            <div v-if="proposal.qty" class="prop-row">
              <span class="prop-label">数量</span>
              <span class="prop-value">{{ proposal.qty }} 股</span>
            </div>
            <div v-if="proposal.price" class="prop-row">
              <span class="prop-label">价格</span>
              <span class="prop-value">{{ proposal.price.toFixed(2) }} 元</span>
            </div>
            <div v-if="proposal.amount" class="prop-row">
              <span class="prop-label">金额</span>
              <span class="prop-value">{{ proposal.amount.toFixed(2) }} 元</span>
            </div>
            <div v-if="proposal.reason" class="prop-row">
              <span class="prop-label">AI建议理由</span>
              <span class="prop-value reason">{{ proposal.reason }}</span>
            </div>
          </div>

          <div class="warning-box">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            <span>投资有风险，入市需谨慎。请确认您了解本次交易的风险后再操作。</span>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn-cancel" @click="emit('cancel')">取消</button>
          <button class="btn-confirm" @click="emit('confirm', proposal.proposal_id || proposal.id)">
            确认执行
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
}
.modal-card {
  width: 480px; border-radius: 12px; background: var(--bg-surface);
  border: 1px solid var(--border-default); box-shadow: 0 12px 40px rgba(0,0,0,0.2);
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 24px; border-bottom: 1px solid var(--border-subtle);
}
.modal-header h3 { font-size: 16px; font-weight: 600; color: var(--text-primary); }
.countdown { font-size: 13px; color: var(--text-tertiary); font-family: var(--font-mono); }
.countdown.urgent { color: var(--down); }
.modal-body { padding: 20px 24px; }
.proposal-summary { display: flex; flex-direction: column; gap: 12px; }
.prop-row { display: flex; gap: 12px; }
.prop-label { width: 100px; font-size: 13px; color: var(--text-tertiary); flex-shrink: 0; }
.prop-value { font-size: 14px; color: var(--text-primary); font-weight: 500; }
.prop-value.buy { color: var(--up); }
.prop-value.sell { color: var(--down); }
.prop-value.reason { font-weight: 400; color: var(--text-secondary); line-height: 1.5; }
.warning-box {
  margin-top: 16px; padding: 12px 14px; border-radius: 8px;
  background: rgba(245,200,66,0.1); display: flex; gap: 10px; align-items: flex-start;
  color: #eab308; font-size: 12px; line-height: 1.5;
}
.modal-footer {
  display: flex; gap: 12px; padding: 16px 24px; border-top: 1px solid var(--border-subtle);
  justify-content: flex-end;
}
.btn-cancel, .btn-confirm {
  padding: 10px 24px; border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer;
  border: 1px solid var(--border-default); transition: all 0.2s;
}
.btn-cancel { background: var(--bg-overlay); color: var(--text-secondary); }
.btn-cancel:hover { background: var(--bg-elevated); }
.btn-confirm { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-confirm:hover { opacity: 0.9; }
</style>
