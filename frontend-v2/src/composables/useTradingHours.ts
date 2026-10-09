/**
 * A股交易时间规则:
 * - 股票: 周一至周五 9:30-11:30, 13:00-15:00
 * - 基金: 交易日15:00前申购/赎回算当天，15:00后算下一个交易日
 */
import { ref, computed, onMounted, onUnmounted } from "vue"

function isWeekend(d: Date): boolean {
  const day = d.getDay()
  return day === 0 || day === 6
}

function getTimeMinutes(d: Date): number {
  return d.getHours() * 60 + d.getMinutes()
}

export function useTradingHours() {
  const now = ref(new Date())
  let timer: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    timer = setInterval(() => { now.value = new Date() }, 30000)
  })
  onUnmounted(() => { if (timer) clearInterval(timer) })

  const stockMarketOpen = computed(() => {
    if (isWeekend(now.value)) return false
    const t = getTimeMinutes(now.value)
    return (t >= 570 && t <= 690) || (t >= 780 && t <= 900)
  })

  const canTradeStock = computed(() => {
    if (isWeekend(now.value)) return false
    const t = getTimeMinutes(now.value)
    return t >= 555 && t <= 900
  })

  const fundSameDay = computed(() => {
    if (isWeekend(now.value)) return false
    return getTimeMinutes(now.value) < 900
  })

  const canTradeFund = computed(() => {
    return !isWeekend(now.value)
  })

  const stockStatusText = computed(() => {
    if (isWeekend(now.value)) return "周末休市"
    const t = getTimeMinutes(now.value)
    if (t < 555) return "未开盘 (9:15集合竞价)"
    if (t >= 555 && t < 570) return "集合竞价中"
    if (t >= 570 && t <= 690) return "交易中"
    if (t > 690 && t < 780) return "午间休市"
    if (t >= 780 && t <= 900) return "交易中"
    return "已收盘"
  })

  const fundStatusText = computed(() => {
    if (isWeekend(now.value)) return "周末提交将顺延至周一处理"
    if (fundSameDay.value) return "15:00前提交，按今日净值确认"
    return "已过15:00，将按下一交易日净值确认"
  })

  return {
    now,
    stockMarketOpen,
    canTradeStock,
    canTradeFund,
    fundSameDay,
    stockStatusText,
    fundStatusText,
  }
}
