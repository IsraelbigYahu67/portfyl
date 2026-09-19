import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  fetchOptionsTrades,
  fetchOptionsSummary,
  fetchOptionsByUnderlying,
  fetchOptionsCalendar,
  fetchIBKRBalance,
} from "../api";
import {
  Target,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  TrendingDown,
  ArrowUpDown,
  Wallet,
} from "lucide-react";
import OptionsCalendar from "../components/OptionsCalendar";
import MetricCard from "../components/MetricCard";

const TABS = [
  { key: "underlying", label: "By Underlying" },
  { key: "calendar", label: "Calendar" },
  { key: "trades", label: "All Trades" },
];

function fmtMoney(v) {
  if (v == null) return "-";
  // A negative v previously fell through to "" here, so a loss rendered as
  // a bare positive-looking amount (e.g. "$500.00") distinguished from a
  // gain only by text-gain/text-loss color -- no sign for screen readers or
  // colorblind users. Losses now get an explicit "-".
  const sign = v >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(dateStr) {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtPercent(v) {
  if (v == null) return "-";
  return `${v.toFixed(1)}%`;
}

const CURRENCY_SYMBOLS = {
  USD: "$", EUR: "€", GBP: "£", CZK: "Kč", CHF: "Fr",
  JPY: "¥", CAD: "C$", AUD: "A$", HKD: "HK$", SGD: "S$",
};

// Plain balance figure (no +/- sign forced like fmtMoney does for P&L).
function fmtCurrency(v, ccy) {
  if (v == null) return "-";
  const num = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const sign = v < 0 ? "-" : "";
  const sym = CURRENCY_SYMBOLS[ccy];
  if (sym) return `${sign}${sym}${num}`;
  return `${sign}${num}${ccy ? ` ${ccy}` : ""}`;
}

export default function Options() {
  const [tab, setTab] = useState("underlying");

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["options-summary"],
    queryFn: fetchOptionsSummary,
    staleTime: 5 * 60 * 1000,
  });

  const { data: trades, isLoading: tradesLoading } = useQuery({
    queryKey: ["options-trades"],
    queryFn: fetchOptionsTrades,
    staleTime: 5 * 60 * 1000,
  });

  const { data: byUnderlying, isLoading: underlyingLoading } = useQuery({
    queryKey: ["options-by-underlying"],
    queryFn: fetchOptionsByUnderlying,
    staleTime: 5 * 60 * 1000,
  });

  const { data: calendarData, isLoading: calendarLoading } = useQuery({
    queryKey: ["options-calendar"],
    queryFn: () => fetchOptionsCalendar(),
    staleTime: 5 * 60 * 1000,
  });

  const { data: ibkrBalance, isLoading: balanceLoading } = useQuery({
    queryKey: ["ibkr-balance"],
    queryFn: fetchIBKRBalance,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <Target size={20} className="text-brand" />
          <h1 className="text-xl font-semibold">Options</h1>
        </div>
        <p className="text-sm text-muted">Options trading P&L and analytics</p>
      </div>

      {/* IBKR account balance */}
      <BalancePanel data={ibkrBalance} loading={balanceLoading} />

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard
          icon={TrendingUp}
          label="Total P&L"
          value={fmtMoney(summary?.total_pnl)}
          positive={summary?.total_pnl != null && summary.total_pnl >= 0}
          negative={summary?.total_pnl != null && summary.total_pnl < 0}
          loading={summaryLoading}
        />
        <MetricCard
          icon={Wallet}
          label="Commissions"
          value={fmtMoney(summary?.total_commission ? -Math.abs(summary.total_commission) : null)}
          negative={!!summary?.total_commission}
          loading={summaryLoading}
        />
        <MetricCard
          icon={Target}
          label="Win Rate"
          value={fmtPercent(summary?.win_rate)}
          positive={summary?.win_rate != null && summary.win_rate >= 50}
          loading={summaryLoading}
        />
        <MetricCard
          icon={TrendingUp}
          label="Avg Win"
          value={fmtMoney(summary?.avg_win)}
          positive={summary?.avg_win != null && summary.avg_win >= 0}
          negative={summary?.avg_win != null && summary.avg_win < 0}
          loading={summaryLoading}
        />
        <MetricCard
          icon={TrendingDown}
          label="Avg Loss"
          value={fmtMoney(summary?.avg_loss)}
          positive={summary?.avg_loss != null && summary.avg_loss >= 0}
          negative={summary?.avg_loss != null && summary.avg_loss < 0}
          loading={summaryLoading}
        />
        <MetricCard
          icon={ArrowUpDown}
          label="Total Trades"
          value={summary?.total_trades != null ? summary.total_trades.toLocaleString() : "-"}
          loading={summaryLoading}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 bg-surface-hover rounded-lg p-0.5 w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm rounded-md font-medium transition-colors ${
              tab === t.key
                ? "bg-surface-card text-brand font-semibold shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "underlying" && (
        <ByUnderlyingTab data={byUnderlying} loading={underlyingLoading} />
      )}
      {tab === "calendar" && (
        <CalendarTab data={calendarData} loading={calendarLoading} />
      )}
      {tab === "trades" && (
        <AllTradesTab trades={trades} loading={tradesLoading} />
      )}
    </div>
  );
}

/* ---------- IBKR Balance Panel ---------- */

function BalancePanel({ data, loading }) {
  if (loading) {
    return <div className="rounded-xl border border-surface-border bg-surface-card h-24 animate-pulse" />;
  }

  // No IBKR connection for this portfolio — show nothing.
  if (!data?.connected) return null;

  const bal = data.balance;

  // Connected but no balance stored yet (sections not enabled, or never synced).
  if (!bal) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 flex items-start gap-3">
        <Wallet size={18} className="text-muted mt-0.5 shrink-0" />
        <p className="text-sm text-muted">
          <span className="font-medium text-ink">No IBKR balance yet.</span> Enable the{" "}
          <span className="font-medium">Net Asset Value (NAV) in Base</span> and{" "}
          <span className="font-medium">Cash Report</span> sections in your IBKR Flex Query, then run a sync from Settings.
        </p>
      </div>
    );
  }

  const ccy = bal.base_currency;
  const cashEntries = Object.entries(bal.cash_by_currency || {}).filter(([, v]) => v != null);
  const showCurrencyChips =
    cashEntries.length > 1 || (cashEntries.length === 1 && cashEntries[0][0] !== ccy);

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card overflow-hidden">
      <div className="px-5 py-3.5 flex items-center justify-between border-b border-surface-border">
        <div className="flex items-center gap-2">
          <Wallet size={18} className="text-brand" />
          <span className="text-sm font-semibold text-ink">IBKR Account Balance</span>
          {ccy && <span className="text-xs text-muted font-mono">{ccy}</span>}
        </div>
        {bal.as_of && <span className="text-xs text-muted">as of {fmtDate(bal.as_of)}</span>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-surface-border">
        <BalanceCell label="Net Liquidation" value={bal.net_liquidation} ccy={ccy} emphasis />
        <BalanceCell label="Cash" value={bal.cash} ccy={ccy} />
        <BalanceCell label="Stock" value={bal.stock} ccy={ccy} />
        <BalanceCell label="Options" value={bal.options_value} ccy={ccy} />
      </div>

      {showCurrencyChips && (
        <div className="px-5 py-3 border-t border-surface-border flex flex-wrap items-center gap-2">
          <span className="data-label mr-1">
            Cash by currency
          </span>
          {cashEntries.map(([cur, v]) => (
            <span
              key={cur}
              className="text-xs font-sans bg-surface-hover text-muted rounded px-2 py-1 tabular-nums"
            >
              {cur} {v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function BalanceCell({ label, value, ccy, emphasis }) {
  return (
    <div className="px-5 py-4 flex flex-col gap-1">
      <span className="data-label">{label}</span>
      <span
        className={`tabular-nums font-bold ${
          emphasis ? "text-xl text-ink" : "text-lg text-ink"
        }`}
      >
        {value == null ? "-" : fmtCurrency(value, ccy)}
      </span>
    </div>
  );
}

/* ---------- By Underlying Tab ---------- */

function ByUnderlyingTab({ data, loading }) {
  const [expanded, setExpanded] = useState({});

  if (loading) {
    return <div className="text-center py-16 text-muted">Loading options data...</div>;
  }

  if (!data?.length) {
    return (
      <div className="text-center py-16 text-muted">
        No options trades found. Import options data to see analytics here.
      </div>
    );
  }

  function toggleExpand(ticker) {
    setExpanded((prev) => ({ ...prev, [ticker]: !prev[ticker] }));
  }

  return (
    <div className="space-y-3">
      {data.map((item) => {
        const isOpen = expanded[item.underlying];
        return (
          <div
            key={item.underlying}
            className="rounded-xl border border-surface-border bg-surface-card overflow-hidden"
          >
            {/* Card header */}
            <button
              onClick={() => toggleExpand(item.underlying)}
              className="w-full px-5 py-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono font-bold text-ink text-base">{item.underlying}</span>
                <span className="text-xs text-muted">{item.trade_count} trades</span>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  {item.total_pnl >= 0 ? (
                    <TrendingUp size={14} className="text-gain" />
                  ) : (
                    <TrendingDown size={14} className="text-loss" />
                  )}
                  <span
                    className={`font-bold tabular-nums ${
                      item.total_pnl >= 0 ? "text-gain" : "text-loss"
                    }`}
                  >
                    {fmtMoney(item.total_pnl)}
                  </span>
                </div>
                {item.total_commission > 0 && (
                  <span className="text-xs text-muted tabular-nums">
                    comm: -${item.total_commission.toFixed(2)}
                  </span>
                )}
                <span className="text-xs text-muted">WR: {fmtPercent(item.win_rate)}</span>
                {isOpen ? (
                  <ChevronUp size={16} className="text-muted" />
                ) : (
                  <ChevronDown size={16} className="text-muted" />
                )}
              </div>
            </button>

            {/* Expanded trades table */}
            {isOpen && item.trades?.length > 0 && (
              <div className="border-t border-surface-border overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-surface-hover">
                      {["Date", "Strike", "Expiry", "P/C", "Qty", "Open", "Close", "P&L", "Status"].map(
                        (h) => (
                          <th
                            key={h}
                            className="data-label text-left px-4 py-2.5"
                          >
                            {h}
                          </th>
                        )
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {item.trades.map((trade) => (
                      <tr
                        key={trade.id}
                        className="border-t border-surface-border hover:bg-surface-hover transition-colors"
                      >
                        <td className="px-4 py-2.5 text-muted tabular-nums">{fmtDate(trade.close_date)}</td>
                        <td className="px-4 py-2.5 font-sans text-ink">${trade.strike}</td>
                        <td className="px-4 py-2.5 text-muted tabular-nums">{fmtDate(trade.expiry)}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                              trade.put_call === "PUT"
                                ? "bg-loss/10 text-loss"
                                : "bg-gain/10 text-gain"
                            }`}
                          >
                            {trade.put_call}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-muted tabular-nums">{trade.quantity}</td>
                        <td className="px-4 py-2.5 text-muted tabular-nums">${trade.open_price?.toFixed(2)}</td>
                        <td className="px-4 py-2.5 text-muted tabular-nums">${trade.close_price?.toFixed(2)}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`font-bold tabular-nums ${
                              trade.pnl >= 0 ? "text-gain" : "text-loss"
                            }`}
                          >
                            {fmtMoney(trade.pnl)}
                          </span>
                        </td>
                        <td className="px-4 py-2.5">
                          <StatusBadge status={trade.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ---------- Calendar Tab ---------- */

function CalendarTab({ data, loading }) {
  if (loading) {
    return <div className="text-center py-16 text-muted">Loading calendar data...</div>;
  }

  return <OptionsCalendar data={data || []} />;
}

/* ---------- All Trades Tab ---------- */

function AllTradesTab({ trades, loading }) {
  const [sortKey, setSortKey] = useState("close_date");
  const [sortDir, setSortDir] = useState("desc");

  const sorted = useMemo(() => {
    if (!trades?.length) return [];
    return [...trades].sort((a, b) => {
      let aVal = a[sortKey];
      let bVal = b[sortKey];

      // Handle null values
      if (aVal == null && bVal == null) return 0;
      if (aVal == null) return 1;
      if (bVal == null) return -1;

      // String comparison for dates and strings
      if (typeof aVal === "string") {
        const cmp = aVal.localeCompare(bVal);
        return sortDir === "asc" ? cmp : -cmp;
      }

      // Numeric comparison
      const cmp = aVal - bVal;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [trades, sortKey, sortDir]);

  function handleSort(key) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (loading) {
    return <div className="text-center py-16 text-muted">Loading trades...</div>;
  }

  if (!trades?.length) {
    return (
      <div className="text-center py-16 text-muted">
        No options trades found. Import options data to see trades here.
      </div>
    );
  }

  const columns = [
    { key: "close_date", label: "Close Date" },
    { key: "underlying", label: "Underlying" },
    { key: "strike", label: "Strike" },
    { key: "expiry", label: "Expiry" },
    { key: "put_call", label: "P/C" },
    { key: "quantity", label: "Qty" },
    { key: "open_price", label: "Open Price" },
    { key: "close_price", label: "Close Price" },
    { key: "pnl", label: "P&L" },
    { key: "status", label: "Status" },
  ];

  return (
    <div className="rounded-xl border border-surface-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-card border-b border-surface-border">
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className="data-label text-left px-4 py-3 cursor-pointer hover:text-ink transition-colors select-none"
                >
                  <span className="flex items-center gap-1">
                    {col.label}
                    {sortKey === col.key ? (
                      sortDir === "asc" ? (
                        <ChevronUp size={12} className="text-brand" />
                      ) : (
                        <ChevronDown size={12} className="text-brand" />
                      )
                    ) : (
                      <ArrowUpDown size={10} className="text-muted" />
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((trade) => (
              <tr
                key={trade.id}
                className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors"
              >
                <td className="px-4 py-3 text-muted tabular-nums">{fmtDate(trade.close_date)}</td>
                <td className="px-4 py-3 font-mono font-semibold text-ink">{trade.underlying}</td>
                <td className="px-4 py-3 font-sans text-ink tabular-nums">${trade.strike}</td>
                <td className="px-4 py-3 text-muted tabular-nums">{fmtDate(trade.expiry)}</td>
                <td className="px-4 py-3">
                  <span
                    className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                      trade.put_call === "PUT"
                        ? "bg-loss/10 text-loss"
                        : "bg-gain/10 text-gain"
                    }`}
                  >
                    {trade.put_call}
                  </span>
                </td>
                <td className="px-4 py-3 text-muted tabular-nums">{trade.quantity}</td>
                <td className="px-4 py-3 text-muted tabular-nums">${trade.open_price?.toFixed(2)}</td>
                <td className="px-4 py-3 text-muted tabular-nums">${trade.close_price?.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span
                    className={`font-bold tabular-nums ${
                      trade.pnl >= 0 ? "text-gain" : "text-loss"
                    }`}
                  >
                    {fmtMoney(trade.pnl)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={trade.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- Status Badge ---------- */

function StatusBadge({ status }) {
  if (!status) return <span className="text-muted">-</span>;

  const styles = {
    closed: "bg-surface-hover text-muted",
    expired: "bg-yellow-50 text-yellow-700",
    assigned: "bg-purple-50 text-purple-700",
    open: "bg-blue-50 text-blue-700",
  };

  const className = styles[status?.toLowerCase()] || "bg-surface-hover text-muted";

  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full uppercase ${className}`}>
      {status}
    </span>
  );
}
