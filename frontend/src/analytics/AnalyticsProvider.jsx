import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  CONSENT_STATES,
  getAnalyticsConsent,
  setAnalyticsConsent,
} from "./consent";
import { createNoopAdapter, createMemoryAdapter, loadPostHogAdapter } from "./analyticsClient";
import { sanitizeEvent } from "./eventContract";

const AnalyticsContext = createContext(null);
const EU_POSTHOG_HOST = "https://eu.i.posthog.com";
const ONCE_STORAGE_PREFIX = "portfyl_captured_once:";

function defaultAdapterFactory({ consent }) {
  if (import.meta.env.DEV || import.meta.env.MODE === "test") return createMemoryAdapter();
  const key = import.meta.env.VITE_POSTHOG_KEY;
  const host = import.meta.env.VITE_POSTHOG_HOST;
  if (!key || host !== EU_POSTHOG_HOST) return createNoopAdapter();
  return loadPostHogAdapter({ key, host, consent });
}

/**
 * Consent-owned analytics provider. Sends nothing while consent is
 * "pending"; initializes exactly one adapter on an explicit accept/reject
 * decision, and swaps it (reset + shutdown the old one, then re-init) on any
 * later consent change. All product calls (capture/identify/reset) are
 * non-throwing -- a missing key, blocked script, or adapter failure never
 * affects the caller.
 */
export default function AnalyticsProvider({ children, initialConsent, adapterFactory = defaultAdapterFactory }) {
  const [consent, setConsent] = useState(() => initialConsent ?? getAnalyticsConsent());
  const [ready, setReady] = useState(false);
  const adapterRef = useRef(null);
  const readyRef = useRef(false);
  // A React child's first-mount effect runs *before* this provider's own
  // effect (children commit bottom-up), and adapter.init() is genuinely
  // async (a real SDK does a dynamic import). A capture attempted in that
  // window queues here instead of being silently dropped, and is flushed
  // once init() resolves -- this is not the same as replaying a "pending"
  // capture: consent is already decided, only the adapter isn't ready yet.
  const queueRef = useRef([]);
  const acceptedOnceRef = useRef(new Set());

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    readyRef.current = false;

    if (consent === CONSENT_STATES.PENDING) {
      adapterRef.current = null;
      queueRef.current = []; // pending genuinely drops queued captures, per spec
      return () => {
        cancelled = true;
      };
    }

    // Note: queueRef.current is intentionally NOT cleared here. On the very
    // first run, a child's mount effect may have already queued a capture
    // (children's effects commit before this one); clearing here would
    // discard it before the .then() below ever sees it. On a later run
    // (consent changed), the previous run's cleanup already cleared it.

    const adapter = adapterFactory({ consent });
    adapterRef.current = adapter;
    adapter
      .init()
      .then(() => {
        if (cancelled) return;
        readyRef.current = true;
        setReady(true);
        const queued = queueRef.current;
        queueRef.current = [];
        queued.forEach(([name, properties]) => adapter.capture(name, properties).catch(() => {}));
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      queueRef.current = [];
      adapter.reset().catch(() => {});
      adapter.shutdown().catch(() => {});
    };
  }, [consent, adapterFactory]);

  const capture = useCallback(
    (name, properties) => {
      // Only an explicit "accepted" choice may send events; a rejected choice
      // sends nothing at all (privacy review A1).
      if (consent !== CONSENT_STATES.ACCEPTED) return;
      const sanitized = sanitizeEvent(name, properties, { strict: false });
      if (!sanitized) return;
      if (readyRef.current && adapterRef.current) {
        adapterRef.current.capture(sanitized.name, sanitized.properties).catch(() => {});
      } else {
        queueRef.current.push([sanitized.name, sanitized.properties]);
      }
    },
    [consent]
  );

  // `scope` never leaves the browser: it only keys local dedup state
  // (localStorage, stored only after the user accepted analytics), and is
  // never passed to capture()/the adapter.
  const captureOnce = useCallback(
    (scope, name, properties) => {
      if (consent !== CONSENT_STATES.ACCEPTED) return;
      const key = `${scope}:${name}`;
      const storageKey = ONCE_STORAGE_PREFIX + key;
      try {
        if (localStorage.getItem(storageKey)) return;
        localStorage.setItem(storageKey, "1");
      } catch {
        if (acceptedOnceRef.current.has(key)) return;
        acceptedOnceRef.current.add(key);
      }
      capture(name, properties);
    },
    [capture, consent]
  );

  const identify = useCallback(
    (userId) => {
      const adapter = adapterRef.current;
      if (!adapter || consent !== CONSENT_STATES.ACCEPTED) return;
      adapter.identify(String(userId)).catch(() => {});
    },
    [consent]
  );

  const reset = useCallback(() => {
    const adapter = adapterRef.current;
    if (adapter) adapter.reset().catch(() => {});
  }, []);

  const acceptAnalytics = useCallback(() => {
    setAnalyticsConsent(CONSENT_STATES.ACCEPTED);
    setConsent(CONSENT_STATES.ACCEPTED);
  }, []);

  const rejectAnalytics = useCallback(() => {
    setAnalyticsConsent(CONSENT_STATES.REJECTED);
    setConsent(CONSENT_STATES.REJECTED);
  }, []);

  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const reopenAnalyticsPreferences = useCallback(() => setPreferencesOpen(true), []);
  const closeAnalyticsPreferences = useCallback(() => setPreferencesOpen(false), []);

  const value = useMemo(
    () => ({
      consent,
      ready,
      capture,
      captureOnce,
      identify,
      reset,
      acceptAnalytics,
      rejectAnalytics,
      reopenAnalyticsPreferences,
      preferencesOpen,
      closeAnalyticsPreferences,
    }),
    [consent, ready, capture, captureOnce, identify, reset, acceptAnalytics, rejectAnalytics, reopenAnalyticsPreferences, preferencesOpen, closeAnalyticsPreferences]
  );

  return <AnalyticsContext.Provider value={value}>{children}</AnalyticsContext.Provider>;
}

export function useAnalytics() {
  const ctx = useContext(AnalyticsContext);
  if (ctx == null) {
    throw new Error("useAnalytics must be used inside AnalyticsProvider");
  }
  return ctx;
}

// For components that also render outside the provider (prerender, unit
// tests): the same value as useAnalytics, or null when there is no provider.
export function useOptionalAnalytics() {
  return useContext(AnalyticsContext);
}
