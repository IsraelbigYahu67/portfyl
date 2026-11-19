import { describe, expect, it } from "vitest";
import { ANALYTICS_EVENTS, sanitizeEvent } from "./eventContract";
import { SUPPORTED_BROKERS } from "../lib/onboardingBrokers";
import eventContractSource from "./eventContract.js?raw";

const validEvents = [
  ["landing_viewed", { language: " en ", referrer_class: "search", utm_source: "newsletter", utm_medium: "email", utm_campaign: "launch" }],
  ["landing_minidemo_used", { minidemo: "stock", language: "de" }],
  ["signup_cta_clicked", { source_surface: "landing_hero", language: "en" }],
  ["signup_started", { source_surface: "direct", language: "cs" }],
  ["signup_completed", { source_surface: "landing_closing", auth_method: "google" }],
  ["portfolio_created", { creation_path: "blank" }],
  ["portfolio_data_imported", { source_type: "csv" }],
  ["dashboard_first_value_rendered", { source_type: "broker" }],
  ["user_activation_reached", { source_type: "demo" }],
  ["onboarding_step_viewed", { step: "broker" }],
  ["onboarding_broker_picked", { broker_key: "xtb" }],
  ["broker_check_used", { result: "supported", language: "cs" }],
  ["broker_request_sent", {}],
];

describe("activation event contract", () => {
  it("exposes exactly the approved event names", () => {
    expect(Object.values(ANALYTICS_EVENTS)).toEqual(validEvents.map(([name]) => name));
    expect(Object.isFrozen(ANALYTICS_EVENTS)).toBe(true);
  });

  it.each(validEvents)("sanitizes the approved %s payload", (name, properties) => {
    expect(sanitizeEvent(name, properties, { strict: true })).toEqual({
      name,
      properties: { ...properties, ...(name === "landing_viewed" ? { language: "en" } : {}) },
    });
  });

  it("accepts every supported broker key, the unsupported marker and each onboarding step", () => {
    for (const broker of SUPPORTED_BROKERS) {
      expect(sanitizeEvent("onboarding_broker_picked", { broker_key: broker.key }, { strict: true }).properties).toEqual({ broker_key: broker.key });
    }
    expect(sanitizeEvent("onboarding_broker_picked", { broker_key: "unsupported" }, { strict: true }).properties).toEqual({ broker_key: "unsupported" });
    for (const step of ["broker", "choices", "connect", "unsupported"]) {
      expect(sanitizeEvent("onboarding_step_viewed", { step }, { strict: true }).properties).toEqual({ step });
    }
    expect(sanitizeEvent("broker_check_used", { result: "unsupported", language: "de" }, { strict: true }).properties).toEqual({ result: "unsupported", language: "de" });
    expect(sanitizeEvent("signup_started", { source_surface: "landing_broker_check", language: "cs" }, { strict: true }).properties.source_surface).toBe("landing_broker_check");
  });

  it("rejects typed broker names, unknown steps and results, and any property on broker_request_sent", () => {
    expect(() => sanitizeEvent("onboarding_broker_picked", { broker_key: "Revolut" }, { strict: true })).toThrow(/broker_key/);
    expect(sanitizeEvent("onboarding_broker_picked", { broker_key: "Revolut" }, { strict: false })).toBeNull();
    expect(() => sanitizeEvent("onboarding_step_viewed", { step: "language" }, { strict: true })).toThrow(/step/);
    expect(sanitizeEvent("onboarding_step_viewed", { step: "language" }, { strict: false })).toBeNull();
    expect(() => sanitizeEvent("broker_check_used", { result: "maybe", language: "cs" }, { strict: true })).toThrow(/result/);
    expect(() => sanitizeEvent("broker_check_used", { result: "supported", language: "fr" }, { strict: true })).toThrow(/language/);
    expect(() => sanitizeEvent("broker_request_sent", { broker_name: "Revolut" }, { strict: true })).toThrow(/broker_name/);
  });

  it("trims allowed strings and caps UTM values separately", () => {
    expect(sanitizeEvent("broker_check_used", { result: "supported", language: "  en  " }, { strict: true }))
      .toEqual({ name: "broker_check_used", properties: { result: "supported", language: "en" } });
    expect(() => sanitizeEvent("landing_viewed", { language: "en", referrer_class: "direct", utm_source: "x".repeat(121) }, { strict: true })).toThrow(/utm_source/i);
    expect(() => sanitizeEvent("landing_viewed", { language: "en", referrer_class: "direct", utm_source: "x".repeat(81), utm_medium: "x".repeat(121), utm_campaign: "c" }, { strict: true })).toThrow(/utm_medium/i);
  });

  it.each([
    ["portfolio_data_imported", { source_type: "invalid" }, "source_type"],
    ["portfolio_created", { creation_path: "invalid" }, "creation_path"],
    ["signup_completed", { source_surface: "invalid", auth_method: "password" }, "source_surface"],
    ["signup_completed", { source_surface: "direct", auth_method: "github" }, "auth_method"],
    ["broker_check_used", { result: "supported", language: "fr" }, "language"],
  ])("rejects invalid enum value for %s %j", (event, properties, property) => {
    expect(() => sanitizeEvent(event, properties, { strict: true })).toThrow(new RegExp(property));
    expect(sanitizeEvent(event, properties, { strict: false })).toBeNull();
  });
  it("accepts landing_minidemo_used for each of the five mini demos and rejects anything else", () => {
    for (const minidemo of ["allocation", "stock", "performance", "dividends", "portfolios"]) {
      expect(sanitizeEvent("landing_minidemo_used", { minidemo, language: "cs" }, { strict: true }).properties).toEqual({ minidemo, language: "cs" });
    }
    expect(() => sanitizeEvent("landing_minidemo_used", { minidemo: "overview", language: "cs" }, { strict: true })).toThrow(/minidemo/);
    expect(sanitizeEvent("landing_minidemo_used", { minidemo: "overview", language: "cs" }, { strict: false })).toBeNull();
    expect(() => sanitizeEvent("landing_minidemo_used", { minidemo: "stock" }, { strict: true })).toThrow(/language/);
    expect(sanitizeEvent("landing_minidemo_used", { minidemo: "stock" }, { strict: false })).toBeNull();
    expect(() => sanitizeEvent("landing_minidemo_used", { minidemo: "stock", language: "fr" }, { strict: true })).toThrow(/language/);
    expect(() => sanitizeEvent("landing_minidemo_used", { minidemo: "stock", language: "en", symbol: "MSFT" }, { strict: true })).toThrow(/symbol/);
  });

  it("rejects unknown fields and unsafe values in strict mode", () => {
    expect(() => sanitizeEvent("unknown", {}, { strict: true })).toThrow(/event/i);
    expect(() => sanitizeEvent("broker_check_used", { result: "supported", language: "en", extra: "no" }, { strict: true })).toThrow(/extra/i);
    expect(() => sanitizeEvent("broker_check_used", { result: "supported", language: ["en"] }, { strict: true })).toThrow(/language/i);
    expect(() => sanitizeEvent("broker_check_used", { result: "supported", language: { value: "en" } }, { strict: true })).toThrow(/language/i);
  });

  it("drops invalid events in non-strict mode and preserves valid fields", () => {
    expect(sanitizeEvent("unknown", {}, { strict: false })).toBeNull();
    expect(sanitizeEvent("broker_check_used", { result: "supported", language: "en", extra: "removed" }, { strict: false }))
      .toEqual({ name: "broker_check_used", properties: { result: "supported", language: "en" } });
    expect(sanitizeEvent("broker_check_used", { result: ["supported"], language: "en" }, { strict: false })).toBeNull();
  });

  describe("the retired public /demo", () => {
    it.each([
      ["demo_started", { language: "cs", entry_point: "landing_hero" }],
      ["demo_page_viewed", { demo_page: "overview", language: "de" }],
      ["demo_stock_viewed", { demo_symbol: "MSFT" }],
      ["demo_activation_reached", { activation_path: "three_pages", distinct_demo_pages: 3 }],
    ])("treats %s as an unknown event", (name, properties) => {
      expect(Object.values(ANALYTICS_EVENTS)).not.toContain(name);
      expect(() => sanitizeEvent(name, properties, { strict: true })).toThrow(/Unknown analytics event/);
      expect(sanitizeEvent(name, properties, { strict: false })).toBeNull();
    });

    it("no longer accepts source_surface=demo on the signup events", () => {
      for (const name of ["signup_cta_clicked", "signup_started"]) {
        expect(() => sanitizeEvent(name, { source_surface: "demo", language: "en" }, { strict: true })).toThrow(/source_surface/);
        expect(sanitizeEvent(name, { source_surface: "demo", language: "en" }, { strict: false })).toBeNull();
      }
      expect(() => sanitizeEvent("signup_completed", { source_surface: "demo", auth_method: "google" }, { strict: true })).toThrow(/source_surface/);
    });

    it("has dropped the demo-only properties from the contract source", () => {
      for (const property of ["entry_point", "demo_page", "demo_symbol", "activation_path", "distinct_demo_pages", "DEMO_STARTED", "DEMO_PAGE_VIEWED", "DEMO_STOCK_VIEWED", "DEMO_ACTIVATION_REACHED"]) {
        expect(eventContractSource, property).not.toContain(property);
      }
    });

    // The onboarding sample portfolio (POST /portfolios/demo) is a different
    // thing and keeps its values.
    it("still accepts the onboarding sample portfolio values", () => {
      expect(sanitizeEvent("portfolio_created", { creation_path: "demo" }, { strict: true }).properties).toEqual({ creation_path: "demo" });
      for (const name of ["portfolio_data_imported", "dashboard_first_value_rendered", "user_activation_reached"]) {
        expect(sanitizeEvent(name, { source_type: "demo" }, { strict: true }).properties).toEqual({ source_type: "demo" });
      }
    });
  });

  it("keeps forbidden data-category words out of the contract source", () => {
    expect(eventContractSource).not.toMatch(/\b(email|display_name|workspace_name|portfolio_id|balance|amount|holdings|transactions)\b/i);
  });
});
