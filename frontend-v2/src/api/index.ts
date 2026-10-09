import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sp-token')
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  // Fallback: legacy API key (for backward compat)
  const key = localStorage.getItem('sp-api-key')
  if (key) {
    config.headers['x-api-key'] = key
  }
  return config
})

api.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      const hadToken = !!localStorage.getItem('sp-token')
      localStorage.removeItem('sp-token')
      // Only force-redirect if user was previously logged in (session expired)
      if (hadToken && location.pathname !== '/login') {
        location.href = '/login'
      }
    }
    const msg = err.response?.data?.message || err.message
    return Promise.reject(new Error(msg))
  }
)

export default api

// ===== Auth =====
export const login = (username: string, password: string) =>
  api.post('/auth/login', { username, password })
export const register = (username: string, password: string, display_name?: string) =>
  api.post('/auth/register', { username, password, display_name })
export const getMe = () => api.get('/auth/me')

// ===== System =====
export const getHealth = () => api.get('/health')
export const getAIConfig = () => api.get('/config/ai')
export const saveAIConfig = (data: any) => api.post('/config/ai/save', data)
export const testAIConnection = (data: any) => api.post('/config/ai/test', data)
export const getAIModels = () => api.get('/config/ai/models')
export const getAuditLogs = (params?: any) => api.get('/audit/logs', { params })

// ===== Market Data =====
function pfx(code: string): string {
  if (code.startsWith('sh') || code.startsWith('sz')) return code
  if (code.startsWith('6') || code.startsWith('9')) return 'sh' + code
  return 'sz' + code
}

export const getIndex = () => api.get('/index')
export const getQuote = (code: string) => api.get('/quote', { params: { code: pfx(code) } })
export const getKline = (code: string, period = 'day', count = 120) =>
  api.get('/kline', { params: { code: pfx(code), period, count } })
export const searchStock = (q: string) => api.get('/search', { params: { q } })
export const getBreadth = () => api.get('/breadth')
export const getTopMovers = (direction = 'up', limit = 10) =>
  api.get('/top-movers', { params: { direction, limit } })

// ===== Sectors =====
export const getSectors = () => api.get('/sectors')
export const getSectorStocks = (sectorCode: string, limit = 20) =>
  api.get('/sector/stocks', { params: { sector: sectorCode, limit } })

// ===== Screener =====
export const getStrategies = () => api.get('/screener/strategies')
export const runScreener = (strategy: string, universe = 'hs300') =>
  api.get('/screener/run', { params: { strategy, universe } })

// ===== Backtest =====
export const runBacktest = (code: string, strategy = 'ma_cross', days = 250) =>
  api.get('/backtest/run', { params: { code, strategy, days } })

// ===== Trade =====
export const getAccount = () => api.get('/account')
export const getPositions = () => api.get('/positions')
export const buyStock = (data: any) => api.post('/trade/buy', data)
export const sellStock = (data: any) => api.post('/trade/sell', data)
export const getTradeHistory = (limit = 50) => api.get('/trade/history', { params: { limit } })
export const aiAutoBuy = (data: { strategy?: string; universe?: string; top_n?: number; max_position_pct?: number }) =>
  api.post('/trade/ai-auto', data)
export const aiAutoSell = (data: { stop_loss_pct?: number; take_profit_pct?: number }) =>
  api.post('/trade/ai-sell', data)
export const confirmProposal = (proposalId: string) =>
  api.post('/trade/confirm-proposal', { proposal_id: proposalId })
export const resetAccount = () => api.post('/trade/reset-account')

// ===== Watchlist =====
export const getWatchlist = () => api.get('/watchlist')
export const addWatch = (code: string, name = '') => api.post('/watchlist/add', null, { params: { code, name } })
export const removeWatch = (code: string) => api.post('/watchlist/remove', null, { params: { code } })

// ===== Fund =====
export const screenFunds = (fundType = 'all', sortBy = 'return_1y', limit = 20) =>
  api.get('/fund/screen', { params: { fund_type: fundType, sort_by: sortBy, limit } })
export const getFundDetail = (code: string) => api.get('/fund/detail', { params: { code } })

// ===== Report =====
export const getDailyReport = () => api.get('/report/daily')

// ===== Minute K-line & Realtime =====
export const getMinuteKline = (code: string, period = 'm5', count = 120) =>
  api.get('/kline/minute', { params: { code: pfx(code), period, count } })
export const getRealtime = (code: string) => api.get('/realtime', { params: { code: pfx(code) } })

// ===== AI =====
export const analyzeStock = (code: string, name = '', context = '') =>
  api.post('/ai/analyze', { code, name, context })
export const getMarketSummary = () => api.get('/ai/market-summary')
export const chatAI = (messages: {role: string, content: string}[], context = '') =>
  api.post('/ai/chat', { messages, context })

// Streaming AI chat (SSE)
export function streamAI(
  messages: {role: string, content: string}[],
  context: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
) {
  const token = localStorage.getItem('sp-token') || ''
  const key = localStorage.getItem('sp-api-key') || ''
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (key) headers['x-api-key'] = key

  fetch('/api/ai/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify({ messages, context }),
  }).then(async (res) => {
    if (!res.ok) { onError('HTTP ' + res.status); return }
    const reader = res.body?.getReader()
    if (!reader) { onError('No stream'); return }
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6)
        if (payload === '[DONE]') { onDone(); return }
        try {
          const d = JSON.parse(payload)
          if (d.text) onChunk(d.text)
          if (d.error) { onError(d.error); return }
        } catch {}
      }
    }
    onDone()
  }).catch((e) => onError(e.message))
}

// ===== Phase 2: Proactive Management =====
export const getBriefing = () => api.get('/ai/briefing')
export const getAlerts = () => api.get('/ai/alerts')
export const diagnosePortfolio = () => api.post('/ai/diagnose', {})

// ===== Phase 3: Auto Trading =====
export const getSignals = (codes?: string) =>
  api.get('/ai/signals', { params: codes ? { codes } : {}, timeout: 90000 })
export const getRiskStatus = () => api.get('/ai/risk-status')
export const autoExecute = () => api.post('/ai/auto-execute', {}, { timeout: 90000 })
export const confirmExecute = (proposalId: string) =>
  api.post('/ai/confirm-execute', { proposal_id: proposalId })

// ===== Portfolio Import =====
export const importManual = (data: { positions: any[]; cash?: number }) =>
  api.post('/portfolio/import-manual', data)
export const importText = (data: { text: string; cash?: number }) =>
  api.post('/portfolio/import-text', data)
export const importImage = (data: { image_base64: string; cash?: number }) =>
  api.post('/portfolio/import-image', data, { timeout: 60000 })
export const getPortfolioStatus = () => api.get('/portfolio/status')
export const clearPortfolio = () => api.post('/portfolio/clear', {})

// ===== Suitability (Risk Assessment) =====
export const getSuitabilityQuestions = () => api.get('/suitability/questionnaire')
export const submitSuitability = (answers: number[]) =>
  api.post('/suitability/assess', { answers })
export const getSuitabilityProfile = () => api.get('/suitability/profile')
export const getProductGrades = () => api.get('/suitability/product-grades')
export const checkProductSuitability = (productType: string) =>
  api.post('/suitability/check-product', { product_type: productType })
export const getRiskWarnings = () => api.get('/risk-warnings')
export const getRiskWarning = (productType?: string) =>
  api.get('/risk-warnings', { params: productType ? { product_type: productType } : {} })
