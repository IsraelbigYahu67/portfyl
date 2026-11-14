// The currencies the signed-in app can show the portfolio in. The backend
// converts to any of them (routers/portfolio.py goes through CZK); the few
// client-side conversions multiply a USD figure by the provider's `rate`,
// which is "display units per 1 USD" (1 for USD itself).
export const DISPLAY_CURRENCIES = Object.freeze(["USD", "CZK", "EUR", "GBP", "PLN"]);

// Device-level preference. It keeps the legacy sb_ prefix so existing users
// keep their choice (see CLAUDE.md "Naming").
export const CURRENCY_STORAGE_KEY = "sb_currency";

// Where speakers of each app language most likely live, by language alone.
// English means the UK (pounds); anything unknown falls back to USD.
const LOCAL_CURRENCY_BY_LANGUAGE = Object.freeze({
  cs: "CZK",
  de: "EUR",
  fr: "EUR",
  es: "EUR",
  it: "EUR",
  pt: "EUR",
  nl: "EUR",
  pl: "PLN",
  en: "GBP",
});

const CURRENCY_SYMBOLS = Object.freeze({ USD: "$", CZK: "Kč", EUR: "€", GBP: "£", PLN: "zł" });

export function isDisplayCurrency(code) {
  return DISPLAY_CURRENCIES.includes(code);
}

export function localCurrencyForLanguage(language) {
  return LOCAL_CURRENCY_BY_LANGUAGE[language] ?? "USD";
}

// The currency cards to offer for a language: its local currency, plus a
// non-USD currency already chosen elsewhere (Settings) so the selection is
// never hidden. USD is offered separately, as "Display only in USD".
export function currencyChoicesForLanguage(language, current = null) {
  const choices = [localCurrencyForLanguage(language)].filter((code) => code !== "USD");
  if (isDisplayCurrency(current) && current !== "USD" && !choices.includes(current)) choices.push(current);
  return choices;
}

export function currencySymbol(code) {
  return CURRENCY_SYMBOLS[code] ?? code;
}

export function readStoredCurrency() {
  try {
    const stored = localStorage.getItem(CURRENCY_STORAGE_KEY);
    return isDisplayCurrency(stored) ? stored : null;
  } catch {
    return null; // Storage may be unavailable (private browsing, blocked cookies).
  }
}

export function saveCurrency(code) {
  try {
    localStorage.setItem(CURRENCY_STORAGE_KEY, code);
  } catch {
    /* Storage may be unavailable; the choice then lasts for this visit. */
  }
}

// Saved choice first, otherwise the local currency of the app language.
export function initialDisplayCurrency(language) {
  return readStoredCurrency() ?? localCurrencyForLanguage(language);
}

// A USD amount in the display currency. Without a rate the USD figure is
// returned unchanged (the UI warns that the rate is unavailable).
export function convertFromUsd(amount, currency, rate) {
  return currency !== "USD" && rate ? amount * rate : amount;
}
