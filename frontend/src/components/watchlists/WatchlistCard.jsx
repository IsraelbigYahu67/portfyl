import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Loader2, Search, Trash2, TrendingDown, TrendingUp, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import {
  addWatchlistItem,
  deleteWatchlist,
  removeWatchlistItem,
  searchTickers,
} from "../../api";
import { getApiErrorMessage } from "../../lib/apiError";
import Select from "../ui/Select";
import { formatCompact, formatMoney, formatPercent } from "../../lib/format";
import { useConfirm } from "../ui/ConfirmDialog";
import { useToast } from "../ui/Toast";
import { TickerLink } from "../TickerLink";
import { useT } from "../../i18n/I18nProvider";

function compareNullable(left, right, direction) {
  const leftMissing = left == null || Number.isNaN(Number(left));
  const rightMissing = right == null || Number.isNaN(Number(right));
  if (leftMissing && rightMissing) return 0;
  if (leftMissing) return 1;
  if (rightMissing) return -1;
  return (Number(left) - Number(right)) * direction;
}

export function sortWatchlistItems(items, sort) {
  return [...items].sort((left, right) => {
    let result = 0;
    if (sort === "change_desc") result = compareNullable(left.quote?.change_percent, right.quote?.change_percent, -1);
    else if (sort === "change_asc") result = compareNullable(left.quote?.change_percent, right.quote?.change_percent, 1);
    else if (sort === "market_cap_desc") result = compareNullable(left.quote?.market_cap, right.quote?.market_cap, -1);
    else result = left.ticker.localeCompare(right.ticker);
    return result || left.ticker.localeCompare(right.ticker);
  });
}

function AddTickerForm({ watchlistId, watchlistName }) {
  const t = useT();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const search = useQuery({
    queryKey: ["search", query],
    queryFn: () => searchTickers(query, 8),
    enabled: query.trim().length > 0,
    staleTime: 60_000,
    retry: false,
  });
  const add = useMutation({
    mutationFn: (ticker) => addWatchlistItem(watchlistId, ticker),
    onSuccess: (_data, ticker) => {
      toast.success(t("{ticker} added to {list}", { ticker, list: watchlistName }));
      setQuery("");
    },
    onError: (error) => toast.error(getApiErrorMessage(error, t("Could not add ticker"), t)),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  const results = search.data?.results || [];
  return (
    <div className="relative">
      <label className="sr-only" htmlFor={`add-ticker-${watchlistId}`}>{t("Add ticker to {list}", { list: watchlistName })}</label>
      <input
        id={`add-ticker-${watchlistId}`}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className="w-44 rounded-md border border-surface-border bg-surface px-3 py-1.5 text-xs"
        placeholder={t("Add ticker…")}
      />
      {(search.isFetching || add.isPending) && <Loader2 size={12} className="absolute right-2 top-2 animate-spin" />}
      {results.length > 0 && (
        <ul className="absolute right-0 z-20 mt-1 w-72 rounded-lg border border-surface-border bg-surface-card shadow-xl">
          {results.map((result) => (
            <li key={`${result.symbol}-${result.exchange || ""}`}>
              <button type="button" onClick={() => add.mutate(result.symbol)} className="flex w-full gap-2 px-3 py-2 text-left hover:bg-surface-hover">
                <span className="font-mono font-bold">{result.symbol}</span><span className="truncate text-xs text-muted">{result.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function WatchlistCard({ wl, onAlert, alertsByTicker = new Map(), alertDisabledReason = "" }) {
  const t = useT();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const searchKey = `wl.${wl.id}.q`;
  const sortKey = `wl.${wl.id}.sort`;
  const search = searchParams.get(searchKey) || "";
  const requestedSort = searchParams.get(sortKey);
  const sort = ["change_desc", "change_asc", "market_cap_desc"].includes(requestedSort) ? requestedSort : "ticker";
  const updateView = (key, value, defaultValue) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (value === defaultValue) next.delete(key);
      else next.set(key, value);
      return next;
    }, { replace: true });
  };
  const setSearch = (value) => updateView(searchKey, value, "");
  const setSort = (value) => updateView(sortKey, value, "ticker");

  const visibleItems = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const filtered = needle
      ? wl.items.filter((item) => item.ticker.toLowerCase().includes(needle) || (item.quote?.name || "").toLowerCase().includes(needle))
      : wl.items;
    return sortWatchlistItems(filtered, sort);
  }, [search, sort, wl.items]);

  const removeList = useMutation({
    mutationFn: () => deleteWatchlist(wl.id),
    onSuccess: () => toast.success(t("{name} deleted", { name: wl.name })),
    onError: (error) => toast.error(getApiErrorMessage(error, t("Could not delete watchlist"), t)),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });
  const removeItem = useMutation({
    mutationFn: (item) => removeWatchlistItem(wl.id, item.id),
    onMutate: async (item) => {
      await queryClient.cancelQueries({ queryKey: ["watchlists"] });
      const previous = queryClient.getQueryData(["watchlists"]);
      queryClient.setQueryData(["watchlists"], (lists = []) => lists.map((list) => (
        list.id === wl.id
          ? { ...list, items: list.items.filter((current) => current.id !== item.id), count: Math.max(0, list.count - 1) }
          : list
      )));
      return { previous };
    },
    onSuccess: (_data, item) => toast.success(t("{ticker} removed from {list}", { ticker: item.ticker, list: wl.name })),
    onError: (error, _item, context) => {
      if (context?.previous) queryClient.setQueryData(["watchlists"], context.previous);
      toast.error(getApiErrorMessage(error, t("Could not remove ticker from {list}", { list: wl.name }), t));
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });

  const askDeleteList = async () => {
    if (await confirm({ title: t("Delete {name}?", { name: wl.name }), message: t("The list and its tracked symbols will be removed."), confirmLabel: t("Delete watchlist"), danger: true })) removeList.mutate();
  };
  const askRemoveItem = async (item) => {
    if (await confirm({ title: t("Remove {ticker}?", { ticker: item.ticker }), message: t("Remove {ticker} from {list}?", { ticker: item.ticker, list: wl.name }), confirmLabel: t("Remove ticker"), danger: true })) removeItem.mutate(item);
  };

  return (
    <section className="rounded-xl border border-surface-border bg-surface-card" aria-labelledby={`watchlist-${wl.id}-heading`}>
      <header className="flex flex-wrap items-center gap-3 border-b border-surface-border px-4 py-3">
        <div className="mr-auto"><h2 id={`watchlist-${wl.id}-heading`} className="text-lg font-bold">{wl.name}</h2><p className="text-xs text-muted">{wl.count === 1 ? t("{count} stock", { count: 1 }) : t("{count} stocks", { count: wl.count })}</p></div>
        <AddTickerForm watchlistId={wl.id} watchlistName={wl.name} />
        <button type="button" onClick={askDeleteList} aria-label={t("Delete {name}", { name: wl.name })} className="text-muted hover:text-red-600"><Trash2 size={15} /></button>
      </header>
      <div className="flex flex-wrap gap-2 border-b border-surface-border px-4 py-3">
        <label className="relative flex-1 min-w-48"><span className="sr-only">{t("Search {list}", { list: wl.name })}</span><Search size={14} className="absolute left-2.5 top-2.5 text-muted" /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("Search {list}", { list: wl.name })} className="w-full rounded-md border border-surface-border bg-surface py-2 pl-8 pr-3 text-sm" /></label>
        <label><span className="sr-only">{t("Sort {list}", { list: wl.name })}</span><Select aria-label={t("Sort {list}", { list: wl.name })} value={sort} onChange={setSort} className="text-sm" options={[{ value: "ticker", label: t("Ticker A–Z") }, { value: "change_desc", label: t("Daily change: high to low") }, { value: "change_asc", label: t("Daily change: low to high") }, { value: "market_cap_desc", label: t("Market cap: high to low") }]} /></label>
      </div>
      {alertDisabledReason && <p className="border-b border-surface-border px-4 py-2 text-xs text-muted">{t("Price alerts unavailable: {reason}.", { reason: alertDisabledReason })} <Link className="text-brand hover:underline" to="/settings?section=notifications">{t("Notification settings")}</Link></p>}
      {!visibleItems.length ? <p className="px-4 py-8 text-center text-sm text-muted">{t("No tracked symbols match this view.")}</p> : (
        <ul className="divide-y divide-surface-border">
          {visibleItems.map((item) => {
            const quote = item.quote || {};
            const change = quote.change_percent;
            const up = change != null && change >= 0;
            const alert = alertsByTicker.get(item.ticker);
            return (
              <li key={item.id} className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover">
                <TickerLink aria-label={`${item.ticker} ${quote.name || item.ticker}`} ticker={item.ticker} className="flex min-w-0 flex-1 items-center gap-3">
                  <span className="w-16 shrink-0 font-mono font-bold">{item.ticker}</span>
                  <span className="min-w-0 flex-1 truncate text-sm">{quote.name || item.ticker}</span>
                  <span className="hidden w-24 text-right text-sm tabular-nums sm:block">{formatMoney(quote.price, quote.currency || "USD")}</span>
                  <span className={`flex w-24 items-center justify-end gap-1 text-xs tabular-nums ${change == null ? "text-muted" : up ? "text-gain" : "text-loss"}`}>{change != null && (up ? <TrendingUp size={11} /> : <TrendingDown size={11} />)}{formatPercent(change)}</span>
                  <span className="hidden w-24 text-right text-xs text-muted tabular-nums lg:block">{formatCompact(quote.market_cap, quote.currency || "USD")}</span>
                </TickerLink>
                {alert && <span className="text-xs font-medium text-muted">{alert.status === "triggered" ? t("Triggered") : t("Active")}</span>}
                <button type="button" disabled={Boolean(alertDisabledReason)} onClick={() => onAlert?.(item.ticker)} aria-label={t("Create price alert for {ticker}", { ticker: item.ticker })} title={alertDisabledReason || t("Create price alert")} className="p-1 text-muted hover:text-brand disabled:cursor-not-allowed disabled:opacity-40"><Bell size={14} /></button>
                <button type="button" onClick={() => askRemoveItem(item)} aria-label={t("Remove {ticker} from {list}", { ticker: item.ticker, list: wl.name })} className="p-1 text-muted hover:text-red-600"><X size={14} /></button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
