import { useQuery } from "@tanstack/react-query";
import { fetchHistory, fetchHoldings, fetchTransactionsPage } from "../../api";
import { useCurrency } from "../../App";
import { formatLongDate, formatMoney, formatPercent, formatQuantity } from "../../lib/format";
import { StockOverview } from "../StockDetail";
import { AsyncSection } from "../ui";

function HistorySummary({ history, ticker }) {
  const points = history?.data || [];
  if (!points.length) return <p className="text-sm text-muted">Price history is unavailable.</p>;
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
        One-year price history
      </h3>
      <svg className="mt-3 h-48 w-full" viewBox="0 0 100 40" role="img" aria-label={`${ticker} one-year closing-price chart`} preserveAspectRatio="none">
        <polyline points={polyline} fill="none" stroke="var(--accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="text-xs text-muted">Range: {low.toFixed(2)} to {high.toFixed(2)} across {points.length} closes.</p>
    </section>
  );
}

function PositionSummary({ ticker, holding, latest, currency }) {
  if (!holding) {
    return (
      <section aria-labelledby="position-heading" className="rounded-xl bg-surface p-4">
        <h3 id="position-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">Your position</h3>
        <p className="mt-2 text-sm text-muted">You do not currently own {ticker}</p>
      </section>
    );
  }

  const avgCost = holding.avg_price ?? holding.avg_cost;
  const pnl = holding.unrealized_pnl ?? holding.pnl;
  const pnlPercent = holding.unrealized_pnl_percent ?? holding.pnl_percent;
  const rows = [
    ["Shares", formatQuantity(holding.shares)],
    ["Average cost", formatMoney(avgCost, currency)],
    ["Market value", formatMoney(holding.market_value, currency)],
    ["Unrealized P&L", formatMoney(pnl, currency)],
    ["Unrealized P&L percentage", formatPercent(pnlPercent)],
    ["Portfolio weight", formatPercent(holding.weight, { sign: false })],
  ];

  return (
    <section aria-labelledby="position-heading" className="rounded-xl bg-surface p-4">
      <h3 id="position-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">Your position</h3>
      <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="mt-1 font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 border-t border-surface-border pt-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted">Latest transaction</h4>
        {latest ? (
          <p className="mt-1 text-sm">
            {formatLongDate(latest.date)} · {latest.type} · {formatQuantity(latest.shares)} shares at {formatMoney(latest.price, latest.currency || currency)}
          </p>
        ) : (
          <p className="mt-1 text-sm text-muted">No transaction found for {ticker}.</p>
        )}
        {latest?.notes ? <p className="mt-2 text-sm text-muted">Note: {latest.notes}</p> : null}
      </div>
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
  const latest = useQuery({
    queryKey: ["transactions-page", { ticker, sort: "-date", limit: 1 }],
    queryFn: () => fetchTransactionsPage({ ticker, sort: "-date", limit: 1 }),
    staleTime: 30_000,
    retry: false,
  });
  const holding = (holdings.data || []).find((row) => row.ticker?.toUpperCase() === ticker);

  return (
    <div>
      <StockOverview
        data={overviewData}
        sectionIds={["quickStats", "weekRange"]}
        showHeader={false}
        showCustomizer={false}
      />
      <div className="grid gap-4 p-4 pt-0 lg:grid-cols-2 sm:p-6 sm:pt-0">
        <AsyncSection isLoading={history.isLoading} error={history.error} onRetry={() => history.refetch()}>
          <HistorySummary history={history.data} ticker={ticker} />
        </AsyncSection>
        <AsyncSection
          isLoading={holdings.isLoading || latest.isLoading}
          error={holdings.error || latest.error}
          onRetry={() => Promise.all([holdings.refetch(), latest.refetch()])}
        >
          <PositionSummary ticker={ticker} holding={holding} latest={latest.data?.items?.[0]} currency={currency} />
        </AsyncSection>
      </div>
      {overviewData.description ? (
        <section className="mx-4 mb-6 rounded-xl bg-surface p-4 sm:mx-6" aria-labelledby="company-description-heading">
          <h3 id="company-description-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">About</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted">{overviewData.description}</p>
        </section>
      ) : null}
    </div>
  );
}
