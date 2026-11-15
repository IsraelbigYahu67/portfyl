import { describe, expect, it } from "vitest";
import {
  BROKER_ORDER_BY_LANGUAGE,
  SUPPORTED_BROKERS,
  brokersForLanguage,
  filterBrokers,
} from "./onboardingBrokers";

const keys = (brokers) => brokers.map((broker) => broker.key);
const EN = ["trading212", "ibkr", "etoro", "degiro", "xtb"];
const EU = ["trading212", "degiro", "ibkr", "xtb", "etoro"];

describe("brokersForLanguage", () => {
  it("orders brokers per language", () => {
    expect(keys(brokersForLanguage("cs"))).toEqual(["trading212", "xtb", "degiro", "ibkr", "etoro"]);
    expect(keys(brokersForLanguage("pl"))).toEqual(["xtb", "trading212", "degiro", "ibkr", "etoro"]);
    for (const language of ["de", "fr", "es", "it", "pt", "nl"]) {
      expect(keys(brokersForLanguage(language))).toEqual(EU);
    }
    expect(keys(brokersForLanguage("en"))).toEqual(EN);
  });

  it("falls back to the English order for an unknown language", () => {
    expect(keys(brokersForLanguage("xx"))).toEqual(EN);
    expect(keys(brokersForLanguage(undefined))).toEqual(EN);
  });

  it("covers every supported broker exactly once in every order", () => {
    const all = SUPPORTED_BROKERS.map((broker) => broker.key).sort();
    for (const language of Object.keys(BROKER_ORDER_BY_LANGUAGE)) {
      expect([...BROKER_ORDER_BY_LANGUAGE[language]].sort()).toEqual(all);
    }
  });

  it("is frozen", () => {
    expect(Object.isFrozen(BROKER_ORDER_BY_LANGUAGE)).toBe(true);
    expect(Object.isFrozen(BROKER_ORDER_BY_LANGUAGE.cs)).toBe(true);
  });
});

describe("filterBrokers", () => {
  it("defaults to the English order", () => {
    expect(keys(filterBrokers("").supported)).toEqual(EN);
  });

  it("follows the language order", () => {
    expect(filterBrokers("", "pl").supported[0].key).toBe("xtb");
  });

  it("filters by name within the language order", () => {
    expect(keys(filterBrokers("deg", "cs").supported)).toEqual(["degiro"]);
    expect(keys(filterBrokers("de", "cs").supported)).toEqual(["degiro"]);
  });

  it("still filters unsupported brokers", () => {
    expect(filterBrokers("revo").unsupported).toEqual(["Revolut"]);
  });

  it("lists the US-only brokers as unsupported", () => {
    expect(filterBrokers("schwab")).toEqual({ supported: [], unsupported: ["Charles Schwab"] });
    expect(filterBrokers("fidelity")).toEqual({ supported: [], unsupported: ["Fidelity"] });
  });
});
