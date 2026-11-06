// The languages the signed-in app can be used in. English is the source
// language: every UI string is written in English in the code, and the
// dictionaries in ./messages map that English text to each translation.
//
// Glossary: anglicisms that investors use as-is stay in English in every
// language -- Dashboard, Insider, Watchlist, ETF, ticker, broker, benchmark,
// CSV, API, P/E, Flex Query, the plan names (Free, Investor, Pro) and the
// product and broker names. See
// docs/superpowers/plans/2026-11-06-portfyl-app-languages.md.

export const APP_LANGUAGES = Object.freeze([
  { code: "cs", name: "Čeština", englishName: "Czech" },
  { code: "en", name: "English", englishName: "English" },
  { code: "de", name: "Deutsch", englishName: "German" },
  { code: "fr", name: "Français", englishName: "French" },
  { code: "es", name: "Español", englishName: "Spanish" },
  { code: "it", name: "Italiano", englishName: "Italian" },
  { code: "pt", name: "Português", englishName: "Portuguese" },
  { code: "pl", name: "Polski", englishName: "Polish" },
  { code: "nl", name: "Nederlands", englishName: "Dutch" },
]);

export const SOURCE_LANGUAGE = "en";

// Device-level, like the theme and currency preferences (sb_*). New key, so
// it has the product prefix rather than the legacy sb_ one.
export const LANGUAGE_STORAGE_KEY = "portfyl_language";
// The public landing page's own choice (cs/en/de, pages/welcomeCopy.js). A
// visitor who picked Czech there starts the app in Czech too.
const LANDING_LANGUAGE_KEY = "portfyl_landing_language";

export function isAppLanguage(code) {
  return APP_LANGUAGES.some((language) => language.code === code);
}

function readStorage(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // Storage may be unavailable (private browsing, blocked cookies).
  }
}

// Saved choice, then the landing page's choice, then the browser's languages,
// then English.
export function initialLanguage(browserLanguages = globalThis.navigator?.languages ?? []) {
  for (const code of [readStorage(LANGUAGE_STORAGE_KEY), readStorage(LANDING_LANGUAGE_KEY)]) {
    if (isAppLanguage(code)) return code;
  }
  for (const tag of browserLanguages) {
    const code = String(tag).toLowerCase().split("-")[0];
    if (isAppLanguage(code)) return code;
  }
  return SOURCE_LANGUAGE;
}

export function saveLanguage(code) {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, code);
  } catch {
    /* Storage may be unavailable; the choice then lasts for this visit. */
  }
}
