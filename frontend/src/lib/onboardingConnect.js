// Pure helpers for the onboarding "connect a broker" step: the connect-step
// marker (so a closed tab or a Stripe round trip reopens the step), the
// checkout return and the few API answers the step must tell apart.
// Imported by the onboarding view's neighbours, so it must never reach `api`,
// `App` or `analytics`.
import { findSupportedBroker } from "./onboardingBrokers";

// Device-level, like the intended-broker key: holds a supported API broker key
// and a timestamp only.
export const CONNECT_STEP_KEY = "portfyl_onboarding_connect";
export const CONNECT_STEP_TTL_MS = 86_400_000;

function removeMarker() {
  try {
    localStorage.removeItem(CONNECT_STEP_KEY);
  } catch {
    /* Storage may be unavailable; there is nothing to remove. */
  }
}

export function rememberConnectStep(brokerKey, now = Date.now()) {
  if (!findSupportedBroker(brokerKey)?.api) return;
  try {
    localStorage.setItem(CONNECT_STEP_KEY, JSON.stringify({ broker: brokerKey, at: now }));
  } catch {
    /* Storage may be unavailable (private browsing); the step is then not restored. */
  }
}

// Re-validated on every read: the stored value is not trusted. An invalid or
// expired marker is removed.
export function connectStepBroker(now = Date.now()) {
  let raw;
  try {
    raw = localStorage.getItem(CONNECT_STEP_KEY);
  } catch {
    return null;
  }
  if (raw === null) return null;
  let marker = null;
  try {
    marker = JSON.parse(raw);
  } catch {
    marker = null;
  }
  const valid = marker
    && typeof marker === "object"
    && typeof marker.broker === "string"
    && Number.isFinite(marker.at)
    && findSupportedBroker(marker.broker)?.api === true
    && now - marker.at <= CONNECT_STEP_TTL_MS;
  if (!valid) {
    removeMarker();
    return null;
  }
  return marker.broker;
}

export function clearConnectStep() {
  removeMarker();
}

// Stripe sends the customer back with `?checkout=success&session_id=...` or
// `?checkout=canceled`; anything else is not a checkout return.
export function readCheckoutReturn(searchParams) {
  const outcome = searchParams.get("checkout");
  if (outcome !== "success" && outcome !== "canceled") return null;
  return { outcome, sessionId: searchParams.get("session_id") || null };
}

// The flat entitlement 403 (`{ code: "plan_upgrade_required" }`), not the
// billing routes' `{ detail: { code } }` shape.
export function isPlanUpgradeRequired(error) {
  const response = error?.response;
  return response?.status === 403 && response?.data?.code === "plan_upgrade_required";
}

// Billing errors carry their code under `detail`.
export function apiErrorCode(error) {
  return error?.response?.data?.detail?.code ?? null;
}

// Whether a first sync wrote anything, by each broker's response shape.
export function syncImportedData(brokerKey, result) {
  const count = (value) => (Number.isFinite(value) ? value : 0);
  if (brokerKey === "trading212") return count(result?.snapshot?.positions) > 0;
  if (brokerKey === "ibkr") return count(result?.ledger?.imported) > 0;
  if (brokerKey === "etoro") return count(result?.imported) > 0;
  return false;
}
