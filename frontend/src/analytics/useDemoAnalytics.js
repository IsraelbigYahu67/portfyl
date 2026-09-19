import { useEffect, useRef } from "react";
import { useAnalytics } from "./AnalyticsProvider";
import { ANALYTICS_EVENTS } from "./eventContract";

// Shared with Welcome.jsx's same-tab CTA transition so the landing page's
// demo_started capture and the demo's own "direct entry" fallback dedupe
// against the same captureOnce key instead of double-firing.
export const DEMO_SESSION_SCOPE = "public-demo-session";

const NON_STOCK_PAGES = new Set(["overview", "allocation", "analytics", "dividends"]);
const DEMO_SYMBOLS = new Set(["VUAA", "MSFT", "JPM", "JNJ", "XOM", "PG", "AMZN", "CAT", "NEE", "PLD"]);
const MAX_DISTINCT_PAGES = 5;

/**
 * Instruments the public demo's route-level analytics: a session-scoped
 * demo_started fallback (for direct/new-tab entry, deduped against the
 * landing page's own capture), one demo_page_viewed/demo_stock_viewed per
 * distinct page visited, and demo_activation_reached exactly once per
 * session when either three distinct analysis pages have been viewed or a
 * stock detail is viewed after at least one other demo page. Visited-page
 * state lives only in this hook's refs -- never written to browser storage,
 * and never derived from real portfolio data.
 */
export function useDemoAnalytics({ page, symbol, language }) {
  const { captureOnce } = useAnalytics();
  const visitedPagesRef = useRef(new Set());
  const seenViewsRef = useRef(new Set());
  const hasNonStockPageRef = useRef(false);
  const activatedRef = useRef(false);

  useEffect(() => {
    captureOnce(DEMO_SESSION_SCOPE, ANALYTICS_EVENTS.DEMO_STARTED, { language, entry_point: "direct" });
    // Intentionally runs once per mounted DemoApp session, not per route.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!page) return;
    const isStock = page === "stock";
    if (isStock && !DEMO_SYMBOLS.has(symbol)) return; // invalid stock symbol: no event at all

    const viewKey = isStock ? `stock:${symbol}` : page;
    if (!seenViewsRef.current.has(viewKey)) {
      seenViewsRef.current.add(viewKey);
      if (isStock) {
        captureOnce(`demo-view:${viewKey}`, ANALYTICS_EVENTS.DEMO_STOCK_VIEWED, { demo_symbol: symbol });
      } else {
        captureOnce(`demo-view:${viewKey}`, ANALYTICS_EVENTS.DEMO_PAGE_VIEWED, { demo_page: page, language });
      }
    }

    if (NON_STOCK_PAGES.has(page)) {
      visitedPagesRef.current.add(page);
      hasNonStockPageRef.current = true;
    }

    if (activatedRef.current) return;
    const distinctNonStock = visitedPagesRef.current.size;
    if (distinctNonStock >= 3) {
      activatedRef.current = true;
      captureOnce(DEMO_SESSION_SCOPE, ANALYTICS_EVENTS.DEMO_ACTIVATION_REACHED, {
        activation_path: "three_pages",
        distinct_demo_pages: Math.min(distinctNonStock, MAX_DISTINCT_PAGES),
      });
    } else if (isStock && hasNonStockPageRef.current) {
      activatedRef.current = true;
      captureOnce(DEMO_SESSION_SCOPE, ANALYTICS_EVENTS.DEMO_ACTIVATION_REACHED, {
        activation_path: "stock_after_page",
        distinct_demo_pages: Math.min(distinctNonStock + 1, MAX_DISTINCT_PAGES),
      });
    }
  }, [page, symbol, language, captureOnce]);
}
