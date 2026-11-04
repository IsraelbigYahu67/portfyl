import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Star, Plus, Check, Loader2 } from "lucide-react";
import {
  fetchStockView,
  fetchWatchlists,
  addWatchlistItem,
  removeWatchlistItem,
} from "../api";
import { AsyncSection, UrlTabs } from "../components/ui";
import { StockHeader } from "../components/stock/StockHeader";
import { StockOverviewTab } from "../components/stock/StockOverviewTab";
import { StockFinancialsTab } from "../components/stock/StockFinancialsTab";
import { StockValuationTab } from "../components/stock/StockValuationTab";
import { StockOwnershipTab } from "../components/stock/StockOwnershipTab";

const STOCK_TABS = [
  { value: "overview", label: "Overview", panelId: "stock-overview-panel" },
  { value: "financials", label: "Financials", panelId: "stock-financials-panel" },
  { value: "valuation", label: "Valuation", panelId: "stock-valuation-panel" },
  { value: "ownership", label: "Ownership", panelId: "stock-ownership-panel" },
];
const VALID_TABS = new Set(STOCK_TABS.map((tab) => tab.value));

function WatchlistMenu({ ticker }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: watchlists = [] } = useQuery({
    queryKey: ["watchlists"],
    queryFn: fetchWatchlists,
    staleTime: 30_000,
  });

  const addMut = useMutation({
    mutationFn: ({ id, t }) => addWatchlistItem(id, t),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  const removeMut = useMutation({
    mutationFn: ({ id, itemId }) => removeWatchlistItem(id, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });

  // Which watchlists already contain this ticker (so we can show a check).
  const inLists = watchlists.filter((w) =>
    (w.items || []).some((i) => i.ticker === ticker),
  );
  const isWatching = inLists.length > 0;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-colors ${
          isWatching
            ? "bg-yellow-500/10 text-yellow-300 border-yellow-500/30"
            : "bg-surface-hover text-muted border-surface-border hover:bg-surface-hover"
        }`}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Star
          size={14}
          className={isWatching ? "fill-yellow-300" : ""}
        />
        {isWatching ? `In ${inLists.length} watchlist${inLists.length > 1 ? "s" : ""}` : "Add to watchlist"}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-2 w-64 z-50 bg-surface-card border border-surface-border rounded-lg shadow-lg overflow-hidden">
            <div className="px-3 py-2 text-xs uppercase tracking-wider text-muted border-b border-surface-border">
              Watchlists
            </div>
            {watchlists.length === 0 ? (
              <div className="px-3 py-4 text-xs text-muted">
                No watchlists yet.{" "}
                <Link to="/watchlists" className="text-brand hover:underline">
                  Create one →
                </Link>
              </div>
            ) : (
              <ul className="max-h-72 overflow-y-auto">
                {watchlists.map((w) => {
                  const existing = (w.items || []).find((i) => i.ticker === ticker);
                  const checked = Boolean(existing);
                  const busy =
                    (addMut.isPending && addMut.variables?.id === w.id) ||
                    (removeMut.isPending && removeMut.variables?.id === w.id);
                  return (
                    <li key={w.id}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          if (checked) {
                            removeMut.mutate({ id: w.id, itemId: existing.id });
                          } else {
                            addMut.mutate({ id: w.id, t: ticker });
                          }
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-surface-hover transition-colors text-left disabled:opacity-50"
                      >
                        <div
                          className={`w-4 h-4 rounded border flex items-center justify-center ${
                            checked
                              ? "bg-brand border-brand"
                              : "border-surface-border"
                          }`}
                        >
                          {busy ? (
                            <Loader2 size={10} className="animate-spin" />
                          ) : checked ? (
                            <Check size={12} className="text-white" />
                          ) : null}
                        </div>
                        <span className="flex-1 truncate">{w.name}</span>
                        <span className="text-xs text-muted">{w.count}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="border-t border-surface-border">
              <Link
                to="/watchlists"
                className="flex items-center gap-2 px-3 py-2 text-xs text-brand hover:bg-surface-hover"
                onClick={() => setOpen(false)}
              >
                <Plus size={12} />
                Manage watchlists
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function Stock() {
  const { ticker: rawTicker } = useParams();
  const ticker = (rawTicker || "").toUpperCase();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const activeTab = VALID_TABS.has(requestedTab) ? requestedTab : "overview";
  // React Router stamps the initial entry with key="default". Anything else
  // means we navigated here from somewhere inside the SPA, so popping that
  // history entry is safe and lands the user back where they came from.
  const canGoBack = location.key !== "default";
  const goBack = () => (canGoBack ? navigate(-1) : navigate("/"));

  useEffect(() => {
    if (requestedTab === activeTab) return;
    const next = new URLSearchParams(searchParams);
    next.set("tab", activeTab);
    setSearchParams(next, { replace: true });
  }, [activeTab, requestedTab, searchParams, setSearchParams]);

  const selectTab = (tab) => {
    const next = new URLSearchParams(searchParams);
    next.set("tab", tab);
    setSearchParams(next);
  };

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["stock-view", ticker, "overview"],
    queryFn: () => fetchStockView(ticker, "overview"),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: Boolean(ticker),
  });

  return (
    <div className="max-w-7xl min-w-0 mx-auto py-2">
      <div className="flex items-center gap-3 mb-4">
        <button
          type="button"
          onClick={goBack}
          className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink transition-colors"
        >
          <ChevronLeft size={16} />
          Back
        </button>
      </div>

      <div className="bg-surface-card border border-surface-border rounded-xl shadow-lg">
        <AsyncSection
          isLoading={isLoading}
          error={error || (!isLoading && !data ? new Error(`Could not load fundamentals for ${ticker}.`) : null)}
          onRetry={() => refetch()}
          loading={(
            <div className="h-96 flex items-center justify-center text-muted text-sm animate-pulse">
              Loading fundamentals for {ticker}…
            </div>
          )}
        >
          {data ? (
            <>
              <StockHeader
                data={data}
                trailing={<WatchlistMenu ticker={data.ticker || ticker} />}
              />
              <div className="border-b border-surface-border px-4 py-2 sm:px-6">
                <UrlTabs
                  ariaLabel="Stock sections"
                  idPrefix="stock"
                  items={STOCK_TABS}
                  value={activeTab}
                  onChange={selectTab}
                />
              </div>
              <div
                id={`stock-${activeTab}-panel`}
                role="tabpanel"
                aria-labelledby={`stock-${activeTab}-tab`}
              >
                {activeTab === "overview" && <StockOverviewTab ticker={ticker} overviewData={data} />}
                {activeTab === "financials" && <StockFinancialsTab ticker={ticker} overviewData={data} />}
                {activeTab === "valuation" && <StockValuationTab ticker={ticker} overviewData={data} />}
                {activeTab === "ownership" && <StockOwnershipTab ticker={ticker} overviewData={data} />}
              </div>
            </>
          ) : null}
        </AsyncSection>
      </div>
    </div>
  );
}
