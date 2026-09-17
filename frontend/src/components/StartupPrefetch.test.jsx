import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, QueryObserver } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import StartupPrefetch from './StartupPrefetch';
import { useStockIntentPrefetch } from '../hooks/useStockIntentPrefetch';
import source from './StartupPrefetch.jsx?raw';

const state = vi.hoisted(() => ({ currency: 'USD', currentId: 'p1', ready: true }));
const api = vi.hoisted(() => ({ fetchSummary: vi.fn(), fetchHoldings: vi.fn(), fetchPerformance: vi.fn(), fetchStockView: vi.fn(), fetchHistory: vi.fn() }));
vi.mock('../App', () => ({ useCurrency: () => state, usePortfolio: () => state }));
vi.mock('../api', () => api);
vi.mock('../routes/authenticatedRoutes', () => ({ loadStock: vi.fn() }));
beforeEach(() => { Object.assign(state, { currency: 'USD', currentId: 'p1', ready: true }); Object.values(api).forEach(fn => fn.mockReset().mockResolvedValue([])); });
it('warms exactly the three Dashboard keys, handles currency changes and ignores errors', async () => {
  const client = new QueryClient();
  const view = render(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>);
  await waitFor(() => expect(api.fetchSummary).toHaveBeenCalledTimes(1));
  expect(client.getQueryCache().getAll().map(q => q.queryKey)).toEqual([['summary', 'USD'], ['holdings', 'USD'], ['performance', 'USD', 'All']]);
  expect(api.fetchPerformance.mock.calls[0][0]).toBe('USD');
  expect(api.fetchPerformance.mock.calls[0][1]).toBe('all');
  state.currency = 'EUR'; api.fetchSummary.mockRejectedValue(new Error('offline'));
  view.rerender(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>);
  await waitFor(() => expect(api.fetchHoldings.mock.calls[1][0]).toBe('EUR'));
  expect(view.container).toBeEmptyDOMElement();
  client.clear();
});
it.each([{ ready: false }, { currentId: null }])('does not warm without an active ready portfolio: %o', extra => {
  Object.assign(state, extra);
  const client = new QueryClient();
  render(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>);
  Object.values(api).forEach(fn => expect(fn).not.toHaveBeenCalled());
});
it('has no API imports beyond the startup allowlist', () => {
  const names = source.match(/\bfetch[A-Z]\w*/g);
  expect([...new Set(names)].sort()).toEqual(['fetchHoldings', 'fetchPerformance', 'fetchSummary']);
});
it('rewarms a switched portfolio after PortfolioProvider clears the entire cache', async () => {
  const client = new QueryClient();
  const view = render(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>);
  await waitFor(() => expect(api.fetchSummary).toHaveBeenCalledTimes(1));
  // This is the existing switch order owned by PortfolioProvider, before the new ID is active.
  client.clear(); state.currentId = 'p2';
  view.rerender(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>);
  await waitFor(() => expect(api.fetchSummary).toHaveBeenCalledTimes(2));
  client.clear();
});
it('cleans orphaned intent requests when scope changes after ticker links unmount', async () => {
  vi.useFakeTimers();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  api.fetchSummary.mockResolvedValue({});
  api.fetchStockView.mockImplementation(() => new Promise(() => {}));
  api.fetchHistory.mockImplementation(() => new Promise(() => {}));
  api.fetchPerformance.mockResolvedValue([]);
  const startup = render(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>);
  const hook = renderHook(() => useStockIntentPrefetch('AAPL'), { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
  const foreground = new QueryObserver(client, { queryKey: ['stock-view', 'MSFT', 'overview'], enabled: false, queryFn: () => Promise.resolve({}), meta: { intentPrefetch: true, portfolioId: 'p1', currency: 'USD' } });
  client.setQueryData(['stock-view', 'MSFT', 'overview'], { keep: true });
  const unsubscribe = foreground.subscribe(() => {});
  client.setQueryData(['unrelated'], 'keep');

  act(() => hook.result.current.onFocus());
  await act(async () => vi.advanceTimersByTime(150));
  const oldSignals = [api.fetchStockView.mock.calls[0]?.[2]?.signal, api.fetchHistory.mock.calls[0]?.[2]?.signal];
  hook.unmount();
  state.currency = 'EUR';
  await act(async () => startup.rerender(<QueryClientProvider client={client}><StartupPrefetch /></QueryClientProvider>));

  expect(oldSignals).toEqual([expect.any(AbortSignal), expect.any(AbortSignal)]);
  expect(oldSignals.every(signal => signal.aborted)).toBe(true);
  expect(client.getQueryCache().find({ queryKey: ['stock-view', 'AAPL', 'overview'] })).toBeUndefined();
  expect(client.getQueryCache().find({ queryKey: ['history', 'AAPL', '1y'] })).toBeUndefined();
  expect(client.getQueryData(['stock-view', 'MSFT', 'overview'])).toEqual({ keep: true });
  expect(client.getQueryData(['unrelated'])).toBe('keep');
  unsubscribe();
  startup.unmount();
  client.clear();
  vi.useRealTimers();
});
