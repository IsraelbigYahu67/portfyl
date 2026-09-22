import { AlertCircle, RefreshCw } from "lucide-react";

import { formatDateTime, formatMoney } from "../lib/format";
import { useT212Sync } from "../hooks/useT212Sync";

const HISTORY_ACTIVE = new Set(["pending", "fetching", "waiting_rate_limit"]);

/** Current broker evidence only; never fed into ledger allocation or returns. */
export default function T212SnapshotPositions({ currency }) {
  const { status, history, positions, connected, run } = useT212Sync({ currency, includePositions: true });
  if (status.isLoading) return null;
  if (status.isError) return (
    <section className="card" role="alert">
      <p className="text-sm text-loss">Could not check the Trading 212 connection.</p>
      <button type="button" onClick={() => status.refetch()} className="btn-ghost mt-2 text-xs">Retry</button>
    </section>
  );
  if (!connected) return null;

  const snapshot = positions.data;
  const rows = snapshot?.positions ?? [];
  return (
    <section className="card space-y-3" aria-labelledby="t212-snapshot-heading">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 id="t212-snapshot-heading" className="text-base font-semibold">Trading 212 positions</h2>
          <p className="text-xs text-muted">Current broker snapshot · separate from recorded holdings and performance</p>
        </div>
        {snapshot?.as_of && <span className="text-xs text-muted">As of {formatDateTime(snapshot.as_of)}</span>}
      </div>

      {run && HISTORY_ACTIVE.has(run.state) && (
        <p className="text-xs text-muted">Broker history is still being fetched. Current positions are available separately.</p>
      )}
      {run?.state === "completed" && (
        <p className="text-xs text-muted">Broker history pages fetched; ledger processing is still pending.</p>
      )}
      {history.isError && <p role="alert" className="text-xs text-loss">History progress is unavailable.</p>}
      {positions.isLoading && <p className="text-sm text-muted">Loading broker positions…</p>}
      {positions.isError && (
        <div role="alert" className="flex items-center gap-2 text-sm text-loss">
          <AlertCircle size={16} aria-hidden="true" /> Could not load broker positions.
          <button type="button" onClick={() => positions.refetch()} className="btn-ghost text-xs">Retry</button>
        </div>
      )}
      {snapshot?.status === "stale" && (
        <p role="status" className="flex items-center gap-2 text-xs text-loss">
          <RefreshCw size={14} aria-hidden="true" /> This broker snapshot is out of date. Sync Trading 212 to refresh it.
        </p>
      )}
      {!positions.isLoading && !positions.isError && snapshot?.status === "unavailable" && (
        <p className="text-sm text-muted">No current broker position snapshot is available yet.</p>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-surface-border text-xs uppercase text-muted">
              <tr><th scope="col" className="py-2 text-left">Ticker</th><th scope="col" className="py-2 text-right">Quantity</th><th scope="col" className="py-2 text-right">Current value</th></tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {rows.map((row) => (
                <tr key={row.provider_ticker ?? row.ticker}>
                  <td className="py-2 font-mono font-medium">{row.ticker}</td>
                  <td className="py-2 text-right tabular-nums">{Number(row.quantity).toLocaleString(undefined, { maximumFractionDigits: 6 })}</td>
                  <td className="py-2 text-right tabular-nums">
                    {!row.currency
                      ? <span className="text-muted">Currency unknown</span>
                      : Number.isFinite(row.market_value)
                        ? formatMoney(row.market_value, currency)
                        : <span className="text-muted">Price unavailable</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.some((row) => !row.currency) && (
            <p className="mt-2 text-xs text-muted">A value is hidden when the instrument currency cannot be verified.</p>
          )}
        </div>
      )}
    </section>
  );
}
