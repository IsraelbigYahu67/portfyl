import { formatMoney } from "../lib/format";

export default function AllocationBarList({ holdings, currency }) {
  const open = (holdings || [])
    .filter((h) => !h.closed && h.market_value > 0)
    .sort((a, b) => b.weight - a.weight);
  if (!open.length) return null;

  return (
    <ul className="space-y-2" aria-label="Full allocation breakdown">
      {open.map((h) => (
        <li key={h.ticker} className="flex items-center gap-3">
          <span className="w-16 font-mono text-xs font-bold shrink-0">{h.ticker}</span>
          <div className="flex-1 bg-surface-hover rounded-full h-1.5">
            <div className="bg-brand rounded-full h-1.5" style={{ width: `${Math.min(100, h.weight)}%` }} />
          </div>
          <span className="w-20 text-right text-xs tabular-nums text-muted shrink-0">
            {formatMoney(h.market_value, currency)}
          </span>
          <span className="w-12 text-right text-xs tabular-nums text-muted shrink-0">{h.weight}%</span>
        </li>
      ))}
    </ul>
  );
}
