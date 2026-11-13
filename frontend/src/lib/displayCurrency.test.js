import { describe, expect, it, afterEach } from "vitest";

import { APP_LANGUAGES } from "../i18n/languages";
import {
  DISPLAY_CURRENCIES,
  convertFromUsd,
  currencyChoicesForLanguage,
  initialDisplayCurrency,
  localCurrencyForLanguage,
} from "./displayCurrency";
import { formatCompact, formatMoney } from "./format";

describe("displayCurrency", () => {
  afterEach(() => localStorage.clear());

  it("maps every app language to a display currency", () => {
    for (const { code } of APP_LANGUAGES) {
      expect(DISPLAY_CURRENCIES).toContain(localCurrencyForLanguage(code));
    }
    expect(localCurrencyForLanguage("cs")).toBe("CZK");
    expect(localCurrencyForLanguage("de")).toBe("EUR");
    expect(localCurrencyForLanguage("pl")).toBe("PLN");
    expect(localCurrencyForLanguage("en")).toBe("USD");
    expect(localCurrencyForLanguage("xx")).toBe("USD");
  });

  it("offers USD plus the local currency", () => {
    expect(currencyChoicesForLanguage("cs")).toEqual(["USD", "CZK"]);
    expect(currencyChoicesForLanguage("fr")).toEqual(["USD", "EUR"]);
    expect(currencyChoicesForLanguage("en")).toEqual(["USD"]);
  });

  it("starts from the saved currency, else the language's local one", () => {
    expect(initialDisplayCurrency("de")).toBe("EUR");
    localStorage.setItem("sb_currency", "CZK");
    expect(initialDisplayCurrency("de")).toBe("CZK");
    localStorage.setItem("sb_currency", "XYZ");
    expect(initialDisplayCurrency("pl")).toBe("PLN");
  });

  it("converts USD amounts only for a non-USD currency with a rate", () => {
    expect(convertFromUsd(10, "USD", 1)).toBe(10);
    expect(convertFromUsd(10, "EUR", 0.9)).toBe(9);
    expect(convertFromUsd(10, "PLN", null)).toBe(10);
  });

  it("formats PLN with the Polish locale", () => {
    expect(formatMoney(12345.5, "PLN").replace(/\s/g, " ")).toBe("12 345,50 zł");
    expect(formatCompact(1500, "PLN")).toBe("1,5K zł");
  });
});
