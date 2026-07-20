import { useCountUp } from "../hooks/useCountUp";
import { formatMoney, formatCompact, formatNumber } from "../lib/format";
import { DeltaPill, Skeleton, SkeletonMetric } from "./ui";
import HeroSparkline from "./HeroSparkline";

function Chip({ label, value, positive, negative }) {
  const valueColor = positive ? "text-gain" : negative ? "text-loss" : "text-ink";
  return (
    <div className="flex flex-col gap-0.5 rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5 min-w-0">
      <span className="eyebrow truncate">{label}</span>
      <span className={`font-sans text-sm font-bold tabular-nums truncate ${valueColor}`}>{value}</span>
    </div>
  );
}

export default function PortfolioHero({ summary, loading, currency = "USD", series = [] }) {
  const positive = (summary?.day_change ?? summary?.total_pnl ?? 0) >= 0;
  const netWorth = summary?.net_worth ?? summary?.total_value ?? 0;
  const animatedValue = useCountUp(netWorth, { enabled: !loading && summary != null });

  return (
    <section className="card card-interactive relative overflow-hidden p-6 animate-fade-up">
      <HeroSparkline data={series} positive={positive} />
      <div className="relative">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow">Net Worth</p>
            {loading || summary == null ? (
              <div className="mt-2"><Skeleton h="2.75rem" w="16rem" /></div>
            ) : (
              <>
                <div className="flex items-baseline gap-3 flex-wrap mt-1">
                  <span className="font-display text-[clamp(2.25rem,5vw,3.25rem)] font-bold tracking-tight text-ink tnum leading-none">
                    {formatMoney(animatedValue, currency)}
                  </span>
                  <DeltaPill value={summary.day_change} pct={summary.day_change_percent} currency={currency} size="lg" />
                </div>
                <div className="flex items-center gap-3 mt-1 text-xs font-sans tabular-nums text-slate-500">
                  <span>Positions {formatMoney(summary.total_value, currency)}</span>
                  <span aria-hidden="true">·</span>
                  <span>Cash {formatMoney(summary.cash, currency)}</span>
                </div>
              </>
            )}
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-2xl">
          {loading || summary == null ? (
            <>
              <div className="rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5"><SkeletonMetric /></div>
              <div className="rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5"><SkeletonMetric /></div>
              <div className="rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5"><SkeletonMetric /></div>
              <div className="rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5"><SkeletonMetric /></div>
            </>
          ) : (
            <>
              <Chip label="Invested" value={formatCompact(summary.total_invested, currency)} />
              <Chip
                label="All-time P&L"
                value={`${summary.total_pnl >= 0 ? "+" : ""}${formatCompact(summary.total_pnl, currency)}`}
                positive={summary.total_pnl >= 0}
                negative={summary.total_pnl < 0}
              />
              <Chip label="Dividends" value={formatCompact(summary.total_dividends, currency)} />
              <Chip label="Holdings" value={formatNumber(summary.holdings_count)} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
