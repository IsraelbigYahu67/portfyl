import { useQuery } from "@tanstack/react-query";
import { fetchDividends, fetchDividendForecast } from "../api";
import { CalendarDays, RefreshCw, TrendingUp, DollarSign } from "lucide-react";
import { useStockDetail } from "../components/StockDetail";
import MetricCard from "../components/MetricCard";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

const today = new Date().toISOString().slice(0, 10);

function statusBadge(exDate) {
  if (!exDate) return null;
  const diff = Math.ceil((new Date(exDate) - new Date(today)) / 86400000);
  if (diff < 0) return <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">Past</span>;
  if (diff === 0) return <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400">Today</span>;
  if (diff <= 7) return <span className="text-xs px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-400">In {diff}d</span>;
  if (diff <= 30) return <span className="text-xs px-2 py-0.5 rounded-full bg-brand/20 text-brand">In {diff}d</span>;
  return <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">In {diff}d</span>;
}

function fmt(dateStr) {
  if (!dateStr) return <span className="text-slate-400">—</span>;
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function fmtMoney(v, ccy = "USD") {
  if (v == null) return "—";
  const symbol = ccy === "USD" ? "$" : "";
  const suffix = ccy === "USD" ? "" : ` ${ccy}`;
  return `${symbol}${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}${suffix}`;
}

export default function Dividends() {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["dividends"],
    queryFn: fetchDividends,
    staleTime: 5 * 60 * 1000,
  });

  const {
    data: forecast,
    isLoading: forecastLoading,
    isFetching: forecastFetching,
    refetch: refetchForecast,
  } = useQuery({
    queryKey: ["dividends-forecast"],
    queryFn: fetchDividendForecast,
    staleTime: 5 * 60 * 1000,
  });

  const upcoming = data?.filter((d) => d.ex_date && d.ex_date >= today) ?? [];
  const past = data?.filter((d) => !d.ex_date || d.ex_date < today) ?? [];

  const refreshing = isFetching || forecastFetching;
  const refreshAll = () => {
    refetch();
    refetchForecast();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Dividend Calendar</h1>
          <p className="text-sm text-slate-500 mt-0.5">Ex-dates and pay-dates for your portfolio holdings</p>
        </div>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-sm text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <ForecastChart forecast={forecast} loading={forecastLoading} />

      {isLoading ? (
        <div className="text-center py-20 text-slate-400">Loading dividend data…</div>
      ) : !data?.length ? (
        <div className="text-center py-20 text-slate-400">No holdings found. Import a portfolio to see dividend info.</div>
      ) : (
        <>
          {upcoming.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                <CalendarDays size={13} /> Upcoming ex-dates
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={upcoming} />
              </div>
            </section>
          )}

          {past.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                <CalendarDays size={13} /> Past / no upcoming date
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={past} />
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ForecastChart({ forecast, loading }) {
  if (loading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-slate-500">
        Loading forecast…
      </div>
    );
  }
  if (!forecast?.months?.length) return null;

  const hasAny = forecast.months.some((m) => m.paid > 0 || m.estimated > 0);
  if (!hasAny) return null;

  const tickFormatter = (v) =>
    v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
        <DollarSign size={13} /> Dividend income {forecast.year}
      </h2>
      <div className="grid grid-cols-2 gap-4">
        <MetricCard icon={DollarSign} label="Paid YTD" value={fmtMoney(forecast.total_paid)} />
        <MetricCard icon={TrendingUp} label="Estimated remaining" value={fmtMoney(forecast.total_estimated)} />
      </div>
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={forecast.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis dataKey="month" tick={{ fill: "#6b7280", fontSize: 11 }} />
            <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickFormatter={tickFormatter} width={56} />
            <Tooltip content={<ForecastTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
            <Legend
              formatter={(v) => (
                <span className="text-xs text-slate-500">
                  {v === "paid" ? "Paid" : "Estimated"}
                </span>
              )}
            />
            <Bar dataKey="paid" stackId="div" fill="#22c55e" radius={[0, 0, 0, 0]} />
            <Bar dataKey="estimated" stackId="div" fill="#7c3aed" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function ForecastTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const paid = row.paid ?? 0;
  const est = row.estimated ?? 0;
  const entries = row.entries ?? [];

  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs shadow-lg max-w-[320px]">
      <p className="text-slate-500 mb-1.5">{label}</p>

      {entries.length > 0 ? (
        <div className="space-y-1 mb-2">
          {entries.map((e) => (
            <div key={`${e.ticker}-${e.status}`} className="flex justify-between gap-4 items-center">
              <span className="flex items-center gap-2 min-w-0">
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                    e.status === "paid" ? "bg-emerald-600" : "bg-brand"
                  }`}
                />
                <span className="font-mono text-slate-800 shrink-0">{e.ticker}</span>
                <span className="text-slate-500 truncate">{e.name}</span>
              </span>
              <span
                className={`font-medium tabular-nums shrink-0 ${
                  e.status === "paid" ? "text-emerald-600" : "text-brand"
                }`}
                title={e.status === "paid" ? "Already paid" : "Estimated"}
              >
                {e.status === "paid" ? "" : "~"}
                {fmtMoney(e.amount)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-slate-400 mb-2">No dividends</p>
      )}

      <div className="space-y-1 pt-1.5 border-t border-surface-border">
        {paid > 0 && (
          <div className="flex justify-between gap-6">
            <span className="text-slate-500">Paid</span>
            <span className="font-medium text-emerald-600">{fmtMoney(paid)}</span>
          </div>
        )}
        {est > 0 && (
          <div className="flex justify-between gap-6">
            <span className="text-slate-500">Estimated</span>
            <span className="font-medium text-brand">{fmtMoney(est)}</span>
          </div>
        )}
        <div className="flex justify-between gap-6">
          <span className="text-slate-500">Total</span>
          <span className="font-medium text-slate-800">{fmtMoney(paid + est)}</span>
        </div>
      </div>
    </div>
  );
}

function Table({ rows }) {
  const { openStock } = useStockDetail();
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-surface-border bg-surface-card">
          {["Ticker", "Company", "Shares", "Ex-Date", "Pay-Date", "Rate/Share", "Annual Income", "Yield", ""].map((h) => (
            <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.ticker}
            onClick={() => openStock(row.ticker)}
            className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
          >
            <td className="px-4 py-3 font-mono font-semibold text-slate-800">{row.ticker}</td>
            <td className="px-4 py-3 text-slate-500 max-w-[180px] truncate">{row.name}</td>
            <td className="px-4 py-3 text-slate-500 tabular-nums">{row.shares.toLocaleString()}</td>
            <td className="px-4 py-3 text-slate-500 tabular-nums">{fmt(row.ex_date)}</td>
            <td className="px-4 py-3 text-slate-500 tabular-nums">{fmt(row.pay_date)}</td>
            <td className="px-4 py-3 text-slate-500 tabular-nums">
              {row.dividend_rate != null ? (
                <span className="flex items-center gap-1">
                  <DollarSign size={11} className="text-brand" />
                  {row.dividend_rate.toFixed(2)} {row.currency}
                </span>
              ) : <span className="text-slate-400">—</span>}
            </td>
            <td className="px-4 py-3 text-slate-800 tabular-nums font-medium">
              {row.annual_income != null
                ? `${row.annual_income.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${row.currency}`
                : <span className="text-slate-400">—</span>}
            </td>
            <td className="px-4 py-3 tabular-nums">
              {row.dividend_yield != null ? (
                <span className="flex items-center gap-1 text-brand">
                  <TrendingUp size={11} />
                  {row.dividend_yield.toFixed(2)}%
                </span>
              ) : <span className="text-slate-400">—</span>}
            </td>
            <td className="px-4 py-3">{statusBadge(row.ex_date)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
