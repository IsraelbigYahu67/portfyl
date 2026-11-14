import axios from "axios";

// Single source of truth for the active portfolio id, mirrored from React state
// by PortfolioProvider via setActivePortfolioId(). The axios interceptor below
// reads it on every request so we never have to thread portfolio_id through call
// sites — every page just calls the same fetch helpers.
//
// Portfolio ids are UUID strings end-to-end (backend Tasks 5-8 replaced the
// integer public identifiers). Never coerce this with Number()/parseInt() —
// that silently turns a UUID into NaN.
let _activePortfolioId = null;

export function setActivePortfolioId(id) {
  _activePortfolioId = id == null ? null : String(id);
}

export function getActivePortfolioId() {
  return _activePortfolioId;
}

// Workspace + CSRF context, set once AuthProvider has exchanged a Firebase ID
// token (or resolved an existing session) for a Portfyl session. Held in module
// state rather than localStorage — the design spec is explicit that the CSRF
// token is memory-only and never persisted.
let _requestContext = { workspaceId: null, csrfToken: null };

export function configureRequestContext({ workspaceId = null, csrfToken = null } = {}) {
  _requestContext = { workspaceId: workspaceId ?? null, csrfToken: csrfToken ?? null };
}

export function getRequestContext() {
  return _requestContext;
}

export const api = axios.create({ baseURL: "/api" });

// Endpoints that are NOT portfolio-scoped — these must not receive portfolio_id
// or they'd 404 / mis-route.
const PORTFOLIO_AGNOSTIC_PREFIXES = ["/portfolios", "/market", "/watchlists", "/settings", "/auth", "/capabilities", "/test-plans", "/billing", "/broker-requests"];

function isPortfolioAgnostic(url) {
  if (!url) return false;
  return PORTFOLIO_AGNOSTIC_PREFIXES.some((p) => url === p || url.startsWith(p + "/") || url.startsWith(p + "?"));
}

// State-changing requests need X-CSRF-Token (backend's csrf_guard checks it on
// every mutating /api route); every request needs X-Workspace-ID once a
// workspace has been resolved, GETs included, so tenancy.get_request_context can
// select the right workspace.
const MUTATING_METHODS = new Set(["post", "put", "patch", "delete"]);

// Exported (and registered below) rather than kept as an inline arrow function
// so tests can drive the exact same interceptor logic without spinning up a
// real HTTP call — see api.auth.test.js.
export function applyRequestInterceptors(config) {
  const method = (config.method || "get").toLowerCase();

  if (_activePortfolioId != null && !isPortfolioAgnostic(config.url)) {
    config.params = { ...(config.params || {}), portfolio_id: _activePortfolioId };
  }

  if (_requestContext.workspaceId) {
    config.headers = { ...(config.headers || {}), "X-Workspace-ID": _requestContext.workspaceId };
  }

  if (_requestContext.csrfToken && MUTATING_METHODS.has(method)) {
    config.headers = { ...(config.headers || {}), "X-CSRF-Token": _requestContext.csrfToken };
  }

  return config;
}

api.interceptors.request.use(applyRequestInterceptors);

// Pages reachable while signed out — a 401 here means "not logged in yet",
// not "session expired", so the response interceptor below must not bounce
// the user away from them.
const PUBLIC_AUTH_PATHS = ["/login", "/register", "/verify-email", "/forgot-password"];

function isPublicAuthPath(pathname) {
  return PUBLIC_AUTH_PATHS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

// When the session is missing/expired the API returns 401; bounce the user to
// the login page (same-origin in prod; proxied in dev), unless they're already
// on one of the public auth pages. Guarded so a burst of 401s triggers a
// single navigation.
// Entitlement denials (403 plan_upgrade_required etc.) raise a window event the
// UpgradePrompt listens for.
//
// A 403 csrf_failed means the in-memory CSRF token no longer matches the session
// (e.g. a rolling deploy, or a token issued before the session-bound scheme).
// AuthProvider registers a handler that re-reads the token from /auth/me; the
// failed request is then replayed exactly once (config._csrfRetried guards the
// loop).
let _csrfRefreshHandler = null;
let _csrfRefreshInFlight = null;

export function setCsrfRefreshHandler(fn) {
  _csrfRefreshHandler = typeof fn === "function" ? fn : null;
}

function refreshCsrfOnce() {
  // Parallel failures share one /auth/me round trip.
  if (!_csrfRefreshInFlight) {
    _csrfRefreshInFlight = Promise.resolve()
      .then(() => _csrfRefreshHandler())
      .finally(() => {
        _csrfRefreshInFlight = null;
      });
  }
  return _csrfRefreshInFlight;
}

export async function handleResponseError(error) {
  const config = error?.config;
  if (
    error?.response?.status === 403
    && error.response.data?.code === "csrf_failed"
    && _csrfRefreshHandler
    && config
    && !config._csrfRetried
  ) {
    config._csrfRetried = true;
    let refreshed = false;
    try {
      await refreshCsrfOnce();
      refreshed = true;
    } catch {
      // Could not re-read the token (offline, or the session is gone and the
      // 401 path below already took over); surface the original 403.
    }
    if (refreshed) {
      // The request interceptor stamps the freshly configured token again.
      return api.request(config);
    }
  }
  if (error?.response?.status === 401 && typeof window !== "undefined") {
    if (!window.__sbRedirectingToLogin && !isPublicAuthPath(window.location.pathname)) {
      window.__sbRedirectingToLogin = true;
      window.location.assign("/login");
    }
  }
  return rejectWithEntitlementEvent(error);
}

function rejectWithEntitlementEvent(error) {
  const denial = error?.response?.data;
  if (
    error?.response?.status === 403
    && ["plan_upgrade_required", "quota_exceeded", "resource_read_only"].includes(denial?.code)
    && !error?.config?.suppressEntitlementPrompt
    && typeof window !== "undefined"
  ) {
    window.dispatchEvent(new CustomEvent("portfyl:entitlement-denied", { detail: denial }));
  }
  return Promise.reject(error);
}

api.interceptors.response.use((response) => response, handleResponseError);

// ----- Auth/session/account (not portfolio-scoped) --------------------------

export const fetchMe = () => api.get("/auth/me").then((r) => r.data);
export const exchangeSession = (idToken) =>
  api.post("/auth/session", { id_token: idToken }).then((r) => r.data);
export const logoutSession = () => api.post("/auth/logout").then((r) => r.data);
export const logoutAllSessions = () => api.post("/auth/logout-all").then((r) => r.data);
export const fetchCapabilities = () => api.get("/capabilities").then((r) => r.data);
export const fetchTestPlan = () => api.get("/test-plans").then((r) => r.data);
export const updateTestPlan = (plan) => api.put("/test-plans", { plan }).then((r) => r.data);

// Stripe Managed Payments (cloud). Checkout and the portal answer with a
// Stripe-hosted URL the browser navigates to.
export const fetchBillingStatus = () => api.get("/billing/status").then((r) => r.data);
export const startCheckout = (plan) =>
  api.post("/billing/checkout", { plan, accept_immediate_start: true }).then((r) => r.data);
export const confirmCheckout = (sessionId) =>
  api.post("/billing/checkout/confirm", { session_id: sessionId }).then((r) => r.data);
export const openBillingPortal = () => api.post("/billing/portal").then((r) => r.data);
// Books a switch between paid plans for the end of the paid period (no
// proration); choosing the current plan again withdraws a booked switch.
export const changePlan = (plan) => api.post("/billing/change-plan", { plan }).then((r) => r.data);

// "Notify me when my broker is supported": the name is free text the user typed;
// 201 = stored, 200 = already requested (case-insensitive), 422/429 = rejected.
export const requestBrokerSupport = (brokerName) =>
  api.post("/broker-requests", { broker_name: brokerName }).then((r) => r.data);

export const fetchDeletionStatus = () =>
  api.get("/settings/account/deletion").then((r) => r.data);

export const scheduleWorkspaceDeletion = (payload) =>
  api.post("/settings/account/deletion", payload).then((r) => r.data);

export const cancelWorkspaceDeletion = () =>
  api.delete("/settings/account/deletion").then((r) => r.data);

export function exportFilename(contentDisposition) {
  const match = String(contentDisposition || "").match(/filename="([^"]+)"/i);
  return match?.[1] || "portfyl-workspace-export.json";
}

export async function downloadWorkspaceExport() {
  const response = await api.get("/settings/account/export", {
    responseType: "blob",
  });
  return {
    blob: response.data,
    filename: exportFilename(response.headers?.["content-disposition"]),
  };
}

// ----- Portfolios CRUD (not portfolio-scoped) ---------------------------------

export const fetchPortfolios = () => api.get("/portfolios").then((r) => r.data);
export const createPortfolio = (data) => api.post("/portfolios", data).then((r) => r.data);
export const createDemoPortfolio = () => api.post("/portfolios/demo").then((r) => r.data);
export const createPendingImportPortfolio = () => api.post("/portfolios/pending-import").then((r) => r.data);
export const activatePortfolio = (id) => api.post(`/portfolios/${id}/activate`).then((r) => r.data);
export const updatePortfolio = (id, data) => api.patch(`/portfolios/${id}`, data).then((r) => r.data);
export const deletePortfolio = (id) => api.delete(`/portfolios/${id}`).then((r) => r.data);

// ----- Everything below is portfolio-scoped via the interceptor ---------------

export const fetchSummary = (currency = "USD") =>
  api.get(`/portfolio/summary`, { params: { currency } }).then((r) => r.data);
export const fetchHoldings = (currency = "USD") =>
  api.get(`/portfolio/holdings`, { params: { currency } }).then((r) => r.data);
export const fetchAllHoldings = (currency = "USD") =>
  api.get(`/portfolio/holdings`, { params: { currency, include_closed: true } }).then((r) => r.data);
export const fetchAllocationTargetDrift = (currency = "USD") =>
  api.get("/allocation-targets/drift", { params: { currency } }).then((r) => r.data);
export const saveAllocationTargets = (targets) =>
  api.put("/allocation-targets", { targets }).then((r) => r.data);
export const fetchTransactions = () => api.get("/portfolio/transactions").then((r) => r.data);
export const fetchTransactionsPage = ({ offset = 0, limit = 50, q = "", type = "", ticker = "", sort = "-date" } = {}) =>
  api
    .get("/portfolio/transactions/page", {
      params: {
        offset,
        limit,
        q: q || undefined,
        type: type || undefined,
        ticker: ticker || undefined,
        sort,
      },
    })
    .then((r) => r.data);
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
const importForm = (file) => {
  const form = new FormData();
  form.append("file", file);
  return form;
};
export const previewImportCSV = (file, replace = false) =>
  api.post("/portfolio/import-csv/preview", importForm(file), { params: { replace } }).then((r) => r.data);
export const commitImportCSV = (file, previewId, replace = false) =>
  api.post("/portfolio/import-csv/commit", importForm(file), {
    params: { preview_id: previewId, replace },
  }).then((r) => r.data);
export const fetchImportUndo = () => api.get("/portfolio/import-csv/undo").then((r) => r.data);
export const undoLastImport = () => api.post("/portfolio/import-csv/undo").then((r) => r.data);
export const clearAllTransactions = () =>
  api.delete("/portfolio/transactions").then((r) => r.data);
export const fetchQuote = (ticker) => api.get(`/market/quote/${ticker}`).then((r) => r.data);
export const fetchHistory = (ticker, period = "1y", requestConfig = {}) =>
  api.get(`/market/history/${ticker}`, { ...requestConfig, params: { ...(requestConfig.params || {}), period } }).then((r) => r.data);
export const fetchFundamentals = (ticker, requestConfig = {}) =>
  api.get(`/market/fundamentals/${ticker}`, requestConfig).then((r) => r.data);
export const fetchStockView = (ticker, view, requestConfig = {}) =>
  api
    .get(`/market/fundamentals/${ticker}`, {
      ...requestConfig,
      params: { ...(requestConfig.params || {}), view },
    })
    .then((r) => r.data);
export const searchTickers = (q, limit = 10) =>
  api.get(`/market/search`, { params: { q, limit } }).then((r) => r.data);

// ----- Shibui-backed stock data (insiders, earnings, etc.) -----------------
export const fetchShibuiInsiders = (ticker, months = 12) =>
  api.get(`/market/shibui/insiders/${ticker}`, { params: { months } }).then((r) => r.data);

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
export const fetchDividendForecast = (requestConfig = {}) =>
  api.get("/portfolio/dividends/forecast", requestConfig).then((r) => r.data);
export const fetchDividendGrowth = () =>
  api.get("/portfolio/dividends/growth").then((r) => r.data);
export const fetchStockDividendGrowth = (ticker) =>
  api.get(`/market/dividend-growth/${ticker}`).then((r) => r.data);
export const fetchRiskMetrics = (period = "1y", benchmarkId = null, requestConfig = {}) =>
  api
    .get(`/analytics/risk-metrics`, {
      ...requestConfig,
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
export const fetchBenchmarkComparison = (period = "1y", benchmarkId = null, requestConfig = {}) =>
  api
    .get(`/analytics/benchmarks/comparison`, {
      ...requestConfig,
      params: { period, ...(benchmarkId != null ? { benchmark_id: benchmarkId } : {}) },
    })
    .then((r) => r.data);
export const fetchSectorBreakdown = (currency = "USD", requestConfig = {}) =>
  api.get(`/analytics/sector-breakdown`, { ...requestConfig, params: { currency } }).then((r) => r.data);
export const fetchMovers = (period = "1d", currency = "USD", requestConfig = {}) =>
  api.get(`/portfolio/movers`, { ...requestConfig, params: { period, currency } }).then((r) => r.data);
export const fetchEarnings = (requestConfig = {}) =>
  api.get("/portfolio/earnings", requestConfig).then((r) => r.data);
export const fetchHeatmap = (period = "1d", requestConfig = {}) =>
  api.get(`/portfolio/heatmap`, { ...requestConfig, params: { period } }).then((r) => r.data);
export const fetchInsiderBuys = () =>
  api.get("/portfolio/insider-buys").then((r) => r.data);

export const fetchT212Status = () => api.get("/broker/trading212/status").then((r) => r.data);
export const connectT212 = (apiKey, apiSecret) =>
  api.post("/broker/trading212/connect", { api_key: apiKey, api_secret: apiSecret }).then((r) => r.data);
export const disconnectT212 = () => api.delete("/broker/trading212/connect").then((r) => r.data);
export const syncT212 = () => api.post("/broker/trading212/sync").then((r) => r.data);
export const setT212AutoSync = (enabled) =>
  api.post("/broker/trading212/auto-sync", { enabled }).then((r) => r.data);
export const fetchT212Positions = (currency = "USD") =>
  api.get("/broker/trading212/positions", { params: { currency } }).then((r) => r.data);
export const fetchT212HistoryStatus = () =>
  api.get("/broker/trading212/history-status").then((r) => r.data);
export const retryT212History = () =>
  api.post("/broker/trading212/history/retry").then((r) => r.data);

export const fetchCombinedSummary = (currency = "USD") =>
  api.get(`/portfolio/combined-summary`, { params: { currency } }).then((r) => r.data);

// ----- IBKR (Flex Web Service) ---------------------------------------------
export const fetchIBKRStatus = () => api.get("/broker/ibkr/status").then((r) => r.data);
export const connectIBKR = (flexToken, queryId) =>
  api.post("/broker/ibkr/connect", { flex_token: flexToken, query_id: queryId }).then((r) => r.data);
export const disconnectIBKR = () => api.delete("/broker/ibkr/connect").then((r) => r.data);
// The response's `ledger` reports the stock/ETF/dividend/cash import:
// { status: "imported" | "needs_review" | "deferred" | "sections_missing",
//   imported, already_present, errors }.
export const syncIBKR = () => api.post("/broker/ibkr/sync").then((r) => r.data);
export const setIBKRAutoSync = (enabled) =>
  api.post("/broker/ibkr/auto-sync", { enabled }).then((r) => r.data);

// ----- eToro (Public API, personal Read key) -----------------------------------
// Status carries `configured: false` when the server has no eToro app key.
export const fetchEtoroStatus = () => api.get("/broker/etoro/status").then((r) => r.data);
export const connectEtoro = (userKey) =>
  api.post("/broker/etoro/connect", { user_key: userKey }).then((r) => r.data);
// { status: "imported" | "needs_review", imported, already_present, errors, skipped_reasons }
export const syncEtoro = () => api.post("/broker/etoro/sync").then((r) => r.data);
export const setEtoroAutoSync = (enabled) =>
  api.post("/broker/etoro/auto-sync", { enabled }).then((r) => r.data);
export const disconnectEtoro = () => api.delete("/broker/etoro/connect").then((r) => r.data);

// ----- Global settings (not portfolio-scoped) ---------------------------------

export const fetchSyncSchedule = () => api.get("/settings/sync-schedule").then((r) => r.data);
export const updateSyncSchedule = (data) => api.put("/settings/sync-schedule", data).then((r) => r.data);



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
export const fetchCashReconciliation = (currency = "USD") =>
  api.get("/cash/reconciliation", { params: { currency } }).then((r) => r.data);
export const fetchInterestRates = () => api.get("/cash/interest-rates").then((r) => r.data);
export const saveInterestRates = (rates) =>
  api.put("/cash/interest-rates", { rates }).then((r) => r.data);

// ----- Price alerts (portfolio-scoped) ---------------------------------------
export const fetchAlerts = () => api.get("/alerts").then((r) => r.data);
export const createAlert = (data) => api.post("/alerts", data).then((r) => r.data);
export const updateAlert = (id, data) => api.patch(`/alerts/${id}`, data).then((r) => r.data);
export const deleteAlert = (id) => api.delete(`/alerts/${id}`).then((r) => r.data);
export const checkAlerts = () => api.post("/alerts/check").then((r) => r.data);
