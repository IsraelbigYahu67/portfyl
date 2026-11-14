import { afterEach, describe, expect, it, vi } from "vitest";

import {
  GETTING_STARTED_IDS,
  dismissGettingStarted,
  gettingStartedItems,
  markGettingStartedVisited,
  readGettingStarted,
} from "./gettingStarted";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

const byId = (items, id) => items.find((item) => item.id === id);

describe("gettingStartedItems", () => {
  it("lists the four items in order with their destinations", () => {
    const items = gettingStartedItems({ portfolios: [], preferencesConfirmed: false, visited: [] });
    expect(items.map((item) => item.id)).toEqual(GETTING_STARTED_IDS);
    expect(items.map((item) => item.to)).toEqual(["/import", "/import", "/settings?section=preferences", "/dividends"]);
    expect(items.every((item) => item.done === false)).toBe(true);
  });

  it("does not count a demo-only portfolio as the first portfolio", () => {
    const items = gettingStartedItems({
      portfolios: [{ brokers: ["demo"] }],
      preferencesConfirmed: false,
      visited: [],
    });
    expect(byId(items, "first_portfolio").done).toBe(false);
    expect(byId(items, "second_broker").done).toBe(false);
  });

  it("marks the first portfolio done once a real broker is present", () => {
    const items = gettingStartedItems({
      portfolios: [{ brokers: ["demo", "xtb"] }],
      preferencesConfirmed: false,
      visited: [],
    });
    expect(byId(items, "first_portfolio").done).toBe(true);
    expect(byId(items, "second_broker").done).toBe(false);
  });

  it("marks the second broker done with two distinct real brokers across portfolios", () => {
    const items = gettingStartedItems({
      portfolios: [{ brokers: ["xtb"] }, { brokers: ["degiro"] }],
      preferencesConfirmed: false,
      visited: [],
    });
    expect(byId(items, "second_broker").done).toBe(true);
  });

  it("does not count the same broker twice, and tolerates portfolios without brokers", () => {
    const items = gettingStartedItems({
      portfolios: [{ brokers: ["xtb"] }, { brokers: ["xtb"] }, {}],
      preferencesConfirmed: false,
      visited: [],
    });
    expect(byId(items, "second_broker").done).toBe(false);
  });

  it("follows the preferences confirmation and the dividends visit", () => {
    const items = gettingStartedItems({ portfolios: [], preferencesConfirmed: true, visited: ["dividends"] });
    expect(byId(items, "preferences").done).toBe(true);
    expect(byId(items, "dividends").done).toBe(true);
  });
});

describe("getting started storage", () => {
  it("reads defaults when nothing is stored", () => {
    expect(readGettingStarted("ws-1")).toEqual({ dismissed: false, visited: [] });
  });

  it("stores visits and the dismissal per workspace under a portfyl_ key", () => {
    markGettingStartedVisited("ws-1", "dividends");
    markGettingStartedVisited("ws-1", "dividends");
    dismissGettingStarted("ws-2");
    expect(readGettingStarted("ws-1")).toEqual({ dismissed: false, visited: ["dividends"] });
    expect(readGettingStarted("ws-2")).toEqual({ dismissed: true, visited: [] });
    expect(localStorage.getItem("portfyl_getting_started:ws-1")).toContain("dividends");
  });

  it("keeps earlier visits when the panel is dismissed afterwards", () => {
    markGettingStartedVisited("ws-1", "dividends");
    dismissGettingStarted("ws-1");
    expect(readGettingStarted("ws-1")).toEqual({ dismissed: true, visited: ["dividends"] });
  });

  it("falls back to defaults for malformed stored JSON", () => {
    localStorage.setItem("portfyl_getting_started:ws-1", "{not json");
    expect(readGettingStarted("ws-1")).toEqual({ dismissed: false, visited: [] });
    localStorage.setItem("portfyl_getting_started:ws-1", JSON.stringify({ dismissed: "yes", visited: "x" }));
    expect(readGettingStarted("ws-1")).toEqual({ dismissed: false, visited: [] });
  });

  it("keeps working when the workspace is not known yet", () => {
    expect(readGettingStarted(undefined)).toEqual({ dismissed: false, visited: [] });
    expect(() => markGettingStartedVisited(undefined, "dividends")).not.toThrow();
    expect(() => dismissGettingStarted(null)).not.toThrow();
  });

  it("never throws when storage is unavailable", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readGettingStarted("ws-1")).toEqual({ dismissed: false, visited: [] });
    expect(() => markGettingStartedVisited("ws-1", "dividends")).not.toThrow();
    expect(() => dismissGettingStarted("ws-1")).not.toThrow();
  });
});
