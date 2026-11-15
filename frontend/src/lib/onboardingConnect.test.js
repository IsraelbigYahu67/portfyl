import {
  CONNECT_STEP_KEY,
  CONNECT_STEP_TTL_MS,
  apiErrorCode,
  clearConnectStep,
  connectStepBroker,
  isPlanUpgradeRequired,
  readCheckoutReturn,
  rememberConnectStep,
  syncImportedData,
} from "./onboardingConnect";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("connect-step marker", () => {
  it("remembers an API broker and reads it back", () => {
    rememberConnectStep("ibkr", 1000);
    expect(JSON.parse(localStorage.getItem(CONNECT_STEP_KEY))).toEqual({ broker: "ibkr", at: 1000 });
    expect(connectStepBroker(2000)).toBe("ibkr");
    clearConnectStep();
    expect(connectStepBroker(2000)).toBeNull();
  });

  it("ignores a file-only broker", () => {
    rememberConnectStep("xtb");
    expect(localStorage.getItem(CONNECT_STEP_KEY)).toBeNull();
    expect(connectStepBroker()).toBeNull();
  });

  it("expires the marker after 24 h", () => {
    expect(CONNECT_STEP_TTL_MS).toBe(86_400_000);
    rememberConnectStep("trading212", 0);
    expect(connectStepBroker(CONNECT_STEP_TTL_MS)).toBe("trading212");
    expect(connectStepBroker(CONNECT_STEP_TTL_MS + 1)).toBeNull();
    expect(localStorage.getItem(CONNECT_STEP_KEY)).toBeNull();
  });

  it("drops an unparseable marker", () => {
    localStorage.setItem(CONNECT_STEP_KEY, "{not json");
    expect(connectStepBroker()).toBeNull();
    expect(localStorage.getItem(CONNECT_STEP_KEY)).toBeNull();
    localStorage.setItem(CONNECT_STEP_KEY, JSON.stringify({ broker: "xtb", at: Date.now() }));
    expect(connectStepBroker()).toBeNull();
    expect(localStorage.getItem(CONNECT_STEP_KEY)).toBeNull();
  });

  it("survives unavailable storage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("denied"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    expect(() => rememberConnectStep("ibkr")).not.toThrow();
    expect(connectStepBroker()).toBeNull();
  });
});

describe("readCheckoutReturn", () => {
  it("reads a success and a canceled checkout return", () => {
    expect(readCheckoutReturn(new URLSearchParams("?checkout=success&session_id=cs_1")))
      .toEqual({ outcome: "success", sessionId: "cs_1" });
    expect(readCheckoutReturn(new URLSearchParams("?checkout=canceled")))
      .toEqual({ outcome: "canceled", sessionId: null });
  });

  it("ignores unknown checkout values", () => {
    expect(readCheckoutReturn(new URLSearchParams("?checkout=weird"))).toBeNull();
    expect(readCheckoutReturn(new URLSearchParams(""))).toBeNull();
  });
});

describe("error helpers", () => {
  it("recognizes the flat entitlement 403", () => {
    expect(isPlanUpgradeRequired({ response: { status: 403, data: { code: "plan_upgrade_required" } } })).toBe(true);
    expect(isPlanUpgradeRequired({
      response: { status: 403, data: { detail: { code: "plan_upgrade_required" } } },
    })).toBe(false);
    expect(isPlanUpgradeRequired({ response: { status: 402, data: { code: "plan_upgrade_required" } } })).toBe(false);
    expect(isPlanUpgradeRequired(null)).toBe(false);
  });

  it("reads a billing detail code", () => {
    expect(apiErrorCode({ response: { data: { detail: { code: "workspace_owner_required" } } } }))
      .toBe("workspace_owner_required");
    expect(apiErrorCode({ response: { data: { detail: "text" } } })).toBeNull();
    expect(apiErrorCode(undefined)).toBeNull();
  });
});

describe("syncImportedData", () => {
  it("tells whether the first sync imported data", () => {
    expect(syncImportedData("trading212", { snapshot: { positions: 2 } })).toBe(true);
    expect(syncImportedData("trading212", { snapshot: { positions: 0 } })).toBe(false);
    expect(syncImportedData("ibkr", { ledger: { imported: 3 } })).toBe(true);
    expect(syncImportedData("ibkr", { ledger: { imported: 0 } })).toBe(false);
    expect(syncImportedData("etoro", { imported: 1 })).toBe(true);
    expect(syncImportedData("etoro", { imported: 0 })).toBe(false);
    expect(syncImportedData("trading212", {})).toBe(false);
    expect(syncImportedData("ibkr", {})).toBe(false);
    expect(syncImportedData("etoro", {})).toBe(false);
    expect(syncImportedData("etoro", undefined)).toBe(false);
  });
});
