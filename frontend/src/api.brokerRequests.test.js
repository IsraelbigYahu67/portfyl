import {
  api,
  applyRequestInterceptors,
  configureRequestContext,
  connectT212,
  requestBrokerSupport,
  setActivePortfolioId,
  syncEtoro,
  syncIBKR,
} from "./api";

describe("broker support requests", () => {
  afterEach(() => {
    setActivePortfolioId(null);
    configureRequestContext({ workspaceId: null, csrfToken: null });
    vi.restoreAllMocks();
  });

  it("never injects portfolio_id into /broker-requests", async () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    const config = await applyRequestInterceptors({ method: "post", url: "/broker-requests", params: {} });
    expect(config.params.portfolio_id).toBeUndefined();
  });

  it("still sends the CSRF and workspace headers", async () => {
    configureRequestContext({ workspaceId: "22222222-2222-4222-8222-222222222222", csrfToken: "csrf-token" });
    const config = await applyRequestInterceptors({ method: "post", url: "/broker-requests", params: {} });
    expect(config.headers["X-CSRF-Token"]).toBe("csrf-token");
    expect(config.headers["X-Workspace-ID"]).toBe("22222222-2222-4222-8222-222222222222");
  });

  it("requestBrokerSupport posts the name and returns the response body", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { broker_name: "Revolut", created: true } });
    await expect(requestBrokerSupport("Revolut")).resolves.toEqual({ broker_name: "Revolut", created: true });
    expect(post).toHaveBeenCalledWith("/broker-requests", { broker_name: "Revolut" });
  });

  it("passes suppressEntitlementPrompt on onboarding connect and sync", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { ok: true } });
    await connectT212("k", "s", { suppressEntitlementPrompt: true });
    expect(post).toHaveBeenLastCalledWith(
      "/broker/trading212/connect",
      { api_key: "k", api_secret: "s" },
      { suppressEntitlementPrompt: true },
    );
    await syncIBKR({ suppressEntitlementPrompt: true });
    expect(post).toHaveBeenLastCalledWith("/broker/ibkr/sync", undefined, { suppressEntitlementPrompt: true });
  });

  it("ignores a non-options argument", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: {} });
    await syncEtoro({ type: "click" });
    expect(post).toHaveBeenLastCalledWith("/broker/etoro/sync", undefined, { suppressEntitlementPrompt: false });
  });
});
