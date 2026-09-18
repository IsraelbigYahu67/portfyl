vi.mock('@sentry/react', () => ({ init: vi.fn(), captureException: vi.fn() }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
  vi.clearAllMocks();
});

it('does not load the Sentry SDK without VITE_SENTRY_DSN', async () => {
  vi.stubEnv('VITE_SENTRY_DSN', '');
  const { initErrorMonitoring } = await import('./errorMonitoring?no-dsn-init');
  expect(initErrorMonitoring()).toBeNull();
  const Sentry = await import('@sentry/react');
  expect(Sentry.init).not.toHaveBeenCalled();
});

it('lazily loads and initializes Sentry once VITE_SENTRY_DSN is set', async () => {
  vi.stubEnv('VITE_SENTRY_DSN', 'https://example.invalid/1');
  const { initErrorMonitoring } = await import('./errorMonitoring?with-dsn-init');
  await initErrorMonitoring();
  const Sentry = await import('@sentry/react');
  expect(Sentry.init).toHaveBeenCalledWith(expect.objectContaining({
    dsn: 'https://example.invalid/1',
    sendDefaultPii: false,
  }));
});

it('reportError is a no-op without a configured DSN', async () => {
  vi.stubEnv('VITE_SENTRY_DSN', '');
  const { reportError } = await import('./errorMonitoring?no-dsn-report');
  expect(reportError(new Error('boom'))).toBeNull();
  const Sentry = await import('@sentry/react');
  expect(Sentry.captureException).not.toHaveBeenCalled();
});

it('reportError forwards to Sentry.captureException once the SDK is loaded', async () => {
  vi.stubEnv('VITE_SENTRY_DSN', 'https://example.invalid/1');
  const { reportError } = await import('./errorMonitoring?with-dsn-report');
  const error = new Error('boom');
  await reportError(error, { extra: { x: 1 } });
  const Sentry = await import('@sentry/react');
  expect(Sentry.captureException).toHaveBeenCalledWith(error, { extra: { x: 1 } });
});
