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
  const acceptedOnceRef = useRef(new Set());
  const rejectedOnceRef = useRef(new Set());

  useEffect(() => {
    let cancelled = false;
    setReady(false);

    if (consent === CONSENT_STATES.PENDING) {
      adapterRef.current = null;
      return () => {
        cancelled = true;
      };
    }

    const adapter = adapterFactory({ consent });
    adapterRef.current = adapter;
    adapter
      .init()
      .then(() => {
        if (!cancelled) setReady(true);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      adapter.reset().catch(() => {});
      adapter.shutdown().catch(() => {});
    };
  }, [consent, adapterFactory]);

  const capture = useCallback(
    (name, properties) => {
      const adapter = adapterRef.current;
      if (!adapter || consent === CONSENT_STATES.PENDING) return;
      const sanitized = sanitizeEvent(name, properties, { strict: false });
      if (!sanitized) return;
      adapter.capture(sanitized.name, sanitized.properties).catch(() => {});
    },
    [consent]
  );

  // `scope` never leaves the browser: it only keys local dedup state
  // (localStorage in accepted mode, an in-memory Set in rejected mode), and
  // is never passed to capture()/the adapter.
  const captureOnce = useCallback(
    (scope, name, properties) => {
      const key = `${scope}:${name}`;
      if (consent === CONSENT_STATES.ACCEPTED) {
        const storageKey = ONCE_STORAGE_PREFIX + key;
        try {
          if (localStorage.getItem(storageKey)) return;
          localStorage.setItem(storageKey, "1");
        } catch {
          if (acceptedOnceRef.current.has(key)) return;
          acceptedOnceRef.current.add(key);
        }
      } else {
        if (rejectedOnceRef.current.has(key)) return;
        rejectedOnceRef.current.add(key);
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
    rejectedOnceRef.current.clear();
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
