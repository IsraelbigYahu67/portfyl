import { Link, useParams } from "react-router-dom";
import StockValuationPanel from "../../components/showcase/StockValuationPanel";
import { SHOWCASE_PE_HISTORY } from "../../components/showcase/showcaseData";
import KpiBox from "../../components/ui/KpiBox";
import { formatMoney, formatPercent, formatShortDate } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

const LABELS = {
  pe: "P/E",
  fivePe: "5-year average P/E",
  forwardPe: "Forward P/E",
  vsAverage: "P/E vs 5-year average",
  historyTitle: "P/E valuation history",
  tableCaption: "P/E history by quarter",
  disclaimer: "Synthetic demo data — not a live quote or investment recommendation.",
};

function normalizeSymbol(value) {
  try {
    return decodeURIComponent(value || "").trim().toUpperCase();
  } catch {
    return "";
  }
}

export default function DemoStock() {
  const { ticker } = useParams();
  const data = useDemoData();
  const symbol = normalizeSymbol(ticker);
  const holding = data.holdings.find((candidate) => candidate.symbol === symbol);

  if (!holding) {
    return <div className="text-center py-16"><h1 className="text-2xl font-display font-bold">Demo stock not found</h1><p className="financial-meta text-muted mt-2">This synthetic demo only includes approved fixture assets.</p><div className="mt-5 flex justify-center gap-3"><Link className="btn-primary" to="/demo">Back to demo</Link><Link className="btn-secondary" to="/demo/allocation">View allocation</Link></div></div>;
  }

  const f = holding.fundamentals;
  // P/E and Forward P/E are in the valuation panel above, so they are not repeated here.
  const metrics = [
    ["Market cap", f.marketCap == null ? "—" : `$${(f.marketCap / 1e9).toFixed(1)}B`],
    ["EPS", f.eps == null ? "—" : `$${f.eps.toFixed(2)}`], ["Revenue growth", formatPercent(f.revenueGrowth, { sign: false })], ["Profit margin", formatPercent(f.profitMargin, { sign: false })],
    ["Dividend yield", formatPercent(f.dividendYield, { sign: false })], ["52-week range", `$${f.week52Low.toFixed(2)} – $${f.week52High.toFixed(2)}`],
    ["Next earnings", f.nextEarnings ? formatShortDate(f.nextEarnings) : "Not applicable"], ["Portfolio value", formatMoney(holding.marketValue, "USD")], ["Portfolio weight", formatPercent(holding.weight, { sign: false })],
  ];

  return <div className="space-y-6"><StockValuationPanel holding={holding} peHistory={SHOWCASE_PE_HISTORY[holding.symbol] ?? []} currency="USD" labels={LABELS} /><section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{metrics.map(([label, value]) => <KpiBox key={label} label={label} value={String(value)} />)}</section><section className="card p-5"><h2 className="data-label">About {holding.name}</h2><p className="financial-data text-muted leading-relaxed mt-3">{f.description}</p></section><section className="card p-5"><h2 className="data-label">Holding context</h2><div className="mt-3 flex flex-wrap gap-5 financial-data"><span>Value {formatMoney(holding.marketValue, "USD")}</span><span>Weight {formatPercent(holding.weight, { sign: false })}</span><span className={holding.dayChangePercent >= 0 ? "text-gain" : "text-loss"}>Day change {formatPercent(holding.dayChangePercent)}</span></div><Link to="/demo/allocation" className="inline-block mt-4 text-sm text-brand hover:underline">Back to allocation</Link></section></div>;
}
