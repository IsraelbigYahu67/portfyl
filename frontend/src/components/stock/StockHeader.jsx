import { Building2, Globe, TrendingDown, TrendingUp } from "lucide-react";

// This identity header is shared by the authenticated stock route and the
// anonymous demo. It is intentionally presentational, so public routes do
// not inherit StockDetail's query-owning sections or their API imports.
export function StockHeader({ data, trailing = null }) {
  const positive = data.change_percent == null || data.change_percent >= 0;
  const currency = data.currency === "EUR" ? "€" : data.currency === "GBP" ? "£" : "$";
  return (
    <div className="flex flex-col gap-4 px-4 py-4 border-b border-surface-border sm:flex-row sm:items-start sm:justify-between sm:px-6">
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-3 flex-wrap"><h1 className="text-3xl font-bold font-mono">{data.ticker}</h1><span className="text-muted text-lg truncate">{data.name}</span></div>
        <div className="flex items-center gap-2 mt-1 text-sm text-muted flex-wrap">
          {data.sector && <span className="flex items-center gap-1"><Building2 size={11} />{data.sector}</span>}
          {data.country && <span className="flex items-center gap-1">· <Globe size={11} />{data.country}</span>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3"><div className="text-left sm:text-right"><div className="text-3xl font-bold tabular-nums">{data.price == null ? "—" : `${currency}${data.price.toFixed(2)}`}</div>{data.change_percent != null && <div className={`text-base font-medium flex items-center gap-1 sm:justify-end ${positive ? "text-gain" : "text-loss"}`}>{positive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}{data.change != null && `${data.change >= 0 ? "+" : ""}${data.change.toFixed(2)} `}({data.change_percent >= 0 ? "+" : ""}{data.change_percent.toFixed(2)}%)</div>}</div>{trailing}</div>
    </div>
  );
}
