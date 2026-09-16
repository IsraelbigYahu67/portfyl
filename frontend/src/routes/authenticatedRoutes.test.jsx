import { SHARED_AUTHENTICATED_ROUTES, LazyOnboarding } from './authenticatedRoutes';
import { buildNavGroups, preloadRoute } from '../components/layout/navigation';
import { TRACKER_HOME } from '../lib/routes';

it('gives every shared authenticated route a lazy component and stable loader', () => {
  expect(SHARED_AUTHENTICATED_ROUTES.map(route => route.path)).toEqual([TRACKER_HOME, '/allocation', '/transactions', '/import', '/dividends', '/analytics', '/search', '/stock/:ticker', '/watchlists', '/assistant', '/settings']);
  for (const route of SHARED_AUTHENTICATED_ROUTES) {
    expect(route.Component.$$typeof).toBe(Symbol.for('react.lazy'));
    expect(route.preload).toBeTypeOf('function');
  }
  expect(LazyOnboarding.$$typeof).toBe(Symbol.for('react.lazy'));
});
it('attaches loaders to visible navigation and suppresses background failures', async () => {
  const load = vi.fn().mockRejectedValue(new Error('offline')), other = vi.fn();
  const groups = buildNavGroups([{ to: '/private', capability: 'hidden', preload: other }], [], [{ path: '/allocation', preload: load }]);
  expect(other).not.toHaveBeenCalled();
  const item = groups.flatMap(group => group.items).find(item => item.to === '/allocation');
  expect(item.preload).toBe(load);
  await preloadRoute(item.preload);
  expect(load).toHaveBeenCalledTimes(1);
});
