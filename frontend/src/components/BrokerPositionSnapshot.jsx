import { useState } from "react";
import { formatDateTime, formatMoney, formatQuantity, formatTableDate, pluralize } from "../lib/format";
import { Badge } from "./ui/Badge";

function PositionList({ positions, snapshot, limit }) {
  return (
    <>
      <ul className="mt-3 divide-y divide-surface-border" aria-label="Broker snapshot positions">
        {positions.slice(0, limit).map((position) => (
          <li key={position.provider_ticker ?? position.ticker} className="flex items-center justify-between gap-3 py-2 text-xs">
            <span className="min-w-0 truncate font-mono font-medium text-ink">{position.ticker}</span>
            <span className="shrink-0 text-muted">
              {`${formatQuantity(position.quantity, snapshot.currency)} ${pluralize(Number(position.quantity), "share", "shares")}`}
            </span>
            <span className="min-w-20 shrink-0 text-right font-mono tabular-nums text-ink">
              {Number.isFinite(position.market_value) ? formatMoney(position.market_value, snapshot.currency) : "—"}
            </span>
          </li>
        ))}
      </ul>
      {positions.length > limit && <p className="mt-2 text-xs text-muted">+{positions.length - limit} more positions</p>}
    </>
  );
}

// variant="list" (default): the card with the top `limit` positions.
// variant="summary": one line (count, total, updated date) with a disclosure
// that expands to the full position list.
export default function BrokerPositionSnapshot({ query, variant = "list", limit = 5 }) {
  const [expanded, setExpanded] = useState(false);

  if (query.isLoading) {
    return <div className="h-28 animate-pulse rounded-lg bg-surface-hover" aria-label="Loading current positions" />;
  }

  if (query.isError) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-4" aria-label="Trading 212 current positions">
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <span className="text-muted">Current positions could not be loaded.</span>
          <button type="button" className="text-brand hover:underline" onClick={() => query.refetch()}>Retry positions</button>
        </div>
      </section>
    );
  }

  const snapshot = query.data;
  const positions = snapshot?.positions ?? [];
  const unavailable = !snapshot || snapshot.status === "unavailable";
  const completeValue = !unavailable && positions.length > 0 && positions.every((position) => Number.isFinite(position.market_value));
  const totalValue = completeValue
    ? positions.reduce((total, position) => total + position.market_value, 0)
    : null;
  const stale = snapshot?.status === "stale";
  const countLabel = `${positions.length} position${positions.length === 1 ? "" : "s"}`;

  if (variant === "summary") {
    const hasPositions = !unavailable && positions.length > 0;
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card px-4 py-3" aria-label="Trading 212 current positions">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
          <p className="min-w-0">
            Trading 212 snapshot
            {unavailable ? (
              <> · No position snapshot yet. Sync to load current holdings.</>
            ) : (
              <>
                {" · "}<span>{countLabel}</span>
                {totalValue !== null && <> · <span className="font-mono font-semibold tabular-nums text-ink">{formatMoney(totalValue, snapshot.currency)}</span></>}
                {snapshot.as_of && <> · updated {formatTableDate(String(snapshot.as_of).slice(0, 10))}</>}
              </>
            )}
          </p>
          {stale && <Badge tone="warn" size="sm">Stale</Badge>}
          {hasPositions && (
            <button
              type="button"
              className="ml-auto min-h-11 px-2 text-brand hover:underline md:min-h-0 md:px-0"
              aria-expanded={expanded}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "Hide positions" : "Show positions"}
            </button>
          )}
        </div>
        {hasPositions && expanded && (
          <>
            {totalValue === null && <p className="mt-3 text-xs text-muted">Total value unavailable until instrument currencies are known.</p>}
            <PositionList positions={positions} snapshot={snapshot} limit={positions.length} />
          </>
        )}
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-4" aria-label="Trading 212 current positions">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Current positions</h2>
          <p className="mt-1 text-xs text-muted">Trading 212 snapshot · <span>{countLabel}</span></p>
        </div>
        {!unavailable && (
          <div className="flex flex-col items-end gap-1 text-right">
            {totalValue !== null && <p className="font-mono font-semibold tabular-nums text-ink">{formatMoney(totalValue, snapshot.currency)}</p>}
            {stale ? (
              <Badge tone="warn" size="sm">Snapshot stale</Badge>
            ) : (
              <p className="text-xs text-gain">Snapshot fresh</p>
            )}
          </div>
        )}
      </div>

      {unavailable ? (
        <p className="mt-3 text-xs text-muted">No position snapshot yet. Sync to load current holdings.</p>
      ) : positions.length === 0 ? (
        <p className="mt-3 text-xs text-muted">No open positions in the latest snapshot.</p>
      ) : (
        <>
          {totalValue === null && <p className="mt-3 text-xs text-muted">Total value unavailable until instrument currencies are known.</p>}
          <PositionList positions={positions} snapshot={snapshot} limit={limit} />
        </>
      )}
      {snapshot?.as_of && <p className="mt-2 text-xs text-muted">Updated {formatDateTime(snapshot.as_of)}</p>}
    </section>
  );
}
