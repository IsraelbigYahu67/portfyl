import { useEffect, useRef } from "react";

const SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

let scriptPromise = null;

// Loads Cloudflare's script once per page, however many widgets ask.
function loadTurnstile() {
  if (typeof window !== "undefined" && window.turnstile) return Promise.resolve(window.turnstile);
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.onload = () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile")));
      script.onerror = () => {
        script.remove();
        reject(new Error("turnstile"));
      };
      document.head.appendChild(script);
    }).catch((error) => {
      scriptPromise = null;
      throw error;
    });
  }
  return scriptPromise;
}

// Test helper: forget the cached script promise.
export function resetTurnstileLoader() {
  scriptPromise = null;
}

// Cloudflare's widget for one challenge. `onToken` receives the one-time token;
// `onError` fires when the widget or its script cannot run. The frame itself is
// Cloudflare's, so it takes no Portfyl styling.
export default function TurnstileWidget({ siteKey, action = "signup", language, onToken, onError }) {
  const containerRef = useRef(null);
  const callbacks = useRef({ onToken, onError });
  callbacks.current = { onToken, onError };

  useEffect(() => {
    let cancelled = false;
    let widgetId = null;
    loadTurnstile()
      .then((turnstile) => {
        if (cancelled || !containerRef.current) return;
        widgetId = turnstile.render(containerRef.current, {
          sitekey: siteKey,
          action,
          ...(language ? { language } : {}),
          theme: "light",
          callback: (token) => callbacks.current.onToken?.(token),
          "error-callback": () => callbacks.current.onError?.(),
          // A token not used within 5 minutes expires; ask for a fresh one.
          "expired-callback": () => {
            try {
              turnstile.reset(widgetId);
            } catch {
              /* The widget is already gone. */
            }
          },
        });
      })
      .catch(() => {
        if (!cancelled) callbacks.current.onError?.();
      });
    return () => {
      cancelled = true;
      if (widgetId !== null) {
        try {
          window.turnstile?.remove(widgetId);
        } catch {
          /* Nothing to clean up. */
        }
      }
    };
  }, [siteKey, action, language]);

  return <div ref={containerRef} />;
}
