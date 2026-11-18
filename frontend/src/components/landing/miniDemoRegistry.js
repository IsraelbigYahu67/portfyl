import { lazy } from "react";

export const MINI_DEMO_KINDS = Object.freeze(["allocation", "stock", "performance", "dividends", "portfolios"]);

// Each live demo is its own chunk (Recharts, the app's components and the
// sample data live there), so the landing page's static graph stays small.
// Created once at module level: a lazy component made during render would
// be a new type, and remount, on every render.
export const MINI_DEMOS = Object.freeze({
  allocation: lazy(() => import("./minidemo/MiniAllocation.jsx")),
  stock: lazy(() => import("./minidemo/MiniStock.jsx")),
  performance: lazy(() => import("./minidemo/MiniPerformance.jsx")),
  dividends: lazy(() => import("./minidemo/MiniDividends.jsx")),
  portfolios: lazy(() => import("./minidemo/MiniPortfolios.jsx")),
});

// Where the full demo page of each feature lives (until the public /demo is
// retired, plan wave 3).
export const DEMO_HREFS = Object.freeze({
  allocation: "/demo/allocation",
  stock: "/demo/stock/MSFT",
  performance: "/demo/analytics",
  dividends: "/demo/dividends",
  portfolios: "/demo",
});
