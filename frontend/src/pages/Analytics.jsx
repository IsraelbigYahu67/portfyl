import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchRiskMetrics,
  fetchBenchmarkCatalog,
  fetchBenchmarkComparison,
} from "../api";
import { useCurrency } from "../App";
import MetricCard, { InfoIcon } from "../components/MetricCard";
import {
  Tooltip, ResponsiveContainer, XAxis, YAxis, CartesianGrid, LineChart, Line,
} from "recharts";
import { Activity, RefreshCw, TrendingDown, TrendingUp, Shield, Wallet } from "lucide-react";
import { AsyncSection, Badge } from "../components/ui";
import SegmentedControl from "../components/ui/SegmentedControl";
import { formatMoney } from "../lib/format";
import {
  CATEGORICAL, GAIN_COLOR, NEUTRAL_COLOR, AXIS_TICK_STYLE, GRID_STROKE, TOOLTIP_STYLE,
} from "../lib/chartTheme";

const PERIODS = ["3M", "6M", "1Y", "2Y"];

// Definitions + formulas surfaced via the (i) icon next to each metric.
// Kept on the client so the API stays data-only and translations are easy.
const INFO = {
  total_return: {
    title: "Total Return (TWR)",
    what: "Cumulative time-weighted return over the selected period. Strips out the timing of your deposits/withdrawals so the % reflects investment performance only — the same methodology funds use on their factsheets.",
    formula: "∏(1 + rᵢ) − 1, where rᵢ = (Vᵢ − Vᵢ₋₁ − Cᵢ) / (Vᵢ₋₁ + 0.5·Cᵢ)",
    note: "Cᵢ = net buys minus sells on day i (Modified-Dietz).",
  },
  ann_return: {
    title: "Annualized Return (Arithmetic)",
    what: "Average daily return scaled to one year. Used inside Sharpe/Sortino. Not the same as CAGR — this one ignores compounding.",
    formula: "mean(daily_returns) × 252",
  },
  cagr: {
    title: "CAGR (Geometric)",
    what: "Compound annual growth rate from the TWR cumulative return. The constant yearly rate that, compounded, would produce the same total return over the period.",
    formula: "(1 + TotalReturn)^(1/years) − 1",
  },
  ann_vol: {
    title: "Annualized Volatility",
    what: "Standard deviation of daily TWR returns, scaled to one year. Measures how much your portfolio's daily return varies.",
    formula: "stdev(daily_returns) × √252",
  },
  sharpe: {
    title: "Sharpe Ratio",
    what: "Return earned per unit of total volatility, vs the risk-free rate. >1 is decent, >2 is great. Negative means you'd be better off in cash.",
    formula: "(Annualized Return − Rf) / Annualized Volatility",
    note: "Rf = 5% (risk-free rate).",
  },
  beta: {
    title: "Beta (vs benchmark)",
    what: "Sensitivity of your portfolio's daily TWR to the chosen benchmark's daily return. 1 = moves with the benchmark; >1 = more volatile; <1 = less volatile.",
    formula: "cov(rₚ, r_B) / var(r_B)",
  },
  alpha: {
    title: "Alpha (annualized)",
    what: "Excess annualized return your portfolio earned over what its Beta vs the chosen benchmark would predict. Positive = outperformed; negative = underperformed.",
    formula: "AnnReturn − [Rf + β × (R_B − Rf)]",
    note: "Jensen's Alpha. Uses the same Rf as Sharpe.",
  },
  active_return: {
    title: "Active Return",
    what: "Cumulative portfolio TWR minus benchmark cumulative return over the window. Positive = outperformed the benchmark in raw percentage terms.",
    formula: "PortfolioReturn − BenchmarkReturn",
  },
  max_dd: {
    title: "Maximum Drawdown",
    what: "Worst peak-to-trough decline in the cumulative TWR curve during the selected period. The biggest 'paper loss' you would have ridden through.",
    formula: "min[(cumulative_t − peak_t) / peak_t]",
  },
  current_dd: {
    title: "Current Drawdown",
    what: "How far below your most recent equity peak the portfolio is right now (in TWR terms).",
    formula: "(cumulative_last − cumulative_peak) / cumulative_peak",
  },
  best_day: {
    title: "Best Day",
    what: "Largest single-day TWR return inside the selected period.",
    formula: "max(daily_returns)",
  },
  worst_day: {
    title: "Worst Day",
    what: "Largest single-day TWR loss inside the selected period.",
    formula: "min(daily_returns)",
  },
  simple_roi: {
    title: "Simple ROI (lifetime)",
    what: "Simple ROI is that net profit divided by everything you ever bought, so it also leaves out interest and fees and can differ from the Dashboard's Total profit %.",
    formula: "(Unrealized + Realized + Dividends) / Σ Buy Cost",
    note: "Sells with no matching prior buy in the DB are excluded.",
  },
  xirr: {
    title: "Annualized IRR (XIRR)",
    what: "The discount rate at which the NPV of every buy (−), sell (+), dividend (+), and the current value (+) equals zero. Annualized money-weighted return — the rate your actual cash flows earned.",
    formula: "Find r where Σ CFᵢ / (1+r)^(dᵢ/365) = 0",
    note: "Solved via Newton + bisection over the lifetime cashflow series.",
  },
  net_profit: {
    title: "Net Profit (lifetime)",
    what: "Net profit is unrealized gains on open positions plus realized gains on sells plus dividends, without interest or fees, so it can differ from the Dashboard's Total profit, which also adds interest and subtracts fees.",
    formula: "Unrealized + Realized + Dividends",
  },
  total_invested: {
    title: "Capital Currently Invested",
    what: "Cost basis of the positions you still hold. Cash you've deployed and not yet recovered through sells.",
    formula: "Σ (open shares × avg cost)",
  },
  current_value: {
    title: "Current Market Value",
    what: "Latest mark-to-market value of all open positions, converted to USD.",
    formula: "Σ (open shares × latest close × FX→USD)",
  },
};

const RATING_TONES = ["loss", "warn", "brand", "gain"];

function RatingBadge({ value, thresholds, labels }) {
  let level = 0;
  for (let i = 0; i < thresholds.length; i++) {
    if (value >= thresholds[i]) level = i + 1;
  }
  return (
    <Badge tone={RATING_TONES[Math.min(level, RATING_TONES.length - 1)]} size="sm">
      {labels[Math.min(level, labels.length - 1)]}
    </Badge>
  );
}

function NetProfitSub({ text }) {
  return <span className="block truncate" title={text}>{text}</span>;
}

export default function Analytics() {
  const { currency, rate } = useCurrency();
  const [period, setPeriod] = useState("1Y");
  const [benchmarkId, setBenchmarkId] = useState(null);

  const convert = (n) => (currency === "CZK" && rate ? n * rate : n);
  const fmt = (n) => (n == null ? "—" : formatMoney(convert(n), currency));
  const { data: benchmarks } = useQuery({
    queryKey: ["benchmark-catalog"],
    queryFn: fetchBenchmarkCatalog,
    staleTime: 5 * 60 * 1000,
  });

  // Auto-select the catalog's marked default — or fall back to the S&P preset —
  // once the catalog lands. Without this, the first paint uses the server-side
  // default but the dropdown shows nothing selected.
  useEffect(() => {
    if (benchmarkId != null || !benchmarks?.length) return;
    const def =
      benchmarks.find((b) => b.is_default) ||
      benchmarks.find((b) => b.is_preset && b.ticker === "^GSPC") ||
      benchmarks[0];
    if (def) setBenchmarkId(def.id);
  }, [benchmarks, benchmarkId]);

  const { data: metrics = {}, isLoading: ml, error: metricsError, refetch: refetchMetrics, isFetching, dataUpdatedAt: metricsUpdatedAt } = useQuery({
    queryKey: ["risk-metrics", period, benchmarkId],
    queryFn: () => fetchRiskMetrics(period.toLowerCase(), benchmarkId),
  });

  const { data: comparison = {}, isLoading: bl, error: comparisonError, refetch: refetchComparison, dataUpdatedAt: comparisonUpdatedAt } = useQuery({
    queryKey: ["benchmark-comparison", period, benchmarkId],
    queryFn: () => fetchBenchmarkComparison(period.toLowerCase(), benchmarkId),
  });

  const benchName = metrics?.benchmark?.name || comparison?.benchmark?.name || "benchmark";
  const loadedAt = (ts) => (ts ? new Date(ts).toLocaleTimeString() : "—");
  const dataContext = (ts) => `Period: ${period} · Data loaded ${loadedAt(ts)}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Activity size={20} className="text-brand" />
            Portfolio Analytics
          </h1>
          <p className="text-xs text-muted mt-0.5">Return, risk and benchmark comparison</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={benchmarkId ?? ""}
            onChange={(e) => setBenchmarkId(e.target.value || null)}
            className="input min-w-0 max-w-full !w-auto text-xs"
            title="Benchmark for beta / alpha / tracking error"
          >
            {benchmarks?.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
                {b.is_preset ? "" : " ·"}
                {b.is_default ? " (default)" : ""}
              </option>
            ))}
          </select>
          <SegmentedControl
            size="sm"
            aria-label="Analytics period"
            value={period}
            onChange={setPeriod}
            options={PERIODS.map((p) => ({ value: p, label: p }))}
          />
          <button onClick={() => refetchMetrics()} className="btn-ghost flex items-center gap-2 text-sm" disabled={isFetching}>
            <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      <AsyncSection
        isLoading={ml}
        error={metricsError}
        onRetry={() => refetchMetrics()}
        loading={(
          <div className="card animate-pulse h-32 flex items-center justify-center text-muted">
            Calculating risk metrics…
          </div>
        )}
        isEmpty={!metrics || metrics.sharpe_ratio == null}
        empty={(
          <div className="card text-muted text-sm text-center py-12">
            Not enough data to compute risk metrics. Add more transactions and try again.
          </div>
        )}
      >
        <>
          <p className="text-xs text-muted mb-3">{dataContext(metricsUpdatedAt)}</p>
          {metrics.lifetime && (
            <section>
              <h2 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wider flex items-center gap-2">
                <Wallet size={14} className="text-brand" />
                Lifetime — Money-Weighted (your actual cashflows)
              </h2>
              <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
                <MetricCard
                  label="Simple ROI"
                  info={INFO.simple_roi}
                  value={`${metrics.lifetime.simple_roi >= 0 ? "+" : ""}${metrics.lifetime.simple_roi}%`}
                  positive={metrics.lifetime.simple_roi >= 0}
                  negative={metrics.lifetime.simple_roi < 0}
                  sub="Profit ÷ everything you bought"
                />
                <MetricCard
                  label="Annualized IRR (XIRR)"
                  info={INFO.xirr}
                  value={`${metrics.lifetime.xirr >= 0 ? "+" : ""}${metrics.lifetime.xirr}%`}
                  positive={metrics.lifetime.xirr >= 0}
                  negative={metrics.lifetime.xirr < 0}
                  sub="Per-year, weights cashflow timing"
                />
                <MetricCard
                  label="Net Profit"
                  info={INFO.net_profit}
                  value={fmt(metrics.lifetime.net_profit)}
                  positive={metrics.lifetime.net_profit >= 0}
                  negative={metrics.lifetime.net_profit < 0}
                  sub={<NetProfitSub text={`Realized ${fmt(metrics.lifetime.realized_pnl)} · Div ${fmt(metrics.lifetime.dividends)}`} />}
                />
                <MetricCard
                  label="Capital Invested"
                  info={INFO.total_invested}
                  value={fmt(metrics.lifetime.total_invested)}
                  sub={`Value ${fmt(metrics.lifetime.current_value)}`}
                />
              </div>
            </section>
          )}

          <section>
            <h2 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wider flex items-center gap-2">
              <Activity size={14} className="text-brand" />
              {period} — Time-Weighted (investment performance only)
            </h2>
            <div className="grid grid-cols-2 xl:grid-cols-3 gap-4">
              <MetricCard
                label="Total Return"
                info={INFO.total_return}
                value={`${metrics.total_return >= 0 ? "+" : ""}${metrics.total_return}%`}
                positive={metrics.total_return >= 0}
                negative={metrics.total_return < 0}
                sub={metrics.cagr != null ? `CAGR ${metrics.cagr >= 0 ? "+" : ""}${metrics.cagr}%` : null}
              />
              <MetricCard
                label="Ann. Return"
                info={INFO.ann_return}
                value={`${metrics.annualized_return >= 0 ? "+" : ""}${metrics.annualized_return}%`}
                positive={metrics.annualized_return >= 0}
                negative={metrics.annualized_return < 0}
                sub="Arithmetic (mean × 252)"
              />
              <MetricCard
                label="Ann. Volatility"
                info={INFO.ann_vol}
                value={`${metrics.annualized_volatility}%`}
                sub={<RatingBadge value={-metrics.annualized_volatility} thresholds={[-30, -20, -15]} labels={["High", "Moderate", "Low", "Very Low"]} />}
              />
            </div>
          </section>

          <section>
            <h2 className="text-sm font-semibold text-muted mb-1 uppercase tracking-wider flex items-center gap-2">
              <TrendingUp size={14} className="text-brand" />
              vs {benchName} — Active Performance
            </h2>
            <p className="text-xs text-muted mb-3">{dataContext(comparisonUpdatedAt)}</p>
            <AsyncSection
              isLoading={bl}
              error={comparisonError}
              onRetry={() => refetchComparison()}
              loading={(
                <div className="card animate-pulse h-48 flex items-center justify-center text-muted">
                  Loading benchmark comparison…
                </div>
              )}
              isEmpty={!comparison?.series?.length}
              empty={(
                <div className="card text-muted text-sm text-center py-8">
                  No overlapping data with this benchmark over the selected window.
                </div>
              )}
            >
              <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <div className="card xl:col-span-2">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs uppercase tracking-wider text-muted">Cumulative Return</h3>
                    <div className="flex items-center gap-3 text-xs">
                      <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: GAIN_COLOR }} />Portfolio</span>
                      <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full inline-block" style={{ background: NEUTRAL_COLOR }} />{benchName}</span>
                    </div>
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <LineChart data={comparison.series} margin={{ top: 4, right: 12, bottom: 0, left: -8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
                      <XAxis dataKey="date" tick={AXIS_TICK_STYLE} minTickGap={32} />
                      <YAxis tick={AXIS_TICK_STYLE} tickFormatter={(v) => `${v}%`} />
                      <Tooltip
                        contentStyle={TOOLTIP_STYLE}
                        labelStyle={{ color: "var(--muted, #8A93B3)", fontSize: 12 }}
                        formatter={(v, k) => [`${v}%`, k === "portfolio_pct" ? "Portfolio" : k === "benchmark_pct" ? benchName : "Active"]}
                      />
                      <Line type="monotone" dataKey="portfolio_pct" stroke={GAIN_COLOR} strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="benchmark_pct" stroke={NEUTRAL_COLOR} strokeWidth={2} dot={false} />
                      <Line type="monotone" dataKey="active_pct" stroke={CATEGORICAL[0]} strokeWidth={1} strokeDasharray="4 4" dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid grid-cols-1 gap-3 content-start">
                  <MetricCard
                    label="Active Return"
                    info={INFO.active_return}
                    value={`${(comparison.metrics?.active_return ?? 0) >= 0 ? "+" : ""}${comparison.metrics?.active_return ?? 0}%`}
                    positive={(comparison.metrics?.active_return ?? 0) > 0}
                    negative={(comparison.metrics?.active_return ?? 0) < 0}
                    sub={`P ${comparison.metrics?.portfolio_return}% · B ${comparison.metrics?.benchmark_return}%`}
                  />
                </div>
              </div>
            </AsyncSection>
          </section>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="card">
              <h2 className="text-sm font-semibold text-muted mb-4 uppercase tracking-wider flex items-center gap-2">
                <Shield size={14} />
                Risk-Adjusted Returns
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface-hover rounded-lg p-4">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-muted flex items-center gap-1.5">
                      Sharpe Ratio <InfoIcon info={INFO.sharpe} />
                    </span>
                    <RatingBadge value={metrics.sharpe_ratio} thresholds={[0, 1, 2]} labels={["Poor", "Below Avg", "Good", "Excellent"]} />
                  </div>
                  <span className="text-2xl font-bold tabular-nums">{metrics.sharpe_ratio}</span>
                  <p className="text-xs text-muted mt-1">Return per unit of total risk</p>
                </div>
                {metrics.beta != null && (
                  <div className="bg-surface-hover rounded-lg p-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-muted flex items-center gap-1.5">
                        Beta (vs {benchName}) <InfoIcon info={INFO.beta} />
                      </span>
                      <RatingBadge value={-Math.abs(metrics.beta - 1)} thresholds={[-1, -0.3, -0.1]} labels={["Aggressive", "Active", "Moderate", "Benchmark"]} />
                    </div>
                    <span className="text-2xl font-bold tabular-nums">{metrics.beta}</span>
                    <p className="text-xs text-muted mt-1">Benchmark sensitivity</p>
                  </div>
                )}
                {metrics.alpha != null && (
                  <div className="bg-surface-hover rounded-lg p-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-muted flex items-center gap-1.5">
                        Alpha (ann.) <InfoIcon info={INFO.alpha} />
                      </span>
                    </div>
                    <span className={`text-2xl font-bold tabular-nums ${metrics.alpha >= 0 ? "text-gain" : "text-loss"}`}>
                      {metrics.alpha >= 0 ? "+" : ""}{metrics.alpha}%
                    </span>
                    <p className="text-xs text-muted mt-1">Excess return vs {benchName}</p>
                  </div>
                )}
              </div>
            </div>

            <div className="card">
              <h2 className="text-sm font-semibold text-muted mb-4 uppercase tracking-wider flex items-center gap-2">
                <TrendingDown size={14} />
                Drawdown Analysis
              </h2>
              <div className="space-y-4">
                <div className="bg-surface-hover rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-muted flex items-center gap-1.5">
                      Maximum Drawdown <InfoIcon info={INFO.max_dd} />
                    </span>
                    <RatingBadge value={metrics.max_drawdown} thresholds={[-50, -30, -15]} labels={["Severe", "High", "Moderate", "Low"]} />
                  </div>
                  <span className="text-3xl font-bold tabular-nums text-loss">{metrics.max_drawdown}%</span>
                  {metrics.max_drawdown_start && (
                    <p className="text-xs text-muted mt-2">
                      {metrics.max_drawdown_start} → {metrics.max_drawdown_end}
                      {metrics.max_drawdown_recovery && ` (recovered ${metrics.max_drawdown_recovery})`}
                    </p>
                  )}
                </div>
                <div className="bg-surface-hover rounded-lg p-4">
                  <span className="text-xs text-muted flex items-center gap-1.5 mb-1">
                    Current Drawdown <InfoIcon info={INFO.current_dd} />
                  </span>
                  <span
                    className={`text-xl font-bold tabular-nums ${metrics.current_drawdown < -5 ? "text-loss" : metrics.current_drawdown < 0 ? "" : "text-gain"}`}
                    style={metrics.current_drawdown >= -5 && metrics.current_drawdown < 0 ? { color: "var(--chart-3)" } : undefined}
                  >
                    {metrics.current_drawdown}%
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-surface-hover rounded-lg p-3">
                    <span className="text-xs text-muted flex items-center gap-1.5 mb-1">
                      Best Day <InfoIcon info={INFO.best_day} />
                    </span>
                    <span className="text-sm font-bold tabular-nums text-gain">+{metrics.best_day}%</span>
                  </div>
                  <div className="bg-surface-hover rounded-lg p-3">
                    <span className="text-xs text-muted flex items-center gap-1.5 mb-1">
                      Worst Day <InfoIcon info={INFO.worst_day} />
                    </span>
                    <span className="text-sm font-bold tabular-nums text-loss">{metrics.worst_day}%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      </AsyncSection>
    </div>
  );
}
