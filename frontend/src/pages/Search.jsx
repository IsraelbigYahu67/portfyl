import { useEffect, useMemo, useRef, useState } from "react";
import { TickerLink } from "../components/TickerLink";
import { useQuery } from "@tanstack/react-query";
import { Search as SearchIcon, Loader2, ArrowRight } from "lucide-react";
import { searchTickers } from "../api";
import { AsyncSection } from "../components/ui";

// Light debounce so typing doesn't fire a query on every keystroke. 250ms is
// short enough to feel instant but cuts request count by ~10x for fast typers.
function useDebounced(value, delay = 250) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}

export default function Search() {
  const [query, setQuery] = useState("");
  const debounced = useDebounced(query, 250);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const enabled = debounced.trim().length >= 1;
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => searchTickers(debounced, 20),
    enabled,
    staleTime: 60_000,
    retry: false,
  });

  const results = useMemo(() => data?.results || [], [data]);

  return (
    <div className="max-w-4xl mx-auto py-6">
      <h1 className="text-2xl font-bold mb-1">Search Stocks</h1>
      <p className="text-sm text-muted mb-6">
        Look up any ticker or company name to see fundamentals, ratios, and
        analyst targets.
      </p>

      <div className="relative">
        <SearchIcon
          size={18}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none"
        />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by ticker (AAPL) or company name…"
          className="w-full bg-surface-card border border-surface-border rounded-lg pl-10 pr-10 py-3 text-base focus:outline-none focus:border-brand"
        />
        {(isLoading || isFetching) && enabled && (
          <Loader2
            size={16}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted animate-spin"
          />
        )}
      </div>

      <div className="mt-6">
        {!enabled && (
          <div className="text-center text-muted py-12 text-sm">
            Start typing to see suggestions.
          </div>
        )}

        {enabled && (
          <AsyncSection
            isLoading={isLoading}
            error={error}
            onRetry={() => refetch()}
            loading={(
              <div className="text-center text-muted py-12 text-sm animate-pulse">
                Searching…
              </div>
            )}
            isEmpty={results.length === 0}
            empty={(
              <div className="text-center text-muted py-12 text-sm">
                No matches for "{debounced}".
              </div>
            )}
          >
            <ul className="bg-surface-card border border-surface-border rounded-lg divide-y divide-surface-border overflow-hidden">
              {results.map((r) => (
                <li key={`${r.symbol}-${r.exchange ?? ""}`}>
                  <TickerLink
                    ticker={r.symbol}
                    className="flex items-center gap-3 px-4 py-3 hover:bg-surface-hover group transition-colors"
                  >
                    <div className="flex-shrink-0 w-16 font-mono font-bold text-base">
                      {r.symbol}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="truncate text-sm">{r.name}</div>
                      <div className="text-xs text-muted truncate">
                        {[r.exchange, r.type, r.sector].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                    <ArrowRight
                      size={16}
                      className="text-muted group-hover:text-brand transition-colors"
                    />
                  </TickerLink>
                </li>
              ))}
            </ul>
          </AsyncSection>
        )}
      </div>
    </div>
  );
}
