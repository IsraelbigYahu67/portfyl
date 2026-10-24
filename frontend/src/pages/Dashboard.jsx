import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient, useIsFetching } from "@tanstack/react-query";
import {
  fetchSummary, fetchHoldings, fetchPerformance, fetchBenchmarks, fetchMovers, fetchEarnings, fetchInsiderBuys, fetchDividends,
  fetchCapabilities, fetchRiskMetrics, fetchSectorBreakdown, fetchAllocationTargetDrift, fetchDividendForecast,
} from "../api";
import { useCurrency, usePortfolio } from "../App";
import { useRegisteredActivation } from "../analytics/useRegisteredActivation";
import { fetchEditionDashboardSignals, fetchEditionPlanCapabilities } from "@edition-manifest";
import MetricCard from "../components/MetricCard";
import PerformanceChart from "../components/PerformanceChart";
import { RefreshCw, TrendingUp, TrendingDown, Calendar, LayoutGrid, Lock, PieChart, Activity, Coins } from "lucide-react";
import { formatMoney, formatPercent, formatShortDate } from "../lib/format";
import { AsyncSection, Card, SectionHeader, SkeletonRows, SkeletonChart, EmptyState, DeltaPill, KpiBox } from "../components/ui";
import SegmentedControl from "../components/ui/SegmentedControl";
import Heatmap from "../components/Heatmap";
import { TickerLink } from "../components/TickerLink";
import DashboardGrid from "../components/DashboardGrid";
import PortfolioHero from "../components/PortfolioHero";
import InsightCards from "../components/dashboard/InsightCards";
import CompositionCard from "../components/dashboard/CompositionCard";
import DividendBarsCard from "../components/dashboard/DividendBarsCard";
import InsiderBuysCard from "../components/dashboard/InsiderBuysCard";
import { snapshotNetWorth, summarizePassiveIncome, splitDividendForecast } from "../lib/dashboardSummaries";
import BrokerPositionSnapshot from "../components/BrokerPositionSnapshot";
import { useT212Sync } from "../hooks/useT212Sync";
import { derivePortfolioAlerts } from "../lib/portfolioAlerts";
import { priceFreshnessLine } from "../lib/priceFreshness";
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

// Slot content for an Investor-plan widget on a workspace without
// standard_research: no request is made, the card just points at the plans.
function InvestorOnly({ icon }) {
  return (
    <div className="flex-1 flex">
      <EmptyState
        icon={icon}
        title="Dostupné od plánu Investor"
        action={<Link to="/pricing" className="btn-primary text-xs">Porovnat plány</Link>}
        className="flex-1"
      />
    </div>
  );
}

export default function Dashboard() {
  const { currency, rate } = useCurrency();
  const currentPortfolio = usePortfolio()?.current;
  const t212 = useT212Sync({ portfolioId: currentPortfolio?.id, currency });
  const queryClient = useQueryClient();
  const { recordPopulatedDashboard } = useRegisteredActivation();
  const refreshing = useIsFetching() > 0;
  const [period, setPeriod] = useState("All");
  const [chartMode, setChartMode] = useState("growth");
  const [activeBenchmarks, setActiveBenchmarks] = useState([]);
  const [moverPeriod, setMoverPeriod] = useState("1d");
  const [moverSort, setMoverSort] = useState("pct");
  const [editingLayout, setEditingLayout] = useState(false);

  const toggleBenchmark = (key) =>
    setActiveBenchmarks((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );

  const { data: summary, isLoading: sl, error: summaryError, refetch: refetchSummary } = useQuery({
    queryKey: ["summary", currency],
    queryFn: () => fetchSummary(currency),
  });
  const { data: holdings = [], isLoading: hl, error: holdingsError, refetch: refetchHoldings } = useQuery({
    queryKey: ["holdings", currency],
    queryFn: () => fetchHoldings(currency),
  });
  const { data: perf = [], isLoading: pl, error: performanceError, refetch: refetchPerformance } = useQuery({
    queryKey: ["performance", currency, period],
    queryFn: () => fetchPerformance(currency, period.toLowerCase()),
  });
  const { data: benchmarkData = {} } = useQuery({
    queryKey: ["benchmarks", activeBenchmarks, period],
    queryFn: () => fetchBenchmarks(activeBenchmarks, period.toLowerCase()),
    enabled: activeBenchmarks.length > 0,
  });

  const { data: dividends = [], isLoading: dl, error: dividendsError, refetch: refetchDividends } = useQuery({
    queryKey: ["dividends"],
    queryFn: fetchDividends,
  });

  const { data: editionSignals } = useQuery({
    queryKey: ["edition-dashboard-signals"],
    queryFn: fetchEditionDashboardSignals,
  });

  // Paid-tier widgets (variant A): only query what this workspace can use, and
  // reuse the cache keys of the Analytics / Allocation / Dividends pages.
  const { data: capabilityState, isPending: editionCapabilitiesPending } = useQuery({
    queryKey: ["capabilities"],
    queryFn: fetchCapabilities,
    staleTime: Infinity,
    retry: false,
  });
  // The edition's capabilities, narrowed to the workspace's plan where the
  // edition has plans (null = no narrowing). Without this a cloud Free
  // workspace would request Investor/Pro endpoints and get 403 upgrade prompts.
  const { data: planCapabilities, isPending: planCapabilitiesPending, isError: planCapabilitiesError } = useQuery({
    queryKey: ["plan-capabilities"],
    queryFn: fetchEditionPlanCapabilities,
    staleTime: 60 * 1000,
    retry: false,
  });
  const capabilitiesPending = editionCapabilitiesPending || planCapabilitiesPending;
  // A plan that is still loading or failed to load fails closed to the free
  // widgets, so no paid endpoint is requested before the plan is known.
  const planFilter = planCapabilitiesPending || planCapabilitiesError ? [] : planCapabilities;
  const capabilities = new Set(
    (capabilityState?.capabilities || []).filter(
      (key) => planFilter == null || planFilter.includes(key)
    )
  );
  const hasAnalytics = capabilities.has("portfolio_analytics");
  const hasDividendAnalysis = capabilities.has("dividend_analysis");
  // Insider buys are a Pro (advanced_research) endpoint; workspaces without it
  // keep the Top 10 Holdings card in that slot instead of a 403 error card.
  const hasResearch = capabilities.has("advanced_research");
  // Movers, earnings and the heatmap are Investor (standard_research)
  // endpoints; on Free they would 403 and raise the upgrade prompt on load.
  const hasStandardResearch = capabilities.has("standard_research");

  const { data: movers, isLoading: ml, error: moversError, refetch: refetchMovers } = useQuery({
    queryKey: ["movers", moverPeriod],
    queryFn: () => fetchMovers(moverPeriod),
    enabled: hasStandardResearch,
  });
  // The %/$ toggle switches between two server-side rankings of the WHOLE
  // portfolio — re-sorting the five %-ranked rows would hide bigger money
  // movers. Older API responses lack value_* lists, so fall back to %.
  const moverGainers = (moverSort === "value" ? movers?.value_gainers : null) ?? movers?.gainers ?? [];
  const moverLosers = (moverSort === "value" ? movers?.value_losers : null) ?? movers?.losers ?? [];

  const { data: earnings = [], isLoading: el, error: earningsError, refetch: refetchEarnings } = useQuery({
    queryKey: ["earnings"],
    queryFn: fetchEarnings,
    enabled: hasStandardResearch,
  });

  const { data: insiderBuys = [], isLoading: il, error: insiderError, refetch: refetchInsider } = useQuery({
    queryKey: ["insider-buys"],
    queryFn: fetchInsiderBuys,
    staleTime: 30 * 60 * 1000,
    enabled: hasResearch,
  });

  const { data: riskMetrics, isLoading: rl, isError: riskError } = useQuery({
    queryKey: ["risk-metrics", "1Y", null],
    queryFn: () => fetchRiskMetrics("1y", null),
    enabled: hasAnalytics,
    staleTime: 10 * 60 * 1000,
  });
  const { data: sectorBreakdown, isLoading: sbl, error: sectorError, refetch: refetchSectors } = useQuery({
    queryKey: ["sector-breakdown", currency],
    queryFn: () => fetchSectorBreakdown(currency),
    enabled: hasAnalytics,
  });
  const { data: targetDrift } = useQuery({
    queryKey: ["allocation-target-drift", currency],
    queryFn: () => fetchAllocationTargetDrift(currency),
    enabled: hasAnalytics,
    retry: false,
  });
  const { data: dividendForecast, isLoading: fl, error: forecastError, refetch: refetchForecast } = useQuery({
    queryKey: ["dividends-forecast"],
    queryFn: fetchDividendForecast,
    enabled: hasDividendAnalysis,
  });

  const today = new Date().toISOString().slice(0, 10);
  const passive = summarizePassiveIncome({ dividends, holdings, totalValue: summary?.total_value ?? null, today });
  // The forecast is in USD; `rate` is CZK per USD.
  const forecastRate = currency === "CZK" && rate ? rate : 1;
  const { received: dividendsReceived, upcoming: dividendsUpcoming } = splitDividendForecast(dividendForecast, {
    monthIndex: new Date().getMonth(),
    usdRate: forecastRate,
  });
  const forecastYear = dividendForecast?.year ?? new Date().getFullYear();

  const irr = riskMetrics?.lifetime?.xirr;
  let profitSub = summary ? `${formatMoney(summary.total_invested, currency)} invested` : null;
  if (hasAnalytics && Number.isFinite(irr)) profitSub = `IRR ${formatPercent(irr)} · ${profitSub}`;
  else if (hasAnalytics && rl) profitSub = `IRR calculating… · ${profitSub}`;
  else if (hasAnalytics && riskError) profitSub = `IRR unavailable · ${profitSub}`;

  const passiveSub = [
    passive.annualIncome > 0 ? `${formatMoney(passive.annualIncome, currency)} a year` : "No dividend payers yet",
    passive.next ? `next ex-date ${passive.next.ticker} ${formatShortDate(passive.next.date)}` : null,
  ].filter(Boolean).join(" · ");

  const alerts = derivePortfolioAlerts({
    holdings,
    dividends,
    taxReport: editionSignals?.taxReport ?? null,
    earnings,
    today,
  });
  const alertsLoading = dl;
  const alertsError = dividendsError;

  // Keyed on a boolean, not the summary/holdings objects themselves, so a
  // same-shape refetch (e.g. currency change) doesn't re-fire this effect.
  const hasPopulatedDashboard = !sl && !hl && !summaryError && !holdingsError && Boolean(summary) && holdings.length > 0;
  useEffect(() => {
    if (hasPopulatedDashboard) recordPopulatedDashboard();
  }, [hasPopulatedDashboard, recordPopulatedDashboard]);


  const heroSeries = (perf || [])
    .map((p) => ({ value: p.value }))
    .filter((p) => Number.isFinite(p.value));

  // Server now returns values in the requested currency, so no client-side
  // multiplication is needed. The convert() shim is kept for components that
  // are still currency-agnostic.
  const convert = (n) => n;


  const snapshot = snapshotNetWorth({
    positions: t212.positionsQuery.data,
    historyRun: t212.historyRun,
    currency,
  });

  const pnlPos = summary?.total_pnl >= 0;
  const priceLine = priceFreshnessLine(summary);

  return (
    <div className="space-y-6 hover-pop-zone">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div>
          <h1 className="text-xl font-bold" tabIndex={-1}>Dashboard</h1>
          {priceLine && <p className="text-xs text-muted mt-0.5">{priceLine}</p>}
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

      {/* Variant A: the Net Worth hero stays the anchor, with profit and
          passive income beside it. */}
      <div className="grid gap-6 xl:grid-cols-[minmax(0,2.1fr)_minmax(0,1fr)]">
        <AsyncSection
          isLoading={sl}
          error={summaryError}
          onRetry={() => refetchSummary()}
          loading={<PortfolioHero loading currency={currency} series={[]} />}
        >
          <PortfolioHero summary={summary} snapshot={snapshot} currency={currency} series={heroSeries} />
        </AsyncSection>
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-1">
          <KpiBox
            icon={TrendingUp}
            label="Total profit"
            loading={sl}
            value={summary ? `${summary.total_pnl >= 0 ? "+" : ""}${formatMoney(summary.total_pnl, currency)}` : null}
            delta={summary ? { pct: summary.total_pnl_percent } : null}
            sub={profitSub}
          />
          <KpiBox
            icon={Coins}
            label="Passive income"
            loading={sl || dl}
            value={passive.yieldPct == null ? "—" : `${passive.yieldPct.toFixed(2)}%`}
            sub={passiveSub}
          />
        </div>
      </div>

      {t212.connected && (
        <div className="space-y-2">
          <BrokerPositionSnapshot query={t212.positionsQuery} variant="summary" />
          <p className="text-xs text-muted">Historical performance uses imported transactions and may lag behind this current snapshot.</p>
        </div>
      )}

      <DashboardGrid editing={editingLayout} onEditToggle={() => setEditingLayout(!editingLayout)}>
        {{
          attention: (
            <Card className="animate-fade-up">
              <SectionHeader icon={Activity}>Attention signals</SectionHeader>
              <AsyncSection
                isLoading={alertsLoading}
                error={alertsError}
                onRetry={() => refetchDividends()}
                loading={<SkeletonRows rows={3} cols={1} />}
              >
                <InsightCards alerts={alerts} />
              </AsyncSection>
            </Card>
          ),

          performance: (
            <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "100ms" }}>
              <SectionHeader icon={TrendingUp} action={<div className="flex flex-wrap items-center gap-3">
                  <div className="flex gap-0.5 bg-surface-hover rounded-lg p-0.5">
                    {["value", "growth"].map((m) => (
                      <button
                        key={m}
                        onClick={() => setChartMode(m)}
                        aria-pressed={chartMode === m}
                        className={`px-3 py-2 text-xs rounded-md font-medium transition-colors md:px-2.5 md:py-1 ${
                          chartMode === m
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        {m === "value" ? "Value" : "Growth %"}
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {PERIODS.map((p) => (
                      <button
                        key={p}
                        onClick={() => setPeriod(p)}
                        aria-pressed={period === p}
                        className={`px-3 py-2 text-xs rounded-md font-medium transition-colors md:px-2.5 md:py-1 ${
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
                    aria-pressed={activeBenchmarks.includes(b.key)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-md font-medium transition-colors border md:py-1 ${
                      activeBenchmarks.includes(b.key)
                        ? "border-hairline bg-surface-card text-ink shadow-sm"
                        : "border-transparent text-muted hover:text-ink"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: b.color, opacity: activeBenchmarks.includes(b.key) ? 1 : 0.5 }}
                    />
                    {b.label}
                  </button>
                ))}
              </div>
              <AsyncSection
                isLoading={pl}
                error={performanceError}
                onRetry={() => refetchPerformance()}
                loading={<div className="flex-1"><SkeletonChart height={256} /></div>}
              >
                <PerformanceChart
                  data={perf}
                  currency={currency}
                  mode={chartMode}
                  benchmarks={benchmarkData}
                  benchmarkMeta={BENCHMARKS.filter((b) => activeBenchmarks.includes(b.key))}
                />
              </AsyncSection>
            </Card>
          ),

          composition: hasAnalytics ? (
            <Card className="animate-fade-up">
              <AsyncSection
                isLoading={sbl}
                error={sectorError}
                onRetry={() => refetchSectors()}
                loading={<SkeletonChart height={280} />}
              >
                <CompositionCard breakdown={sectorBreakdown} targetGroups={targetDrift?.groups || []} currency={currency} />
              </AsyncSection>
            </Card>
          ) : null,

          concentration: (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {capabilitiesPending || hasResearch ? (
              <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "200ms" }}>
                <InsiderBuysCard
                  buys={insiderBuys}
                  isLoading={capabilitiesPending || il}
                  error={insiderError}
                  onRetry={() => refetchInsider()}
                />
              </Card>
              ) : (
              <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "200ms" }}>
                <SectionHeader icon={PieChart}>Top 10 Holdings</SectionHeader>
                <AsyncSection
                  isLoading={hl}
                  error={holdingsError}
                  onRetry={() => refetchHoldings()}
                  loading={<SkeletonRows rows={8} cols={3} />}
                  isEmpty={holdings.length === 0}
                  empty={<EmptyState icon={PieChart} title="No holdings yet" hint="Import your transactions to see your top positions." action={<a href="/import" className="btn-primary text-xs">Import CSV</a>} />}
                >
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
                </AsyncSection>
              </Card>
              )}
              <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "150ms" }}>
                <SectionHeader icon={LayoutGrid}>Heatmap</SectionHeader>
                {!capabilitiesPending && !hasStandardResearch ? (
                  <InvestorOnly icon={LayoutGrid} />
                ) : (
                  <AsyncSection
                    isLoading={capabilitiesPending || hl}
                    error={holdingsError}
                    onRetry={() => refetchHoldings()}
                    loading={<div className="flex-1"><SkeletonChart height={256} /></div>}
                    isEmpty={holdings.length === 0}
                    empty={<div className="flex-1 flex"><EmptyState icon={LayoutGrid} title="No holdings to map" hint="Import transactions to see your heatmap." /></div>}
                  >
                    <Heatmap />
                  </AsyncSection>
                )}
              </Card>

            </div>
          ),

          movers: (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "350ms" }}>
                <SectionHeader icon={Activity} action={!capabilitiesPending && !hasStandardResearch ? null : <div className="flex items-center gap-3">
                    <SegmentedControl
                      aria-label="Sort movers by"
                      size="sm"
                      value={moverSort}
                      onChange={setMoverSort}
                      options={[{ value: "pct", label: "%" }, { value: "value", label: "$" }]}
                    />
                    <SegmentedControl
                      aria-label="Movers period"
                      value={moverPeriod}
                      onChange={setMoverPeriod}
                      options={MOVER_PERIODS.map((p) => ({ value: p.key, label: p.label }))}
                    />
                  </div>}>Top Movers</SectionHeader>
                {!capabilitiesPending && !hasStandardResearch ? (
                  <InvestorOnly icon={Activity} />
                ) : (
                <AsyncSection
                  isLoading={capabilitiesPending || ml}
                  error={moversError}
                  onRetry={() => refetchMovers()}
                  loading={<SkeletonRows rows={6} cols={3} />}
                  isEmpty={!movers?.gainers?.length && !movers?.losers?.length}
                  empty={<EmptyState icon={Activity} title="No movers yet" hint="Import transactions to track daily gainers and losers." />}
                >
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2 gap-x-8 gap-y-6">
                    {[
                      { key: "gainers", label: "Gainers", Icon: TrendingUp, tone: "text-gain", rows: moverGainers },
                      { key: "losers", label: "Losers", Icon: TrendingDown, tone: "text-loss", rows: moverLosers },
                    ].map(({ key, label, Icon, tone, rows }) => (
                      <div key={key} className="min-w-0">
                        <h3 className={`eyebrow mb-3 flex items-center gap-1.5 ${tone}`}>
                          <Icon size={14} /> {label}
                        </h3>
                        {rows.length === 0 ? (
                          <p className="text-muted text-xs">No data</p>
                        ) : (
                          <ul className="space-y-1">
                            {rows.map((m) => (
                              <li
                                key={m.ticker}
                                className="grid grid-cols-[3.25rem_minmax(0,1fr)_auto_5.75rem] items-center gap-x-3 rounded-xl px-2 py-1.5 text-sm hover:bg-surface-hover transition-colors"
                              >
                                <TickerLink ticker={m.ticker} className="font-mono font-semibold text-left truncate" />
                                <span className="min-w-0 truncate text-muted" title={m.name}>{m.name}</span>
                                <span className={`tabular-nums whitespace-nowrap text-right font-medium ${m.period_pnl >= 0 ? "text-gain" : "text-loss"}`}>
                                  {formatMoney(m.period_pnl, m.currency)}
                                </span>
                                <span className="flex justify-end">
                                  <DeltaPill pct={m.change_pct} value={null} size="sm" className="whitespace-nowrap" />
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                </AsyncSection>
                )}
              </Card>
              <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "300ms" }}>
                <SectionHeader icon={Calendar}>Earnings Calendar</SectionHeader>
                {!capabilitiesPending && !hasStandardResearch ? (
                  <InvestorOnly icon={Calendar} />
                ) : (
                <AsyncSection
                  isLoading={capabilitiesPending || el}
                  error={earningsError}
                  onRetry={() => refetchEarnings()}
                  loading={<SkeletonRows rows={6} cols={3} />}
                  isEmpty={earnings.length === 0}
                  empty={<EmptyState icon={Calendar} title="No upcoming earnings" hint="None of your current holdings report soon." />}
                >
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
                </AsyncSection>
                )}
              </Card>
            </div>
          ),

          dividends: hasDividendAnalysis ? (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <Card className="h-full animate-fade-up">
                <AsyncSection isLoading={fl} error={forecastError} onRetry={() => refetchForecast()} loading={<SkeletonChart height={220} />}>
                  <DividendBarsCard title="Dividends received" half={dividendsReceived} totalLabel={`${forecastYear} so far`} currency={currency} tone="accent" emptyHint="No dividends received this year yet." leadStat={{ label: "All time", amount: dividendsReceived.allTime }} />
                </AsyncSection>
              </Card>
              <Card className="h-full animate-fade-up">
                <AsyncSection isLoading={fl} error={forecastError} onRetry={() => refetchForecast()} loading={<SkeletonChart height={220} />}>
                  <DividendBarsCard title="Upcoming payments" half={dividendsUpcoming} totalLabel="Next 12 months" currency={currency} emptyHint="No dividends expected in the next 12 months." trailStat={{ label: "Daily average", amount: dividendsUpcoming.dailyAverage }} />
                </AsyncSection>
              </Card>
            </div>
          ) : null,
        }}
      </DashboardGrid>
    </div>
  );
}
