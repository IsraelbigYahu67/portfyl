import { formatMoney, formatPercent } from "../../lib/format";

const SIZES = {
  sm: "financial-meta px-1.5 py-0.5 gap-1",
  md: "text-xs px-2 py-1 gap-1.5",
  lg: "text-sm px-2.5 py-1 gap-1.5",
};

export function DeltaPill({ value = null, pct = null, currency = "USD", size = "md", className = "" }) {
  if (value == null && pct == null) return null;
  const positive = (value ?? pct ?? 0) >= 0;
  const tone = positive
    ? "bg-gain/10 text-gain"
    : "bg-loss/10 text-loss";
  // The ▲/▼ glyph is aria-hidden (decorative), so the sign must also be
  // spelled out in the visible text -- otherwise a screen reader gets no
  // gain/loss signal at all, only color.
  const sign = positive ? "+" : "−";
  return (
    <span className={`inline-flex items-center rounded-full font-sans font-semibold tabular-nums ${SIZES[size]} ${tone} ${className}`}>
      <span aria-hidden="true">{positive ? "▲" : "▼"}</span>
      {value != null && <span>{sign}{formatMoney(Math.abs(value), currency)}</span>}
      {pct != null && <span>({formatPercent(pct)})</span>}
    </span>
  );
}
