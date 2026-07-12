import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllHoldings, fetchSectorBreakdown } from "../api";
import { useCurrency } from "../App";
import { formatMoney } from "../lib/format";
import { groupPositions } from "../lib/positionsPie";
import { TrendingUp, TrendingDown, RefreshCw } from "lucide-react";
import { TickerLink, useStockDetail } from "../components/StockDetail";
import BreakdownChart from "../components/BreakdownChart";

const fmtPct = (n) => (n >= 0 ? "+" : "") + n.toFixed(2) + "%";

export default function Allocation() {
  const { currency } = useCurrency();
  const { openStock } = useStockDetail();

  // Portfolio-level money (value, P&L, dividends) is shown in the display
  // currency (CZK by default). Per-share prices (avg cost, current price) are
  // shown in each stock's *native* currency — a US stock's price is $, not Kč.
  const fmt = (n) => formatMoney(n, currency);
  const fmtNative = (n, code) => formatMoney(n, code || currency);

  const {
    data: holdings = [],
    isLoading: holdingsLoading,
    refetch: refetchHoldings,
    isFetching,
  } = useQuery({
    queryKey: ["holdings-all", currency],
    queryFn: () => fetchAllHoldings(currency),
  });

  const { data: breakdown, isLoading: breakdownLoading } = useQuery({
    queryKey: ["sector-breakdown", currency],
    queryFn: () => fetchSectorBreakdown(currency),
  });

  // Positions pie: >2% holdings get their own slice, the rest fold into
  // "Other". Derived from the same holdings query as the table, so the pie
  // always matches the Weight column (and refreshes with "Refresh prices").
  const positions = useMemo(() => groupPositions(holdings), [holdings]);

  const [sort, setSort] = useState({ key: "market_value", dir: "desc" });

  const sorted = [...holdings].sort((a, b) => {
    const v = a[sort.key] > b[sort.key] ? 1 : -1;
    return sort.dir === "asc" ? v : -v;
  });

  const toggle = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));

  const Th = ({ label, k }) => (
    <th
      onClick={() => toggle(k)}
      className="text-left px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-800 select-none"
    >
      {label}
      {sort.key === k && <span className="ml-1">{sort.dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Allocation</h1>
        <button
          onClick={() => refetchHoldings()}
          className="btn-ghost flex items-center gap-2 text-sm"
          disabled={isFetching}
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
          Refresh prices
        </button>
      </div>

      {breakdownLoading || holdingsLoading ? (
        <div className="card animate-pulse h-48 flex items-center justify-center text-slate-500">
          Loading allocation data...
        </div>
      ) : (
        <>
          <BreakdownChart
            title="Positions"
            data={positions}
            currencyLabel={currency}
            legendColumns={2}
          />
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <BreakdownChart
              title="Sector Allocation"
              data={breakdown?.sectors}
              currencyLabel={currency}
            />
            <BreakdownChart
              title="Country Allocation"
              data={breakdown?.countries}
              currencyLabel={currency}
            />
          </div>
        </>
      )}

      <div>
        <h2 className="text-sm font-semibold text-slate-500 mb-3 uppercase tracking-wider">
          All Holdings
        </h2>
        {holdingsLoading ? (
          <div className="card animate-pulse h-48 flex items-center justify-center text-slate-500">
            Loading live prices...
          </div>
        ) : holdings.length === 0 ? (
          <div className="card text-slate-500 text-sm text-center py-12">
            No holdings yet. Import a CSV or add transactions to get started.
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-surface-border">
                  <tr>
                    <Th label="Ticker" k="ticker" />
                    <Th label="Company" k="name" />
                    <Th label="Shares" k="shares" />
                    <Th label="Avg Cost" k="avg_cost" />
                    <Th label="Price" k="current_price" />
                    <Th label="Value" k="market_value" />
                    <Th label="P&L" k="pnl" />
                    <Th label="P&L %" k="pnl_percent" />
                    <Th label="Weight" k="weight" />
                    <Th label="Dividends" k="dividends" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {sorted.map((h) => {
                    const up = h.pnl >= 0;
                    const closed = h.closed;
                    return (
                      <tr
                        key={h.ticker}
                        onClick={() => openStock(h.ticker)}
                        className={`hover:bg-surface-hover transition-colors cursor-pointer ${closed ? "bg-red-50" : ""}`}
                      >
                        <td className="px-4 py-3 font-mono font-bold text-sm">
                          <TickerLink ticker={h.ticker} className="text-left">{h.ticker}</TickerLink>
                          {closed && <span className="ml-1.5 text-[10px] font-medium text-red-600/80 uppercase">Sold</span>}
                        </td>
                        <td className={`px-4 py-3 text-sm max-w-xs truncate ${closed ? "text-slate-500" : "text-slate-700"}`}>{h.name}</td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right ${closed ? "text-slate-500" : ""}`}>
                          {closed ? "—" : h.shares.toLocaleString()}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right ${closed ? "text-slate-500" : ""}`}>{fmtNative(h.avg_cost, h.currency)}</td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-medium ${closed ? "text-slate-500" : ""}`}>
                          <div>{fmtNative(h.current_price, h.currency)}</div>
                          {closed && h.live_price != null && (
                            <div className="text-[10px] text-slate-400 leading-tight" title="Live market price today">
                              now {fmtNative(h.live_price, h.currency)}
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-semibold ${closed ? "text-slate-500" : ""}`}>
                          {closed ? "—" : fmt(h.market_value)}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-medium ${up ? "text-emerald-600" : "text-red-600"}`}>
                          <span className="flex items-center justify-end gap-1">
                            {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                            {fmt(h.pnl)}
                          </span>
                          {closed && h.pnl_if_held != null && (
                            <div
                              className={`text-[10px] leading-tight mt-0.5 font-normal ${h.pnl_if_held >= 0 ? "text-emerald-500" : "text-red-500"}`}
                              title="P&L if you had held instead of sold (live price today)"
                            >
                              if held: {h.pnl_if_held >= 0 ? "+" : ""}{fmt(h.pnl_if_held)}
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-medium ${up ? "text-emerald-600" : "text-red-600"}`}>
                          {fmtPct(h.pnl_percent)}
                          {closed && h.pnl_if_held_pct != null && (
                            <div
                              className={`text-[10px] leading-tight mt-0.5 font-normal ${h.pnl_if_held_pct >= 0 ? "text-emerald-500" : "text-red-500"}`}
                            >
                              if held: {fmtPct(h.pnl_if_held_pct)}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-right">
                          {closed ? (
                            <span className="text-slate-500 text-xs">—</span>
                          ) : (
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 bg-slate-100 rounded-full h-1.5">
                                <div className="bg-brand rounded-full h-1.5" style={{ width: `${h.weight}%` }} />
                              </div>
                              <span className="tabular-nums text-slate-500 w-10">{h.weight}%</span>
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right ${closed ? "text-slate-500" : "text-slate-500"}`}>
                          {fmt(h.dividends)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
