import { useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchPolymarketPositions, fetchPolymarketSummary, syncPolymarket } from "../api";
import { Hexagon, RefreshCw } from "lucide-react";

function fmtCents(v) {
  if (v == null) return "-";
  return `${Math.round(v * 100)}c`;
}

function fmtMoney(v) {
  if (v == null) return "-";
  const sign = v >= 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPercent(v) {
  if (v == null) return "-";
  return `${v.toFixed(1)}%`;
}

function pctReturn(pos) {
  if (!pos.avg_price || pos.avg_price === 0) return null;
  const exitPrice = pos.status === "closed" ? pos.resolved_price : pos.current_price;
  if (exitPrice == null) return null;
  return ((exitPrice - pos.avg_price) / pos.avg_price) * 100;
}

export default function Polymarket() {
  const queryClient = useQueryClient();

  const { data: positions, isLoading: positionsLoading } = useQuery({
    queryKey: ["polymarket-positions"],
    queryFn: fetchPolymarketPositions,
    staleTime: 5 * 60 * 1000,
  });

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["polymarket-summary"],
    queryFn: fetchPolymarketSummary,
  });

  const syncMutation = useMutation({
    mutationFn: syncPolymarket,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["polymarket-positions"] });
      queryClient.invalidateQueries({ queryKey: ["polymarket-summary"] });
    },
  });

  const sorted = useMemo(() => {
    if (!positions?.length) return [];
    const open = positions.filter((p) => p.status === "open").sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0));
    const closed = positions.filter((p) => p.status !== "open").sort((a, b) => (b.pnl ?? 0) - (a.pnl ?? 0));
    return [...open, ...closed];
  }, [positions]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Hexagon size={20} className="text-brand" />
            <h1 className="text-xl font-semibold">Polymarket</h1>
          </div>
          <p className="text-sm text-slate-500">Prediction market positions and P&L</p>
        </div>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-4 py-2 rounded-lg hover:bg-brand/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={15} className={syncMutation.isPending ? "animate-spin" : ""} />
          {syncMutation.isPending ? "Syncing..." : "Refresh"}
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <SummaryCard label="Positions Value" value={summary?.total_value} isMoney loading={summaryLoading} neutral />
        <SummaryCard label="Unrealized P&L" value={summary?.unrealized_pnl} isMoney loading={summaryLoading} />
        <SummaryCard label="Realized P&L" value={summary?.realized_pnl} isMoney loading={summaryLoading} />
        <SummaryCard label="Win Rate" value={summary?.win_rate} isPercent loading={summaryLoading} />
        <SummaryCard label="Open Positions" value={summary?.open_positions} isCount loading={summaryLoading} />
      </div>

      {/* Positions table */}
      {positionsLoading ? (
        <div className="text-center py-16 text-slate-400">Loading positions...</div>
      ) : !sorted.length ? (
        <div className="text-center py-16 text-slate-400">
          No positions found. Connect Polymarket and sync to see positions here.
        </div>
      ) : (
        <div className="rounded-xl border border-surface-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-card border-b border-surface-border">
                  {["Market", "Outcome", "Size", "Avg Price", "Sell Price", "P&L", "Return", "Status"].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((pos) => (
                  <tr
                    key={pos.id}
                    className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors"
                  >
                    <td className="px-4 py-3 max-w-[280px]">
                      <span className="text-slate-800 truncate block" title={pos.question}>
                        {pos.question}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs font-semibold px-2 py-0.5 rounded ${
                          pos.outcome?.toLowerCase() === "yes"
                            ? "bg-emerald-50 text-emerald-600"
                            : "bg-red-50 text-red-600"
                        }`}
                      >
                        {pos.outcome}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 tabular-nums">{pos.size}</td>
                    <td className="px-4 py-3 text-slate-600 tabular-nums">{fmtCents(pos.avg_price)}</td>
                    <td className="px-4 py-3 text-slate-600 tabular-nums">
                      {fmtCents(pos.status === "closed" ? pos.resolved_price : pos.current_price)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`font-bold tabular-nums ${
                          (pos.pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
                        }`}
                      >
                        {fmtMoney(pos.pnl)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {pctReturn(pos) != null ? (
                        <span
                          className={`font-semibold tabular-nums text-xs ${
                            pctReturn(pos) >= 0 ? "text-emerald-600" : "text-red-600"
                          }`}
                        >
                          {pctReturn(pos) >= 0 ? "+" : ""}{pctReturn(pos).toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={pos.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ label, value, isMoney, isPercent, isCount, loading, neutral }) {
  let displayValue = "-";
  let colorClass = "text-slate-800";

  if (!loading && value != null) {
    if (isMoney) {
      if (neutral) {
        displayValue = `$${Math.abs(value).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      } else {
        displayValue = fmtMoney(value);
        colorClass = value >= 0 ? "text-emerald-600" : "text-red-600";
      }
    } else if (isPercent) {
      displayValue = fmtPercent(value * 100);
      colorClass = value >= 0.5 ? "text-emerald-600" : "text-slate-800";
    } else if (isCount) {
      displayValue = value.toLocaleString();
    }
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 flex flex-col gap-1">
      <span className="text-[11px] text-slate-500 uppercase tracking-wider font-medium">{label}</span>
      {loading ? (
        <div className="h-7 w-20 bg-slate-100 rounded animate-pulse mt-1" />
      ) : (
        <span className={`text-lg font-bold tabular-nums ${colorClass}`}>{displayValue}</span>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  if (!status) return <span className="text-slate-400">-</span>;

  const styles = {
    open: "bg-blue-50 text-blue-700",
    resolved: "bg-slate-100 text-slate-600",
    closed: "bg-yellow-50 text-yellow-700",
  };

  const className = styles[status?.toLowerCase()] || "bg-slate-100 text-slate-600";

  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase ${className}`}>
      {status}
    </span>
  );
}
