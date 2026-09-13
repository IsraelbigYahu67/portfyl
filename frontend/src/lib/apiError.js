const DEFAULT_MESSAGE = "We couldn't load this data.";

export function getApiErrorMessage(error, fallback = DEFAULT_MESSAGE) {
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
    return "The request timed out. Please try again.";
  }

  if (error?.request && !error?.response) {
    return "We couldn't reach Portfyl. Check your connection and try again.";
  }

  const message = typeof error?.message === "string" ? error.message.trim() : "";
  if (!error?.response && message && !/[\r\n]/.test(message)) {
    return message;
  }

  return fallback;
}
