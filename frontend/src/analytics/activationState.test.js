import { describe, it, expect, afterEach, vi } from "vitest";
import { readActivationState, writeActivationState } from "./activationState";

const EMPTY = { sourceType: null, dataImported: false, dashboardRendered: false, activated: false };

afterEach(() => localStorage.clear());

describe("activationState", () => {
  it("returns empty state for an identity that has never been written", () => {
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(EMPTY);
    expect(readActivationState("u1", "w1", { persist: false })).toEqual(EMPTY);
  });

  it("round-trips accepted (persisted) state through localStorage under the versioned key", () => {
    const state = { sourceType: "csv", dataImported: true, dashboardRendered: false, activated: false };
    writeActivationState("u1", "w1", state, { persist: true });

    expect(localStorage.getItem("portfyl_activation_v1:u1:w1")).toBe(JSON.stringify(state));
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(state);
  });

  it("recovers to empty state from corrupted JSON in localStorage", () => {
    localStorage.setItem("portfyl_activation_v1:u1:w1", "{not json");
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(EMPTY);
  });

  it("recovers to empty state from a validly-parsed but wrong-shaped value", () => {
    localStorage.setItem("portfyl_activation_v1:u1:w1", JSON.stringify({ dataImported: true }));
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(EMPTY);
  });

  it("rejects an out-of-enum sourceType as corrupted state", () => {
    localStorage.setItem(
      "portfyl_activation_v1:u1:w1",
      JSON.stringify({ sourceType: "not-a-real-source", dataImported: true, dashboardRendered: false, activated: false })
    );
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(EMPTY);
  });

  it.each(["demo", "csv", "broker"])("accepts %s as a valid stored sourceType", (sourceType) => {
    const state = { sourceType, dataImported: true, dashboardRendered: true, activated: true };
    writeActivationState("u1", "w1", state, { persist: true });
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(state);
  });

  it("keeps each workspace's state isolated under the same user", () => {
    writeActivationState("u1", "w1", { sourceType: "csv", dataImported: true, dashboardRendered: false, activated: false }, { persist: true });
    writeActivationState("u1", "w2", { sourceType: "demo", dataImported: true, dashboardRendered: true, activated: true }, { persist: true });

    expect(readActivationState("u1", "w1", { persist: true }).sourceType).toBe("csv");
    expect(readActivationState("u1", "w2", { persist: true }).sourceType).toBe("demo");
  });

  it("keeps each user's state isolated under the same workspace id", () => {
    writeActivationState("u1", "w1", { sourceType: "csv", dataImported: true, dashboardRendered: false, activated: false }, { persist: true });
    writeActivationState("u2", "w1", { sourceType: null, dataImported: false, dashboardRendered: false, activated: false }, { persist: true });

    expect(readActivationState("u1", "w1", { persist: true }).dataImported).toBe(true);
    expect(readActivationState("u2", "w1", { persist: true }).dataImported).toBe(false);
  });

  it("persists accepted state across repeated reads, simulating survival across an analytics identity reset", () => {
    const state = { sourceType: "broker", dataImported: true, dashboardRendered: true, activated: true };
    writeActivationState("u1", "w1", state, { persist: true });

    // A reset() call on the analytics adapter clears adapter-side identity only;
    // this module's storage key is keyed by user/workspace id, not by adapter
    // state, so re-reading with the same ids must still see the prior write.
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(state);
    expect(readActivationState("u1", "w1", { persist: true })).toEqual(state);
  });

  it("keeps rejected (in-memory) state readable within the same session, scoped like persisted state", () => {
    const state = { sourceType: "csv", dataImported: true, dashboardRendered: false, activated: false };
    writeActivationState("u3", "w3", state, { persist: false });
    expect(readActivationState("u3", "w3", { persist: false })).toEqual(state);
    // A different, never-persisted workspace must not see it.
    expect(readActivationState("u3", "w4", { persist: false })).toEqual(EMPTY);
  });

  it("never writes to localStorage in rejected (in-memory) mode", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    writeActivationState("u5", "w5", { sourceType: "demo", dataImported: true, dashboardRendered: true, activated: true }, { persist: false });
    expect(setItemSpy).not.toHaveBeenCalled();
    expect(localStorage.getItem("portfyl_activation_v1:u5:w5")).toBeNull();
    setItemSpy.mockRestore();
  });

  it("in-memory (rejected) state is never visible through the persisted (accepted) reader for the same ids", () => {
    writeActivationState("u6", "w6", { sourceType: "csv", dataImported: true, dashboardRendered: true, activated: true }, { persist: false });
    expect(readActivationState("u6", "w6", { persist: true })).toEqual(EMPTY);
  });
});
