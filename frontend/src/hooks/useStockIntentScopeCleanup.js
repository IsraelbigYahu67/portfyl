import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCurrency, usePortfolio } from "../App";

export function useStockIntentScopeCleanup() {
  const client = useQueryClient();
  const { currency } = useCurrency();
  const { currentId } = usePortfolio();
  const scope = useRef({ currentId, currency });

  useEffect(() => {
    const previous = scope.current;
    scope.current = { currentId, currency };
    if (previous.currentId === currentId && previous.currency === currency) return;
    const predicate = query => query.meta?.intentPrefetch && query.getObserversCount() === 0 &&
      (query.meta.portfolioId !== currentId || query.meta.currency !== currency);
    void client.cancelQueries({ predicate });
    client.removeQueries({ predicate });
  }, [client, currentId, currency]);
}
