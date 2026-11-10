import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchHistory, fetchHoldings, fetchStockView } from "../../api";
import { useCurrency } from "../../App";
import { formatMoney, formatPercent, formatQuantity } from "../../lib/format";
import { StockOverview } from "../StockDetail";
import { AsyncSection } from "../ui";
import { msg, useT } from "../../i18n/I18nProvider";

function HistorySummary({ history, ticker }) {
  const t = useT();
  const points = history?.data || [];
  if (!points.length) return <p className="text-sm text-muted">{t("Price history is unavailable.")}</p>;
  const closes = points.map((point) => Number(point.close)).filter(Number.isFinite);
  const low = Math.min(...closes);
  const high = Math.max(...closes);
  const span = high - low || 1;
  const polyline = closes
    .map((value, index) => `${(index / Math.max(1, closes.length - 1)) * 100},${38 - ((value - low) / span) * 36}`)
    .join(" ");
  return (
    <section aria-labelledby="price-history-heading" className="rounded-xl bg-surface p-4">
      <h3 id="price-history-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">
        {t("One-year price history")}
      </h3>
      <svg className="mt-3 h-48 w-full" viewBox="0 0 100 40" role="img" aria-label={t("{ticker} one-year closing-price chart", { ticker })} preserveAspectRatio="none">
        <polyline points={polyline} fill="none" stroke="var(--brand)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="text-xs text-muted">{t("Range: {low} to {high} across {count} closes.", { low: low.toFixed(2), high: high.toFixed(2), count: points.length })}</p>
    </section>
  );
}

function PositionSummary({ ticker, holding, currency }) {
  const t = useT();
  if (!holding) {
    return (
      <section aria-labelledby="position-heading" className="rounded-xl bg-surface p-4">
        <h3 id="position-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">{t("Your position")}</h3>
        <p className="mt-2 text-sm text-muted">{t("You do not currently own {ticker}", { ticker })}</p>
      </section>
    );
  }

  const avgCost = holding.avg_price ?? holding.avg_cost;
  const pnl = holding.unrealized_pnl ?? holding.pnl;
  const pnlPercent = holding.unrealized_pnl_percent ?? holding.pnl_percent;
  const rows = [
    [msg("Shares"), formatQuantity(holding.shares)],
    [msg("Average cost"), formatMoney(avgCost, holding.currency || currency)],
    [msg("Market value"), formatMoney(holding.market_value, currency)],
    [msg("Unrealized P&L"), formatMoney(pnl, currency)],
    [msg("Unrealized P&L percentage"), formatPercent(pnlPercent)],
    [msg("Portfolio weight"), formatPercent(holding.weight, { sign: false })],
  ];

  return (
    <section aria-labelledby="position-heading" className="rounded-xl bg-surface p-4">
      <h3 id="position-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">{t("Your position")}</h3>
      <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted">{t(label)}</dt>
            <dd className="mt-1 font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// Roughly three lines of text on a desktop-width card; shorter text needs no toggle.
const ABOUT_CLAMP_CHARS = 180;

function AboutSection({ description }) {
  const t = useT();
  const [expanded, setExpanded] = useState(false);
  const clampable = description.length > ABOUT_CLAMP_CHARS;
  return (
    <section className="mx-4 mb-6 rounded-xl bg-surface p-4 sm:mx-6" aria-labelledby="company-description-heading">
      <h3 id="company-description-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">{t("About")}</h3>
      <p className={`mt-2 text-sm leading-relaxed text-muted ${clampable && !expanded ? "line-clamp-3" : ""}`}>
        {description}
      </p>
      {clampable ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="mt-1 text-sm font-semibold text-brand hover:underline max-md:min-h-[44px]"
        >
          {expanded ? t("Show less") : t("Show more")}
        </button>
      ) : null}
    </section>
  );
}

export function StockOverviewTab({ ticker, overviewData }) {
  const currency = useCurrency()?.currency || "USD";
  const history = useQuery({
    queryKey: ["history", ticker, "1y"],
    queryFn: () => fetchHistory(ticker, "1y"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const holdings = useQuery({
    queryKey: ["holdings", currency],
    queryFn: () => fetchHoldings(currency),
    staleTime: 30_000,
    retry: false,
  });
  // TTM revenue and FCF come from the financials view (the same query, and
  // cache entry, as the Financials tab), so the headline figures match the
  // sum of the last four quarterly bars shown there.
  const financials = useQuery({
    queryKey: ["stock-view", ticker, "financials"],
    queryFn: () => fetchStockView(ticker, "financials"),
    enabled: Boolean(ticker),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
  const holding = (holdings.data || []).find((row) => row.ticker?.toUpperCase() === ticker);

  return (
    <div>
      <StockOverview
        data={{ ...overviewData, ttm: { ...overviewData.ttm, ...financials.data?.ttm } }}
        ttmLoading={financials.isLoading}
        sectionIds={["quickStats"]}
        showHeader={false}
        showCustomizer={false}
      />
      <div className="grid gap-4 p-4 pt-0 lg:grid-cols-2 sm:p-6 sm:pt-0">
        <AsyncSection isLoading={history.isLoading} error={history.error} onRetry={() => history.refetch()}>
          <HistorySummary history={history.data} ticker={ticker} />
        </AsyncSection>
        <AsyncSection isLoading={holdings.isLoading} error={holdings.error} onRetry={() => holdings.refetch()}>
          <PositionSummary ticker={ticker} holding={holding} currency={currency} />
        </AsyncSection>
      </div>
      {overviewData.description ? <AboutSection description={overviewData.description} /> : null}
    </div>
  );
}
