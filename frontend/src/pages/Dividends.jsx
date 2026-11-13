import { Fragment } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDividends, fetchDividendForecast, fetchDividendGrowth } from "../api";
import { AlertTriangle, CalendarDays, RefreshCw, TrendingUp } from "lucide-react";
import { useCurrency } from "../App";
import { convertFromUsd } from "../lib/displayCurrency";
import { useStockDetail } from "../components/StockDetail";
import DividendBarsCard from "../components/dashboard/DividendBarsCard";
import { splitDividendForecast } from "../lib/dashboardSummaries";
import { formatMoney, formatQuantity, formatTableDate } from "../lib/format";
import { getApiErrorMessage } from "../lib/apiError";
import { AsyncSection, Badge, Card, SkeletonChart } from "../components/ui";
import { msg, useT } from "../i18n/I18nProvider";

const today = new Date().toISOString().slice(0, 10);

function statusBadge(row, t) {
  if (row.date_status === "inconsistent") return <Badge tone="loss" size="sm">{t("Needs review")}</Badge>;
  if (!row.ex_date) return <Badge tone="neutral" size="sm">{t("Date unavailable")}</Badge>;
  const diff = Math.ceil((new Date(row.ex_date) - new Date(today)) / 86400000);
  if (diff < 0) return <Badge tone="neutral" size="sm">{t("Past")}</Badge>;
  if (diff === 0) return <Badge tone="warn" size="sm">{t("Today")}</Badge>;
  const label = t("In {days}d", { days: diff });
  if (diff <= 7) return <Badge tone="warn" size="sm">{label}</Badge>;
  if (diff <= 30) return <Badge tone="brand" size="sm">{label}</Badge>;
  return <Badge tone="neutral" size="sm">{label}</Badge>;
}

function isKnownUpcoming(row, currentDay) {
  return row.date_status !== "inconsistent" && row.ex_date && row.ex_date >= currentDay;
}

export default function Dividends() {
  const t = useT();
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
          <h1 className="text-xl font-semibold">{t("Dividend Calendar")}</h1>
          <p className="text-sm text-muted mt-0.5">{t("Ex-dates and pay-dates for your portfolio holdings")}</p>
        </div>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-sm text-muted hover:text-ink transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          {t("Refresh")}
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
        error={error ? new Error(`${t("Could not load dividend data.")} ${getApiErrorMessage(error, undefined, t)}`) : null}
        onRetry={() => refetch()}
        loading={<div className="card animate-pulse h-48" />}
        isEmpty={!data?.length}
        empty={<div className="text-center py-20 text-muted">{t("No holdings found. Import a portfolio to see dividend info.")}</div>}
      >
        <>
          {knownUpcoming.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <CalendarDays size={13} /> {t("Known upcoming dates")}
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={knownUpcoming} columns={UPCOMING_COLUMNS} />
              </div>
            </section>
          )}

          {needsReview.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <AlertTriangle size={13} /> {t("Date unavailable or needs review")}
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={needsReview} />
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
  const t = useT();
  const { currency = "USD", rate } = useCurrency() ?? {};
  // The forecast is in USD; `rate` is display units per USD.
  const usdRate = convertFromUsd(1, currency, rate);
  const { received, upcoming } = splitDividendForecast(forecast, {
    monthIndex: new Date().getMonth(),
    usdRate,
  });
  const year = forecast?.year ?? new Date().getFullYear();

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <Card className="h-full animate-fade-up">
        <AsyncSection isLoading={loading} error={error} onRetry={onRetry} loading={<SkeletonChart height={220} />}>
          <DividendBarsCard title={t("Dividends received")} half={received} totalLabel={t("{year} so far", { year })} currency={currency} tone="accent" emptyHint={t("No dividends received this year yet.")} leadStat={{ label: t("All time"), amount: received.allTime }} />
        </AsyncSection>
      </Card>
      <Card className="h-full animate-fade-up">
        <AsyncSection isLoading={loading} error={error} onRetry={onRetry} loading={<SkeletonChart height={220} />}>
          <DividendBarsCard title={t("Upcoming payments")} half={upcoming} totalLabel={t("Next 12 months")} currency={currency} emptyHint={t("No dividends expected in the next 12 months.")} trailStat={{ label: t("Daily average"), amount: upcoming.dailyAverage }} />
        </AsyncSection>
      </Card>
    </div>
  );
}

// One definition per column; each table picks the order it needs.
function buildColumns(displayCurrency, t) {
  return {
    ticker: {
      header: t("Ticker"),
      cell: (row) => <td className="px-4 py-3 font-mono font-semibold text-ink">{row.ticker}</td>,
    },
    shares: {
      header: t("Shares"),
      cell: (row) => (
        <td className="px-4 py-3 text-muted tabular-nums">{formatQuantity(row.shares, displayCurrency)}</td>
      ),
    },
    exDate: {
      header: t("Ex-Date"),
      cell: (row) => <td className="px-4 py-3 text-muted tabular-nums">{formatTableDate(row.ex_date)}</td>,
    },
    payDate: {
      header: t("Pay-Date"),
      cell: (row) => <td className="px-4 py-3 text-muted tabular-nums">{formatTableDate(row.pay_date)}</td>,
    },
    rate: {
      header: t("Rate/Share"),
      cell: (row) => (
        <td className="px-4 py-3 text-muted tabular-nums">
          {row.dividend_rate != null ? (
            formatMoney(row.dividend_rate, row.currency)
          ) : <span className="text-muted">—</span>}
        </td>
      ),
    },
    income: {
      // Rate per share x the shares you hold = what you receive per year.
      header: t("Annual Income"),
      cell: (row) => (
        <td className="px-4 py-3 text-ink tabular-nums font-medium">
          {row.income_status === "review" ? (
            <span className="inline-flex items-center gap-1 text-loss" title={(row.warnings || []).join(", ")}>
              <AlertTriangle size={13} aria-hidden="true" /> {t("Review estimate")}
            </span>
          ) : row.income_status === "unavailable" || row.annual_income == null ? (
            <span className="text-muted">{t("Unavailable")}</span>
          ) : (
            formatMoney(row.annual_income, row.currency)
          )}
        </td>
      ),
    },
    yield: {
      header: t("Yield"),
      cell: (row) => (
        <td className="px-4 py-3 tabular-nums">
          {row.dividend_yield != null ? (
            <span className="flex items-center gap-1 text-brand">
              <TrendingUp size={11} />
              {row.dividend_yield.toFixed(2)}%
            </span>
          ) : <span className="text-muted">—</span>}
        </td>
      ),
    },
    status: { header: "", cell: (row) => <td className="px-4 py-3">{statusBadge(row, t)}</td> },
  };
}

const REVIEW_COLUMNS = ["ticker", "shares", "exDate", "payDate", "rate", "income", "yield", "status"];
// Known upcoming dates: the per-share rate becomes your annual payout, and the
// two dates close the row.
const UPCOMING_COLUMNS = ["ticker", "shares", "income", "yield", "status", "exDate", "payDate"];

function Table({ rows, columns = REVIEW_COLUMNS }) {
  const t = useT();
  const { openStock } = useStockDetail();
  const { currency: displayCurrency = "USD" } = useCurrency() ?? {};
  const defs = buildColumns(displayCurrency, t);
  const ordered = columns.map((key) => defs[key]);
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-surface-border bg-surface-card">
          {ordered.map((col, i) => (
            <th key={i} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
              {col.header}
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
            {ordered.map((col, i) => (
              <Fragment key={i}>{col.cell(row)}</Fragment>
            ))}
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
  const t = useT();
  const { openStock } = useStockDetail();
  if (loading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-muted">
        {t("Loading dividend growth…")}
      </div>
    );
  }
  if (!rows?.length) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold text-muted uppercase tracking-wider flex items-center gap-2">
        <TrendingUp size={13} /> {t("Dividend growth")}
      </h2>
      <div className="rounded-xl border border-surface-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border bg-surface-card">
              {[msg("Ticker"), msg("Streak"), msg("CAGR"), msg("YoY"), msg("Payout")].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
                  {t(h)}
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
                <td className="px-4 py-3 text-ink tabular-nums">
                  {r.streak_years > 0 ? t("{years} yrs", { years: r.streak_years }) : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">
                  {r.cagr_pct != null ? (
                    <span className="flex items-baseline gap-1">
                      {fmtPct(r.cagr_pct)}
                      <span className="text-xs text-muted">{t("{years}yr", { years: r.cagr_years_used })}</span>
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
