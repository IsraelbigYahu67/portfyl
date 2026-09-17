import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useCurrency, usePortfolio } from '../App';
import { fetchSummary, fetchHoldings, fetchPerformance } from '../api';
import { useStockIntentScopeCleanup } from '../hooks/useStockIntentScopeCleanup';

export default function StartupPrefetch() {
  useStockIntentScopeCleanup();
  const client = useQueryClient();
  const { currency } = useCurrency();
  const { ready, currentId } = usePortfolio();
  useEffect(() => {
    if (!ready || currentId == null) return;
    const warms = [
      [['summary', currency], () => fetchSummary(currency)],
      [['holdings', currency], () => fetchHoldings(currency)],
      [['performance', currency, 'All'], () => fetchPerformance(currency, 'all')],
    ];
    for (const [queryKey, queryFn] of warms) {
      client.prefetchQuery({ queryKey, queryFn, staleTime: 60_000 }).catch(() => {});
    }
  }, [client, currency, ready, currentId]);
  return null;
}
