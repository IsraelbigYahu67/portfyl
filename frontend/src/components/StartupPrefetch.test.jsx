import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import StartupPrefetch from './StartupPrefetch';
import source from './StartupPrefetch.jsx?raw';

const state = vi.hoisted(() => ({ currency: 'USD', currentId: 'p1', ready: true }));
const api = vi.hoisted(() => ({ fetchSummary: vi.fn(), fetchHoldings: vi.fn(), fetchPerformance: vi.fn() }));
vi.mock('../App', () => ({ useCurrency: () => state, usePortfolio: () => state }));
vi.mock('../api', () => api);
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
