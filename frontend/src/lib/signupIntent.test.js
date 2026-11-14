import {
  INTENDED_BROKER_KEY,
  clearIntendedBroker,
  intendedBroker,
  readSignupIntent,
  registerUrl,
  rememberIntendedBroker,
} from "./signupIntent";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("signupIntent", () => {
  it("builds the register URL with only valid params", () => {
    expect(registerUrl({ origin: "https://app.test", source: "demo", broker: "xtb", lang: "cs" }))
      .toBe("https://app.test/register?source=demo&broker=xtb&lang=cs");
    expect(registerUrl({ origin: "https://app.test", broker: "robinhood", lang: "xx" }))
      .toBe("https://app.test/register");
  });

  it("passes a non-empty source through and encodes it", () => {
    expect(registerUrl({ origin: "https://app.test", source: "landing hero" }))
      .toBe("https://app.test/register?source=landing+hero");
    expect(registerUrl({ origin: "https://app.test", source: "" })).toBe("https://app.test/register");
  });

  it("reads only supported brokers and app languages", () => {
    expect(readSignupIntent(new URLSearchParams("broker=degiro&lang=de"))).toEqual({ broker: "degiro", lang: "de" });
    expect(readSignupIntent(new URLSearchParams("broker=<x>&lang=klingon"))).toEqual({ broker: null, lang: null });
    expect(readSignupIntent(new URLSearchParams(""))).toEqual({ broker: null, lang: null });
  });

  it("remembers, re-validates and clears the intended broker", () => {
    rememberIntendedBroker("xtb");
    expect(intendedBroker()).toBe("xtb");
    localStorage.setItem(INTENDED_BROKER_KEY, "robinhood");
    expect(intendedBroker()).toBeNull();
    rememberIntendedBroker("ibkr");
    clearIntendedBroker();
    expect(intendedBroker()).toBeNull();
  });

  it("ignores an unsupported broker key when remembering", () => {
    rememberIntendedBroker("robinhood");
    expect(localStorage.getItem(INTENDED_BROKER_KEY)).toBeNull();
  });

  it("survives storage that throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => rememberIntendedBroker("xtb")).not.toThrow();
    expect(intendedBroker()).toBeNull();
    expect(() => clearIntendedBroker()).not.toThrow();
  });
});
