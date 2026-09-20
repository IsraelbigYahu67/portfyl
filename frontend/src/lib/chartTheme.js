// Shared chart color tokens — every recharts consumer imports from here instead
// of hardcoding hex, so chart colors follow the active theme/accent automatically
// (SVG fill/stroke accept CSS var() strings directly).
export const CATEGORICAL = [
  "var(--chart-1, #3B82F6)",
  "var(--chart-2, #4EDEA3)",
  "var(--chart-3, #FFB95F)",
  "var(--chart-4, #A78BFA)",
  "var(--chart-5, #38BDF8)",
  "var(--chart-6, #FB7185)",
  "var(--chart-7, #FACC15)",
  "var(--chart-8, #64748B)",
];

export const NEUTRAL_COLOR = "var(--chart-8, #64748B)";
export const GAIN_COLOR = "var(--gain, #34D399)";
export const LOSS_COLOR = "var(--loss, #F87171)";

// Deprecated: fontSize 11 is below the 12px chart-label floor. Still
// exported for pages not yet migrated (Analytics.jsx, StockDetail.jsx,
// Dividends.jsx -- readability plan Tasks 4-6). New/updated charts use
// AXIS_TICK_STYLE below instead.
export const AXIS_TICK = { fill: "var(--muted, #8A93B3)", fontSize: 11 };

export const AXIS_TICK_STYLE = { fill: "var(--muted, #8A93B3)", fontSize: 12 };
export const LEGEND_TEXT_STYLE = { fontSize: 12, color: "var(--muted, #8A93B3)" };

export const GRID_STROKE = "var(--hairline, #2A3245)";
export const TOOLTIP_STYLE = {
  background: "var(--surface-card-elevated, #1F2435)",
  border: "1px solid var(--hairline, #2A3245)",
  borderRadius: 8,
  color: "var(--ink, #DAE2FD)",
};

// Color + stroke-dasharray pairs for multi-series charts (e.g. benchmark
// comparison lines) so adjacent series are distinguishable without relying
// on hue alone. Index 0 (solid) is reserved for the primary/portfolio
// series; additional series cycle through 1+.
export const SERIES_STYLES = [
  { color: "var(--chart-1, #3B82F6)", strokeDasharray: undefined },
  { color: "var(--chart-4, #A78BFA)", strokeDasharray: "6 3" },
  { color: "var(--chart-5, #38BDF8)", strokeDasharray: "2 3" },
  { color: "var(--chart-6, #FB7185)", strokeDasharray: "8 3 2 3" },
];
