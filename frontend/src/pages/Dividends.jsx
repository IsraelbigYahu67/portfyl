import { useQuery } from "@tanstack/react-query";
import { fetchDividends, fetchDividendForecast, fetchDividendGrowth } from "../api";
import { AlertTriangle, CalendarDays, RefreshCw, TrendingUp } from "lucide-react";
import { useCurrency } from "../App";
import { useStockDetail } from "../components/StockDetail";
import MetricCard from "../components/MetricCard";
import DividendBarsCard from "../components/dashboard/DividendBarsCard";
import { splitDividendForecast } from "../lib/dashboardSummaries";
import { formatMoney, formatQuantity, formatTableDate } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiError";
import { AsyncSection, Badge, Card, SkeletonChart } from "../components/ui";

const today = new Date().toISOString().slice(0, 10);

function statusBadge(row) {
  if (row.date_status === "inconsistent") return <Badge tone="loss" size="sm">Needs review</Badge>;
  if (!row.ex_date) return <Badge tone="neutral" size="sm">Date unavailable</Badge>;
  const diff = Math.ceil((new Date(row.ex_date) - new Date(today)) / 86400000);
  if (diff < 0) return <Badge tone="neutral" size="sm">Past</Badge>;
  if (diff === 0) return <Badge tone="warn" size="sm">Today</Badge>;
  if (diff <= 7) return <Badge tone="warn" size="sm">In {diff}d</Badge>;
  if (diff <= 30) return <Badge tone="brand" size="sm">In {diff}d</Badge>;
  return <Badge tone="neutral" size="sm">In {diff}d</Badge>;
}

function isKnownUpcoming(row, currentDay) {
  return row.date_status !== "inconsistent" && row.ex_date && row.ex_date >= currentDay;
}

export default function Dividends() {
  const { currency: displayCurrency = "USD", rate } = useCurrency() ?? {};
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["dividends"],
    queryFn: fetchDividends,
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: forecast,
    isLoading: forecastLoading,
    isFetching: forecastFetching,
    error: forecastError,
    refetch: refetchForecast,
  } = useQuery({
    queryKey: ["dividends-forecast"],
    queryFn: fetchDividendForecast,
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: growth,
    isLoading: growthLoading,
    refetch: refetchGrowth,
  } = useQuery({
    queryKey: ["dividend-growth"],
    queryFn: fetchDividendGrowth,
    staleTime: 5 * 60 * 1000,
  });

  const rows = data ?? [];
  const needsReview = rows.filter((row) => row.date_status === "inconsistent" || !row.ex_date);
  const knownUpcoming = rows.filter(
    (row) => !needsReview.includes(row) && isKnownUpcoming(row, today),
  );
  const past = rows.filter(
    (row) => !needsReview.includes(row) && !knownUpcoming.includes(row),
  );
  // USD estimates are folded into the display currency with the same rate the
  // dividend charts use (`rate` is CZK per USD). Other currencies stay separate.
  const usdRate = displayCurrency === "CZK" && rate ? rate : null;
  const estimatedByCurrency = rows.reduce((totals, row) => {
    if (row.income_status === "estimated" && row.annual_income != null) {
      const rowCurrency = row.currency || "USD";
      const converts = usdRate && rowCurrency === "USD";
      const key = converts ? displayCurrency : rowCurrency;
      const amount = Number(row.annual_income) * (converts ? usdRate : 1);
      totals[key] = (totals[key] || 0) + amount;
    }
    return totals;
  }, {});
  const estimatedTotals = Object.entries(estimatedByCurrency);
  if (!estimatedTotals.length && rows.length) {
    estimatedTotals.push([usdRate ? displayCurrency : rows[0].currency || "USD", 0]);
  }
  const latestAsOf = rows.reduce(
    (latest, row) => (row.as_of && (!latest || row.as_of > latest) ? row.as_of : latest),
    null,
  );

  const refreshing = isFetching || forecastFetching;
  const refreshAll = () => {
    refetch();
    refetchForecast();
    refetchGrowth();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Dividend Calendar</h1>
          <p className="text-sm text-muted mt-0.5">Ex-dates and pay-dates for your portfolio holdings</p>
        </div>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-sm text-muted hover:text-ink transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <DividendBars
        forecast={forecast}
        loading={forecastLoading}
        error={forecastError}
        onRetry={() => refetchForecast()}
      />

      <GrowthSection rows={growth} loading={growthLoading} />

      <AsyncSection
        isLoading={isLoading}
        error={error ? new Error(`Could not load dividend data. ${getApiErrorMessage(error)}`) : null}
        onRetry={() => refetch()}
        loading={<div className="card animate-pulse h-48" />}
        isEmpty={!data?.length}
        empty={<div className="text-center py-20 text-muted">No holdings found. Import a portfolio to see dividend info.</div>}
      >
        <>
          <section className="space-y-3">
            <h2 className="text-xs font-semibold text-muted uppercase tracking-wider">
              Estimated annual income
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {estimatedTotals.map(([currency, amount]) => (
                <MetricCard
                  key={currency}
                  icon={TrendingUp}
                  label={currency}
                  value={formatMoney(amount, currency)}
                />
              ))}
            </div>
            <details className="text-xs text-muted">
              <summary>Estimate source and freshness</summary>
              <p className="mt-2">
                Estimates come from Yahoo Finance and are not guaranteed payments.
                {latestAsOf && <> Data retrieved {new Date(latestAsOf).toLocaleString()}.</>}
              </p>
            </details>
          </section>

          {knownUpcoming.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <CalendarDays size={13} /> Known upcoming dates
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={knownUpcoming} />
              </div>
            </section>
          )}

          {needsReview.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <AlertTriangle size={13} /> Date unavailable or needs review
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={needsReview} />
              </div>
            </section>
          )}

          {past.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <CalendarDays size={13} /> Past dates
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={past} />
              </div>
            </section>
          )}
        </>
      </AsyncSection>
    </div>
  );
}

// Same received / upcoming bar cards as the dashboard's dividend row.
function DividendBars({ forecast, loading, error, onRetry }) {
  const { currency = "USD", rate } = useCurrency() ?? {};
  // The forecast is in USD; `rate` is CZK per USD.
  const usdRate = currency === "CZK" && rate ? rate : 1;
  const { received, upcoming } = splitDividendForecast(forecast, {
    monthIndex: new Date().getMonth(),
    usdRate,
  });
  const year = forecast?.year ?? new Date().getFullYear();

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <Card className="h-full animate-fade-up">
        <AsyncSection isLoading={loading} error={error} onRetry={onRetry} loading={<SkeletonChart height={220} />}>
          <DividendBarsCard title="Dividends received" half={received} totalLabel={`${year} so far`} currency={currency} tone="accent" emptyHint="No dividends received this year yet." leadStat={{ label: "All time", amount: received.allTime }} />
        </AsyncSection>
      </Card>
      <Card className="h-full animate-fade-up">
        <AsyncSection isLoading={loading} error={error} onRetry={onRetry} loading={<SkeletonChart height={220} />}>
          <DividendBarsCard title="Upcoming payments" half={upcoming} totalLabel="Next 12 months" currency={currency} emptyHint="No dividends expected in the next 12 months." trailStat={{ label: "Daily average", amount: upcoming.dailyAverage }} />
        </AsyncSection>
      </Card>
    </div>
  );
}

function Table({ rows }) {
  const { openStock } = useStockDetail();
  const { currency: displayCurrency = "USD" } = useCurrency() ?? {};
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-surface-border bg-surface-card">
          {["Ticker", "Company", "Shares", "Ex-Date", "Pay-Date", "Rate/Share", "Annual Income", "Yield", ""].map((h) => (
            <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.ticker}
            onClick={() => openStock(row.ticker)}
            className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
          >
            <td className="px-4 py-3 font-mono font-semibold text-ink">{row.ticker}</td>
            <td className="px-4 py-3 text-muted max-w-[180px] truncate">{row.name}</td>
            <td className="px-4 py-3 text-muted tabular-nums">{formatQuantity(row.shares, displayCurrency)}</td>
            <td className="px-4 py-3 text-muted tabular-nums">{formatTableDate(row.ex_date)}</td>
            <td className="px-4 py-3 text-muted tabular-nums">{formatTableDate(row.pay_date)}</td>
            <td className="px-4 py-3 text-muted tabular-nums">
              {row.dividend_rate != null ? (
                formatMoney(row.dividend_rate, row.currency)
              ) : <span className="text-muted">—</span>}
            </td>
            <td className="px-4 py-3 text-ink tabular-nums font-medium">
              {row.income_status === "review" ? (
                <span className="inline-flex items-center gap-1 text-loss" title={(row.warnings || []).join(", ")}>
                  <AlertTriangle size={13} aria-hidden="true" /> Review estimate
                </span>
              ) : row.income_status === "unavailable" || row.annual_income == null ? (
                <span className="text-muted">Unavailable</span>
              ) : (
                formatMoney(row.annual_income, row.currency)
              )}
            </td>
            <td className="px-4 py-3 tabular-nums">
              {row.dividend_yield != null ? (
                <span className="flex items-center gap-1 text-brand">
                  <TrendingUp size={11} />
                  {row.dividend_yield.toFixed(2)}%
                </span>
              ) : <span className="text-muted">—</span>}
            </td>
            <td className="px-4 py-3">{statusBadge(row)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function fmtPct(v) {
  if (v == null) return <span className="text-muted">—</span>;
  const cls = v > 0 ? "text-gain" : v < 0 ? "text-loss" : "text-muted";
  return <span className={`tabular-nums ${cls}`}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;
}

function GrowthSection({ rows, loading }) {
  const { openStock } = useStockDetail();
  if (loading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-muted">
        Loading dividend growth…
      </div>
    );
  }
  if (!rows?.length) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold text-muted uppercase tracking-wider flex items-center gap-2">
        <TrendingUp size={13} /> Dividend growth
      </h2>
      <div className="rounded-xl border border-surface-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border bg-surface-card">
              {["Ticker", "Company", "Streak", "CAGR", "YoY", "Payout"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.ticker}
                onClick={() => openStock(r.ticker)}
                className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
              >
                <td className="px-4 py-3 font-mono font-semibold text-ink">{r.ticker}</td>
                <td className="px-4 py-3 text-muted max-w-[180px] truncate">{r.name}</td>
                <td className="px-4 py-3 text-ink tabular-nums">
                  {r.streak_years > 0 ? `${r.streak_years} yrs` : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">
                  {r.cagr_pct != null ? (
                    <span className="flex items-baseline gap-1">
                      {fmtPct(r.cagr_pct)}
                      <span className="text-xs text-muted">{r.cagr_years_used}yr</span>
                    </span>
                  ) : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">{fmtPct(r.yoy_pct)}</td>
                <td className="px-4 py-3 tabular-nums text-muted">
                  {r.payout_ratio_pct != null ? `${r.payout_ratio_pct.toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
