import axios from "axios";

// Single source of truth for the active portfolio id, mirrored from React state
// by PortfolioProvider via setActivePortfolioId(). The axios interceptor below
// reads it on every request so we never have to thread portfolio_id through call
// sites — every page just calls the same fetch helpers.
let _activePortfolioId = null;

export function setActivePortfolioId(id) {
  _activePortfolioId = id == null ? null : Number(id);
}

export function getActivePortfolioId() {
  return _activePortfolioId;
}

const api = axios.create({ baseURL: "/api" });

// Endpoints that are NOT portfolio-scoped — these must not receive portfolio_id
// or they'd 404 / mis-route.
const PORTFOLIO_AGNOSTIC_PREFIXES = ["/portfolios", "/market", "/watchlists", "/settings"];

function isPortfolioAgnostic(url) {
  if (!url) return false;
  return PORTFOLIO_AGNOSTIC_PREFIXES.some((p) => url === p || url.startsWith(p + "/") || url.startsWith(p + "?"));
}

api.interceptors.request.use((config) => {
  if (_activePortfolioId == null) return config;
  if (isPortfolioAgnostic(config.url)) return config;
  config.params = { ...(config.params || {}), portfolio_id: _activePortfolioId };
  return config;
});

// When the session is missing/expired the gate returns 401; bounce the user to
// the server-rendered login page (same-origin in prod; proxied in dev). Guarded
// so a burst of 401s triggers a single navigation.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && typeof window !== "undefined") {
      if (!window.__sbRedirectingToLogin && window.location.pathname !== "/login") {
        window.__sbRedirectingToLogin = true;
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  }
);

// ----- Portfolios CRUD (not portfolio-scoped) ---------------------------------

export const fetchPortfolios = () => api.get("/portfolios").then((r) => r.data);
export const createPortfolio = (data) => api.post("/portfolios", data).then((r) => r.data);
export const updatePortfolio = (id, data) => api.patch(`/portfolios/${id}`, data).then((r) => r.data);
export const deletePortfolio = (id) => api.delete(`/portfolios/${id}`).then((r) => r.data);
export const fetchOverview = (currency = "USD") =>
  api.get("/portfolios/overview", { params: { currency } }).then((r) => r.data);

// ----- Everything below is portfolio-scoped via the interceptor ---------------

export const fetchSummary = (currency = "USD") =>
  api.get(`/portfolio/summary`, { params: { currency } }).then((r) => r.data);
export const fetchHoldings = (currency = "USD") =>
  api.get(`/portfolio/holdings`, { params: { currency } }).then((r) => r.data);
export const fetchAllHoldings = (currency = "USD") =>
  api.get(`/portfolio/holdings`, { params: { currency, include_closed: true } }).then((r) => r.data);
export const fetchTransactions = () => api.get("/portfolio/transactions").then((r) => r.data);
export const fetchPerformance = (currency = "USD", period = "all") =>
  api.get(`/portfolio/performance`, { params: { currency, period } }).then((r) => r.data);
export const fetchBenchmarks = (benchmarks = [], period = "all") =>
  benchmarks.length
    ? api.get(`/portfolio/benchmarks`, { params: { benchmarks: benchmarks.join(","), period } }).then((r) => r.data)
    : Promise.resolve({});
export const fetchFxRate = (pair = "USDCZK") =>
  api.get(`/market/fx/${pair}`).then((r) => r.data);
export const createTransaction = (data) => api.post("/portfolio/transactions", data).then((r) => r.data);
export const deleteTransaction = (id) => api.delete(`/portfolio/transactions/${id}`).then((r) => r.data);
export const importCSV = (file, replace = false) => {
  const form = new FormData();
  form.append("file", file);
  return api.post(`/portfolio/import-csv`, form, { params: { replace } }).then((r) => r.data);
};
export const clearAllTransactions = () =>
  api.delete("/portfolio/transactions").then((r) => r.data);
export const fetchQuote = (ticker) => api.get(`/market/quote/${ticker}`).then((r) => r.data);
export const fetchHistory = (ticker, period = "1y") =>
  api.get(`/market/history/${ticker}`, { params: { period } }).then((r) => r.data);
export const fetchFundamentals = (ticker) =>
  api.get(`/market/fundamentals/${ticker}`).then((r) => r.data);
export const searchTickers = (q, limit = 10) =>
  api.get(`/market/search`, { params: { q, limit } }).then((r) => r.data);

// ----- Shibui-backed stock data (SEC filings, insiders, earnings, etc.) ----
export const fetchShibuiFilings = (ticker, formTypes, years = 2) =>
  api
    .get(`/market/shibui/filings/${ticker}`, {
      params: { years, ...(formTypes ? { form_types: formTypes } : {}) },
    })
    .then((r) => r.data);
export const fetchShibuiInsiders = (ticker, months = 12) =>
  api.get(`/market/shibui/insiders/${ticker}`, { params: { months } }).then((r) => r.data);
export const fetchShibuiActivistStakes = (ticker) =>
  api.get(`/market/shibui/activist-stakes/${ticker}`).then((r) => r.data);
export const fetchShibuiStrategicInvestors = (ticker) =>
  api.get(`/market/shibui/strategic-investors/${ticker}`).then((r) => r.data);
export const fetchShibuiOwnershipDetail = (cik, accession, doc) =>
  api.get(`/market/shibui/ownership-detail`, { params: { cik, accession, doc } }).then((r) => r.data);
export const fetchShibuiEarningsRecap = (ticker) =>
  api.get(`/market/shibui/earnings-recap/${ticker}`).then((r) => r.data);
export const fetchShibuiValuationHistory = (ticker, years = 10) =>
  api.get(`/market/shibui/valuation-history/${ticker}`, { params: { years } }).then((r) => r.data);
export const fetchPoliticianTrades = (ticker) =>
  api.get(`/market/politician-trades/${ticker}`).then((r) => r.data);

// ----- Watchlists (global, not portfolio-scoped) ----------------------------
export const fetchWatchlists = () => api.get("/watchlists").then((r) => r.data);
export const createWatchlist = (data) =>
  api.post("/watchlists", data).then((r) => r.data);
export const updateWatchlist = (id, data) =>
  api.patch(`/watchlists/${id}`, data).then((r) => r.data);
export const deleteWatchlist = (id) =>
  api.delete(`/watchlists/${id}`).then((r) => r.data);
export const addWatchlistItem = (watchlistId, ticker, note = null) =>
  api.post(`/watchlists/${watchlistId}/items`, { ticker, note }).then((r) => r.data);
export const removeWatchlistItem = (watchlistId, itemId) =>
  api.delete(`/watchlists/${watchlistId}/items/${itemId}`).then((r) => r.data);
export const fetchDividends = () => api.get("/portfolio/dividends").then((r) => r.data);
export const fetchDividendForecast = () =>
  api.get("/portfolio/dividends/forecast").then((r) => r.data);
export const fetchDividendGrowth = () =>
  api.get("/portfolio/dividends/growth").then((r) => r.data);
export const fetchStockDividendGrowth = (ticker) =>
  api.get(`/market/dividend-growth/${ticker}`).then((r) => r.data);
export const fetchTaxReport = (year) =>
  api.get(`/analytics/tax-report`, { params: year ? { year } : {} }).then((r) => r.data);
export const fetchRiskMetrics = (period = "1y", benchmarkId = null) =>
  api
    .get(`/analytics/risk-metrics`, {
      params: { period, ...(benchmarkId != null ? { benchmark_id: benchmarkId } : {}) },
    })
    .then((r) => r.data);
export const fetchBenchmarkCatalog = () =>
  api.get(`/analytics/benchmarks`).then((r) => r.data);
export const createBenchmark = (data) =>
  api.post(`/analytics/benchmarks`, data).then((r) => r.data);
export const updateBenchmark = (id, data) =>
  api.patch(`/analytics/benchmarks/${id}`, data).then((r) => r.data);
export const deleteBenchmark = (id) =>
  api.delete(`/analytics/benchmarks/${id}`).then((r) => r.data);
export const fetchBenchmarkComparison = (period = "1y", benchmarkId = null) =>
  api
    .get(`/analytics/benchmarks/comparison`, {
      params: { period, ...(benchmarkId != null ? { benchmark_id: benchmarkId } : {}) },
    })
    .then((r) => r.data);
export const fetchSectorBreakdown = (currency = "USD") =>
  api.get(`/analytics/sector-breakdown`, { params: { currency } }).then((r) => r.data);
export const fetchCorrelation = (period = "1y") =>
  api.get(`/analytics/correlation`, { params: { period } }).then((r) => r.data);
export const fetchMovers = (period = "1d") =>
  api.get(`/portfolio/movers`, { params: { period } }).then((r) => r.data);
export const fetchEarnings = () =>
  api.get("/portfolio/earnings").then((r) => r.data);
export const fetchHeatmap = (period = "1d") =>
  api.get(`/portfolio/heatmap`, { params: { period } }).then((r) => r.data);
export const fetchInsiderBuys = () =>
  api.get("/portfolio/insider-buys").then((r) => r.data);

// ----- Stock Screener ------------------------------------------------------
export const fetchScreener = (params = {}) =>
  api.get(`/market/screener`, { params }).then((r) => r.data);

export const fetchT212Status = () => api.get("/broker/trading212/status").then((r) => r.data);
export const connectT212 = (apiKey, apiSecret) =>
  api.post("/broker/trading212/connect", { api_key: apiKey, api_secret: apiSecret }).then((r) => r.data);
export const disconnectT212 = () => api.delete("/broker/trading212/connect").then((r) => r.data);
export const syncT212 = () => api.post("/broker/trading212/sync").then((r) => r.data);
export const setT212AutoSync = (enabled) =>
  api.post("/broker/trading212/auto-sync", { enabled }).then((r) => r.data);

export const fetchCombinedSummary = (currency = "USD") =>
  api.get(`/portfolio/combined-summary`, { params: { currency } }).then((r) => r.data);

// ----- IBKR broker --------------------------------------------------------
export const fetchIBKRStatus = () => api.get("/broker/ibkr/status").then((r) => r.data);
export const connectIBKR = (flexToken, queryId) =>
  api.post("/broker/ibkr/connect", { flex_token: flexToken, query_id: queryId }).then((r) => r.data);
export const disconnectIBKR = () => api.delete("/broker/ibkr/connect").then((r) => r.data);
export const syncIBKR = () => api.post("/broker/ibkr/sync").then((r) => r.data);
export const setIBKRAutoSync = (enabled) =>
  api.post("/broker/ibkr/auto-sync", { enabled }).then((r) => r.data);
export const fetchIBKRBalance = () => api.get("/broker/ibkr/balance").then((r) => r.data);

// ----- Global settings (not portfolio-scoped) ---------------------------------

export const fetchSyncSchedule = () => api.get("/settings/sync-schedule").then((r) => r.data);
export const updateSyncSchedule = (data) => api.put("/settings/sync-schedule", data).then((r) => r.data);

// ----- Options (portfolio-scoped) -----------------------------------------
export const fetchOptionsTrades = () => api.get("/options/trades").then((r) => r.data);
export const fetchOptionsSummary = () => api.get("/options/summary").then((r) => r.data);
export const fetchOptionsByUnderlying = () => api.get("/options/by-underlying").then((r) => r.data);
export const fetchOptionsCalendar = (period) =>
  api.get("/options/calendar", { params: period ? { period } : {} }).then((r) => r.data);

// ----- Polymarket broker ---------------------------------------------------
export const fetchPolymarketStatus = () => api.get("/broker/polymarket/status").then((r) => r.data);
export const connectPolymarket = (address) =>
  api.post("/broker/polymarket/connect", { address }).then((r) => r.data);
export const disconnectPolymarket = () => api.delete("/broker/polymarket/connect").then((r) => r.data);
export const syncPolymarket = () => api.post("/broker/polymarket/sync").then((r) => r.data);

// ----- Polymarket positions (portfolio-scoped) -----------------------------
export const fetchPolymarketPositions = () => api.get("/polymarket/positions").then((r) => r.data.positions);
export const fetchPolymarketSummary = () => api.get("/polymarket/summary").then((r) => r.data);

// ----- AI assistant (DeepSeek) ---------------------------------------------
export const fetchAssistantConfig = () => api.get("/assistant/config").then((r) => r.data);
export const saveAssistantConfig = (apiKey, model) =>
  api.put("/assistant/config", { api_key: apiKey, model }).then((r) => r.data);
export const deleteAssistantConfig = () => api.delete("/assistant/config").then((r) => r.data);
export const sendAssistantMessage = (messages) =>
  api.post("/assistant/chat", { messages }).then((r) => r.data);

// ----- Discord Webhook -------------------------------------------------------
export const fetchDiscordWebhook = () => api.get("/discord/webhook").then((r) => r.data);
export const createDiscordWebhook = (data) => api.post("/discord/webhook", data).then((r) => r.data);
export const updateDiscordWebhook = (data) => api.patch("/discord/webhook", data).then((r) => r.data);
export const deleteDiscordWebhook = () => api.delete("/discord/webhook").then((r) => r.data);
export const testDiscordWebhook = (message = null) =>
  api.post("/discord/webhook/test", { message }).then((r) => r.data);

// ----- Trade Notes -----------------------------------------------------------
export const fetchTradeNote = (transactionId) =>
  api.get(`/notes/transaction/${transactionId}`).then((r) => r.data);
export const upsertTradeNote = (transactionId, data) =>
  api.put(`/notes/transaction/${transactionId}`, data).then((r) => r.data);
export const deleteTradeNote = (transactionId) =>
  api.delete(`/notes/transaction/${transactionId}`).then((r) => r.data);
export const fetchAllTradeNotes = () => api.get("/notes/all").then((r) => r.data);

// ----- Cash (portfolio-scoped) ------------------------------------------------
export const fetchCash = () => api.get("/cash").then((r) => r.data);
export const createCash = (data) => api.post("/cash", data).then((r) => r.data);
export const updateCash = (id, data) => api.put(`/cash/${id}`, data).then((r) => r.data);
export const deleteCash = (id) => api.delete(`/cash/${id}`).then((r) => r.data);
export const fetchCashBalance = (currency = "USD") =>
  api.get("/cash/balance", { params: { currency } }).then((r) => r.data);
export const fetchCashHistory = (currency = "USD") =>
  api.get("/cash/history", { params: { currency } }).then((r) => r.data);
export const fetchInterestRates = () => api.get("/cash/interest-rates").then((r) => r.data);
export const saveInterestRates = (rates) =>
  api.put("/cash/interest-rates", { rates }).then((r) => r.data);

// ----- Price alerts (portfolio-scoped) ---------------------------------------
export const fetchAlerts = () => api.get("/alerts").then((r) => r.data);
export const createAlert = (data) => api.post("/alerts", data).then((r) => r.data);
export const updateAlert = (id, data) => api.patch(`/alerts/${id}`, data).then((r) => r.data);
export const deleteAlert = (id) => api.delete(`/alerts/${id}`).then((r) => r.data);
export const checkAlerts = () => api.post("/alerts/check").then((r) => r.data);
