<script setup lang="ts">
import { ref, watch } from "vue"
import { searchStock } from "@/api"

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits(["update:modelValue", "select"])

const query = ref("")
const results = ref<any[]>([])
const show = ref(false)
let debounce: number

watch(query, (v) => {
  clearTimeout(debounce)
  if (!v || v.length < 1) { results.value = []; show.value = false; return }
  debounce = window.setTimeout(async () => {
    try {
      const res: any = await searchStock(v)
      results.value = (res.data || []).slice(0, 8)
      show.value = results.value.length > 0
    } catch { results.value = []; show.value = false }
  }, 300)
})

function pick(item: any) {
  query.value = item.name + " " + item.code
  show.value = false
  emit("select", item)
}

function onBlur() { setTimeout(() => { show.value = false }, 200) }
</script>

<template>
  <div class="search-auto">
    <input
      v-model="query"
      class="search-input"
      placeholder="搜索股票 / 基金 / ETF ..."
      @focus="show = results.length > 0"
      @blur="onBlur"
    />
    <div v-if="show" class="dropdown">
      <div v-for="item in results" :key="item.code" class="drop-item" @mousedown="pick(item)">
        <span class="drop-name">{{ item.name }}</span>
        <span class="drop-code">{{ item.code }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.search-auto { position: relative; width: 100%; }
.search-input {
  background: none; border: none; outline: none; color: var(--text-primary);
  font-size: 12.5px; font-family: var(--font-sans); width: 100%;
  transition: color var(--transition-theme);
}
.search-input::placeholder { color: var(--text-tertiary); }
.dropdown {
  position: absolute; top: calc(100% + 8px); left: -14px; right: -14px;
  background: var(--bg-elevated); border: 1px solid var(--border-default);
  border-radius: var(--radius-md); box-shadow: var(--shadow-elevated);
  overflow: hidden; z-index: 100;
}
.drop-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 9px 14px; cursor: pointer; transition: background 0.12s;
}
.drop-item:hover { background: var(--bg-hover); }
.drop-name { font-size: 12.5px; font-weight: 500; color: var(--text-primary); }
.drop-code { font-size: 11px; font-family: var(--font-mono); color: var(--text-tertiary); }
</style>
