import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrency, usePortfolio } from "../App";
import {
  fetchSummary,
  fetchHoldings,
  fetchAllHoldings,
  fetchPerformance,
  fetchMovers,
  fetchEarnings,
  fetchSectorBreakdown,
  fetchHeatmap,
  fetchFundamentals,
  fetchHistory,
  fetchTransactions,
  fetchAllTradeNotes,
  fetchWatchlists,
  fetchDividends,
  fetchDividendForecast,
  fetchBenchmarkCatalog,
  fetchRiskMetrics,
  fetchBenchmarkComparison,
  fetchCorrelation,
  fetchT212Status,
} from "../api";

// ---------------------------------------------------------------------------
// AutoLoad — background data prefetcher
// ---------------------------------------------------------------------------
//
// Walks every page's queries in a fixed priority order and warms the React
// Query cache so that navigating to a page is instant — the data is already
// there. It deliberately reuses each page's EXACT queryKey + fetch function,
// so a prefetched entry is the same cache entry the page reads (no duplicate
// request, no key mismatch).
//
// Order (mirrors the request):
//   1. Dashboard   2. Allocation
//   3. Stock detail for every open holding, biggest market value first
//   4. Transactions   5. Search (nothing to preload) + Watchlists
//   …then the rest of the shared sidebar (Dividends, Analytics) → Settings.
//
// Runs strictly sequentially with a small gap between requests. yfinance is
// slow and aggressively rate-limited, and `fundamentals` is by far the
// heaviest endpoint, so firing everything in parallel would saturate the
// backend and risk Yahoo throttling. The backend TTL cache means a reload
// re-serves most of this instantly rather than re-hitting Yahoo.

const MIN = 60_000;
// Mirror the staleTime each page declares so a freshly-warmed query isn't
// thrown away and refetched the instant the user lands on the page.
const FUND_STALE = 5 * MIN;       // Stock.jsx / InsiderVolumeChart
const DEFAULT_STALE = MIN;
// Gap between requests — yields the event loop to any user-initiated fetch and
// keeps the single-threaded yfinance backend from being hammered.
const GAP_MS = 200;
// Let the page the user actually landed on issue its own fetches first.
const STARTUP_DELAY_MS = 1500;
const BACKGROUND_REQUEST = Object.freeze({ suppressEntitlementPrompt: true });

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export default function AutoLoad() {
  const qc = useQueryClient();
  const { currency } = useCurrency();
  const { ready, currentId } = usePortfolio();
  // Monotonic run token: bumping it aborts any in-flight run (on unmount or
  // when currency / portfolio changes), so old and new sweeps never interleave.
  const runRef = useRef(0);

  useEffect(() => {
    if (!ready || currentId == null) return;

    const runId = ++runRef.current;
    const alive = () => runRef.current === runId;

    // Warm one query. Shares the page's key/fn so the cache entry is identical.
    // prefetchQuery is a no-op when the entry is already fresh, and swallows
    // errors so one bad ticker never aborts the sweep.
    const warm = (queryKey, queryFn, staleTime = DEFAULT_STALE) =>
      qc.prefetchQuery({ queryKey, queryFn, staleTime }).catch(() => {});

    // Run a list of [key, fn, staleTime?] tasks sequentially, bailing the
    // moment this run is superseded.
    const runTasks = async (tasks) => {
      for (const [key, fn, staleTime] of tasks) {
        if (!alive()) return false;
        await warm(key, fn, staleTime);
        await sleep(GAP_MS);
      }
      return alive();
    };

    (async () => {
      await sleep(STARTUP_DELAY_MS);
      if (!alive()) return;

      // 1) Dashboard
      if (!(await runTasks([
        [["summary", currency], () => fetchSummary(currency)],
        [["holdings", currency], () => fetchHoldings(currency)],
        // Dashboard's default period state is "All" (raw); it lowercases only
        // for the request, so the cache key keeps the capitalised value.
        [["performance", currency, "All"], () => fetchPerformance(currency, "all")],
        [["movers", "1d"], () => fetchMovers("1d", BACKGROUND_REQUEST)],
        [["earnings"], () => fetchEarnings(BACKGROUND_REQUEST)],
        [["sector-breakdown", currency], () => fetchSectorBreakdown(currency, BACKGROUND_REQUEST)],
        [["heatmap", "1d"], () => fetchHeatmap("1d", BACKGROUND_REQUEST)],
      ]))) return;

      // 2) Allocation (sector-breakdown already warmed above)
      if (!(await runTasks([
        [["holdings-all", currency], () => fetchAllHoldings(currency)],
      ]))) return;

      // 3) Stock detail for every open holding, biggest market value first.
      //    Read from the holdings entry we just warmed; each stock page needs
      //    both fundamentals and 1y price history (InsiderVolumeChart).
      const holdings = qc.getQueryData(["holdings", currency]) || [];
      const ordered = [...holdings]
        .filter((h) => h && h.ticker)
        .sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0));
      for (const h of ordered) {
        // The Stock page / TickerLink always upper-cases the symbol in its
        // query keys, so mirror that here to hit the same cache entry.
        const t = String(h.ticker).toUpperCase();
        if (!(await runTasks([
          [["fundamentals", t], () => fetchFundamentals(t, BACKGROUND_REQUEST), FUND_STALE],
          [["history", t, "1y"], () => fetchHistory(t, "1y"), FUND_STALE],
        ]))) return;
      }

      // 4) Transactions
      // 5) Search has no preloadable default (results depend on user input);
      //    warm the Watchlists list instead — it backs both Search-style add
      //    flows and the Watchlists page.
      if (!(await runTasks([
        [["transactions"], () => fetchTransactions()],
        [["trade-notes-all"], () => fetchAllTradeNotes()],
        [["watchlists"], () => fetchWatchlists()],
      ]))) return;

      // …rest of the shared sidebar in order: Dividends → Analytics.
      if (!(await runTasks([
        [["dividends"], () => fetchDividends()],
        [["dividends-forecast"], () => fetchDividendForecast(BACKGROUND_REQUEST)],
      ]))) return;

      // Analytics: resolve the default benchmark the page auto-selects so the
      // prefetched keys (which include the benchmark id) match exactly.
      if (!alive()) return;
      const catalog = await qc
        .fetchQuery({
          queryKey: ["benchmark-catalog"],
          queryFn: fetchBenchmarkCatalog,
          staleTime: FUND_STALE,
        })
        .catch(() => []);
      if (!alive()) return;
      const list = catalog || [];
      const def =
        list.find((b) => b.is_default) ||
        list.find((b) => b.is_preset && b.ticker === "^GSPC") ||
        list[0];
      const benchId = def ? def.id : null;
      const P = "1Y"; // Analytics' default period state (key uses raw, fn lowercases)
      if (!(await runTasks([
        [["risk-metrics", P, benchId], () => fetchRiskMetrics(P.toLowerCase(), benchId, BACKGROUND_REQUEST)],
        [["benchmark-comparison", P, benchId], () => fetchBenchmarkComparison(P.toLowerCase(), benchId, BACKGROUND_REQUEST)],
        [["sector-breakdown", "USD"], () => fetchSectorBreakdown("USD", BACKGROUND_REQUEST)],
        [["correlation", P], () => fetchCorrelation(P.toLowerCase(), BACKGROUND_REQUEST)],
      ]))) return;

      // Settings (T212 status, keyed by the active portfolio id). Local-only
      // pages fetch on navigation so their API helpers never enter cloud builds.
      await runTasks([
        [["t212-status", currentId], () => fetchT212Status()],
      ]);
    })();

    // Abort this run if currency / portfolio changes or the app unmounts.
    return () => {
      runRef.current++;
    };
  }, [qc, currency, ready, currentId]);

  return null;
}
