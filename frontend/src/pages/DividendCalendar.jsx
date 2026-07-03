import { useQuery } from "@tanstack/react-query";
import { fetchDividendCalendar } from "../api";
import { CalendarDays, DollarSign, TrendingUp, RefreshCw, ChevronDown, Info } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { useStockDetail } from "../components/StockDetail";

function fmtMoney(v) {
  if (v == null || isNaN(v)) return "—";
  return `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(v) {
  if (v == null || isNaN(v)) return "—";
  return `${Number(v).toFixed(2)}%`;
}

export default function DividendCalendar() {
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["dividend-calendar"],
    queryFn: () => fetchDividendCalendar(12),
    staleTime: 10 * 60 * 1000,
  });

  const { openStock } = useStockDetail();
  const tickers = data?.tickers ?? [];
  const monthly = data?.monthly_projection ?? [];

  const chartData = monthly.map((m) => ({
    month: m.label,
    total: m.total,
    items: m.items,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Forward Dividend Calendar</h1>
          <p className="text-sm text-slate-500 mt-0.5">12-month dividend projection based on held positions</p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-sm text-slate-500 hover:text-slate-800 transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Est. Annual Income</p>
          <p className="text-2xl font-semibold text-brand">
            {fmtMoney(data?.total_annual_est)}
          </p>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Dividend Payers</p>
          <p className="text-2xl font-semibold">{tickers.filter((t) => t.amount_per_share != null).length} / {tickers.length}</p>
        </div>
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Next 30 Days Est.</p>
          <p className="text-2xl font-semibold text-emerald-600">
            {fmtMoney(monthly.slice(0, 1).reduce((s, m) => s + m.total, 0))}
          </p>
        </div>
      </div>

      {/* Monthly projection chart */}
      {chartData.length > 0 && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-4">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            <DollarSign size={13} /> Monthly Projection
          </h2>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: "#6b7280", fontSize: 11 }} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickFormatter={(v) => v >= 1000 ? `$${(v/1000).toFixed(1)}k` : `$${v.toFixed(0)}`} width={64} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs shadow-lg max-w-[240px]">
                      <p className="text-slate-500 mb-1.5 font-medium">{d.month}</p>
                      <p className="text-brand font-semibold">{fmtMoney(d.total)}</p>
                      {d.items?.slice(0, 5).map((i) => (
                        <p key={i.ticker} className="text-slate-500 flex justify-between gap-4 mt-1">
                          <span>{i.ticker}</span>
                          <span>{fmtMoney(i.est_payment)}</span>
                        </p>
                      ))}
                      {d.items?.length > 5 && (
                        <p className="text-slate-400 mt-1">…and {d.items.length - 5} more</p>
                      )}
                    </div>
                  );
                }}
                cursor={{ fill: "rgba(255,255,255,0.03)" }}
              />
              <Bar dataKey="total" fill="var(--brand, #059669)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Holdings table with dividend info */}
      {isLoading ? (
        <div className="text-center py-20 text-slate-400">Loading dividend calendar…</div>
      ) : !tickers.length ? (
        <div className="text-center py-20 text-slate-400">No holdings found. Import a portfolio first.</div>
      ) : (
        <div className="rounded-xl border border-surface-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-border bg-surface-card">
                {["Ticker", "Shares", "Freq.", "Amt/Share", "Next Ex-Date", "Est. Next Payment", "Annual Est.", "Yield"].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tickers.map((row) => (
                <tr
                  key={row.ticker}
                  onClick={() => openStock(row.ticker)}
                  className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
                >
                  <td className="px-4 py-3 font-mono font-semibold text-slate-800">{row.ticker}</td>
                  <td className="px-4 py-3 text-slate-500 tabular-nums">{row.held_shares?.toLocaleString() ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-500">{row.frequency ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-500 tabular-nums">{fmtMoney(row.amount_per_share)}</td>
                  <td className="px-4 py-3 text-slate-500 tabular-nums">{row.ex_date ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-800 font-medium tabular-nums">{fmtMoney(row.est_next_payment)}</td>
                  <td className="px-4 py-3 text-slate-800 font-medium tabular-nums">{fmtMoney(row.amount_per_share != null && row.held_shares != null ? row.amount_per_share * row.held_shares * (row.frequency === "monthly" ? 12 : row.frequency === "quarterly" ? 4 : row.frequency === "semi-annual" ? 2 : 1) : null)}</td>
                  <td className="px-4 py-3 tabular-nums">{row.trailing_yield_pct != null ? <span className="text-brand flex items-center gap-1"><TrendingUp size={11} />{row.trailing_yield_pct.toFixed(2)}%</span> : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
