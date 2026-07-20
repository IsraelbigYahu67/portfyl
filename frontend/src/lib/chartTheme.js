// Shared chart color tokens — every recharts consumer imports from here instead
// of hardcoding hex, so chart colors follow the active theme/accent automatically
// (SVG fill/stroke accept CSS var() strings directly; DividendCalendar.jsx already
// proved this pattern works in this codebase).
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

export const AXIS_TICK = { fill: "var(--muted, #8A93B3)", fontSize: 11 };
export const GRID_STROKE = "var(--hairline, #2A3245)";
export const TOOLTIP_STYLE = {
  background: "var(--surface-card-elevated, #1F2435)",
  border: "1px solid var(--hairline, #2A3245)",
  borderRadius: 8,
  color: "var(--ink, #DAE2FD)",
};
