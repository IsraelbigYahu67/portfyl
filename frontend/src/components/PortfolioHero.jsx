import { useCountUp } from "../hooks/useCountUp";
import { formatMoney, formatCompact, formatNumber } from "../lib/format";
import { DeltaPill, Skeleton, SkeletonMetric } from "./ui";
import HeroSparkline from "./HeroSparkline";
import ShinyText from "./reactbits/ShinyText";

function Chip({ label, value, positive, negative }) {
  const valueColor = positive ? "text-gain" : negative ? "text-loss" : "text-ink";
  return (
    <div className="pop-tile flex flex-col gap-0.5 rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5 min-w-0">
      <span className="eyebrow truncate">{label}</span>
      <span className={`font-sans text-sm font-bold tabular-nums truncate ${valueColor}`}>{value}</span>
    </div>
  );
}

// `snapshot` ({ positionsValue }) replaces the ledger's position value while
// a broker history backfill is still filling the ledger (see
// lib/dashboardSummaries.snapshotNetWorth). The ledger's day change is
// meaningless then, so it is hidden.
export default function PortfolioHero({ summary, snapshot = null, loading, currency = "USD", series = [] }) {
  const positive = (summary?.day_change ?? summary?.total_pnl ?? 0) >= 0;
  const positionsValue = snapshot ? snapshot.positionsValue : summary?.total_value;
  const netWorth = snapshot
    ? snapshot.positionsValue + (summary?.cash ?? 0)
    : summary?.net_worth ?? summary?.total_value ?? 0;
  const animatedValue = useCountUp(netWorth, { enabled: !loading && summary != null });

  return (
    <section className="card card-interactive relative overflow-hidden p-6 animate-fade-up">
      <HeroSparkline data={series} positive={positive} />
      <div className="relative">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow"><ShinyText text="Net Worth" /></p>
            {loading || summary == null ? (
              <div className="mt-2"><Skeleton h="2.75rem" w="16rem" /></div>
            ) : (
              <>
                <div className="flex items-baseline gap-3 flex-wrap mt-1">
                  <span className="financial-headline font-display text-[clamp(2.25rem,5vw,3.25rem)] tracking-tight leading-none">
                    {formatMoney(animatedValue, currency)}
                  </span>
                  {!snapshot && (
                    <DeltaPill value={summary.day_change} pct={summary.day_change_percent} currency={currency} size="lg" />
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1 financial-data font-sans">
                  <span>Positions {formatMoney(positionsValue, currency)}</span>
                  <span aria-hidden="true">·</span>
                  <span>Cash {formatMoney(summary.cash, currency)}</span>
                </div>
                {snapshot && (
                  <p className="text-xs text-muted mt-1">
                    Current value from your Trading 212 snapshot. Performance figures fill in once the history import finishes.
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Invested and all-time P&L live in the Total profit card beside
            the hero, so the chips only carry what that card does not. */}
        <div className="mt-6 grid grid-cols-2 gap-3 max-w-sm">
          {loading || summary == null ? (
            <>
              <div className="rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5"><SkeletonMetric /></div>
              <div className="rounded-lg bg-surface-card-elevated border border-hairline px-3 py-2.5"><SkeletonMetric /></div>
            </>
          ) : (
            <>
              <Chip label="Dividends" value={formatCompact(summary.total_dividends, currency)} />
              <Chip label="Holdings" value={formatNumber(summary.holdings_count)} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
