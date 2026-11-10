import { msg } from "../i18n/I18nProvider";

const DEFAULT_MESSAGE = msg("We couldn't load this data.");
const identity = (text) => text;

// `fallback` is the caller's own (already translated) sentence; `t` is the i18n
// translate function and only matters for the built-in sentences below. Text
// the server sends in `detail` stays as it is (backend messages are English).
export function getApiErrorMessage(error, fallback, t = identity) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
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
