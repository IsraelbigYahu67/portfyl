import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useCurrency, usePortfolio } from '../App';
import { fetchStockView, fetchHistory } from '../api';
import { loadStock } from '../routes/authenticatedRoutes';

export function useStockIntentPrefetch(ticker) {
  const client = useQueryClient();
  const { currency } = useCurrency();
  const { currentId, ready } = usePortfolio();
  const symbol = String(ticker || '').toUpperCase();
  const timer = useRef(null);
  const started = useRef(false);
  const stop = () => {
    clearTimeout(timer.current);
    timer.current = null;
    started.current = false;
  };
  useEffect(() => {
    stop();
    return stop;
  }, [client, symbol, currentId, currency, ready]);
  const start = () => {
    if (!symbol || started.current) return;
    started.current = true;
    try { Promise.resolve(loadStock()).catch(() => {}); } catch { /* Navigation owns chunk errors. */ }
    if (!ready || currentId == null) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      const meta = { intentPrefetch: true, portfolioId: currentId, currency };
      const request = signal => ({ signal, suppressEntitlementPrompt: true });
      // Plan 7 changed Overview to a bounded view endpoint: reuse its exact key.
      client.prefetchQuery({ queryKey: ['stock-view', symbol, 'overview'],
        queryFn: ({ signal }) => fetchStockView(symbol, 'overview', request(signal)), staleTime: 300_000, meta }).catch(() => {});
      client.prefetchQuery({ queryKey: ['history', symbol, '1y'],
        queryFn: ({ signal }) => fetchHistory(symbol, '1y', request(signal)), staleTime: 300_000, meta }).catch(() => {});
    }, 150);
  };
  return { onMouseEnter: start, onFocus: start, onMouseLeave: stop, onBlur: stop };
}
