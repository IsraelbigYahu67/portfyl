// What a visitor told us on the landing page or in the demo before signing up
// (their broker, their language), carried through registration in the URL and
// remembered on this device until the first portfolio exists.
import { isAppLanguage } from "../i18n/languages";
import { findSupportedBroker } from "./onboardingBrokers";

export const APP_ORIGIN = import.meta.env.VITE_APP_ORIGIN || "https://app.portfyl.com";

// Device-level, like the language choice. Holds a supported broker key only.
export const INTENDED_BROKER_KEY = "portfyl_intended_broker";

// Only valid values travel: an unsupported broker or language is dropped, so a
// link can never carry arbitrary text into the app.
export function registerUrl({ origin = APP_ORIGIN, source = null, broker = null, lang = null } = {}) {
  const params = new URLSearchParams();
  if (typeof source === "string" && source) params.set("source", source);
  if (findSupportedBroker(broker)) params.set("broker", broker);
  if (isAppLanguage(lang)) params.set("lang", lang);
  const query = params.toString();
  return `${origin}/register${query ? `?${query}` : ""}`;
}

export function readSignupIntent(searchParams) {
  const broker = searchParams.get("broker");
  const lang = searchParams.get("lang");
  return {
    broker: findSupportedBroker(broker) ? broker : null,
    lang: isAppLanguage(lang) ? lang : null,
  };
}

export function rememberIntendedBroker(key) {
  if (!findSupportedBroker(key)) return;
  try {
    localStorage.setItem(INTENDED_BROKER_KEY, key);
  } catch {
    /* Storage may be unavailable (private browsing); the intent is then lost. */
  }
}

// Re-validated on every read: the stored value is not trusted.
export function intendedBroker() {
  try {
    const key = localStorage.getItem(INTENDED_BROKER_KEY);
    return findSupportedBroker(key) ? key : null;
  } catch {
    return null;
  }
}

export function clearIntendedBroker() {
  try {
    localStorage.removeItem(INTENDED_BROKER_KEY);
  } catch {
    /* Storage may be unavailable; there is nothing to clear. */
  }
}
