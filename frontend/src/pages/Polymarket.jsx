import { useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchPolymarketPositions, fetchPolymarketSummary, syncPolymarket } from "../api";
import { Hexagon, RefreshCw, Wallet, TrendingUp, TrendingDown, Target, Layers } from "lucide-react";
import MetricCard from "../components/MetricCard";
import { CATEGORICAL } from "../lib/chartTheme";

function fmtCents(v) {
  if (v == null) return "-";
  return `${Math.round(v * 100)}c`;
}

function fmtMoney(v) {
  if (v == null) return "-";
  const sign = v >= 0 ? "+" : "";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Plain absolute-value money (no +/- sign forced) — used for the neutral
// "Positions Value" stat, which isn't a gain/loss figure.
function fmtAbsMoney(v) {
  if (v == null) return "-";
  return `$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
          <p className="text-sm text-muted">Prediction market positions and P&L</p>
        </div>
        <button
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="flex items-center gap-2 bg-brand text-black font-semibold text-sm px-4 py-2 rounded-lg hover:bg-brand/90 transition-colors disabled:bg-brand-light disabled:text-muted disabled:cursor-not-allowed"
        >
          <RefreshCw size={15} className={syncMutation.isPending ? "animate-spin" : ""} />
          {syncMutation.isPending ? "Syncing..." : "Refresh"}
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MetricCard icon={Wallet} label="Positions Value" value={fmtAbsMoney(summary?.total_value)} loading={summaryLoading} />
        <MetricCard
          icon={TrendingUp}
          label="Unrealized P&L"
          value={fmtMoney(summary?.unrealized_pnl)}
          positive={summary?.unrealized_pnl != null && summary.unrealized_pnl >= 0}
          negative={summary?.unrealized_pnl != null && summary.unrealized_pnl < 0}
          loading={summaryLoading}
        />
        <MetricCard
          icon={TrendingDown}
          label="Realized P&L"
          value={fmtMoney(summary?.realized_pnl)}
          positive={summary?.realized_pnl != null && summary.realized_pnl >= 0}
          negative={summary?.realized_pnl != null && summary.realized_pnl < 0}
          loading={summaryLoading}
        />
        <MetricCard
          icon={Target}
          label="Win Rate"
          value={fmtPercent(summary?.win_rate != null ? summary.win_rate * 100 : null)}
          positive={summary?.win_rate != null && summary.win_rate >= 0.5}
          loading={summaryLoading}
        />
        <MetricCard
          icon={Layers}
          label="Open Positions"
          value={summary?.open_positions != null ? summary.open_positions.toLocaleString() : "-"}
          loading={summaryLoading}
        />
      </div>

      {/* Positions table */}
      {positionsLoading ? (
        <div className="text-center py-16 text-muted">Loading positions...</div>
      ) : !sorted.length ? (
        <div className="text-center py-16 text-muted">
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
                      className="text-left px-4 py-3 text-[10px] font-semibold text-muted uppercase tracking-wider"
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
                      <span className="text-ink truncate block" title={pos.question}>
                        {pos.question}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <OutcomeBadge outcome={pos.outcome} />
                    </td>
                    <td className="px-4 py-3 text-muted tabular-nums">{pos.size}</td>
                    <td className="px-4 py-3 text-muted tabular-nums">{fmtCents(pos.avg_price)}</td>
                    <td className="px-4 py-3 text-muted tabular-nums">
                      {fmtCents(pos.status === "closed" ? pos.resolved_price : pos.current_price)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`font-bold tabular-nums ${
                          (pos.pnl ?? 0) >= 0 ? "text-gain" : "text-loss"
                        }`}
                      >
                        {fmtMoney(pos.pnl)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {pctReturn(pos) != null ? (
                        <span
                          className={`font-semibold tabular-nums text-xs ${
                            pctReturn(pos) >= 0 ? "text-gain" : "text-loss"
                          }`}
                        >
                          {pctReturn(pos) >= 0 ? "+" : ""}{pctReturn(pos).toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-muted">-</span>
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

// Yes/No is a categorical outcome side, not a profit/loss result (a losing
// "No" position and a winning "No" position are both just "No") — so this
// must NOT use the gain/loss (P&L-semantic) tokens. Per the Stitch mockup
// (stitch_portfyl_desktop/portfyl_polymarket_glass_edition/screen.png), YES
// renders as a sky-blue pill and NO as an amber pill, so we borrow the fixed,
// non-P&L "chart-5" (sky) / "chart-3" (amber) hues from the already-locked
// chart-color token system (chartTheme.js) instead of inventing a new color.
function OutcomeBadge({ outcome }) {
  if (!outcome) return <span className="text-muted">-</span>;

  const accent = outcome.toLowerCase() === "yes" ? CATEGORICAL[4] : CATEGORICAL[2];

  return (
    <span
      className="text-xs font-semibold px-2 py-0.5 rounded"
      style={{
        backgroundColor: `color-mix(in srgb, ${accent} 15%, var(--surface-card, #F7F9FD) 85%)`,
        color: accent,
      }}
    >
      {outcome}
    </span>
  );
}

function StatusBadge({ status }) {
  if (!status) return <span className="text-muted">-</span>;

  const styles = {
    open: "bg-blue-50 text-blue-700",
    resolved: "bg-surface-hover text-muted",
    closed: "bg-yellow-50 text-yellow-700",
  };

  const className = styles[status?.toLowerCase()] || "bg-surface-hover text-muted";

  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase ${className}`}>
      {status}
    </span>
  );
}
