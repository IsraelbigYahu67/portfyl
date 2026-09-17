import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useStockIntentPrefetch } from './useStockIntentPrefetch';

const state = vi.hoisted(() => ({ currentId: 'p1', ready: true, currency: 'USD' }));
const api = vi.hoisted(() => ({ fetchStockView: vi.fn(), fetchHistory: vi.fn(), loadStock: vi.fn() }));
vi.mock('../App', () => ({ usePortfolio: () => state, useCurrency: () => state }));
vi.mock('../api', () => ({ fetchStockView: api.fetchStockView, fetchHistory: api.fetchHistory }));
vi.mock('../routes/authenticatedRoutes', () => ({ loadStock: api.loadStock }));
beforeEach(() => {
  vi.useFakeTimers(); Object.assign(state, { currentId: 'p1', ready: true, currency: 'USD' });
  Object.values(api).forEach(fn => fn.mockReset().mockResolvedValue({}));
});
afterEach(() => vi.useRealTimers());
function setup(ticker = 'aapl') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const hook = renderHook(({ symbol }) => useStockIntentPrefetch(symbol), { initialProps: { symbol: ticker }, wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
  return { ...hook, client };
}
it('loads one chunk immediately and only two Overview queries after 150 ms', async () => {
  const { result, client } = setup();
  expect(api.loadStock).not.toHaveBeenCalled();
  act(() => { result.current.onMouseEnter(); result.current.onFocus(); });
  expect(api.loadStock).toHaveBeenCalledTimes(1);
  await act(async () => vi.advanceTimersByTime(149));
  expect(api.fetchStockView).not.toHaveBeenCalled();
  await act(async () => vi.advanceTimersByTime(1));
  expect(api.fetchStockView).toHaveBeenCalledTimes(1);
  expect(api.fetchHistory).toHaveBeenCalledTimes(1);
  expect(client.getQueryCache().getAll().map(q => q.queryKey)).toEqual([['stock-view', 'AAPL', 'overview'], ['history', 'AAPL', '1y']]);
  expect(api.fetchStockView.mock.calls[0].slice(0, 2)).toEqual(['AAPL', 'overview']);
  expect(api.fetchHistory.mock.calls[0][2].signal).toBeInstanceOf(AbortSignal);
});
it.each(['onMouseLeave', 'onBlur'])('cancels a short intent via %s', async stop => {
  const { result } = setup();
  act(() => result.current.onFocus());
  await act(async () => vi.advanceTimersByTime(149));
  act(() => result.current[stop]());
  await act(async () => vi.advanceTimersByTime(1));
  expect(api.fetchStockView).not.toHaveBeenCalled();
  expect(api.fetchHistory).not.toHaveBeenCalled();
});
it.each(['currency', 'currentId', 'ticker', 'unmount'])('clears pending intent on %s changes', async change => {
  const { result, rerender, unmount } = setup();
  act(() => result.current.onMouseEnter());
  if (change === 'unmount') unmount();
  else { if (change !== 'ticker') state[change] = 'other'; rerender({ symbol: change === 'ticker' ? 'MSFT' : 'aapl' }); }
  await act(async () => vi.advanceTimersByTime(150));
  expect(api.fetchStockView).not.toHaveBeenCalled();
});
