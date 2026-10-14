import {
  api,
  sendAssistantMessage,
  fetchHistory,
  applyRequestInterceptors,
  configureRequestContext,
  handleResponseError,
  setCsrfRefreshHandler,
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

describe("csrf_failed recovery", () => {
  const csrfError = (config = { url: "/alerts", method: "post" }) => ({
    config,
    response: { status: 403, data: { code: "csrf_failed" } },
  });
  let request;

  beforeEach(() => {
    request = vi.spyOn(api, "request").mockResolvedValue({ data: "replayed" });
  });

  afterEach(() => {
    setCsrfRefreshHandler(null);
    request.mockRestore();
  });

  it("refreshes the token and replays the request exactly once", async () => {
    const handler = vi.fn().mockResolvedValue(undefined);
    setCsrfRefreshHandler(handler);
    const error = csrfError();

    const result = await handleResponseError(error);

    expect(result).toEqual({ data: "replayed" });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledWith(expect.objectContaining({ url: "/alerts", _csrfRetried: true }));
  });

  it("does not retry a request that was already replayed", async () => {
    const handler = vi.fn().mockResolvedValue(undefined);
    setCsrfRefreshHandler(handler);
    const error = csrfError({ url: "/alerts", method: "post", _csrfRetried: true });

    await expect(handleResponseError(error)).rejects.toBe(error);

    expect(handler).not.toHaveBeenCalled();
    expect(request).not.toHaveBeenCalled();
  });

  it("gives up after a single replay when the server still rejects the token", async () => {
    const handler = vi.fn().mockResolvedValue(undefined);
    setCsrfRefreshHandler(handler);
    const stillFailing = csrfError();
    request.mockImplementation((config) => handleResponseError({ ...stillFailing, config }));

    await expect(handleResponseError(csrfError())).rejects.toMatchObject({
      response: { status: 403 },
    });

    expect(handler).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("rejects with the original error when no refresh handler is registered", async () => {
    const error = csrfError();
    await expect(handleResponseError(error)).rejects.toBe(error);
    expect(request).not.toHaveBeenCalled();
  });

  it("rejects with the original error when the token cannot be refreshed", async () => {
    setCsrfRefreshHandler(vi.fn().mockRejectedValue(new Error("offline")));
    const error = csrfError();

    await expect(handleResponseError(error)).rejects.toBe(error);

    expect(request).not.toHaveBeenCalled();
  });

  it("ignores other 403 codes", async () => {
    const handler = vi.fn();
    setCsrfRefreshHandler(handler);
    const error = { config: {}, response: { status: 403, data: { code: "quota_exceeded" } } };
    const listener = vi.fn();
    window.addEventListener("portfyl:entitlement-denied", listener);

    await expect(handleResponseError(error)).rejects.toBe(error);

    window.removeEventListener("portfyl:entitlement-denied", listener);
    expect(handler).not.toHaveBeenCalled();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("shares one token refresh between parallel failures", async () => {
    let release;
    const handler = vi.fn(() => new Promise((resolve) => { release = resolve; }));
    setCsrfRefreshHandler(handler);

    const first = handleResponseError(csrfError());
    const second = handleResponseError(csrfError({ url: "/cash", method: "post" }));
    await Promise.resolve();
    release();
    await Promise.all([first, second]);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(request).toHaveBeenCalledTimes(2);
  });
});
