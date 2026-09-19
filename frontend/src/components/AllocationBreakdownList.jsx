import { formatMoney } from "../lib/format";

// Full, unbounded composition list. The donut is deliberately capped (top 7 +
// Other); this list is the complete text/table equivalent so no value is only
// communicated by a chart segment.
export default function AllocationBreakdownList({ rows, currency }) {
  const sorted = [...(rows || [])].sort((a, b) => b.weight - a.weight);
  if (!sorted.length) return null;

  return (
    <ul className="space-y-2" aria-label="Full allocation breakdown">
      {sorted.map((row) => (
        <li key={row.name} className="flex items-center gap-3">
          <span className="w-24 font-mono text-xs font-bold shrink-0 truncate">{row.name}</span>
          <div className="flex-1 bg-surface-hover rounded-full h-1.5">
            <div className="bg-brand rounded-full h-1.5" style={{ width: `${Math.min(100, row.weight)}%` }} />
          </div>
          <span className="financial-data w-24 text-right shrink-0">
            {formatMoney(row.value, currency)}
          </span>
          <span className="financial-data w-14 text-right shrink-0">{row.weight}%</span>
        </li>
      ))}
    </ul>
  );
}
