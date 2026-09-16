import {
  api,
  sendAssistantMessage,
  fetchHistory,
  applyRequestInterceptors,
  configureRequestContext,
  getActivePortfolioId,
  setActivePortfolioId,
} from "./api";

it('sends the explicit assistant mode and passes cancellation to stock history', async () => {
  const post = vi.spyOn(api, 'post').mockResolvedValue({ data: {} });
  const get = vi.spyOn(api, 'get').mockResolvedValue({ data: {} });
  const messages = [{ role: 'user', content: 'Question' }];
  await sendAssistantMessage(messages);
  expect(post).toHaveBeenLastCalledWith('/assistant/chat', { messages, context_mode: 'none' });
  await sendAssistantMessage(messages, 'portfolio_summary');
  expect(post).toHaveBeenLastCalledWith('/assistant/chat', { messages, context_mode: 'portfolio_summary' });
  const signal = new AbortController().signal;
  await fetchHistory('AAPL', '1y', { signal, suppressEntitlementPrompt: true });
  expect(get).toHaveBeenLastCalledWith('/market/history/AAPL', { signal, suppressEntitlementPrompt: true, params: { period: '1y' } });
  post.mockRestore(); get.mockRestore();
});

describe("api request context (workspace + CSRF + UUID portfolio ids)", () => {
  afterEach(() => {
    setActivePortfolioId(null);
    configureRequestContext({ workspaceId: null, csrfToken: null });
  });

  it("keeps UUID portfolio IDs and attaches workspace plus CSRF headers", async () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    configureRequestContext({
      workspaceId: "22222222-2222-4222-8222-222222222222",
      csrfToken: "csrf-token",
    });
    const config = await applyRequestInterceptors({ method: "post", url: "/alerts", params: {} });
    expect(config.params.portfolio_id).toBe("11111111-1111-4111-8111-111111111111");
    expect(config.headers["X-Workspace-ID"]).toBe("22222222-2222-4222-8222-222222222222");
    expect(config.headers["X-CSRF-Token"]).toBe("csrf-token");
  });

  it("does not attach a CSRF header on GET requests", async () => {
    configureRequestContext({
      workspaceId: "22222222-2222-4222-8222-222222222222",
      csrfToken: "csrf-token",
    });
    const config = await applyRequestInterceptors({ method: "get", url: "/portfolio/summary", params: {} });
    expect(config.headers?.["X-CSRF-Token"]).toBeUndefined();
    expect(config.headers["X-Workspace-ID"]).toBe("22222222-2222-4222-8222-222222222222");
  });

  it("never injects portfolio_id for portfolio-agnostic prefixes", async () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    const config = await applyRequestInterceptors({ method: "get", url: "/watchlists", params: {} });
    expect(config.params.portfolio_id).toBeUndefined();
  });

  it("never injects portfolio_id for auth endpoints", async () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    const config = await applyRequestInterceptors({ method: "get", url: "/auth/me", params: {} });
    expect(config.params.portfolio_id).toBeUndefined();
  });

  it("never injects portfolio_id for the runtime capabilities endpoint", async () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    const config = await applyRequestInterceptors({ method: "get", url: "/capabilities", params: {} });
    expect(config.params.portfolio_id).toBeUndefined();
  });

  it("never injects portfolio_id for the private-test plan endpoint", async () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    const config = await applyRequestInterceptors({ method: "put", url: "/test-plans", params: {} });
    expect(config.params.portfolio_id).toBeUndefined();
  });

  it("omits portfolio_id entirely when no portfolio is active", async () => {
    setActivePortfolioId(null);
    const config = await applyRequestInterceptors({ method: "get", url: "/alerts", params: {} });
    expect(config.params.portfolio_id).toBeUndefined();
  });

  it("does not coerce a UUID portfolio id to a number", () => {
    setActivePortfolioId("11111111-1111-4111-8111-111111111111");
    expect(getActivePortfolioId()).toBe("11111111-1111-4111-8111-111111111111");
    expect(Number.isNaN(getActivePortfolioId())).toBe(false);
    expect(typeof getActivePortfolioId()).toBe("string");
  });
});
