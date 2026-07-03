import { useState } from "react";
import { useQuery, useQueryClient, useIsFetching } from "@tanstack/react-query";
import { fetchSummary, fetchHoldings, fetchPerformance, fetchBenchmarks, fetchMovers, fetchEarnings, fetchInsiderBuys } from "../api";
import { useCurrency } from "../App";
import MetricCard from "../components/MetricCard";
import PerformanceChart from "../components/PerformanceChart";
import { RefreshCw, TrendingUp, TrendingDown, Calendar, LayoutGrid, Lock, UserCheck } from "lucide-react";
import Heatmap from "../components/Heatmap";
import { TickerLink } from "../components/StockDetail";
import DashboardGrid from "../components/DashboardGrid";

const MOVER_PERIODS = [
  { key: "1d", label: "Today" },
  { key: "1w", label: "Week" },
  { key: "1m", label: "Month" },
];

const PERIODS = ["7D", "MTD", "1M", "3M", "YTD", "1Y", "All"];
const BENCHMARKS = [
  { key: "sp500", label: "S&P 500", color: "#f59e0b" },
  { key: "nasdaq100", label: "NASDAQ 100", color: "#8b5cf6" },
  { key: "dowjones", label: "Dow Jones", color: "#ec4899" },
  { key: "stoxx50", label: "STOXX 50", color: "#06b6d4" },
  { key: "bitcoin", label: "Bitcoin", color: "#f97316" },
];

export default function Dashboard() {
  const { currency, rate } = useCurrency();
  const queryClient = useQueryClient();
  const refreshing = useIsFetching() > 0;
  const [period, setPeriod] = useState("All");
  const [chartMode, setChartMode] = useState("value");
  const [activeBenchmarks, setActiveBenchmarks] = useState([]);
  const [moverPeriod, setMoverPeriod] = useState("1d");
  const [moverSort, setMoverSort] = useState("pct");
  const [insiderSort, setInsiderSort] = useState("date");
  const [editingLayout, setEditingLayout] = useState(false);

  const toggleBenchmark = (key) =>
    setActiveBenchmarks((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );

  const { data: summary, isLoading: sl } = useQuery({
    queryKey: ["summary", currency],
    queryFn: () => fetchSummary(currency),
  });
  const { data: holdings = [], isLoading: hl } = useQuery({
    queryKey: ["holdings", currency],
    queryFn: () => fetchHoldings(currency),
  });
  const { data: perf = [], isLoading: pl } = useQuery({
    queryKey: ["performance", currency, period],
    queryFn: () => fetchPerformance(currency, period.toLowerCase()),
  });
  const { data: benchmarkData = {} } = useQuery({
    queryKey: ["benchmarks", activeBenchmarks, period],
    queryFn: () => fetchBenchmarks(activeBenchmarks, period.toLowerCase()),
    enabled: activeBenchmarks.length > 0,
  });

  const { data: movers, isLoading: ml } = useQuery({
    queryKey: ["movers", moverPeriod],
    queryFn: () => fetchMovers(moverPeriod),
  });

  const { data: earnings = [], isLoading: el } = useQuery({
    queryKey: ["earnings"],
    queryFn: fetchEarnings,
  });

  const { data: insiderBuys = [], isLoading: il } = useQuery({
    queryKey: ["insider-buys"],
    queryFn: fetchInsiderBuys,
    staleTime: 30 * 60 * 1000,
  });

  // Server now returns values in the requested currency, so no client-side
  // multiplication is needed. The convert() shim is kept for components that
  // are still currency-agnostic.
  const convert = (n) => n;

  const fmt = (n) => {
    if (n == null) return "—";
    const sign = n < 0 ? "-" : "";
    const str = Math.abs(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return currency === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
  };

  const fmtPct = (n) =>
    n == null ? "—" : (n >= 0 ? "+" : "") + n.toFixed(2) + "%";

  const pnlPos = summary?.total_pnl >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Portfolio Overview</h1>
          {summary?.last_updated && (
            <p className="text-xs text-slate-500 mt-0.5">
              Updated {new Date(summary.last_updated).toLocaleTimeString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setEditingLayout(!editingLayout)}
            className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border transition-colors ${
              editingLayout
                ? "bg-brand/10 border-brand/30 text-brand font-medium"
                : "btn-ghost border-slate-200"
            }`}
          >
            {editingLayout ? <Lock size={14} /> : <LayoutGrid size={14} />}
            {editingLayout ? "Lock Layout" : "Customize"}
          </button>
          <button
            onClick={() =>
              // Scope refresh to this page's own queries. A bare
              // invalidateQueries() nuked every cache key app-wide (including
              // the intentionally long-cached insider-buys and other pages),
              // causing a refetch storm across the slow yfinance endpoints.
              ["summary", "holdings", "performance", "benchmarks", "movers", "earnings"].forEach(
                (k) => queryClient.invalidateQueries({ queryKey: [k] })
              )
            }
            disabled={refreshing}
            className="btn-ghost flex items-center gap-2 text-sm disabled:opacity-60"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      <DashboardGrid editing={editingLayout} onEditToggle={() => setEditingLayout(!editingLayout)}>
        {{
          metrics: (
            <div className="grid grid-cols-2 xl:grid-cols-5 gap-4">
              <MetricCard label="Portfolio Value" value={fmt(summary?.total_value)} loading={sl} />
              <MetricCard label="Total Invested" value={fmt(summary?.total_invested)} loading={sl} />
              <MetricCard
                label="Total P&L"
                value={fmt(summary?.total_pnl)}
                sub={fmtPct(summary?.total_pnl_percent)}
                positive={pnlPos}
                negative={!pnlPos && summary?.total_pnl != null}
                loading={sl}
              />
              <MetricCard label="Dividends Received" value={fmt(summary?.total_dividends)} loading={sl} />
              <MetricCard label="Holdings" value={summary?.holdings_count ?? "—"} loading={sl} />
            </div>
          ),

          performance: (
            <div className="card h-full">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
                  Portfolio Performance
                </h2>
                <div className="flex items-center gap-3">
                  <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5">
                    {["value", "growth"].map((m) => (
                      <button
                        key={m}
                        onClick={() => setChartMode(m)}
                        className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                          chartMode === m
                            ? "bg-white text-brand font-semibold shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        {m === "value" ? "Value" : "Growth %"}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1">
                    {PERIODS.map((p) => (
                      <button
                        key={p}
                        onClick={() => setPeriod(p)}
                        className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                          period === p
                            ? "bg-white text-brand font-semibold shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {BENCHMARKS.map((b) => (
                  <button
                    key={b.key}
                    onClick={() => toggleBenchmark(b.key)}
                    className={`px-2 py-0.5 text-xs rounded-md font-medium transition-colors border ${
                      activeBenchmarks.includes(b.key)
                        ? "border-current opacity-100"
                        : "border-transparent opacity-50 hover:opacity-80"
                    }`}
                    style={{ color: b.color }}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
              {pl ? (
                <div className="h-64 flex items-center justify-center">
                  <div className="text-slate-500 text-sm animate-pulse">Loading chart…</div>
                </div>
              ) : (
                <PerformanceChart
                  data={perf}
                  currency={currency}
                  mode={chartMode}
                  benchmarks={benchmarkData}
                  benchmarkMeta={BENCHMARKS.filter((b) => activeBenchmarks.includes(b.key))}
                />
              )}
            </div>
          ),

          heatmap: (
            <div className="card h-full">
              <Heatmap />
            </div>
          ),

          earnings: (
            <div className="card h-full flex flex-col">
              <h2 className="text-sm font-semibold text-slate-500 mb-4 uppercase tracking-wider flex items-center gap-2">
                <Calendar size={14} /> Earnings Calendar
              </h2>
              {el ? (
                <div className="h-20 flex items-center justify-center">
                  <div className="text-slate-500 text-sm animate-pulse">Loading earnings…</div>
                </div>
              ) : earnings.length === 0 ? (
                <p className="text-slate-400 text-xs">No upcoming earnings reports for current holdings.</p>
              ) : (
                <div className="space-y-2.5">
                  {earnings.slice(0, 10).map((e) => (
                    <div key={e.ticker} className="flex items-center gap-3 text-sm">
                      <TickerLink ticker={e.ticker} className="w-16 font-mono font-semibold text-left" />
                      <span className="flex-1 text-slate-500 truncate">{e.name}</span>
                      <span className="tabular-nums text-slate-500 w-20 text-right">
                        {e.date}
                      </span>
                      <span className="tabular-nums text-slate-800 font-medium w-16 text-right">
                        {e.time}
                      </span>
                      <span className="tabular-nums text-slate-500 w-20 text-right">
                        {e.eps_estimate != null ? `EPS ${e.eps_estimate}` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ),

          holdings: (
            <div className="card h-full flex flex-col">
              <h2 className="text-sm font-semibold text-slate-500 mb-4 uppercase tracking-wider">
                Top 10 Holdings
              </h2>
              {holdings.length === 0 ? (
                <p className="text-slate-400 text-xs">No holdings yet.</p>
              ) : (
                <div className="space-y-2.5">
                  {holdings.slice(0, 10).map((h) => (
                    <div key={h.ticker} className="flex items-center gap-3">
                      <TickerLink ticker={h.ticker} className="w-16 font-mono font-semibold text-sm text-left" />
                      <div className="flex-1 bg-surface-hover rounded-full h-2.5 relative">
                        <div
                          className="bg-brand rounded-full h-2.5 transition-all"
                          style={{ width: `${h.weight}%` }}
                        />
                      </div>
                      <span className="text-sm font-semibold tabular-nums w-14 text-right text-slate-800">
                        {h.weight.toFixed(1)}%
                      </span>
                      <span className="text-sm tabular-nums w-28 text-right text-slate-500">
                        {fmt(h.market_value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ),

          insiderBuys: (() => {
            const sorted = [...insiderBuys].sort((a, b) => {
              if (insiderSort === "value") return (Math.abs(b.value) || 0) - (Math.abs(a.value) || 0);
              if (insiderSort === "pnl") return (b.pnl ?? -Infinity) - (a.pnl ?? -Infinity);
              return (b.date || "").localeCompare(a.date || "");
            });
            const thBase = "text-[10px] font-medium uppercase tracking-wider pb-2";
            const thSortable = (key, align) => `${thBase} ${align} cursor-pointer select-none transition-colors ${insiderSort === key ? "text-brand" : "text-slate-400 hover:text-slate-600"}`;
            const sortArrow = (key) => insiderSort === key ? " ▼" : "";
            return (
            <div className="card h-full flex flex-col">
              <h2 className="text-sm font-semibold text-slate-500 mb-4 uppercase tracking-wider flex items-center gap-2">
                <UserCheck size={14} /> Insider Buys (1Y)
              </h2>
              {il ? (
                <div className="h-20 flex items-center justify-center">
                  <div className="text-slate-500 text-sm animate-pulse">Loading insider buys…</div>
                </div>
              ) : sorted.length === 0 ? (
                <p className="text-slate-400 text-xs">No insider buys in the last 12 months.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-border">
                        <th className={`${thBase} text-left text-slate-400`}>Ticker</th>
                        <th className={`${thBase} text-left text-slate-400`}>Insider</th>
                        <th className={`${thBase} text-right text-slate-400`}>Shares</th>
                        <th className={`${thBase} text-right text-slate-400`}>Buy Price</th>
                        <th className={thSortable("value", "text-right")} onClick={() => setInsiderSort("value")}>Value{sortArrow("value")}</th>
                        <th className={thSortable("pnl", "text-right")} onClick={() => setInsiderSort("pnl")}>P&L{sortArrow("pnl")}</th>
                        <th className={thSortable("date", "text-right")} onClick={() => setInsiderSort("date")}>Date{sortArrow("date")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {sorted.map((b, i) => {
                        const pnlUp = b.pnl != null && b.pnl >= 0;
                        return (
                        <tr key={i} className="hover:bg-surface-hover transition-colors">
                          <td className="py-1.5 pr-3">
                            <TickerLink ticker={b.ticker} className="font-mono font-semibold" />
                          </td>
                          <td className="py-1.5 pr-3 text-slate-600 max-w-[180px] truncate" title={`${b.insider || ""}${b.position ? ` — ${b.position}` : ""}`}>
                            {b.insider || "—"}
                            {b.position && <span className="text-slate-400 text-[10px] ml-1">({b.position})</span>}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-slate-700">
                            {b.shares != null ? Math.abs(b.shares).toLocaleString() : "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-slate-700">
                            {b.buy_price != null ? fmt(b.buy_price) : "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-slate-700 font-medium">
                            {b.value != null ? fmt(Math.abs(b.value)) : "—"}
                          </td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums font-medium ${b.pnl == null ? "text-slate-400" : pnlUp ? "text-emerald-600" : "text-red-600"}`}>
                            {b.pnl != null ? (
                              <span title={`Current: ${fmt(b.current_price)}`}>
                                {b.pnl >= 0 ? "+" : ""}{fmt(b.pnl)}
                                {b.pnl_pct != null && <span className="text-[10px] ml-1">({b.pnl_pct >= 0 ? "+" : ""}{b.pnl_pct.toFixed(1)}%)</span>}
                              </span>
                            ) : "—"}
                          </td>
                          <td className="py-1.5 text-right tabular-nums text-slate-500 text-xs">
                            {b.date || "—"}
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
            );
          })(),

          movers: (
            <div className="card h-full">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wider">
                  Top Movers
                </h2>
                <div className="flex items-center gap-3">
                  <div className="flex gap-0.5 bg-surface rounded-md p-0.5 border border-surface-border">
                    {[{ key: "pct", label: "%" }, { key: "value", label: "$" }].map((s) => (
                      <button
                        key={s.key}
                        onClick={() => setMoverSort(s.key)}
                        className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${
                          moverSort === s.key
                            ? "bg-white text-brand font-semibold shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        {s.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1">
                    {MOVER_PERIODS.map((p) => (
                      <button
                        key={p.key}
                        onClick={() => setMoverPeriod(p.key)}
                        className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                          moverPeriod === p.key
                            ? "bg-white text-brand font-semibold shadow-sm"
                            : "text-slate-500 hover:text-slate-700"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              {ml ? (
                <div className="h-32 flex items-center justify-center">
                  <div className="text-slate-500 text-sm animate-pulse">Loading movers...</div>
                </div>
              ) : (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-xs font-medium text-emerald-600 mb-2 flex items-center gap-1">
                      <TrendingUp size={12} /> Gainers
                    </h3>
                    <div className="space-y-1.5">
                      {(movers?.gainers || []).length === 0 ? (
                        <p className="text-slate-400 text-xs">No data</p>
                      ) : (
                        [...movers.gainers].sort((a, b) => moverSort === "value" ? b.period_pnl - a.period_pnl : b.change_pct - a.change_pct).map((m) => (
                          <div key={m.ticker} className="flex items-center gap-3 text-sm">
                            <TickerLink ticker={m.ticker} className="w-14 font-mono font-semibold text-left" />
                            <span className="flex-1 text-slate-500 truncate">{m.name}</span>
                            <span className={`tabular-nums font-medium w-24 text-right ${m.period_pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                              {fmt(m.period_pnl)}
                            </span>
                            <span className="tabular-nums text-emerald-600 font-medium w-16 text-right">
                              +{m.change_pct}%
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-xs font-medium text-red-600 mb-2 flex items-center gap-1">
                      <TrendingDown size={12} /> Losers
                    </h3>
                    <div className="space-y-1.5">
                      {(movers?.losers || []).length === 0 ? (
                        <p className="text-slate-400 text-xs">No data</p>
                      ) : (
                        [...movers.losers].sort((a, b) => moverSort === "value" ? a.period_pnl - b.period_pnl : a.change_pct - b.change_pct).map((m) => (
                          <div key={m.ticker} className="flex items-center gap-3 text-sm">
                            <TickerLink ticker={m.ticker} className="w-14 font-mono font-semibold text-left" />
                            <span className="flex-1 text-slate-500 truncate">{m.name}</span>
                            <span className={`tabular-nums font-medium w-24 text-right ${m.period_pnl >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                              {fmt(m.period_pnl)}
                            </span>
                            <span className="tabular-nums text-red-600 font-medium w-16 text-right">
                              {m.change_pct}%
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ),
        }}
      </DashboardGrid>
    </div>
  );
}
