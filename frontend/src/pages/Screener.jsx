import { useState, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchScreener } from "../editions/localApi";
import { useStockDetail } from "../components/StockDetail";
import { Search, SlidersHorizontal, RefreshCw, TrendingUp, TrendingDown, Minus } from "lucide-react";

const UNIVERSE_OPTIONS = [
  { value: "sp500", label: "S&P 500 (full index)", slow: true },
  { value: "nasdaq100", label: "NASDAQ-100 (full index)", slow: true },
  { value: "dividend_aristocrats", label: "Dividend Aristocrats", slow: true },
  { value: "tech_large", label: "Tech Mega-Caps" },
  { value: "shibui_all", label: "Whole Market — Shibui (~10,000 stocks)" },
];

const SORT_OPTIONS = [
  { value: "market_cap", label: "Market Cap" },
  { value: "pe", label: "P/E" },
  { value: "forward_pe", label: "Fwd P/E" },
  { value: "pb", label: "P/B" },
  { value: "div_yield", label: "Div Yield" },
  { value: "roe", label: "ROE" },
  { value: "net_margin", label: "Net Margin" },
  { value: "operating_margin", label: "Operating Margin (Shibui)" },
  { value: "piotroski", label: "Piotroski F-Score (Shibui)" },
  { value: "target_mean", label: "Analyst Target" },
  { value: "beta", label: "Beta" },
  { value: "price", label: "Price" },
];

const SECTORS = [
  "", "Technology", "Healthcare", "Financial Services", "Consumer Cyclical",
  "Consumer Defensive", "Energy", "Industrials", "Basic Materials",
  "Real Estate", "Utilities", "Communication Services",
];

function fmtMoney(v) {
  if (v == null || isNaN(v)) return "—";
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

function fmtPct(v) {
  if (v == null || isNaN(v)) return "—";
  return `${Number(v).toFixed(2)}%`;
}

function fmtNum(v) {
  if (v == null || isNaN(v)) return "—";
  return Number(v).toFixed(2);
}

export default function Screener() {
  const { openStock } = useStockDetail();
  const [universe, setUniverse] = useState("sp500");
  const [customTickers, setCustomTickers] = useState("");
  const [sector, setSector] = useState("");
  const [maxPE, setMaxPE] = useState("");
  const [minDivYield, setMinDivYield] = useState("");
  const [minROE, setMinROE] = useState("");
  const [minOperatingMargin, setMinOperatingMargin] = useState("");
  const [minPiotroski, setMinPiotroski] = useState("");
  const [sortBy, setSortBy] = useState("market_cap");
  const [showFilters, setShowFilters] = useState(false);

  const isShibui = universe === "shibui_all";

  const buildParams = useCallback(() => {
    if (isShibui) {
      // Whole-market Shibui screen (PLAN.md 4a-i): ignores universe/tickers
      // entirely, scans ~10,344 NYSE/NASDAQ symbols in one query. Div yield
      // filtering isn't wired on that path yet -- only pe/ps/roe/market_cap/
      // operating_margin/piotroski/sector.
      const p = { source: "shibui", sort_by: sortBy, sort_desc: true, limit: 50 };
      if (sector) p.sector = sector;
      if (maxPE) p.max_pe = Number(maxPE);
      if (minROE) p.min_roe = Number(minROE);
      if (minOperatingMargin) p.min_operating_margin = Number(minOperatingMargin);
      if (minPiotroski) p.min_piotroski = Number(minPiotroski);
      return p;
    }
    const p = { universe, sort_by: sortBy, sort_desc: true, limit: 50 };
    if (customTickers.trim()) p.tickers = customTickers.trim().toUpperCase();
    if (sector) p.sector = sector;
    if (maxPE) p.max_pe = Number(maxPE);
    if (minDivYield) p.min_div_yield = Number(minDivYield);
    if (minROE) p.min_roe = Number(minROE);
    return p;
  }, [universe, customTickers, sector, maxPE, minDivYield, minROE, minOperatingMargin, minPiotroski, sortBy, isShibui]);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["screener", buildParams()],
    queryFn: () => fetchScreener(buildParams()),
    staleTime: 5 * 60 * 1000,
  });

  const results = data?.results ?? [];
  const shibuiMode = data?.source === "shibui";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Stock Screener</h1>
          <p className="text-sm text-muted mt-0.5">
            Filter stocks by valuation and fundamental criteria
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-colors ${
              showFilters
                ? "bg-brand text-white border-brand"
                : "bg-surface-card border-surface-border text-muted hover:text-ink"
            }`}
          >
            <SlidersHorizontal size={14} />
            Filters
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-card border border-surface-border text-sm text-muted hover:text-ink transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={isFetching ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <div className="rounded-xl border border-surface-border bg-surface-card p-4 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-muted mb-1 block">Universe</label>
              <select
                value={universe}
                onChange={(e) => setUniverse(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
              >
                {UNIVERSE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              {isShibui ? (
                <p className="text-[11px] text-muted mt-1">
                  Scans the whole market (~10,344 NYSE/NASDAQ symbols, Common Stock only) in one
                  query. Ignores Custom Tickers.
                </p>
              ) : (
                UNIVERSE_OPTIONS.find((o) => o.value === universe)?.slow && !customTickers.trim() && (
                  <p className="text-[11px] text-muted mt-1">
                    First scan fetches every constituent (~1 min); results are cached for an hour.
                  </p>
                )
              )}
            </div>
            {!isShibui && (
              <div>
                <label className="text-xs text-muted mb-1 block">Custom Tickers</label>
                <input
                  type="text"
                  placeholder="AAPL,MSFT,GOOGL"
                  value={customTickers}
                  onChange={(e) => setCustomTickers(e.target.value)}
                  className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
                />
              </div>
            )}
            <div>
              <label className="text-xs text-muted mb-1 block">Sector</label>
              <select
                value={sector}
                onChange={(e) => setSector(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
              >
                {SECTORS.map((s) => (
                  <option key={s} value={s}>{s || "All Sectors"}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-muted mb-1 block">Max P/E</label>
              <input
                type="number"
                placeholder="e.g. 25"
                value={maxPE}
                onChange={(e) => setMaxPE(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
              />
            </div>
            {!isShibui && (
              <div>
                <label className="text-xs text-muted mb-1 block">Min Div Yield (%)</label>
                <input
                  type="number"
                  placeholder="e.g. 2"
                  step="0.1"
                  value={minDivYield}
                  onChange={(e) => setMinDivYield(e.target.value)}
                  className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
                />
              </div>
            )}
            <div>
              <label className="text-xs text-muted mb-1 block">Min ROE (%)</label>
              <input
                type="number"
                placeholder="e.g. 15"
                value={minROE}
                onChange={(e) => setMinROE(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
              />
            </div>
            {isShibui && (
              <>
                <div>
                  <label className="text-xs text-muted mb-1 block">Min Operating Margin (%)</label>
                  <input
                    type="number"
                    placeholder="e.g. 20"
                    value={minOperatingMargin}
                    onChange={(e) => setMinOperatingMargin(e.target.value)}
                    className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-muted mb-1 block">Min Piotroski F-Score (0–9)</label>
                  <input
                    type="number"
                    placeholder="e.g. 7"
                    min="0"
                    max="9"
                    value={minPiotroski}
                    onChange={(e) => setMinPiotroski(e.target.value)}
                    className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
                  />
                </div>
              </>
            )}
            <div>
              <label className="text-xs text-muted mb-1 block">Sort By</label>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="w-full rounded-lg border border-surface-border bg-surface-card px-3 py-2 text-sm"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex justify-between items-center flex-wrap gap-2">
            <p className="text-xs text-muted">
              {data?.total ?? 0} results (showing up to 50)
              {shibuiMode && data?.capped_at_limit && " — more may match, refine filters to narrow down"}
              {shibuiMode && data?.default_market_cap_floor_applied && " · $500M market-cap floor applied by default"}
            </p>
            <button
              onClick={() => {
                setUniverse("sp500");
                setCustomTickers("");
                setSector("");
                setMaxPE("");
                setMinDivYield("");
                setMinROE("");
                setMinOperatingMargin("");
                setMinPiotroski("");
                setSortBy("market_cap");
              }}
              className="text-xs text-muted hover:text-ink"
            >
              Reset filters
            </button>
          </div>
        </div>
      )}

      {/* Results */}
      {isLoading ? (
        <div className="text-center py-20 text-muted">Loading screener data…</div>
      ) : !results.length ? (
        <div className="text-center py-20 text-muted">
          No stocks match your criteria. Try expanding the filters.
        </div>
      ) : (
        <div className="rounded-xl border border-surface-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm whitespace-nowrap">
              <thead>
                <tr className="border-b border-surface-border bg-surface-card">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Ticker</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Name</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Price</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Mkt Cap</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">P/E</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Fwd P/E</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">P/B</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">P/S</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Div Yield</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">ROE</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Net Margin</th>
                  {shibuiMode ? (
                    <>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Op. Margin</th>
                      <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider" title="Piotroski F-Score (0-9)">Piotroski</th>
                    </>
                  ) : (
                    <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Beta</th>
                  )}
                  <th className="text-right px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Target</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Sector</th>
                  {!shibuiMode && (
                    <th className="text-left px-4 py-3 text-xs font-semibold text-muted uppercase tracking-wider">Rating</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr
                    key={r.ticker}
                    onClick={() => openStock(r.ticker)}
                    className="border-b border-surface-border last:border-0 hover:bg-surface-hover transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 font-mono font-semibold text-ink">{r.ticker}</td>
                    <td className="px-4 py-3 text-muted max-w-[160px] truncate">{r.name}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-ink font-medium">{fmtMoney(r.price)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtMoney(r.market_cap)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtNum(r.pe)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtNum(r.forward_pe)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtNum(r.pb)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtNum(r.ps)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {r.div_yield != null ? (
                        <span className="text-gain font-medium">{fmtPct(r.div_yield)}</span>
                      ) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtPct(r.roe)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtPct(r.net_margin)}</td>
                    {shibuiMode ? (
                      <>
                        <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtPct(r.operating_margin)}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-muted">{r.piotroski_f_score ?? "—"}</td>
                      </>
                    ) : (
                      <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtNum(r.beta)}</td>
                    )}
                    <td className="px-4 py-3 text-right tabular-nums text-muted">{fmtMoney(r.target_mean)}</td>
                    <td className="px-4 py-3 text-muted max-w-[120px] truncate">{r.sector ?? "—"}</td>
                    {!shibuiMode && (
                      <td className="px-4 py-3">
                        {r.rating ? (
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            r.rating === "strong_buy" || r.rating === "buy"
                              ? "bg-gain/20 text-gain"
                              : r.rating === "hold"
                              ? "bg-amber-500/20 text-amber-600"
                              : "bg-loss/20 text-loss"
                          }`}>
                            {r.rating.replace("_", " ")}
                          </span>
                        ) : "—"}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
