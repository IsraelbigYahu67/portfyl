import { describe, expect, it } from "vitest";

import { APP_LANGUAGES, SOURCE_LANGUAGE } from "./languages";

// Every English string the app translates is written as a literal in a
// t("...") or msg("...") call. This collects them from the source and checks
// that each dictionary translates exactly that set: nothing missing (it would
// show in English), nothing stale (text that was reworded in the code).
const SOURCES = import.meta.glob(["../**/*.{js,jsx}", "!../**/*.test.{js,jsx}", "!../test/**", "!./messages/**"], {
  query: "?raw",
  import: "default",
  eager: true,
});
const DICTIONARIES = import.meta.glob("./messages/*.js", { import: "default", eager: true });

const CALL = /(?<![\w$.])(?:t|msg)\(\s*"((?:[^"\\\n]|\\.)*)"/g;

function sourceKeys() {
  const keys = new Map();
  for (const [file, text] of Object.entries(SOURCES)) {
    for (const match of text.matchAll(CALL)) {
      const key = JSON.parse(`"${match[1]}"`);
      if (!keys.has(key)) keys.set(key, file);
    }
  }
  return keys;
}

// The {placeholders} and <tags> a translation must keep from the English.
const placeholders = (text) => [...text.matchAll(/\{(\w+)\}|<(\w+)>/g)].map((match) => match[1] ?? `<${match[2]}>`).sort();

const KEYS = sourceKeys();
const TRANSLATED = APP_LANGUAGES.filter(({ code }) => code !== SOURCE_LANGUAGE);

describe("translation dictionaries", () => {
  it("finds the translatable strings", () => {
    expect(KEYS.size).toBeGreaterThan(0);
  });

  it("has a dictionary for every language except the English source", () => {
    expect(Object.keys(DICTIONARIES).map((path) => path.match(/(\w+)\.js$/)[1]).sort())
      .toEqual(TRANSLATED.map(({ code }) => code).sort());
  });

  describe.each(TRANSLATED.map(({ code }) => code))("%s", (code) => {
    const dictionary = DICTIONARIES[`./messages/${code}.js`];

    it("translates every string in the code", () => {
      const missing = [...KEYS].filter(([key]) => !dictionary[key]?.trim()).map(([key, file]) => `${file}: ${key}`);
      expect(missing).toEqual([]);
    });

    it("has no strings the code no longer uses", () => {
      expect(Object.keys(dictionary).filter((key) => !KEYS.has(key))).toEqual([]);
    });

    it("keeps every {placeholder} and <tag>", () => {
      const broken = Object.entries(dictionary)
        .filter(([key, value]) => placeholders(key).join() !== placeholders(value).join())
        .map(([key]) => key);
      expect(broken).toEqual([]);
    });
  });
});
