import { LANGUAGES, LANGUAGE_KEY } from "../../pages/welcomeCopy";

export const isLanguage = (code) => LANGUAGES.some((language) => language.code === code);

export function savedLanguage() {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY);
    return isLanguage(saved) ? saved : null;
  } catch { return null; }
}

// Only an explicit action saves the language (switcher, banner, demo CTA):
// the app, demo and legal pages read it. Merely landing on a URL does not.
export function rememberLanguage(code) {
  try { localStorage.setItem(LANGUAGE_KEY, code); } catch { /* Storage may be unavailable. */ }
}
