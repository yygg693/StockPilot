/**
 * useStaleRefresh — load-on-mount + refresh-on-activate-if-stale.
 *
 * Pairs with <keep-alive> cached views. The first visit runs `load` immediately.
 * Returning to a cached view re-fetches only when the data is older than `ttlMs`
 * (default 60s). This makes tab switching instant (cached DOM) while preventing
 * data from going stale for long.
 */
import { onMounted, onActivated, ref } from 'vue'

export function useStaleRefresh(
  load: () => Promise<void> | void,
  ttlMs = 60_000,
) {
  const lastLoaded = ref(0)
  const isRefreshing = ref(false)

  async function run() {
    // Mark immediately (before await) so a subsequent onActivated in the same
    // tick sees fresh data and skips a duplicate load.
    lastLoaded.value = Date.now()
    isRefreshing.value = true
    try {
      await load()
    } finally {
      isRefreshing.value = false
      lastLoaded.value = Date.now()
    }
  }

  onMounted(run)
  onActivated(() => {
    if (Date.now() - lastLoaded.value > ttlMs) run()
  })

  return { lastLoaded, isRefreshing, refresh: run }
}
