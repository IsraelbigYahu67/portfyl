import { msg } from "../i18n/I18nProvider";

const DEFAULT_MESSAGE = msg("We couldn't load this data.");
const identity = (text) => text;

// The fixed sentences the broker connect/sync endpoints send in `detail`
// (backend/routers/broker.py, ibkr.py, etoro.py, t212_sync.py). They are
// English on the wire; when one matches exactly it is shown translated.
// Messages with a dynamic part (`...: {reason}`) are not listed and stay English.
const BROKER_DETAILS = Object.freeze(new Set([
  msg("API key is required"),
  msg("Invalid API key"),
  msg("API key does not have the required permissions"),
  msg("Too many requests — Trading 212 rate limit hit. Try again in a minute."),
  msg("This API key is already connected to a different portfolio. Each portfolio must use its own Trading 212 API key."),
  msg("This Trading 212 account is already bound to another portfolio."),
  msg("This portfolio is already bound to a different Trading 212 account. Create a new portfolio for the other account."),
  msg("The existing Trading 212 account identity could not be verified. This portfolio was left unchanged; connect the new account to a new portfolio."),
  msg("Trading 212 did not return a usable account identity"),
  msg("Trading 212 account identity verification is not configured"),
  msg("Trading 212 account identity could not be verified"),
  msg("Trading 212 is not connected"),
  msg("No Trading 212 connection found"),
  msg("API key is invalid or expired"),
  msg("API key cannot read the account summary"),
  msg("API key cannot read positions"),
  msg("Trading 212 rate limit reached"),
  msg("IBKR is not connected"),
  msg("No IBKR connection found"),
  msg("flex_token is required"),
  msg("query_id is required"),
  msg("IBKR returned Success but no ReferenceCode"),
  msg("Unexpected response format from IBKR"),
  msg("Timed out waiting for IBKR Flex statement (60s)"),
  msg("eToro integration is not configured"),
  msg("user_key is required"),
  msg("eToro rejected the key. In eToro open Settings → Trading → API Key Management, create a key with Read permission for the Real environment and paste it here."),
  msg("eToro is not connected"),
  msg("No eToro connection found"),
  msg("Portfolio not found"),
]));

// `fallback` is the caller's own (already translated) sentence; `t` is the i18n
// translate function and matters for the built-in sentences and the known
// broker details above. Any other text the server sends in `detail` stays as
// it is (backend messages are English).
export function getApiErrorMessage(error, fallback, t = identity) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    const text = detail.trim();
    return BROKER_DETAILS.has(text) ? t(text) : text;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => item?.msg)
      .filter((message) => typeof message === "string" && message.trim())
      .map((message) => message.trim());
    if (messages.length) return messages.join("; ");
  }

  if (error?.code === "ECONNABORTED" || /timeout/i.test(error?.message || "")) {
    return t(msg("The request timed out. Please try again."));
  }

  if (error?.request && !error?.response) {
    return t(msg("We couldn't reach Portfyl. Check your connection and try again."));
  }

  const message = typeof error?.message === "string" ? error.message.trim() : "";
  if (!error?.response && message && !/[\r\n]/.test(message)) {
    return message;
  }

  return fallback === undefined ? t(DEFAULT_MESSAGE) : fallback;
}
