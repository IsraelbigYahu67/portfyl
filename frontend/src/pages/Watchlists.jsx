import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Trash2, X, TrendingUp, TrendingDown, Search as SearchIcon, Loader2,
  Bell, BellRing, RotateCcw, RefreshCw,
} from "lucide-react";
import {
  fetchWatchlists,
  createWatchlist,
  deleteWatchlist,
  addWatchlistItem,
  removeWatchlistItem,
  searchTickers,
  fetchAlerts,
  createAlert,
  updateAlert,
  deleteAlert,
  checkAlerts,
} from "../api";

function fmtPrice(v, code = "USD") {
  if (v == null) return "—";
  const sym = code === "EUR" ? "€" : code === "GBP" ? "£" : code === "CZK" ? " Kč" : "$";
  return `${sym}${v.toFixed(2)}`;
}

function fmtPct(v) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function fmtCompact(v) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${s}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${s}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${s}$${(abs / 1e6).toFixed(2)}M`;
  return `${s}$${abs.toFixed(0)}`;
}

function AddTickerForm({ watchlistId }) {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);

  const { data: searchData, isFetching } = useQuery({
    queryKey: ["search", query],
    queryFn: () => searchTickers(query, 8),
    enabled: query.trim().length >= 1,
    staleTime: 60_000,
    retry: false,
  });
  const results = searchData?.results || [];

  const addMut = useMutation({
    mutationFn: (ticker) => addWatchlistItem(watchlistId, ticker),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlists"] });
      setQuery("");
      setOpen(false);
    },
  });

  return (
    <div className="relative">
      <div className="relative">
        <SearchIcon
          size={14}
          className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none"
        />
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Add ticker…"
          className="w-48 bg-surface border border-surface-border rounded-md pl-7 pr-2 py-1.5 text-xs focus:outline-none focus:border-brand"
          onKeyDown={(e) => {
            if (e.key === "Enter" && results[0]) {
              addMut.mutate(results[0].symbol);
            } else if (e.key === "Enter" && query.trim()) {
              addMut.mutate(query.trim().toUpperCase());
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        />
        {(isFetching || addMut.isPending) && query && (
          <Loader2
            size={12}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 animate-spin"
          />
        )}
      </div>
      {open && query.trim().length >= 1 && results.length > 0 && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <ul className="absolute right-0 mt-1 w-72 z-50 bg-surface-card border border-surface-border rounded-md shadow-xl overflow-hidden max-h-72 overflow-y-auto">
            {results.map((r) => (
              <li key={`${r.symbol}-${r.exchange ?? ""}`}>
                <button
                  type="button"
                  onClick={() => addMut.mutate(r.symbol)}
                  className="w-full text-left px-3 py-2 hover:bg-surface-hover flex items-center gap-2"
                >
                  <span className="font-mono font-bold text-xs w-14 truncate">
                    {r.symbol}
                  </span>
                  <span className="text-xs text-slate-700 truncate flex-1">{r.name}</span>
                  {r.exchange && (
                    <span className="text-[10px] text-slate-500 ml-1">{r.exchange}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      {addMut.isError && (
        <div className="absolute right-0 mt-1 text-[10px] text-red-600">
          {addMut.error?.response?.data?.detail || "Add failed"}
        </div>
      )}
    </div>
  );
}

function WatchlistCard({ wl, onAlert }) {
  const qc = useQueryClient();

  const removeWlMut = useMutation({
    mutationFn: () => deleteWatchlist(wl.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  const removeItemMut = useMutation({
    mutationFn: (itemId) => removeWatchlistItem(wl.id, itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlists"] }),
  });

  return (
    <section className="bg-surface-card border border-surface-border rounded-xl">
      <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-surface-border">
        <div className="flex items-baseline gap-3">
          <h2 className="text-lg font-bold">{wl.name}</h2>
          <span className="text-xs text-slate-500">{wl.count} {wl.count === 1 ? "stock" : "stocks"}</span>
        </div>
        <div className="flex items-center gap-3">
          <AddTickerForm watchlistId={wl.id} />
          <button
            type="button"
            onClick={() => {
              if (confirm(`Delete watchlist "${wl.name}"?`)) removeWlMut.mutate();
            }}
            className="text-slate-500 hover:text-red-600 transition-colors"
            title="Delete watchlist"
            aria-label="Delete watchlist"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </header>

      {wl.items.length === 0 ? (
        <div className="py-8 text-center text-slate-400 text-sm">
          No tickers yet. Use the search box above to add one.
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {wl.items.map((it) => {
            const q = it.quote || {};
            const up = q.change_percent != null && q.change_percent >= 0;
            const cur = q.currency || "USD";
            return (
              <li
                key={it.id}
                className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover transition-colors"
              >
                <Link
                  to={`/stock/${encodeURIComponent(it.ticker)}`}
                  className="flex items-center gap-3 flex-1 min-w-0"
                >
                  <div className="w-20 font-mono font-bold text-sm shrink-0">{it.ticker}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">{q.name || it.ticker}</div>
                    <div className="text-[11px] text-slate-500 truncate">
                      {[q.exchange, q.sector].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                  <div className="w-24 text-right tabular-nums text-sm">
                    {fmtPrice(q.price, cur)}
                  </div>
                  <div
                    className={`w-24 text-right tabular-nums text-xs font-medium flex items-center justify-end gap-1 ${
                      q.change_percent == null
                        ? "text-slate-500"
                        : up
                          ? "text-emerald-600"
                          : "text-red-600"
                    }`}
                  >
                    {q.change_percent != null && (up ? <TrendingUp size={11} /> : <TrendingDown size={11} />)}
                    {fmtPct(q.change_percent)}
                  </div>
                  <div className="w-24 text-right tabular-nums text-xs text-slate-500 hidden md:block">
                    {fmtCompact(q.market_cap)}
                  </div>
                </Link>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onAlert?.(it.ticker);
                  }}
                  className="text-slate-400 hover:text-brand p-1 transition-colors"
                  title="Create a price alert for this ticker"
                  aria-label="Create price alert"
                >
                  <Bell size={14} />
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeItemMut.mutate(it.id);
                  }}
                  className="text-slate-400 hover:text-red-600 p-1 transition-colors"
                  title="Remove from watchlist"
                  aria-label="Remove from watchlist"
                >
                  <X size={14} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function PriceAlertsPanel({ prefillTicker, onConsumePrefill }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ ticker: "", direction: "above", target_price: "" });

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: fetchAlerts,
    staleTime: 15_000,
  });

  // A bell click on a watchlist row pre-fills the ticker and focuses the form.
  useEffect(() => {
    if (prefillTicker) {
      setForm((f) => ({ ...f, ticker: prefillTicker }));
      onConsumePrefill?.();
    }
  }, [prefillTicker]); // eslint-disable-line react-hooks/exhaustive-deps

  const invalidate = () => qc.invalidateQueries({ queryKey: ["alerts"] });

  const add = useMutation({
    mutationFn: createAlert,
    onSuccess: () => {
      invalidate();
      setForm((f) => ({ ...f, target_price: "" }));
    },
  });
  const reset = useMutation({
    mutationFn: (id) => updateAlert(id, { status: "active" }),
    onSuccess: invalidate,
  });
  const toggle = useMutation({
    mutationFn: ({ id, enabled }) => updateAlert(id, { enabled }),
    onSuccess: invalidate,
  });
  const remove = useMutation({ mutationFn: deleteAlert, onSuccess: invalidate });
  const check = useMutation({ mutationFn: checkAlerts, onSuccess: invalidate });

  const submit = (e) => {
    e.preventDefault();
    const t = form.ticker.trim().toUpperCase();
    const price = Number(form.target_price);
    if (!t || !price) return;
    add.mutate({ ticker: t, direction: form.direction, target_price: price });
  };

  return (
    <section className="bg-surface-card border border-surface-border rounded-xl mb-6">
      <header className="flex items-center justify-between gap-3 px-4 py-3 border-b border-surface-border">
        <div className="flex items-center gap-2">
          <Bell size={16} className="text-brand" />
          <h2 className="text-lg font-bold">Price Alerts</h2>
          <span className="text-xs text-slate-500">Discord notification when a price is crossed</span>
        </div>
        <button
          type="button"
          onClick={() => check.mutate()}
          disabled={check.isPending || alerts.length === 0}
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-brand disabled:opacity-40"
          title="Evaluate all alerts against live prices right now"
        >
          <RefreshCw size={13} className={check.isPending ? "animate-spin" : ""} />
          Check now
        </button>
      </header>

      <form onSubmit={submit} className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-surface-border">
        <input
          type="text"
          value={form.ticker}
          onChange={(e) => setForm({ ...form, ticker: e.target.value.toUpperCase() })}
          placeholder="Ticker"
          className="w-28 bg-surface border border-surface-border rounded-md px-2 py-1.5 text-sm font-mono focus:outline-none focus:border-brand"
        />
        <select
          value={form.direction}
          onChange={(e) => setForm({ ...form, direction: e.target.value })}
          className="bg-surface border border-surface-border rounded-md px-2 py-1.5 text-sm focus:outline-none focus:border-brand"
        >
          <option value="above">rises to / above</option>
          <option value="below">falls to / below</option>
        </select>
        <input
          type="number"
          step="0.01"
          value={form.target_price}
          onChange={(e) => setForm({ ...form, target_price: e.target.value })}
          placeholder="Target price"
          className="w-32 bg-surface border border-surface-border rounded-md px-2 py-1.5 text-sm tabular-nums focus:outline-none focus:border-brand"
        />
        <button
          type="submit"
          disabled={add.isPending || !form.ticker.trim() || !form.target_price}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-brand text-black text-sm font-medium disabled:opacity-50"
        >
          <Plus size={14} />
          Add alert
        </button>
        {add.isError && (
          <span className="text-xs text-red-600">
            {add.error?.response?.data?.detail || "Failed to add alert"}
          </span>
        )}
      </form>

      {isLoading ? (
        <div className="py-6 text-center text-slate-400 text-sm animate-pulse">Loading alerts…</div>
      ) : alerts.length === 0 ? (
        <div className="py-6 text-center text-slate-400 text-sm">
          No alerts yet. Add one above — you'll get a Discord message when it's crossed.
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {alerts.map((a) => {
            const triggered = a.status === "triggered";
            return (
              <li key={a.id} className="flex items-center gap-3 px-4 py-2.5">
                <div className="w-20 font-mono font-bold text-sm shrink-0">{a.ticker}</div>
                <div className="flex-1 text-sm text-slate-600">
                  {a.direction === "above" ? "≥" : "≤"}{" "}
                  <span className="tabular-nums font-medium">{a.target_price}</span>
                  {a.current_price != null && (
                    <span className="text-xs text-slate-400 ml-2 tabular-nums">
                      now {a.current_price.toFixed(2)}
                    </span>
                  )}
                  {a.note && <span className="text-xs text-slate-400 ml-2 italic">{a.note}</span>}
                </div>
                {triggered ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                    <BellRing size={11} /> Triggered
                  </span>
                ) : (
                  <label className="inline-flex items-center gap-1 text-xs text-slate-500">
                    <input
                      type="checkbox"
                      checked={a.enabled}
                      onChange={(e) => toggle.mutate({ id: a.id, enabled: e.target.checked })}
                    />
                    Armed
                  </label>
                )}
                {triggered && (
                  <button
                    type="button"
                    onClick={() => reset.mutate(a.id)}
                    className="text-slate-400 hover:text-brand p-1 transition-colors"
                    title="Re-arm this alert"
                    aria-label="Re-arm alert"
                  >
                    <RotateCcw size={14} />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => remove.mutate(a.id)}
                  className="text-slate-400 hover:text-red-600 p-1 transition-colors"
                  title="Delete alert"
                  aria-label="Delete alert"
                >
                  <Trash2 size={14} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function NewWatchlistForm() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const createMut = useMutation({
    mutationFn: () => createWatchlist({ name: name.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlists"] });
      setName("");
    },
  });

  return (
    <form
      className="flex items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim()) createMut.mutate();
      }}
    >
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="New watchlist name"
        className="bg-surface-card border border-surface-border rounded-md px-3 py-1.5 text-sm focus:outline-none focus:border-brand"
      />
      <button
        type="submit"
        disabled={!name.trim() || createMut.isPending}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-brand text-black text-sm font-medium disabled:opacity-50"
      >
        <Plus size={14} />
        Create
      </button>
      {createMut.isError && (
        <span className="text-xs text-red-600">
          {createMut.error?.response?.data?.detail || "Failed"}
        </span>
      )}
    </form>
  );
}

export default function Watchlists() {
  const [prefillTicker, setPrefillTicker] = useState("");
  const { data: watchlists = [], isLoading, isError } = useQuery({
    queryKey: ["watchlists"],
    queryFn: fetchWatchlists,
    staleTime: 30_000,
  });

  return (
    <div className="max-w-6xl mx-auto py-6">
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold">Watchlists</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Track stocks you don't (yet) own. Click any ticker to open its overview.
          </p>
        </div>
        <NewWatchlistForm />
      </div>

      <PriceAlertsPanel
        prefillTicker={prefillTicker}
        onConsumePrefill={() => setPrefillTicker("")}
      />

      {isLoading && (
        <div className="text-center py-16 text-slate-500 text-sm animate-pulse">
          Loading watchlists…
        </div>
      )}

      {isError && (
        <div className="text-center py-16 text-red-600 text-sm">
          Could not load watchlists.
        </div>
      )}

      {!isLoading && !isError && watchlists.length === 0 && (
        <div className="text-center py-16 text-slate-500 text-sm">
          No watchlists yet. Create one above to start tracking.
        </div>
      )}

      <div className="space-y-6">
        {watchlists.map((wl) => (
          <WatchlistCard key={wl.id} wl={wl} onAlert={setPrefillTicker} />
        ))}
      </div>
    </div>
  );
}
