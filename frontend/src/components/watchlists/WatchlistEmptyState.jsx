import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { addWatchlistItem, createWatchlist, searchTickers } from "../../api";
import { getApiErrorMessage } from "../../lib/apiError";
import { useToast } from "../ui/Toast";
import { useT } from "../../i18n/I18nProvider";

export function WatchlistEmptyState() {
  const t = useT();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const search = useQuery({
    queryKey: ["search", query],
    queryFn: () => searchTickers(query, 8),
    enabled: query.trim().length > 0,
    staleTime: 60_000,
    retry: false,
  });

  const quickStart = useMutation({
    mutationFn: async (ticker) => {
      const watchlist = await createWatchlist({ name: t("My watchlist") });
      queryClient.setQueryData(["watchlists"], (current = []) => [...current, watchlist]);
      try {
        await addWatchlistItem(watchlist.id, ticker);
      } catch (cause) {
        const partial = new Error(t("The watchlist was created, but the ticker could not be added. Retry from My watchlist."));
        partial.cause = cause;
        throw partial;
      }
      return ticker;
    },
    onSuccess: (ticker) => {
      setError("");
      setQuery("");
      toast.success(t("{ticker} added to {list}", { ticker, list: t("My watchlist") }));
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
    onError: (mutationError) => {
      const message = mutationError.message || getApiErrorMessage(mutationError, t("Could not create watchlist"), t);
      setError(message);
      toast.error(message);
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });

  const results = search.data?.results || [];
  return (
    <section className="mx-auto max-w-xl rounded-xl border border-surface-border bg-surface-card p-6 text-center">
      <h2 className="text-xl font-bold">{t("Track a stock you are researching")}</h2>
      <p className="mt-2 text-sm text-muted">
        {t("A watchlist follows researched symbols without adding them to your portfolio.")}
      </p>
      <div className="relative mx-auto mt-5 max-w-sm text-left">
        <label htmlFor="watchlist-quick-start" className="mb-1.5 block text-sm font-medium">{t("Ticker to track")}</label>
        <Search size={15} className="pointer-events-none absolute left-3 top-[2.6rem] text-muted" />
        <input
          id="watchlist-quick-start"
          autoFocus
          role="combobox"
          aria-autocomplete="list"
          aria-controls="watchlist-quick-results"
          aria-expanded={results.length > 0}
          value={query}
          onChange={(event) => { setQuery(event.target.value); setError(""); }}
          className="w-full rounded-lg border border-surface-border bg-surface py-2 pl-9 pr-9 text-sm focus:border-brand focus:outline-none"
          placeholder={t("Search ticker or company")}
        />
        {(search.isFetching || quickStart.isPending) && <Loader2 size={15} className="absolute right-3 top-[2.6rem] animate-spin text-muted" />}
        {results.length > 0 && (
          <ul id="watchlist-quick-results" role="listbox" className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-surface-border bg-surface-card shadow-xl">
            {results.map((result) => (
              <li key={`${result.symbol}-${result.exchange || ""}`}>
                <button
                  type="button"
                  role="option"
                  aria-selected="false"
                  aria-label={`${result.symbol} ${result.name}`}
                  disabled={quickStart.isPending}
                  onClick={() => quickStart.mutate(result.symbol)}
                  className="flex w-full gap-3 px-3 py-2 text-left hover:bg-surface-hover disabled:opacity-50"
                >
                  <span className="font-mono font-bold">{result.symbol}</span>
                  <span className="truncate text-sm text-muted">{result.name}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {error && <p role="alert" className="mt-3 text-sm text-loss">{error}</p>}
    </section>
  );
}
