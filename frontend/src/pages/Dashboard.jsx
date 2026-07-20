import { useState } from "react";
import { useQuery, useQueryClient, useIsFetching } from "@tanstack/react-query";
import { fetchSummary, fetchHoldings, fetchPerformance, fetchBenchmarks, fetchMovers, fetchEarnings, fetchInsiderBuys } from "../api";
import { useCurrency } from "../App";
import MetricCard from "../components/MetricCard";
import PerformanceChart from "../components/PerformanceChart";
import { RefreshCw, TrendingUp, TrendingDown, Calendar, LayoutGrid, Lock, UserCheck, PieChart, Activity } from "lucide-react";
import { formatMoney, formatPercent } from "../lib/format";
import { Card, SectionHeader, SkeletonRows, SkeletonChart, EmptyState, DeltaPill } from "../components/ui";
import Heatmap from "../components/Heatmap";
import { TickerLink } from "../components/StockDetail";
import DashboardGrid from "../components/DashboardGrid";
import PortfolioHero from "../components/PortfolioHero";
import { CATEGORICAL } from "../lib/chartTheme";

const MOVER_PERIODS = [
  { key: "1d", label: "Today" },
  { key: "1w", label: "Week" },
  { key: "1m", label: "Month" },
];

const PERIODS = ["7D", "MTD", "1M", "3M", "YTD", "1Y", "All"];
// Stable index-per-benchmark mapping so the same benchmark always gets the
// same color across sessions.
const BENCHMARKS = [
  { key: "sp500", label: "S&P 500", color: CATEGORICAL[0] },
  { key: "nasdaq100", label: "NASDAQ 100", color: CATEGORICAL[1] },
  { key: "dowjones", label: "Dow Jones", color: CATEGORICAL[2] },
  { key: "stoxx50", label: "STOXX 50", color: CATEGORICAL[3] },
  { key: "bitcoin", label: "Bitcoin", color: CATEGORICAL[4] },
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

  const heroSeries = (perf || [])
    .map((p) => ({ value: p.value }))
    .filter((p) => Number.isFinite(p.value));

  // Server now returns values in the requested currency, so no client-side
  // multiplication is needed. The convert() shim is kept for components that
  // are still currency-agnostic.
  const convert = (n) => n;


  const pnlPos = summary?.total_pnl >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Portfolio Overview</h1>
          {summary?.last_updated && (
            <p className="text-xs text-muted mt-0.5">
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
                : "btn-ghost border-hairline"
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

      <PortfolioHero summary={summary} loading={sl} currency={currency} series={heroSeries} />
      <DashboardGrid editing={editingLayout} onEditToggle={() => setEditingLayout(!editingLayout)}>
        {{
          performance: (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "100ms" }}>
              <SectionHeader icon={TrendingUp} action={<div className="flex items-center gap-3">
                  <div className="flex gap-0.5 bg-surface-hover rounded-lg p-0.5">
                    {["value", "growth"].map((m) => (
                      <button
                        key={m}
                        onClick={() => setChartMode(m)}
                        className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors ${
                          chartMode === m
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
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
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                </div>}>
                Portfolio Performance
              </SectionHeader>
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
                <div className="flex-1"><SkeletonChart height={256} /></div>
              ) : (
                <PerformanceChart
                  data={perf}
                  currency={currency}
                  mode={chartMode}
                  benchmarks={benchmarkData}
                  benchmarkMeta={BENCHMARKS.filter((b) => activeBenchmarks.includes(b.key))}
                />
              )}
            </Card>
          ),

          heatmap: (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "150ms" }}>
              <SectionHeader icon={LayoutGrid}>Heatmap</SectionHeader>
              {hl ? (
                <div className="flex-1"><SkeletonChart height={256} /></div>
              ) : holdings.length === 0 ? (
                <div className="flex-1 flex"><EmptyState icon={LayoutGrid} title="No holdings to map" hint="Import transactions to see your heatmap." /></div>
              ) : (
                <Heatmap />
              )}
            </Card>
          ),

          earnings: (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "200ms" }}>
              <SectionHeader icon={Calendar}>Earnings Calendar</SectionHeader>
              {el ? (
                <SkeletonRows rows={6} cols={3} />
              ) : earnings.length === 0 ? (
                <EmptyState icon={Calendar} title="No upcoming earnings" hint="None of your current holdings report soon." />
              ) : (
                <div className="space-y-2.5">
                  {earnings.slice(0, 10).map((e) => (
                    <div key={e.ticker} className="flex items-center gap-3 text-sm">
                      <TickerLink ticker={e.ticker} className="w-16 font-mono font-semibold text-left" />
                      <span className="flex-1 text-muted truncate">{e.name}</span>
                      <span className="tabular-nums text-muted w-20 text-right">
                        {e.date}
                      </span>
                      <span className="tabular-nums text-ink font-medium w-16 text-right">
                        {e.time}
                      </span>
                      <span className="tabular-nums text-muted w-20 text-right">
                        {e.eps_estimate != null ? `EPS ${e.eps_estimate}` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ),

          holdings: (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "250ms" }}>
              <SectionHeader icon={PieChart}>Top 10 Holdings</SectionHeader>
              {hl ? (
                <SkeletonRows rows={8} cols={3} />
              ) : holdings.length === 0 ? (
                <EmptyState icon={PieChart} title="No holdings yet" hint="Import your transactions to see your top positions." action={<a href="/import" className="btn-primary text-xs">Import CSV</a>} />
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
                      <span className="text-sm font-semibold tabular-nums w-14 text-right text-ink">
                        {h.weight.toFixed(1)}%
                      </span>
                      <span className="text-sm tabular-nums w-28 text-right text-muted">
                        {formatMoney(h.market_value, currency)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          ),

          insiderBuys: (() => {
            const sorted = [...insiderBuys].sort((a, b) => {
              if (insiderSort === "value") return (Math.abs(b.value) || 0) - (Math.abs(a.value) || 0);
              if (insiderSort === "pnl") return (b.pnl ?? -Infinity) - (a.pnl ?? -Infinity);
              return (b.date || "").localeCompare(a.date || "");
            });
            const thBase = "text-[10px] font-medium uppercase tracking-wider pb-2";
            const thSortable = (key, align) => `${thBase} ${align} cursor-pointer select-none transition-colors ${insiderSort === key ? "text-brand" : "text-muted hover:text-ink"}`;
            const sortArrow = (key) => insiderSort === key ? " ▼" : "";
            return (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "300ms" }}>
              <SectionHeader icon={UserCheck}>Insider Buys (1Y)</SectionHeader>
              {il ? (
                <SkeletonRows rows={6} cols={6} />
              ) : sorted.length === 0 ? (
                <EmptyState icon={UserCheck} title="No insider buys" hint="No insider purchases across your holdings in the last 12 months." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-border">
                        <th className={`${thBase} text-left text-muted`}>Ticker</th>
                        <th className={`${thBase} text-left text-muted`}>Insider</th>
                        <th className={`${thBase} text-right text-muted`}>Shares</th>
                        <th className={`${thBase} text-right text-muted`}>Buy Price</th>
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
                          <td className="py-1.5 pr-3 text-muted max-w-[180px] truncate" title={`${b.insider || ""}${b.position ? ` — ${b.position}` : ""}`}>
                            {b.insider || "—"}
                            {b.position && <span className="text-muted text-[10px] ml-1">({b.position})</span>}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-ink">
                            {b.shares != null ? Math.abs(b.shares).toLocaleString() : "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-ink">
                            {b.buy_price != null ? formatMoney(b.buy_price, b.currency) : "—"}
                          </td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-ink font-medium">
                            {b.value != null ? formatMoney(Math.abs(b.value), b.currency) : "—"}
                          </td>
                          <td className={`py-1.5 pr-3 text-right tabular-nums font-medium ${b.pnl == null ? "text-muted" : pnlUp ? "text-gain" : "text-loss"}`}>
                            {b.pnl != null ? (
                              <span title={`Current: ${formatMoney(b.current_price, b.currency)}`}>
                                {b.pnl >= 0 ? "+" : ""}{formatMoney(b.pnl, b.currency)}
                                {b.pnl_pct != null && <span className="text-[10px] ml-1">({b.pnl_pct >= 0 ? "+" : ""}{b.pnl_pct.toFixed(1)}%)</span>}
                              </span>
                            ) : "—"}
                          </td>
                          <td className="py-1.5 text-right tabular-nums text-muted text-xs">
                            {b.date || "—"}
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
            );
          })(),

          movers: (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "350ms" }}>
              <SectionHeader icon={Activity} action={<div className="flex items-center gap-3">
                  <div className="flex gap-0.5 bg-surface rounded-md p-0.5 border border-surface-border">
                    {[{ key: "pct", label: "%" }, { key: "value", label: "$" }].map((s) => (
                      <button
                        key={s.key}
                        onClick={() => setMoverSort(s.key)}
                        className={`px-2 py-0.5 text-xs rounded font-medium transition-colors ${
                          moverSort === s.key
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
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
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>
                </div>}>Top Movers</SectionHeader>
              {ml ? (
                <SkeletonRows rows={6} cols={3} />
              ) : (!movers?.gainers?.length && !movers?.losers?.length) ? (
                <EmptyState icon={Activity} title="No movers yet" hint="Import transactions to track daily gainers and losers." />
              ) : (
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  <div>
                    <h3 className="text-xs font-medium text-gain mb-2 flex items-center gap-1">
                      <TrendingUp size={12} /> Gainers
                    </h3>
                    <div className="space-y-1.5">
                      {(movers?.gainers || []).length === 0 ? (
                        <p className="text-muted text-xs">No data</p>
                      ) : (
                        [...movers.gainers].sort((a, b) => moverSort === "value" ? b.period_pnl - a.period_pnl : b.change_pct - a.change_pct).map((m) => (
                          <div key={m.ticker} className="flex items-center gap-3 text-sm">
                            <TickerLink ticker={m.ticker} className="w-14 font-mono font-semibold text-left" />
                            <span className="flex-1 text-muted truncate">{m.name}</span>
                            <span className={`tabular-nums font-medium w-24 text-right ${m.period_pnl >= 0 ? "text-gain" : "text-loss"}`}>
                              {formatMoney(m.period_pnl, m.currency)}
                            </span>
                            <div className="w-16 flex justify-end"><DeltaPill pct={m.change_pct} value={null} size="sm" /></div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                  <div>
                    <h3 className="text-xs font-medium text-loss mb-2 flex items-center gap-1">
                      <TrendingDown size={12} /> Losers
                    </h3>
                    <div className="space-y-1.5">
                      {(movers?.losers || []).length === 0 ? (
                        <p className="text-muted text-xs">No data</p>
                      ) : (
                        [...movers.losers].sort((a, b) => moverSort === "value" ? a.period_pnl - b.period_pnl : a.change_pct - b.change_pct).map((m) => (
                          <div key={m.ticker} className="flex items-center gap-3 text-sm">
                            <TickerLink ticker={m.ticker} className="w-14 font-mono font-semibold text-left" />
                            <span className="flex-1 text-muted truncate">{m.name}</span>
                            <span className={`tabular-nums font-medium w-24 text-right ${m.period_pnl >= 0 ? "text-gain" : "text-loss"}`}>
                              {formatMoney(m.period_pnl, m.currency)}
                            </span>
                            <div className="w-16 flex justify-end"><DeltaPill pct={m.change_pct} value={null} size="sm" /></div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}
            </Card>
          ),
        }}
      </DashboardGrid>
    </div>
  );
}
