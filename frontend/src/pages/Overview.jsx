import { useQuery } from "@tanstack/react-query";
import { fetchOverview } from "../api";
import { useCurrency } from "../App";
import { formatMoney } from "../lib/format";
import BreakdownChart from "../components/BreakdownChart";
import { Layers, TrendingUp, TrendingDown } from "lucide-react";

export default function Overview() {
  const currencyCtx = useCurrency?.();
  const currency = currencyCtx?.currency || "USD";

  const { data, isLoading } = useQuery({
    queryKey: ["overview", currency],
    queryFn: () => fetchOverview(currency),
    staleTime: 5 * 60 * 1000,
  });

  const dc = data?.total_day_change ?? 0;
  const dcPct = data?.total_day_change_percent;
  const up = dc >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Layers size={18} className="text-brand" />
        <h1 className="text-xl font-semibold">Overview</h1>
        {data?.portfolio_count != null && (
          <span className="text-sm text-muted">· {data.portfolio_count} portfolios</span>
        )}
      </div>

      <div className="card">
        <p className="text-xs font-semibold text-muted uppercase tracking-wider">Total net worth</p>
        {isLoading ? (
          <p className="text-3xl font-semibold text-ink mt-2">…</p>
        ) : (
          <>
            <p className="text-3xl font-semibold text-ink mt-2 tabular-nums">
              {formatMoney(data?.total_net_worth ?? 0, currency)}
            </p>
            <p className={`text-sm mt-1 flex items-center gap-1 tabular-nums ${up ? "text-gain" : "text-loss"}`}>
              {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
              {up ? "+" : ""}{formatMoney(dc, currency)}
              {dcPct != null && <span>({up ? "+" : ""}{dcPct.toFixed(2)}%) today</span>}
            </p>
          </>
        )}
      </div>

      {!isLoading && data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <BreakdownChart title="Sectors" data={data.sectors} currencyLabel={currency} />
          <BreakdownChart title="Countries" data={data.countries} currencyLabel={currency} />
          <BreakdownChart title="Asset types" data={data.asset_types} currencyLabel={currency} />
        </div>
      )}
    </div>
  );
}
