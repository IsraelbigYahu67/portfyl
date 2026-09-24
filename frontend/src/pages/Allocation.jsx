import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllHoldings, fetchSectorBreakdown } from "../api";
import { useCurrency, usePortfolio } from "../App";
import { formatMoney } from "../lib/format";
import { allocationRows, boundedAllocationRows } from "../lib/allocationBreakdown";
import { TrendingUp, TrendingDown, RefreshCw } from "lucide-react";
import { TickerLink, useStockDetail } from "../components/StockDetail";
import BreakdownChart from "../components/BreakdownChart";
import AllocationBreakdownList from "../components/AllocationBreakdownList";
import SegmentedControl from "../components/ui/SegmentedControl";
import { AsyncSection } from "../components/ui";
import BrokerPositionSnapshot from "../components/BrokerPositionSnapshot";
import { useT212Sync } from "../hooks/useT212Sync";

const fmtPct = (n) => (n >= 0 ? "+" : "") + n.toFixed(2) + "%";

export default function Allocation() {
  const { currency } = useCurrency();
  const currentPortfolio = usePortfolio()?.current;
  const t212 = useT212Sync({ portfolioId: currentPortfolio?.id, currency });
  const { openStock } = useStockDetail();

  // Portfolio-level money (value, P&L, dividends) is shown in the display
  // currency (CZK by default). Per-share prices (avg cost, current price) are
  // shown in each stock's *native* currency — a US stock's price is $, not Kč.
  const fmt = (n) => formatMoney(n, currency);
  const fmtNative = (n, code) => formatMoney(n, code || currency);

  const {
    data: holdings = [],
    isLoading: holdingsLoading,
    error: holdingsError,
    refetch: refetchHoldings,
    isFetching,
  } = useQuery({
    queryKey: ["holdings-all", currency],
    queryFn: () => fetchAllHoldings(currency),
  });

  const {
    data: breakdown,
    isLoading: breakdownLoading,
    error: breakdownError,
    refetch: refetchBreakdown,
  } = useQuery({
    queryKey: ["sector-breakdown", currency],
    queryFn: () => fetchSectorBreakdown(currency),
  });

  const [category, setCategory] = useState("position");
  const [positionState, setPositionState] = useState("active");

  const categoryOptions = useMemo(() => {
    const options = [
      { value: "position", label: "Position" },
      { value: "sector", label: "Sector" },
      { value: "asset_type", label: "Asset type" },
      { value: "currency", label: "Currency" },
    ];
    if (breakdown?.accounts?.length) options.push({ value: "account", label: "Account" });
    return options;
  }, [breakdown]);

  const rows = useMemo(
    () => allocationRows({ category, holdings, breakdown }),
    [category, holdings, breakdown]
  );
  const bounded = useMemo(() => boundedAllocationRows(rows), [rows]);
  const soldHoldings = useMemo(() => holdings.filter((h) => h.closed), [holdings]);
  const top3Weight = useMemo(
    () => Math.round(rows.slice(0, 3).reduce((sum, r) => sum + r.weight, 0) * 10) / 10,
    [rows]
  );
  const CATEGORY_TITLE = {
    position: "Positions",
    sector: "Sector Allocation",
    asset_type: "Asset Type",
    currency: "Currency Exposure",
    account: "Account",
  };

  const [sort, setSort] = useState({ key: "market_value", dir: "desc" });

  const sorted = [...holdings].sort((a, b) => {
    const v = a[sort.key] > b[sort.key] ? 1 : -1;
    return sort.dir === "asc" ? v : -v;
  });

  const toggle = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));

  const Th = ({ label, k }) => (
    <th
      onClick={() => toggle(k)}
      className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider cursor-pointer hover:text-ink select-none"
    >
      {label}
      {sort.key === k && <span className="ml-1">{sort.dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Allocation</h1>
        <button
          onClick={() => refetchHoldings()}
          className="btn-ghost flex items-center gap-2 text-sm"
          disabled={isFetching}
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
          Refresh prices
        </button>
      </div>

      {t212.connected && (
        <div className="space-y-2">
          <BrokerPositionSnapshot query={t212.positionsQuery} limit={20} />
          <p className="text-xs text-muted">Allocation charts use imported transactions and may lag behind this current snapshot.</p>
        </div>
      )}

      <AsyncSection
        isLoading={breakdownLoading || holdingsLoading}
        error={holdingsError || breakdownError}
        onRetry={() => Promise.all([refetchHoldings(), refetchBreakdown()])}
        loading={(
          <div className="card animate-pulse h-48 flex items-center justify-center text-muted">
            Loading allocation data...
          </div>
        )}
      >
        <>
      {breakdownLoading || holdingsLoading ? (
        <div className="card animate-pulse h-48 flex items-center justify-center text-muted">
          Loading allocation data...
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SegmentedControl
              aria-label="Allocation category"
              value={category}
              onChange={setCategory}
              options={categoryOptions}
            />
            {category === "position" && (
              <SegmentedControl
                aria-label="Position state"
                value={positionState}
                onChange={setPositionState}
                options={[
                  { value: "active", label: "Active positions" },
                  { value: "sold", label: "Sold positions" },
                ]}
              />
            )}
          </div>

          {category === "position" && positionState === "sold" ? (
            <div className="card p-0 overflow-hidden">
              {soldHoldings.length === 0 ? (
                <div className="text-muted text-sm text-center py-12">No sold positions.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        {["Ticker", "Company", "Value if held", "P&L if held"].map((h) => (
                          <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {soldHoldings.map((h) => (
                        <tr key={h.ticker} onClick={() => openStock(h.ticker)} className="hover:bg-surface-hover transition-colors cursor-pointer bg-loss/10">
                          <td className="px-4 py-3 font-mono font-bold text-sm">
                            <TickerLink ticker={h.ticker} className="text-left">{h.ticker}</TickerLink>
                          </td>
                          <td className="px-4 py-3 text-sm text-muted max-w-xs truncate">{h.name}</td>
                          <td className="px-4 py-3 tabular-nums text-sm text-right text-muted">
                            {h.pnl_if_held != null ? fmt(h.pnl_if_held) : "—"}
                          </td>
                          <td className={`px-4 py-3 tabular-nums text-sm text-right ${(h.pnl_if_held_pct ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>
                            {h.pnl_if_held_pct != null ? fmtPct(h.pnl_if_held_pct) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : (
            <>
              <p className="text-xs text-muted">
                Largest {category === "position" ? "position" : "category"}:{" "}
                <span className="text-ink font-medium">{rows[0]?.name ?? "—"}</span>
                {" · "}Top 3 combined: <span className="text-ink font-medium">{top3Weight}%</span>
              </p>
              <BreakdownChart
                title={CATEGORY_TITLE[category]}
                data={bounded}
                currencyLabel={currency}
                legendColumns={2}
                nameWidth={category === "sector" ? 140 : 70}
              />
              <div className="card">
                <h2 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wider">
                  Full Breakdown
                </h2>
                <AllocationBreakdownList rows={rows} currency={currency} />
              </div>
            </>
          )}
        </>
      )}

      <div>
        <h2 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wider">
          All Holdings
        </h2>
        {holdingsLoading ? (
          <div className="card animate-pulse h-48 flex items-center justify-center text-muted">
            Loading live prices...
          </div>
        ) : holdings.length === 0 ? (
          <div className="card text-muted text-sm text-center py-12">
            No holdings yet. Import a CSV or add transactions to get started.
          </div>
        ) : (
          <div className="card p-0 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b border-surface-border">
                  <tr>
                    <Th label="Ticker" k="ticker" />
                    <Th label="Company" k="name" />
                    <Th label="Shares" k="shares" />
                    <Th label="Avg Cost" k="avg_cost" />
                    <Th label="Price" k="current_price" />
                    <Th label="Value" k="market_value" />
                    <Th label="P&L" k="pnl" />
                    <Th label="P&L %" k="pnl_percent" />
                    <Th label="Weight" k="weight" />
                    <Th label="Dividends" k="dividends" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {sorted.map((h) => {
                    const up = h.pnl >= 0;
                    const closed = h.closed;
                    return (
                      <tr
                        key={h.ticker}
                        onClick={() => openStock(h.ticker)}
                        className={`hover:bg-surface-hover transition-colors cursor-pointer ${closed ? "bg-loss/10" : ""}`}
                      >
                        <td className="px-4 py-3 font-mono font-bold text-sm">
                          <TickerLink ticker={h.ticker} className="text-left">{h.ticker}</TickerLink>
                          {closed && <span className="ml-1.5 financial-meta font-medium text-loss uppercase">Sold</span>}
                        </td>
                        <td className={`px-4 py-3 text-sm max-w-xs truncate ${closed ? "text-muted" : "text-ink"}`}>{h.name}</td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right ${closed ? "text-muted" : ""}`}>
                          {closed ? "—" : h.shares.toLocaleString()}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right ${closed ? "text-muted" : ""}`}>{fmtNative(h.avg_cost, h.currency)}</td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-medium ${closed ? "text-muted" : ""}`}>
                          <div>{fmtNative(h.current_price, h.currency)}</div>
                          {closed && h.live_price != null && (
                            <div className="financial-meta leading-tight" title="Live market price today">
                              now {fmtNative(h.live_price, h.currency)}
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-semibold ${closed ? "text-muted" : ""}`}>
                          {closed ? "—" : fmt(h.market_value)}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-medium ${up ? "text-gain" : "text-loss"}`}>
                          <span className="flex items-center justify-end gap-1">
                            {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                            {fmt(h.pnl)}
                          </span>
                          {closed && h.pnl_if_held != null && (
                            <div
                              className={`financial-meta leading-tight mt-0.5 font-normal ${h.pnl_if_held >= 0 ? "text-gain" : "text-loss"}`}
                              title="P&L if you had held instead of sold (live price today)"
                            >
                              if held: {h.pnl_if_held >= 0 ? "+" : ""}{fmt(h.pnl_if_held)}
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right font-medium ${up ? "text-gain" : "text-loss"}`}>
                          {fmtPct(h.pnl_percent)}
                          {closed && h.pnl_if_held_pct != null && (
                            <div
                              className={`financial-meta leading-tight mt-0.5 font-normal ${h.pnl_if_held_pct >= 0 ? "text-gain" : "text-loss"}`}
                            >
                              if held: {fmtPct(h.pnl_if_held_pct)}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-right">
                          {closed ? (
                            <span className="text-muted text-xs">—</span>
                          ) : (
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 bg-surface-hover rounded-full h-1.5">
                                <div className="bg-brand rounded-full h-1.5" style={{ width: `${h.weight}%` }} />
                              </div>
                              <span className="tabular-nums text-muted w-10">{h.weight}%</span>
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-right ${closed ? "text-muted" : "text-muted"}`}>
                          {fmt(h.dividends)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
        </>
      </AsyncSection>
    </div>
  );
}
