import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient, useIsFetching } from "@tanstack/react-query";
import {
  fetchSummary, fetchHoldings, fetchPerformance, fetchBenchmarks, fetchMovers, fetchEarnings, fetchInsiderBuys, fetchDividends,
  fetchCapabilities, fetchRiskMetrics, fetchSectorBreakdown, fetchDividendForecast,
} from "../api";
import { useCurrency, usePortfolio } from "../App";
import { useAuth } from "../auth/AuthProvider";
import { convertFromUsd, currencySymbol } from "../lib/displayCurrency";
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
import WelcomePanel from "../components/dashboard/WelcomePanel";
import DemoDataBanner from "../components/dashboard/DemoDataBanner";
import {
  dismissGettingStarted, gettingStartedItems, markGettingStartedVisited, readGettingStarted,
} from "../lib/gettingStarted";
import { preferencesConfirmed } from "../lib/preferencesConfirmation";
import CompositionCard from "../components/dashboard/CompositionCard";
import DividendBarsCard from "../components/dashboard/DividendBarsCard";
import InsiderBuysCard from "../components/dashboard/InsiderBuysCard";
import { snapshotNetWorth, summarizePassiveIncome, splitDividendForecast } from "../lib/dashboardSummaries";
import { useT212Sync } from "../hooks/useT212Sync";
import { derivePortfolioAlerts } from "../lib/portfolioAlerts";
import { priceFreshnessLine } from "../lib/priceFreshness";
import { CATEGORICAL } from "../lib/chartTheme";
import { msg, useT } from "../i18n/I18nProvider";

const MOVER_PERIODS = [
  { key: "1d", label: msg("Today") },
  { key: "1w", label: msg("Week") },
  { key: "1m", label: msg("Month") },
];

const PERIODS = ["7D", "MTD", "1M", "3M", "YTD", "1Y", "All"];
// Stable index-per-benchmark mapping so the same benchmark always gets the
// same color across sessions.
const BENCHMARKS = [
  { key: "sp500", label: "S&P 500", color: CATEGORICAL[0] },
  { key: "nasdaq100", label: "NASDAQ 100", color: CATEGORICAL[1] },
  { key: "stoxx50", label: "STOXX 50", color: CATEGORICAL[3] },
  { key: "bitcoin", label: "Bitcoin", color: CATEGORICAL[4] },
];

// Slot content for an Investor-plan widget on a workspace without
// standard_research: no request is made, the card just points at the plans.
function InvestorOnly({ icon }) {
  const t = useT();
  return (
    <div className="flex-1 flex">
      <EmptyState
        icon={icon}
        title={t("Available from the Investor plan")}
        action={<Link to="/pricing" className="btn-primary text-xs">{t("Compare plans")}</Link>}
        className="flex-1"
      />
    </div>
  );
}

export default function Dashboard() {
  const t = useT();
  const { currency, rate } = useCurrency();
  const { current: currentPortfolio, portfolios } = usePortfolio() ?? {};
  const workspaceId = useAuth().currentWorkspace?.id;
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
  // Bumped after a visit/dismissal so the stored checklist state is re-read.
  const [gettingStartedVersion, setGettingStartedVersion] = useState(0);

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
    queryKey: ["movers", moverPeriod, currency],
    queryFn: () => fetchMovers(moverPeriod, currency),
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
  const { data: dividendForecast, isLoading: fl, error: forecastError, refetch: refetchForecast } = useQuery({
    queryKey: ["dividends-forecast"],
    queryFn: fetchDividendForecast,
    enabled: hasDividendAnalysis,
  });

  const today = new Date().toISOString().slice(0, 10);
  const passive = summarizePassiveIncome({ dividends, holdings, totalValue: summary?.total_value ?? null, today });
  // The forecast is in USD; `rate` is display units per USD.
  const forecastRate = convertFromUsd(1, currency, rate);
  const { received: dividendsReceived, upcoming: dividendsUpcoming } = splitDividendForecast(dividendForecast, {
    monthIndex: new Date().getMonth(),
    usdRate: forecastRate,
  });
  const forecastYear = dividendForecast?.year ?? new Date().getFullYear();

  const gettingStarted = useMemo(
    () => readGettingStarted(workspaceId),
    // gettingStartedVersion is not read inside: bumping it re-reads storage after a write.
    [workspaceId, gettingStartedVersion],
  );
  const gettingStartedList = gettingStartedItems({
    portfolios,
    preferencesConfirmed: preferencesConfirmed(),
    visited: gettingStarted.visited,
  });
  // One line of substance for the panel: dividend income when there is some,
  // otherwise how many positions the portfolio holds. Nothing while loading.
  let welcomeInsight = null;
  if (!hl && !dl && holdings.length > 0) {
    welcomeInsight = passive.annualIncome > 0
      ? t("Over the last 12 months your dividends brought you {amount}.", { amount: formatMoney(passive.annualIncome, currency) })
      : t("You hold {count} positions.", { count: holdings.length });
  }

  const irr = riskMetrics?.lifetime?.xirr;
  let profitSub = summary ? t("{amount} invested", { amount: formatMoney(summary.total_invested, currency) }) : null;
  if (hasAnalytics && Number.isFinite(irr)) profitSub = `${t("IRR {value}", { value: formatPercent(irr) })} · ${profitSub}`;
  else if (hasAnalytics && rl) profitSub = `${t("IRR calculating…")} · ${profitSub}`;
  else if (hasAnalytics && riskError) profitSub = `${t("IRR unavailable")} · ${profitSub}`;

  const passiveSub = [
    passive.annualIncome > 0
      ? t("{amount} a year", { amount: formatMoney(passive.annualIncome, currency) })
      : t("No dividend payers yet"),
    passive.next
      ? t("next ex-date {ticker} {date}", { ticker: passive.next.ticker, date: formatShortDate(passive.next.date) })
      : null,
  ].filter(Boolean).join(" · ");

  const alerts = derivePortfolioAlerts({
    holdings,
    dividends,
    taxReport: editionSignals?.taxReport ?? null,
    earnings,
    today,
    t,
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
  const priceLine = priceFreshnessLine(summary, { t });

  // The cards of the "concentration" row. Desktop renders them side by side
  // inside that one widget; a phone gets each as its own collapsible row
  // (heatmap first, right under the passive-income box), see DashboardGrid.
  const showInsiderBuys = capabilitiesPending || hasResearch;
  const insiderBuysCard = (
    <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "200ms" }}>
      <InsiderBuysCard
        buys={insiderBuys}
        isLoading={capabilitiesPending || il}
        error={insiderError}
        onRetry={() => refetchInsider()}
      />
    </Card>
  );
  const topHoldingsCard = (
    <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "200ms" }}>
      <SectionHeader icon={PieChart}>{t("Top 10 Holdings")}</SectionHeader>
      <AsyncSection
        isLoading={hl}
        error={holdingsError}
        onRetry={() => refetchHoldings()}
        loading={<SkeletonRows rows={8} cols={3} />}
        isEmpty={holdings.length === 0}
        empty={<EmptyState icon={PieChart} title={t("No holdings yet")} hint={t("Import your transactions to see your top positions.")} action={<a href="/import" className="btn-primary text-xs">{t("Import CSV")}</a>} />}
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
  );
  const heatmapCard = (
    <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "150ms" }}>
      <SectionHeader icon={LayoutGrid}>{t("Heatmap")}</SectionHeader>
      {!capabilitiesPending && !hasStandardResearch ? (
        <InvestorOnly icon={LayoutGrid} />
      ) : (
        <AsyncSection
          isLoading={capabilitiesPending || hl}
          error={holdingsError}
          onRetry={() => refetchHoldings()}
          loading={<div className="flex-1"><SkeletonChart height={256} /></div>}
          isEmpty={holdings.length === 0}
          empty={<div className="flex-1 flex"><EmptyState icon={LayoutGrid} title={t("No holdings to map")} hint={t("Import transactions to see your heatmap.")} /></div>}
        >
          <Heatmap />
        </AsyncSection>
      )}
    </Card>
  );

  return (
    <div className="space-y-6 hover-pop-zone">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <div>
          <h1 className="text-xl font-bold" tabIndex={-1}>{t("Dashboard")}</h1>
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
            {editingLayout ? t("Lock Layout") : t("Customize")}
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
            {t("Refresh")}
          </button>
        </div>
      </div>

      <DemoDataBanner portfolio={currentPortfolio} />
      {!gettingStarted.dismissed && (
        <WelcomePanel
          items={gettingStartedList}
          insight={welcomeInsight}
          onVisit={(id) => {
            markGettingStartedVisited(workspaceId, id);
            setGettingStartedVersion((v) => v + 1);
          }}
          onDismiss={() => {
            dismissGettingStarted(workspaceId);
            setGettingStartedVersion((v) => v + 1);
          }}
        />
      )}

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
            label={t("Total profit")}
            loading={sl}
            value={summary ? `${summary.total_pnl >= 0 ? "+" : ""}${formatMoney(summary.total_pnl, currency)}` : null}
            delta={summary ? { pct: summary.total_pnl_percent } : null}
            sub={profitSub}
          />
          <KpiBox
            icon={Coins}
            label={t("Passive income")}
            loading={sl || dl}
            value={passive.yieldPct == null ? "—" : `${passive.yieldPct.toFixed(2)}%`}
            sub={passiveSub}
          />
        </div>
      </div>

      <DashboardGrid editing={editingLayout} onEditToggle={() => setEditingLayout(!editingLayout)}>
        {{
          attention: (
            <Card className="animate-fade-up">
              <SectionHeader icon={Activity}>{t("Attention signals")}</SectionHeader>
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
                  <div className="flex shrink-0 gap-0.5 bg-surface-hover rounded-lg p-0.5">
                    {["value", "growth"].map((m) => (
                      <button
                        key={m}
                        onClick={() => setChartMode(m)}
                        aria-pressed={chartMode === m}
                        className={`min-h-10 px-3 py-2 text-xs rounded-md md:min-h-0 font-medium transition-colors md:px-2.5 md:py-1 ${
                          chartMode === m
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        {m === "value" ? t("Value") : t("Growth %")}
                      </button>
                    ))}
                  </div>
                  {/* One row that scrolls sideways on a phone instead of dropping "All" onto a second line. */}
                  <div className="flex max-w-full gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    {PERIODS.map((p) => (
                      <button
                        key={p}
                        onClick={() => setPeriod(p)}
                        aria-pressed={period === p}
                        className={`min-h-10 shrink-0 px-3 py-2 text-xs rounded-md md:min-h-0 font-medium transition-colors md:px-2.5 md:py-1 ${
                          period === p
                            ? "bg-surface-card text-brand font-semibold shadow-sm"
                            : "text-muted hover:text-ink"
                        }`}
                      >
                        {p === "All" ? t("All") : p}
                      </button>
                    ))}
                  </div>
                </div>}>
                {t("Portfolio Performance")}
              </SectionHeader>
              <div className="flex gap-1.5 mb-4 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden md:flex-wrap">
                {BENCHMARKS.map((b) => (
                  <button
                    key={b.key}
                    onClick={() => toggleBenchmark(b.key)}
                    aria-pressed={activeBenchmarks.includes(b.key)}
                    className={`inline-flex min-h-10 shrink-0 items-center gap-1.5 whitespace-nowrap px-2.5 py-1.5 text-xs rounded-md font-medium transition-colors border md:min-h-0 md:py-1 ${
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
                <CompositionCard breakdown={sectorBreakdown} currency={currency} />
              </AsyncSection>
            </Card>
          ) : null,

          // Desktop keeps the pair in one widget. A phone shows each card as its
          // own collapsible row; the top-10 fallback stands in for insider buys
          // when insider data is not on the plan.
          concentration: (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {showInsiderBuys ? insiderBuysCard : topHoldingsCard}
              {heatmapCard}
            </div>
          ),
          heatmap: heatmapCard,
          insiderBuys: showInsiderBuys ? insiderBuysCard : null,
          topHoldings: showInsiderBuys ? null : topHoldingsCard,

          movers: (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <Card className="h-full flex flex-col animate-fade-up" style={{ animationDelay: "350ms" }}>
                <SectionHeader icon={Activity} action={!capabilitiesPending && !hasStandardResearch ? null : <div className="flex items-center gap-3">
                    <SegmentedControl
                      aria-label={t("Sort movers by")}
                      size="sm"
                      value={moverSort}
                      onChange={setMoverSort}
                      options={[{ value: "pct", label: "%" }, { value: "value", label: currencySymbol(currency) }]}
                    />
                    <SegmentedControl
                      aria-label={t("Movers period")}
                      value={moverPeriod}
                      onChange={setMoverPeriod}
                      options={MOVER_PERIODS.map((p) => ({ value: p.key, label: t(p.label) }))}
                    />
                  </div>}>{t("Top Movers")}</SectionHeader>
                {!capabilitiesPending && !hasStandardResearch ? (
                  <InvestorOnly icon={Activity} />
                ) : (
                <AsyncSection
                  isLoading={capabilitiesPending || ml}
                  error={moversError}
                  onRetry={() => refetchMovers()}
                  loading={<SkeletonRows rows={6} cols={3} />}
                  isEmpty={!movers?.gainers?.length && !movers?.losers?.length}
                  empty={<EmptyState icon={Activity} title={t("No movers yet")} hint={t("Import transactions to track daily gainers and losers.")} />}
                >
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2 gap-x-8 gap-y-6">
                    {[
                      { key: "gainers", label: t("Gainers"), Icon: TrendingUp, tone: "text-gain", rows: moverGainers },
                      { key: "losers", label: t("Losers"), Icon: TrendingDown, tone: "text-loss", rows: moverLosers },
                    ].map(({ key, label, Icon, tone, rows }) => (
                      <div key={key} className="min-w-0">
                        <h3 className={`eyebrow mb-3 flex items-center gap-1.5 ${tone}`}>
                          <Icon size={14} /> {label}
                        </h3>
                        {rows.length === 0 ? (
                          <p className="text-muted text-xs">{t("No data")}</p>
                        ) : (
                          <ul className="space-y-1">
                            {rows.map((m) => (
                              <li
                                key={m.ticker}
                                className="grid grid-cols-[3.25rem_minmax(0,1fr)_auto_5.75rem] items-center gap-x-3 rounded-xl px-2 py-1.5 text-sm hover:bg-surface-hover transition-colors"
                              >
                                <TickerLink ticker={m.ticker} className="font-mono font-semibold text-left truncate" />
                                <span className="min-w-0 truncate text-muted" title={m.name}>{m.name}</span>
                                {(() => {
                                  // The P/L in the display currency; older API
                                  // responses lack period_pnl_display, so fall
                                  // back to the stock's own currency.
                                  const inDisplay = m.display_currency === currency && Number.isFinite(m.period_pnl_display);
                                  const pnl = inDisplay ? m.period_pnl_display : m.period_pnl;
                                  return (
                                    <span className={`tabular-nums whitespace-nowrap text-right font-medium ${pnl >= 0 ? "text-gain" : "text-loss"}`}>
                                      {formatMoney(pnl, inDisplay ? currency : m.currency)}
                                    </span>
                                  );
                                })()}
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
                <SectionHeader icon={Calendar}>{t("Earnings Calendar")}</SectionHeader>
                {!capabilitiesPending && !hasStandardResearch ? (
                  <InvestorOnly icon={Calendar} />
                ) : (
                <AsyncSection
                  isLoading={capabilitiesPending || el}
                  error={earningsError}
                  onRetry={() => refetchEarnings()}
                  loading={<SkeletonRows rows={6} cols={3} />}
                  isEmpty={earnings.length === 0}
                  empty={<EmptyState icon={Calendar} title={t("No upcoming earnings")} hint={t("None of your current holdings report soon.")} />}
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
                  <DividendBarsCard title={t("Dividends received")} half={dividendsReceived} totalLabel={t("{year} so far", { year: forecastYear })} currency={currency} tone="accent" emptyHint={t("No dividends received this year yet.")} leadStat={{ label: t("All time"), amount: dividendsReceived.allTime }} />
                </AsyncSection>
              </Card>
              <Card className="h-full animate-fade-up">
                <AsyncSection isLoading={fl} error={forecastError} onRetry={() => refetchForecast()} loading={<SkeletonChart height={220} />}>
                  <DividendBarsCard title={t("Upcoming payments")} half={dividendsUpcoming} totalLabel={t("Next 12 months")} currency={currency} emptyHint={t("No dividends expected in the next 12 months.")} trailStat={{ label: t("Daily average"), amount: dividendsUpcoming.dailyAverage }} />
                </AsyncSection>
              </Card>
            </div>
          ) : null,
        }}
      </DashboardGrid>
    </div>
  );
}
