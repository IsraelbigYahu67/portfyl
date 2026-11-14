import { describe, expect, it } from "vitest";
import { ANALYTICS_EVENTS, sanitizeEvent } from "./eventContract";
import { SUPPORTED_BROKERS } from "../lib/onboardingBrokers";
import eventContractSource from "./eventContract.js?raw";

const validEvents = [
  ["landing_viewed", { language: " en ", referrer_class: "search", utm_source: "newsletter", utm_medium: "email", utm_campaign: "launch" }],
  ["demo_started", { language: "cs", entry_point: "landing_hero" }],
  ["demo_page_viewed", { demo_page: "overview", language: "de" }],
  ["demo_stock_viewed", { demo_symbol: "MSFT" }],
  ["demo_activation_reached", { activation_path: "three_pages", distinct_demo_pages: 3 }],
  ["signup_cta_clicked", { source_surface: "demo", language: "en" }],
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
    for (const step of ["broker", "choices", "unsupported"]) {
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
    expect(sanitizeEvent("demo_started", { language: "  en  ", entry_point: "direct" }, { strict: true }))
      .toEqual({ name: "demo_started", properties: { language: "en", entry_point: "direct" } });
    expect(() => sanitizeEvent("landing_viewed", { language: "en", referrer_class: "direct", utm_source: "x".repeat(121) }, { strict: true })).toThrow(/utm_source/i);
    expect(() => sanitizeEvent("demo_started", { language: "en", entry_point: "x".repeat(81) }, { strict: true })).toThrow(/entry_point/i);
  });

  it.each([
    ["source_type", "invalid"],
    ["creation_path", "invalid"],
    ["source_surface", "invalid"],
    ["auth_method", "github"],
    ["entry_point", "invalid"],
    ["demo_page", "invalid"],
    ["activation_path", "invalid"],
    ["language", "fr"],
    ["distinct_demo_pages", 1],
    ["distinct_demo_pages", 6],
  ])("rejects invalid enum value %s=%j", (property, value) => {
    const properties = property === "distinct_demo_pages"
      ? { activation_path: "three_pages", distinct_demo_pages: value }
      : property === "source_type"
        ? { source_type: value }
        : property === "creation_path"
          ? { creation_path: value }
          : property === "source_surface"
            ? { source_surface: value, auth_method: "password" }
            : property === "auth_method"
            ? { source_surface: "direct", auth_method: value }
            : property === "entry_point"
              ? { language: "en", entry_point: value }
              : property === "demo_page"
                ? { demo_page: value, language: "en" }
                : property === "activation_path"
                  ? { activation_path: value, distinct_demo_pages: 3 }
                  : { language: value, entry_point: "direct" };
    const event = property === "source_type"
      ? "portfolio_data_imported"
      : property === "creation_path"
        ? "portfolio_created"
        : property === "source_surface" || property === "auth_method"
          ? "signup_completed"
          : property === "demo_page"
            ? "demo_page_viewed"
            : property === "activation_path" || property === "distinct_demo_pages"
              ? "demo_activation_reached"
              : "demo_started";
    expect(() => sanitizeEvent(event, properties, { strict: true })).toThrow();
    expect(sanitizeEvent(event, properties, { strict: false })).toBeNull();
  });

  it("rejects unknown fields and unsafe values in strict mode", () => {
    expect(() => sanitizeEvent("unknown", {}, { strict: true })).toThrow(/event/i);
    expect(() => sanitizeEvent("demo_started", { language: "en", entry_point: "direct", extra: "no" }, { strict: true })).toThrow(/extra/i);
    expect(() => sanitizeEvent("demo_started", { language: ["en"], entry_point: "direct" }, { strict: true })).toThrow(/language/i);
    expect(() => sanitizeEvent("demo_activation_reached", { activation_path: "three_pages", distinct_demo_pages: Number.NaN }, { strict: true })).toThrow(/distinct_demo_pages/i);
    expect(() => sanitizeEvent("demo_activation_reached", { activation_path: "three_pages", distinct_demo_pages: Infinity }, { strict: true })).toThrow(/distinct_demo_pages/i);
    expect(() => sanitizeEvent("demo_started", { language: { value: "en" }, entry_point: "direct" }, { strict: true })).toThrow(/language/i);
  });

  it("drops invalid events in non-strict mode and preserves valid fields", () => {
    expect(sanitizeEvent("unknown", {}, { strict: false })).toBeNull();
    expect(sanitizeEvent("demo_started", { language: "en", entry_point: "direct", extra: "removed" }, { strict: false }))
      .toEqual({ name: "demo_started", properties: { language: "en", entry_point: "direct" } });
    expect(sanitizeEvent("demo_started", { language: "en", entry_point: ["direct"] }, { strict: false })).toBeNull();
  });

  it("keeps forbidden data-category words out of the contract source", () => {
    expect(eventContractSource).not.toMatch(/\b(email|display_name|workspace_name|portfolio_id|balance|amount|holdings|transactions)\b/i);
  });
});
