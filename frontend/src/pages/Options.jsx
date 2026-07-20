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

const TABS = [
  { key: "underlying", label: "By Underlying" },
  { key: "calendar", label: "Calendar" },
  { key: "trades", label: "All Trades" },
];

function fmtMoney(v) {
  if (v == null) return "-";
  const sign = v >= 0 ? "+" : "";
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
        <p className="text-sm text-slate-500">Options trading P&L and analytics</p>
      </div>

      {/* IBKR account balance */}
      <BalancePanel data={ibkrBalance} loading={balanceLoading} />

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <SummaryCard label="Total P&L" value={summary?.total_pnl} isMoney loading={summaryLoading} />
        <SummaryCard label="Commissions" value={summary?.total_commission ? -Math.abs(summary.total_commission) : null} isMoney loading={summaryLoading} />
        <SummaryCard label="Win Rate" value={summary?.win_rate} isPercent loading={summaryLoading} />
        <SummaryCard label="Avg Win" value={summary?.avg_win} isMoney loading={summaryLoading} />
        <SummaryCard label="Avg Loss" value={summary?.avg_loss} isMoney loading={summaryLoading} />
        <SummaryCard label="Total Trades" value={summary?.total_trades} isCount loading={summaryLoading} />
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 bg-slate-100 rounded-lg p-0.5 w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm rounded-md font-medium transition-colors ${
              tab === t.key
                ? "bg-white text-brand font-semibold shadow-sm"
                : "text-slate-500 hover:text-slate-700"
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

/* ---------- Summary Card ---------- */

function SummaryCard({ label, value, isMoney, isPercent, isCount, loading }) {
  let displayValue = "-";
  let colorClass = "text-slate-800";

  if (!loading && value != null) {
    if (isMoney) {
      displayValue = fmtMoney(value);
      colorClass = value >= 0 ? "text-emerald-600" : "text-red-600";
    } else if (isPercent) {
      displayValue = fmtPercent(value);
      colorClass = value >= 50 ? "text-emerald-600" : "text-slate-800";
    } else if (isCount) {
      displayValue = value.toLocaleString();
    }
  }

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4 flex flex-col gap-1">
      <span className="text-[11px] text-slate-500 uppercase tracking-wider font-medium">{label}</span>
      {loading ? (
        <div className="h-7 w-20 bg-slate-100 rounded animate-pulse mt-1" />
      ) : (
        <span className={`text-lg font-bold tabular-nums ${colorClass}`}>{displayValue}</span>
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
        <Wallet size={18} className="text-slate-400 mt-0.5 shrink-0" />
        <p className="text-sm text-slate-500">
          <span className="font-medium text-slate-700">No IBKR balance yet.</span> Enable the{" "}
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
          <span className="text-sm font-semibold text-slate-700">IBKR Account Balance</span>
          {ccy && <span className="text-xs text-slate-400 font-mono">{ccy}</span>}
        </div>
        {bal.as_of && <span className="text-xs text-slate-400">as of {fmtDate(bal.as_of)}</span>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-surface-border">
        <BalanceCell label="Net Liquidation" value={bal.net_liquidation} ccy={ccy} emphasis />
        <BalanceCell label="Cash" value={bal.cash} ccy={ccy} />
        <BalanceCell label="Stock" value={bal.stock} ccy={ccy} />
        <BalanceCell label="Options" value={bal.options_value} ccy={ccy} />
      </div>

      {showCurrencyChips && (
        <div className="px-5 py-3 border-t border-surface-border flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-slate-400 font-medium mr-1">
            Cash by currency
          </span>
          {cashEntries.map(([cur, v]) => (
            <span
              key={cur}
              className="text-xs font-sans bg-slate-100 text-slate-600 rounded px-2 py-1 tabular-nums"
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
      <span className="text-[11px] text-slate-500 uppercase tracking-wider font-medium">{label}</span>
      <span
        className={`tabular-nums font-bold ${
          emphasis ? "text-xl text-slate-900" : "text-lg text-slate-800"
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
    return <div className="text-center py-16 text-slate-400">Loading options data...</div>;
  }

  if (!data?.length) {
    return (
      <div className="text-center py-16 text-slate-400">
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
                <span className="font-mono font-bold text-slate-800 text-base">{item.underlying}</span>
                <span className="text-xs text-slate-400">{item.trade_count} trades</span>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  {item.total_pnl >= 0 ? (
                    <TrendingUp size={14} className="text-emerald-600" />
                  ) : (
                    <TrendingDown size={14} className="text-red-600" />
                  )}
                  <span
                    className={`font-bold tabular-nums ${
                      item.total_pnl >= 0 ? "text-emerald-600" : "text-red-600"
                    }`}
                  >
                    {fmtMoney(item.total_pnl)}
                  </span>
                </div>
                {item.total_commission > 0 && (
                  <span className="text-xs text-slate-400 tabular-nums">
                    comm: -${item.total_commission.toFixed(2)}
                  </span>
                )}
                <span className="text-xs text-slate-500">WR: {fmtPercent(item.win_rate)}</span>
                {isOpen ? (
                  <ChevronUp size={16} className="text-slate-400" />
                ) : (
                  <ChevronDown size={16} className="text-slate-400" />
                )}
              </div>
            </button>

            {/* Expanded trades table */}
            {isOpen && item.trades?.length > 0 && (
              <div className="border-t border-surface-border overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-slate-50">
                      {["Date", "Strike", "Expiry", "P/C", "Qty", "Open", "Close", "P&L", "Status"].map(
                        (h) => (
                          <th
                            key={h}
                            className="text-left px-4 py-2.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider"
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
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">{fmtDate(trade.close_date)}</td>
                        <td className="px-4 py-2.5 font-sans text-slate-700">${trade.strike}</td>
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">{fmtDate(trade.expiry)}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                              trade.put_call === "PUT"
                                ? "bg-red-50 text-red-600"
                                : "bg-emerald-50 text-emerald-600"
                            }`}
                          >
                            {trade.put_call}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">{trade.quantity}</td>
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">${trade.open_price?.toFixed(2)}</td>
                        <td className="px-4 py-2.5 text-slate-600 tabular-nums">${trade.close_price?.toFixed(2)}</td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`font-bold tabular-nums ${
                              trade.pnl >= 0 ? "text-emerald-600" : "text-red-600"
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
    return <div className="text-center py-16 text-slate-400">Loading calendar data...</div>;
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
    return <div className="text-center py-16 text-slate-400">Loading trades...</div>;
  }

  if (!trades?.length) {
    return (
      <div className="text-center py-16 text-slate-400">
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
                  className="text-left px-4 py-3 text-[10px] font-semibold text-slate-500 uppercase tracking-wider cursor-pointer hover:text-slate-700 transition-colors select-none"
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
                      <ArrowUpDown size={10} className="text-slate-300" />
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
                <td className="px-4 py-3 text-slate-600 tabular-nums">{fmtDate(trade.close_date)}</td>
                <td className="px-4 py-3 font-mono font-semibold text-slate-800">{trade.underlying}</td>
                <td className="px-4 py-3 font-sans text-slate-700 tabular-nums">${trade.strike}</td>
                <td className="px-4 py-3 text-slate-600 tabular-nums">{fmtDate(trade.expiry)}</td>
                <td className="px-4 py-3">
                  <span
                    className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
                      trade.put_call === "PUT"
                        ? "bg-red-50 text-red-600"
                        : "bg-emerald-50 text-emerald-600"
                    }`}
                  >
                    {trade.put_call}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600 tabular-nums">{trade.quantity}</td>
                <td className="px-4 py-3 text-slate-600 tabular-nums">${trade.open_price?.toFixed(2)}</td>
                <td className="px-4 py-3 text-slate-600 tabular-nums">${trade.close_price?.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span
                    className={`font-bold tabular-nums ${
                      trade.pnl >= 0 ? "text-emerald-600" : "text-red-600"
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
  if (!status) return <span className="text-slate-400">-</span>;

  const styles = {
    closed: "bg-slate-100 text-slate-600",
    expired: "bg-yellow-50 text-yellow-700",
    assigned: "bg-purple-50 text-purple-700",
    open: "bg-blue-50 text-blue-700",
  };

  const className = styles[status?.toLowerCase()] || "bg-slate-100 text-slate-600";

  return (
    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase ${className}`}>
      {status}
    </span>
  );
}
