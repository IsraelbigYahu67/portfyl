import { Fragment, createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { SOURCE_LANGUAGE, initialLanguage, isAppLanguage, saveLanguage } from "./languages";

// Each dictionary is its own chunk, so a visitor downloads only the language
// they use. English needs none: the English source text is the key.
const LOADERS = {
  cs: () => import("./messages/cs.js"),
  de: () => import("./messages/de.js"),
  fr: () => import("./messages/fr.js"),
  es: () => import("./messages/es.js"),
  it: () => import("./messages/it.js"),
  pt: () => import("./messages/pt.js"),
  pl: () => import("./messages/pl.js"),
  nl: () => import("./messages/nl.js"),
};

// Marks a string for translation where it is defined (a data module, a
// constant) and is translated later with t(variable) where it is shown. It
// returns the text unchanged; i18n/messages.test.js finds the strings by it.
export const msg = (text) => text;

// `text` is the English source; `{name}` placeholders are filled from `vars`.
// Text missing from the dictionary falls back to English.
export function translate(messages, text, vars) {
  const template = messages?.[text] ?? text;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, key) => (key in vars ? String(vars[key]) : match));
}

// For a translated sentence with styled words in it, written with tags in the
// English text ("Open <b>Settings</b>.") and drawn by
// rich(translated, { b: (words) => <strong>{words}</strong> }). Translators
// move the tags with the words; a tag without a renderer shows as plain text.
export function rich(text, tags) {
  const parts = [];
  let last = 0;
  for (const match of text.matchAll(/<(\w+)>(.*?)<\/\1>/g)) {
    if (match.index > last) parts.push(text.slice(last, match.index));
    const render = tags[match[1]];
    parts.push(<Fragment key={match.index}>{render ? render(match[2]) : match[2]}</Fragment>);
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

async function loadMessages(code) {
  if (code === SOURCE_LANGUAGE) return null;
  return (await LOADERS[code]()).default;
}

// Outside a provider (most component tests) everything reads in English.
const I18nContext = createContext({
  language: SOURCE_LANGUAGE,
  setLanguage: () => {},
  t: (text, vars) => translate(null, text, vars),
});

export function I18nProvider({ children, initial = initialLanguage }) {
  const [state, setState] = useState(() => {
    const language = typeof initial === "function" ? initial() : initial;
    return { language, messages: null, ready: language === SOURCE_LANGUAGE };
  });
  const latest = useRef(state.language);

  // Only a user's choice is saved: a language guessed from the browser is
  // guessed again next time, so a changed browser language still counts.
  const apply = useCallback(async (code, { save }) => {
    if (!isAppLanguage(code)) return;
    latest.current = code;
    if (save) saveLanguage(code);
    let messages = null;
    try {
      messages = await loadMessages(code);
    } catch {
      // The chunk failed to load (offline, stale deploy): stay readable in
      // English rather than leave the app blank.
      messages = null;
    }
    // A later choice made while this one was loading wins.
    if (latest.current === code) setState({ language: code, messages, ready: true });
  }, []);
  const setLanguage = useCallback((code) => apply(code, { save: true }), [apply]);

  useEffect(() => {
    if (!state.ready) apply(state.language, { save: false });
    // Only the first render can be not-ready.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    document.documentElement.lang = state.language;
  }, [state.language]);

  const value = useMemo(() => ({
    language: state.language,
    setLanguage,
    t: (text, vars) => translate(state.messages, text, vars),
  }), [state.language, state.messages, setLanguage]);

  // Hold the first paint until the dictionary is in, so a Czech user never
  // sees a flash of English. It is one small chunk.
  if (!state.ready) return null;
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}

// The translate function: t(englishText, { name: value }).
export function useT() {
  return useContext(I18nContext).t;
}
