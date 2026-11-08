import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAllHoldings, fetchSectorBreakdown } from "../api";
import { useCurrency, usePortfolio } from "../App";
import { formatMoney, formatPercent, formatQuantity } from "../lib/format";
import { allocationRows, boundedAllocationRows } from "../lib/allocationBreakdown";
import { TrendingUp, TrendingDown, RefreshCw } from "lucide-react";
import { TickerLink, useStockDetail } from "../components/StockDetail";
import BreakdownChart from "../components/BreakdownChart";
import { AsyncSection } from "../components/ui";
import AllocationTargets from "../components/AllocationTargets";
import { hasPriceProblem, priceFreshnessTitle } from "../lib/priceFreshness";
import { useIsPhone } from "../hooks/useMediaQuery";
import { CardSortBar, HoldingCards, SoldCards, SORT_OPTIONS, SOLD_SORT_OPTIONS } from "../components/HoldingCards";

const fmtPct = (n) => formatPercent(n);

// Right-edge fade shown while the table scrolls sideways and its end is not
// yet in view, so a clipped column reads as "more this way".
const SCROLL_FADE = "linear-gradient(to right, black 92%, transparent)";

function useScrollCue(el, dependency) {
  const [cue, setCue] = useState(false);
  useEffect(() => {
    if (!el) return undefined;
    const measure = () => {
      const overflowing = el.scrollWidth > el.clientWidth;
      const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 1;
      setCue(overflowing && !atEnd);
    };
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => {
      el.removeEventListener("scroll", measure);
      window.removeEventListener("resize", measure);
    };
  }, [el, dependency]);
  return cue;
}

export default function Allocation() {
  const { currency } = useCurrency();
  const currentPortfolio = usePortfolio()?.current;
  const { openStock } = useStockDetail();
  // Phones get a card per position instead of the 10-column tables.
  const isPhone = useIsPhone();

  // Portfolio-level money (value, P&L, dividends) is shown in the display
  // currency (CZK by default). Per-share prices (avg cost, current price) are
  // shown in each stock's *native* currency — a US stock's price is $, not Kč.
  const fmt = (n) => formatMoney(n, currency);
  const missedOut = (h) => (h.pnl_if_held ?? 0) - (h.pnl ?? 0);
  const fmtSigned = (n) => (n >= 0 ? `+${fmt(n)}` : fmt(n));
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

  // Positions get a full-width card; the other breakdowns sit side by side
  // beneath it (plus Account when the portfolio has several).
  const positionRows = useMemo(
    () => boundedAllocationRows(allocationRows({ category: "position", holdings, breakdown })),
    [holdings, breakdown]
  );
  const sideCategories = useMemo(() => {
    const list = ["sector", "asset_type", "currency"];
    if (breakdown?.accounts?.length) list.push("account");
    return list.map((category) => ({
      category,
      rows: boundedAllocationRows(allocationRows({ category, holdings, breakdown })),
    }));
  }, [holdings, breakdown]);
  const soldHoldings = useMemo(() => holdings.filter((h) => h.closed), [holdings]);
  // Sold positions can be ordered by their last three columns; null sorts last.
  const [soldSort, setSoldSort] = useState(null);
  const SOLD_SORT_VALUE = {
    pnl_if_held: (h) => h.pnl_if_held,
    missed_out: (h) => (h.pnl != null && h.pnl_if_held != null ? h.pnl_if_held - h.pnl : null),
    pnl_if_held_pct: (h) => h.pnl_if_held_pct,
  };
  const soldSorted = useMemo(() => {
    if (!soldSort) return soldHoldings;
    const value = SOLD_SORT_VALUE[soldSort.key];
    const dir = soldSort.dir === "asc" ? 1 : -1;
    return [...soldHoldings].sort((a, b) => {
      const x = value(a);
      const y = value(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (x - y) * dir;
    });
  }, [soldHoldings, soldSort]);
  const missedOutTotal = useMemo(
    () => soldHoldings.reduce((sum, h) => sum + (SOLD_SORT_VALUE.missed_out(h) ?? 0), 0),
    [soldHoldings]
  );
  const toggleSoldSort = (key) =>
    setSoldSort((s) => (s?.key === key && s.dir === "desc" ? { key, dir: "asc" } : { key, dir: "desc" }));
  const CATEGORY_TITLE = {
    position: "Positions",
    sector: "Sector Allocation",
    asset_type: "Asset Type",
    currency: "Currency Exposure",
    account: "Account",
  };

  const [sort, setSort] = useState({ key: "market_value", dir: "desc" });

  // All Holdings lists open positions only; sold ones have their own section.
  const visibleHoldings = holdings.filter((h) => !h.closed);
  const [scroller, setScroller] = useState(null);
  const scrollCue = useScrollCue(scroller, visibleHoldings.length);

  const sorted = [...visibleHoldings].sort((a, b) => {
    const v = a[sort.key] > b[sort.key] ? 1 : -1;
    return sort.dir === "asc" ? v : -v;
  });

  const toggle = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));

  const Th = ({ label, k, pinned = false }) => (
    <th
      onClick={() => toggle(k)}
      className={`${label === "Company" || label === "Ticker" ? "text-left" : "text-center"} px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider cursor-pointer hover:text-ink select-none ${pinned ? "sticky left-0 z-[1] bg-surface-card" : ""}`}
    >
      {label}
      {sort.key === k && <span className="ml-1">{sort.dir === "asc" ? "↑" : "↓"}</span>}
    </th>
  );

  return (
    <div className="space-y-6 hover-pop-zone no-block-pop">
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
          <BreakdownChart
            title={CATEGORY_TITLE.position}
            data={positionRows}
            currencyLabel={currency}
            legendColumns={2}
            shortenTickers
          />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {sideCategories.map(({ category, rows }) => (
              <BreakdownChart
                key={category}
                title={CATEGORY_TITLE[category]}
                data={rows}
                currencyLabel={currency}
                stacked
                nameWidth={category === "sector" ? 110 : 70}
              />
            ))}
          </div>
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
        ) : isPhone ? (
          <>
            <CardSortBar sort={sort} onSort={toggle} options={SORT_OPTIONS} />
            <HoldingCards
              holdings={sorted}
              currency={currency}
              fmt={fmt}
              fmtSigned={fmtSigned}
              fmtNative={fmtNative}
              onOpen={openStock}
            />
          </>
        ) : (
          <div className="card p-0 overflow-hidden">
            <div
              ref={setScroller}
              className="overflow-x-auto"
              data-scroll-cue={scrollCue ? "true" : "false"}
              style={scrollCue ? { maskImage: SCROLL_FADE, WebkitMaskImage: SCROLL_FADE } : undefined}
            >
              <table className="w-full" aria-label="All holdings">
                <thead className="border-b border-surface-border">
                  <tr>
                    <Th label="Ticker" k="ticker" pinned />
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
                        <td className="px-4 py-3 font-mono font-bold text-sm sticky left-0 z-[1] bg-surface-card">
                          <TickerLink ticker={h.ticker} className="text-left">{h.ticker}</TickerLink>
                          {closed && <span className="ml-1.5 financial-meta font-medium text-loss uppercase">Sold</span>}
                        </td>
                        <td className={`px-4 py-3 text-sm max-w-xs truncate mx-auto ${closed ? "text-muted" : "text-ink"}`}>{h.name}</td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-center ${closed ? "text-muted" : ""}`}>
                          {closed ? "—" : formatQuantity(h.shares, currency)}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-center ${closed ? "text-muted" : ""}`}>{fmtNative(h.avg_cost, h.currency)}</td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-center font-medium ${closed ? "text-muted" : ""}`}>
                          <div title={closed ? undefined : priceFreshnessTitle(h) ?? undefined}>
                            {fmtNative(h.current_price, h.currency)}
                          </div>
                          {!closed && hasPriceProblem(h) && (
                            <div
                              className={`financial-meta leading-tight ${h.price_status === "missing" ? "text-loss" : "text-[color:var(--chart-3)]"}`}
                              title={priceFreshnessTitle(h)}
                            >
                              {h.price_status === "missing" ? "no price" : "out of date"}
                            </div>
                          )}
                          {closed && h.live_price != null && (
                            <div className="financial-meta leading-tight" title="Live market price today">
                              now {fmtNative(h.live_price, h.currency)}
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-center font-semibold ${closed ? "text-muted" : ""}`}>
                          {closed ? "—" : fmt(h.market_value)}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-center font-medium ${up ? "text-gain" : "text-loss"}`}>
                          <span className="flex items-center justify-center gap-1">
                            {up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                            {fmtSigned(h.pnl)}
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
                        <td className={`px-4 py-3 tabular-nums text-sm text-center font-medium ${up ? "text-gain" : "text-loss"}`}>
                          {fmtPct(h.pnl_percent)}
                          {closed && h.pnl_if_held_pct != null && (
                            <div
                              className={`financial-meta leading-tight mt-0.5 font-normal ${h.pnl_if_held_pct >= 0 ? "text-gain" : "text-loss"}`}
                            >
                              if held: {fmtPct(h.pnl_if_held_pct)}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-center">
                          {closed ? (
                            <span className="text-muted text-xs">—</span>
                          ) : (
                            <div className="flex items-center justify-center gap-2">
                              <div className="w-16 bg-surface-hover rounded-full h-1.5">
                                <div className="bg-brand rounded-full h-1.5" style={{ width: `${h.weight}%` }} />
                              </div>
                              <span className="tabular-nums text-muted w-14 text-right">{formatPercent(h.weight, { sign: false, digits: 2 })}</span>
                            </div>
                          )}
                        </td>
                        <td className={`px-4 py-3 tabular-nums text-sm text-center ${closed ? "text-muted" : "text-muted"}`}>
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
      <div>
        <h2 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wider">
          Sold Positions
        </h2>
        {isPhone && soldHoldings.length > 0 ? (
          <>
            <CardSortBar
              sort={soldSort ?? { key: SOLD_SORT_OPTIONS[0].key, dir: "desc" }}
              onSort={toggleSoldSort}
              options={SOLD_SORT_OPTIONS}
              label="Sort sold positions"
            />
            <p className={`financial-meta mb-3 ${missedOutTotal >= 0 ? "text-gain" : "text-loss"}`}>
              Missed out on, total: {fmtSigned(missedOutTotal)}
            </p>
            <SoldCards holdings={soldSorted} fmtSigned={fmtSigned} fmtPct={fmtPct} missedOut={missedOut} onOpen={openStock} />
          </>
        ) : (
        <div className="card p-0 overflow-hidden">
          {soldHoldings.length === 0 ? (
            <div className="text-muted text-sm text-center py-12">No sold positions.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full" aria-label="Sold positions">
                <thead className="border-b border-surface-border">
                  <tr>
                    {[
                      ["Ticker"],
                      ["Company"],
                      ["Sold for"],
                      ["Return if not sold", "pnl_if_held"],
                      ["Missed out on", "missed_out"],
                      ["P&L if held", "pnl_if_held_pct"],
                    ].map(([label, key]) => (
                      <th
                        key={label}
                        onClick={key ? () => toggleSoldSort(key) : undefined}
                        aria-sort={key && soldSort?.key === key ? (soldSort.dir === "asc" ? "ascending" : "descending") : undefined}
                        className={`relative ${label === "Company" || label === "Ticker" ? "text-left" : "text-center"} px-4 pt-3 pb-6 text-xs font-medium text-muted uppercase tracking-wider ${key ? "cursor-pointer hover:text-ink select-none" : ""}`}
                      >
                        {label}
                        {key && soldSort?.key === key && <span className="ml-1">{soldSort.dir === "asc" ? "↑" : "↓"}</span>}
                        {key === "missed_out" && (
                          <div className={`financial-meta absolute inset-x-0 bottom-1.5 font-normal normal-case tracking-normal ${missedOutTotal >= 0 ? "text-gain" : "text-loss"}`}>
                            Total: {fmtSigned(missedOutTotal)}
                          </div>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {soldSorted.map((h) => (
                    <tr key={h.ticker} onClick={() => openStock(h.ticker)} className="hover:bg-surface-hover transition-colors cursor-pointer bg-loss/10">
                      <td className="px-4 py-3 font-mono font-bold text-sm">
                        <TickerLink ticker={h.ticker} className="text-left">{h.ticker}</TickerLink>
                        <span className="ml-1.5 financial-meta font-medium text-loss uppercase">Sold</span>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted max-w-xs truncate mx-auto">{h.name}</td>
                      <td className={`px-4 py-3 tabular-nums text-sm text-center ${(h.pnl ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>
                        {h.pnl != null ? fmtSigned(h.pnl) : "—"}
                      </td>
                      <td className={`px-4 py-3 tabular-nums text-sm text-center ${(h.pnl_if_held ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>
                        {h.pnl_if_held != null ? fmtSigned(h.pnl_if_held) : "—"}
                      </td>
                      <td className={`px-4 py-3 tabular-nums text-sm text-center ${missedOut(h) >= 0 ? "text-gain" : "text-loss"}`}>
                        {h.pnl != null && h.pnl_if_held != null ? fmtSigned(missedOut(h)) : "—"}
                      </td>
                      <td className={`px-4 py-3 tabular-nums text-sm text-center ${(h.pnl_if_held_pct ?? 0) >= 0 ? "text-gain" : "text-loss"}`}>
                        {h.pnl_if_held_pct != null ? fmtPct(h.pnl_if_held_pct) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        )}
      </div>

      {/* Keyed on the portfolio so an open target draft never survives a
          portfolio switch and gets saved into the newly active portfolio. */}
      <AllocationTargets key={currentPortfolio?.id ?? "none"} currency={currency} />
        </>
      </AsyncSection>
    </div>
  );
}
