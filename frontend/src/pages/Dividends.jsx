import { useQuery } from "@tanstack/react-query";
import { fetchDividends, fetchDividendForecast, fetchDividendGrowth } from "../api";
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
import { CATEGORICAL, GAIN_COLOR, AXIS_TICK, GRID_STROKE } from "../lib/chartTheme";

const today = new Date().toISOString().slice(0, 10);

function statusBadge(exDate) {
  if (!exDate) return null;
  const diff = Math.ceil((new Date(exDate) - new Date(today)) / 86400000);
  if (diff < 0) return <span className="text-xs px-2 py-0.5 rounded-full bg-surface-hover text-muted">Past</span>;
  if (diff === 0) return <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400">Today</span>;
  if (diff <= 7) return <span className="text-xs px-2 py-0.5 rounded-full bg-orange-500/20 text-orange-400">In {diff}d</span>;
  if (diff <= 30) return <span className="text-xs px-2 py-0.5 rounded-full bg-brand/20 text-brand">In {diff}d</span>;
  return <span className="text-xs px-2 py-0.5 rounded-full bg-surface-hover text-muted">In {diff}d</span>;
}

function fmt(dateStr) {
  if (!dateStr) return <span className="text-muted">—</span>;
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

  const { data: growth, isLoading: growthLoading } = useQuery({
    queryKey: ["dividend-growth"],
    queryFn: fetchDividendGrowth,
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
          <p className="text-sm text-muted mt-0.5">Ex-dates and pay-dates for your portfolio holdings</p>
        </div>
        <button
          onClick={refreshAll}
          disabled={refreshing}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-sm text-muted hover:text-ink transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      <ForecastChart forecast={forecast} loading={forecastLoading} />

      <GrowthSection rows={growth} loading={growthLoading} />

      {isLoading ? (
        <div className="text-center py-20 text-muted">Loading dividend data…</div>
      ) : !data?.length ? (
        <div className="text-center py-20 text-muted">No holdings found. Import a portfolio to see dividend info.</div>
      ) : (
        <>
          {upcoming.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
                <CalendarDays size={13} /> Upcoming ex-dates
              </h2>
              <div className="rounded-xl border border-surface-border overflow-hidden">
                <Table rows={upcoming} />
              </div>
            </section>
          )}

          {past.length > 0 && (
            <section>
              <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
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
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-muted">
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
      <h2 className="text-xs font-semibold text-muted uppercase tracking-wider flex items-center gap-2">
        <DollarSign size={13} /> Dividend income {forecast.year}
      </h2>
      <div className="grid grid-cols-2 gap-4">
        <MetricCard icon={DollarSign} label="Paid YTD" value={fmtMoney(forecast.total_paid)} />
        <MetricCard icon={TrendingUp} label="Estimated remaining" value={fmtMoney(forecast.total_estimated)} />
      </div>
      <div className="rounded-xl border border-surface-border bg-surface-card p-4">
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={forecast.months} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} vertical={false} />
            <XAxis dataKey="month" tick={AXIS_TICK} />
            <YAxis tick={AXIS_TICK} tickFormatter={tickFormatter} width={56} />
            <Tooltip content={<ForecastTooltip />} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
            <Legend
              formatter={(v) => (
                <span className="text-xs text-muted">
                  {v === "paid" ? "Paid" : "Estimated"}
                </span>
              )}
            />
            <Bar dataKey="paid" stackId="div" fill={GAIN_COLOR} radius={[0, 0, 0, 0]} />
            <Bar dataKey="estimated" stackId="div" fill={CATEGORICAL[3]} radius={[4, 4, 0, 0]} />
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
    <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-xs shadow-lg max-w-[320px]">
      <p className="text-muted mb-1.5">{label}</p>

      {entries.length > 0 ? (
        <div className="space-y-1 mb-2">
          {entries.map((e) => (
            <div key={`${e.ticker}-${e.status}`} className="flex justify-between gap-4 items-center">
              <span className="flex items-center gap-2 min-w-0">
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
                    e.status === "paid" ? "bg-gain" : "bg-brand"
                  }`}
                />
                <span className="font-mono text-ink shrink-0">{e.ticker}</span>
                <span className="text-muted truncate">{e.name}</span>
              </span>
              <span
                className={`font-medium tabular-nums shrink-0 ${
                  e.status === "paid" ? "text-gain" : "text-brand"
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
        <p className="text-muted mb-2">No dividends</p>
      )}

      <div className="space-y-1 pt-1.5 border-t border-surface-border">
        {paid > 0 && (
          <div className="flex justify-between gap-6">
            <span className="text-muted">Paid</span>
            <span className="font-medium text-gain">{fmtMoney(paid)}</span>
          </div>
        )}
        {est > 0 && (
          <div className="flex justify-between gap-6">
            <span className="text-muted">Estimated</span>
            <span className="font-medium text-brand">{fmtMoney(est)}</span>
          </div>
        )}
        <div className="flex justify-between gap-6">
          <span className="text-muted">Total</span>
          <span className="font-medium text-ink">{fmtMoney(paid + est)}</span>
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
            <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
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
            <td className="px-4 py-3 font-mono font-semibold text-ink">{row.ticker}</td>
            <td className="px-4 py-3 text-muted max-w-[180px] truncate">{row.name}</td>
            <td className="px-4 py-3 text-muted tabular-nums">{row.shares.toLocaleString()}</td>
            <td className="px-4 py-3 text-muted tabular-nums">{fmt(row.ex_date)}</td>
            <td className="px-4 py-3 text-muted tabular-nums">{fmt(row.pay_date)}</td>
            <td className="px-4 py-3 text-muted tabular-nums">
              {row.dividend_rate != null ? (
                <span className="flex items-center gap-1">
                  <DollarSign size={11} className="text-brand" />
                  {row.dividend_rate.toFixed(2)} {row.currency}
                </span>
              ) : <span className="text-muted">—</span>}
            </td>
            <td className="px-4 py-3 text-ink tabular-nums font-medium">
              {row.annual_income != null
                ? `${row.annual_income.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${row.currency}`
                : <span className="text-muted">—</span>}
            </td>
            <td className="px-4 py-3 tabular-nums">
              {row.dividend_yield != null ? (
                <span className="flex items-center gap-1 text-brand">
                  <TrendingUp size={11} />
                  {row.dividend_yield.toFixed(2)}%
                </span>
              ) : <span className="text-muted">—</span>}
            </td>
            <td className="px-4 py-3">{statusBadge(row.ex_date)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function fmtPct(v) {
  if (v == null) return <span className="text-muted">—</span>;
  const cls = v > 0 ? "text-gain" : v < 0 ? "text-loss" : "text-muted";
  return <span className={`tabular-nums ${cls}`}>{v > 0 ? "+" : ""}{v.toFixed(1)}%</span>;
}

function GrowthSection({ rows, loading }) {
  const { openStock } = useStockDetail();
  if (loading) {
    return (
      <div className="rounded-xl border border-surface-border bg-surface-card p-4 text-sm text-muted">
        Loading dividend growth…
      </div>
    );
  }
  if (!rows?.length) return null;

  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold text-muted uppercase tracking-wider flex items-center gap-2">
        <TrendingUp size={13} /> Dividend growth
      </h2>
      <div className="rounded-xl border border-surface-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-border bg-surface-card">
              {["Ticker", "Company", "Streak", "CAGR", "YoY", "Payout"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.ticker}
                onClick={() => openStock(r.ticker)}
                className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
              >
                <td className="px-4 py-3 font-mono font-semibold text-ink">{r.ticker}</td>
                <td className="px-4 py-3 text-muted max-w-[180px] truncate">{r.name}</td>
                <td className="px-4 py-3 text-ink tabular-nums">
                  {r.streak_years > 0 ? `${r.streak_years} yrs` : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">
                  {r.cagr_pct != null ? (
                    <span className="flex items-baseline gap-1">
                      {fmtPct(r.cagr_pct)}
                      <span className="text-[10px] text-muted">{r.cagr_years_used}yr</span>
                    </span>
                  ) : <span className="text-muted">—</span>}
                </td>
                <td className="px-4 py-3">{fmtPct(r.yoy_pct)}</td>
                <td className="px-4 py-3 tabular-nums text-muted">
                  {r.payout_ratio_pct != null ? `${r.payout_ratio_pct.toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
