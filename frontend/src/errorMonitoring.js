// Opt-in via VITE_SENTRY_DSN, a no-op without it. The SDK itself is loaded
// with a dynamic import() -- like auth/firebase.js's loadFirebaseSdk() --
// so it lands in its own chunk, excluded from the initial-bundle gzip gate
// (docs/superpowers/plans/ux-08-browser-closeout-2026-09-17.md's "Final
// bundle gate"), rather than statically inflating every build regardless of
// whether a DSN is even configured. Mirrors backend/error_monitoring.py's
// PII posture (send_default_pii off; the browser SDK does not capture form
// field values on its own).

let _sdkPromise = null;

function isEnabled() {
  return Boolean(import.meta.env.VITE_SENTRY_DSN);
}

function loadSentry() {
  if (!isEnabled()) return null;
  if (!_sdkPromise) {
    _sdkPromise = import('@sentry/react')
      .then((Sentry) => {
        Sentry.init({
          dsn: import.meta.env.VITE_SENTRY_DSN,
          environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || import.meta.env.VITE_PORTFYL_EDITION,
          release: import.meta.env.VITE_SENTRY_RELEASE,
          tracesSampleRate: Number(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || 0),
          sendDefaultPii: false,
        });
        return Sentry;
      })
      .catch((error) => {
        _sdkPromise = null;
        throw error;
      });
  }
  return _sdkPromise;
}

export function initErrorMonitoring() {
  return loadSentry();
}

export function reportError(error, info) {
  const promise = loadSentry();
  if (!promise) return null;
  return promise.then((Sentry) => Sentry.captureException(error, info));
}
