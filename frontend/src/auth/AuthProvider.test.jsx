import { useState } from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./AuthProvider";
import AnalyticsProvider, { useAnalytics } from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";

// vi.mock factories are hoisted above top-level consts — see
// SyncScheduleSettings.test.jsx for the same pattern already used in this repo.
const apiMocks = vi.hoisted(() => ({
  fetchMe: vi.fn(),
  exchangeSession: vi.fn(),
  logoutSession: vi.fn(() => Promise.resolve()),
  logoutAllSessions: vi.fn(() => Promise.resolve()),
  configureRequestContext: vi.fn(),
  setCsrfRefreshHandler: vi.fn(),
}));
vi.mock("../api", () => ({
  fetchMe: apiMocks.fetchMe,
  exchangeSession: apiMocks.exchangeSession,
  logoutSession: apiMocks.logoutSession,
  logoutAllSessions: apiMocks.logoutAllSessions,
  configureRequestContext: apiMocks.configureRequestContext,
  setCsrfRefreshHandler: apiMocks.setCsrfRefreshHandler,
}));

const firebaseMocks = vi.hoisted(() => ({
  signOutFirebaseClient: vi.fn(() => Promise.resolve()),
}));
vi.mock("./firebase", () => ({
  signOutFirebaseClient: firebaseMocks.signOutFirebaseClient,
}));

// The real widget loads Cloudflare's script; the dialog only needs its token.
vi.mock("./TurnstileWidget", () => ({
  default: ({ onToken }) => <button onClick={() => onToken("tok")}>solve-challenge</button>,
}));

afterEach(() => {
  localStorage.clear();
  vi.unstubAllEnvs();
});

function Probe() {
  const auth = useAuth();
  const [signOutError, setSignOutError] = useState("");
  const [loginError, setLoginError] = useState("");
  return (
    <div>
      <span data-testid="signout-error">{signOutError}</span>
      <button onClick={() => auth.logout().catch(() => setSignOutError("logout failed"))}>logout-safe</button>
      <button onClick={() => auth.logoutAll().catch(() => setSignOutError("logout-all failed"))}>logout-all-safe</button>
      <span data-testid="ready">{String(auth.ready)}</span>
      <span data-testid="email">{auth.user?.email ?? ""}</span>
      <span data-testid="workspace">{auth.currentWorkspace?.id ?? ""}</span>
      <span data-testid="csrf">{auth.csrfToken ?? ""}</span>
      <button onClick={() => auth.loginWithIdToken("id-token-123")}>login</button>
      <button onClick={() => auth.loginWithIdToken("id-token-123", { termsAccepted: true })}>login-accepted</button>
      <span data-testid="login-error">{loginError}</span>
      <button
        onClick={() => auth.loginWithIdToken("id-token-123").catch((e) => setLoginError(e?.response?.data?.code ?? "other"))}
      >
        login-safe
      </button>
      <button onClick={() => auth.logout()}>logout</button>
      <button onClick={() => auth.logoutAll()}>logout-all</button>
      <button onClick={() => auth.selectWorkspace("w2")}>switch-workspace</button>
    </div>
  );
}

function ConsentControls() {
  const { acceptAnalytics, rejectAnalytics } = useAnalytics();
  return (
    <div>
      <button onClick={acceptAnalytics}>accept-consent</button>
      <button onClick={rejectAnalytics}>reject-consent</button>
    </div>
  );
}

function mount({ initialConsent = "accepted" } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const clearSpy = vi.spyOn(qc, "clear");
  const adapter = createMemoryAdapter();
  // Stable reference across the test's lifetime: an inline arrow here would
  // cause AnalyticsProvider to reset on every rerender (its effect depends on
  // [consent, adapterFactory]).
  const adapterFactory = () => adapter;
  const utils = render(
    <QueryClientProvider client={qc}>
      <AnalyticsProvider initialConsent={initialConsent} adapterFactory={adapterFactory}>
        <ConsentControls />
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </AnalyticsProvider>
    </QueryClientProvider>
  );
  return { ...utils, clearSpy, adapter };
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("becomes ready with no user when /api/auth/me reports unauthenticated", async () => {
    apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
    mount();
    await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));
    expect(screen.getByTestId("email").textContent).toBe("");
    expect(apiMocks.configureRequestContext).toHaveBeenCalledWith({ workspaceId: null, csrfToken: null });
  });

  it("hydrates user, workspace, and CSRF token from /api/auth/me", async () => {
    apiMocks.fetchMe.mockResolvedValueOnce({
      user: { id: "u1", email: "alice@example.com" },
      workspaces: [{ id: "w1", name: "Alice's workspace", role: "owner" }],
      csrf_token: "csrf-1",
    });
    mount();
    await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));
    expect(screen.getByTestId("email").textContent).toBe("alice@example.com");
    expect(screen.getByTestId("workspace").textContent).toBe("w1");
    expect(screen.getByTestId("csrf").textContent).toBe("csrf-1");
    expect(apiMocks.configureRequestContext).toHaveBeenCalledWith({ workspaceId: "w1", csrfToken: "csrf-1" });
  });

  it("exchanges an ID token, signs the Firebase client out, and adopts the returned account", async () => {
    apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
    apiMocks.exchangeSession.mockResolvedValueOnce({
      user: { id: "u2", email: "bob@example.com" },
      workspaces: [{ id: "w2", name: "Bob's workspace", role: "owner" }],
      csrf_token: "csrf-2",
    });
    mount();
    await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));

    await act(async () => {
      screen.getByRole("button", { name: "login" }).click();
    });

    expect(apiMocks.exchangeSession).toHaveBeenCalledWith("id-token-123");
    expect(firebaseMocks.signOutFirebaseClient).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("email").textContent).toBe("bob@example.com");
    expect(screen.getByTestId("workspace").textContent).toBe("w2");
  });

  it("passes the Terms acceptance to the exchange only when it was given", async () => {
    apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
    apiMocks.exchangeSession.mockResolvedValueOnce({
      user: { id: "u2", email: "bob@example.com" },
      workspaces: [{ id: "w2", name: "Bob's workspace", role: "owner" }],
      csrf_token: "csrf-2",
    });
    mount();
    await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));

    await act(async () => {
      screen.getByRole("button", { name: "login-accepted" }).click();
    });

    expect(apiMocks.exchangeSession).toHaveBeenCalledWith("id-token-123", { termsAccepted: true });
  });

  describe("new-account bot check", () => {
    const botCheckRequired = { response: { status: 403, data: { code: "bot_check_required" } } };
    const account = {
      user: { id: "u3", email: "carol@example.com" },
      workspaces: [{ id: "w3", name: "Carol's workspace", role: "owner" }],
      csrf_token: "csrf-3",
    };

    async function mountSignedOut() {
      vi.stubEnv("VITE_TURNSTILE_SITE_KEY", "1x00000000000000000000AA");
      apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
      mount();
      await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));
    }

    it("shows the challenge once and retries the exchange with its token", async () => {
      await mountSignedOut();
      apiMocks.exchangeSession.mockRejectedValueOnce(botCheckRequired).mockResolvedValueOnce(account);

      await act(async () => {
        screen.getByRole("button", { name: "login" }).click();
      });
      expect(await screen.findByRole("dialog", { name: "One quick check" })).toBeInTheDocument();
      await act(async () => {
        screen.getByRole("button", { name: "solve-challenge" }).click();
      });

      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("carol@example.com"));
      expect(apiMocks.exchangeSession).toHaveBeenNthCalledWith(1, "id-token-123");
      expect(apiMocks.exchangeSession).toHaveBeenNthCalledWith(2, "id-token-123", { turnstileToken: "tok" });
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("rethrows the original error when the challenge is cancelled", async () => {
      await mountSignedOut();
      apiMocks.exchangeSession.mockRejectedValueOnce(botCheckRequired);

      await act(async () => {
        screen.getByRole("button", { name: "login-safe" }).click();
      });
      await act(async () => {
        screen.getByRole("button", { name: "Cancel" }).click();
      });

      await waitFor(() => expect(screen.getByTestId("login-error").textContent).toBe("bot_check_required"));
      expect(apiMocks.exchangeSession).toHaveBeenCalledTimes(1);
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("passes a rejected token on to the caller after the single retry", async () => {
      await mountSignedOut();
      apiMocks.exchangeSession
        .mockRejectedValueOnce(botCheckRequired)
        .mockRejectedValueOnce({ response: { status: 403, data: { code: "bot_check_failed" } } });

      await act(async () => {
        screen.getByRole("button", { name: "login-safe" }).click();
      });
      await act(async () => {
        screen.getByRole("button", { name: "solve-challenge" }).click();
      });

      await waitFor(() => expect(screen.getByTestId("login-error").textContent).toBe("bot_check_failed"));
      expect(apiMocks.exchangeSession).toHaveBeenCalledTimes(2);
    });

    it("never shows the challenge when the first exchange succeeds", async () => {
      await mountSignedOut();
      apiMocks.exchangeSession.mockResolvedValueOnce(account);

      await act(async () => {
        screen.getByRole("button", { name: "login" }).click();
      });

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(apiMocks.exchangeSession).toHaveBeenCalledTimes(1);
    });

    it("says the check is unavailable when the build has no site key", async () => {
      vi.stubEnv("VITE_TURNSTILE_SITE_KEY", "");
      apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
      mount();
      await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));
      apiMocks.exchangeSession.mockRejectedValueOnce(botCheckRequired);

      await act(async () => {
        screen.getByRole("button", { name: "login-safe" }).click();
      });

      expect(await screen.findByText(/sign-up check is not available right now/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "solve-challenge" })).not.toBeInTheDocument();
      expect(document.querySelector('script[src*="challenges.cloudflare.com"]')).toBeNull();
    });
  });

  it("clears account state and calls the backend on logout", async () => {
    apiMocks.fetchMe.mockResolvedValueOnce({
      user: { id: "u1", email: "alice@example.com" },
      workspaces: [{ id: "w1", name: "Alice's workspace", role: "owner" }],
      csrf_token: "csrf-1",
    });
    const { clearSpy } = mount();
    await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
    clearSpy.mockClear();

    await act(async () => {
      screen.getByRole("button", { name: "logout" }).click();
    });

    expect(apiMocks.logoutSession).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("email").textContent).toBe("");
    expect(clearSpy).toHaveBeenCalled();
  });

  it("clears account state and calls the backend on logout-all", async () => {
    apiMocks.fetchMe.mockResolvedValueOnce({
      user: { id: "u1", email: "alice@example.com" },
      workspaces: [{ id: "w1", name: "Alice's workspace", role: "owner" }],
      csrf_token: "csrf-1",
    });
    mount();
    await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));

    await act(async () => {
      screen.getByRole("button", { name: "logout-all" }).click();
    });

    expect(apiMocks.logoutAllSessions).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("email").textContent).toBe("");
  });

  describe("sign-out failures", () => {
    const account = {
      user: { id: "u1", email: "alice@example.com" },
      workspaces: [{ id: "w1", name: "Alice's workspace", role: "owner" }],
      csrf_token: "csrf-1",
    };

    it.each([
      ["logout", "logout-safe", "logoutSession", "logout failed"],
      ["logout-all", "logout-all-safe", "logoutAllSessions", "logout-all failed"],
    ])("keeps the user signed in when the server does not confirm %s", async (_name, button, mockName, message) => {
      apiMocks.fetchMe.mockResolvedValueOnce(account);
      const { adapter, clearSpy } = mount();
      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
      clearSpy.mockClear();
      apiMocks.configureRequestContext.mockClear();
      apiMocks[mockName].mockRejectedValueOnce({ response: { status: 403, data: { code: "csrf_failed" } } });

      await act(async () => {
        screen.getByRole("button", { name: button }).click();
      });

      expect(screen.getByTestId("signout-error").textContent).toBe(message);
      expect(screen.getByTestId("email").textContent).toBe("alice@example.com");
      expect(screen.getByTestId("csrf").textContent).toBe("csrf-1");
      expect(clearSpy).not.toHaveBeenCalled();
      expect(apiMocks.configureRequestContext).not.toHaveBeenCalledWith({ workspaceId: null, csrfToken: null });
      expect(adapter.resetCount).toBe(0);
    });

    it("treats an already-expired session (401) as signed out", async () => {
      apiMocks.fetchMe.mockResolvedValueOnce(account);
      mount();
      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
      apiMocks.logoutSession.mockRejectedValueOnce({ response: { status: 401 } });

      await act(async () => {
        screen.getByRole("button", { name: "logout-safe" }).click();
      });

      expect(screen.getByTestId("email").textContent).toBe("");
      expect(screen.getByTestId("signout-error").textContent).toBe("");
    });
  });

  describe("csrf refresh handler", () => {
    it("re-reads the token from /auth/me without clearing the query cache or workspace", async () => {
      apiMocks.fetchMe.mockResolvedValueOnce({
        user: { id: "u1", email: "alice@example.com" },
        workspaces: [{ id: "w1", name: "Alice's workspace", role: "owner" }],
        csrf_token: "csrf-1",
      });
      const { clearSpy } = mount();
      await waitFor(() => expect(screen.getByTestId("csrf").textContent).toBe("csrf-1"));
      const handler = apiMocks.setCsrfRefreshHandler.mock.calls
        .map(([fn]) => fn)
        .filter(Boolean)
        .at(-1);
      expect(handler).toBeTypeOf("function");
      clearSpy.mockClear();
      apiMocks.fetchMe.mockResolvedValueOnce({
        user: { id: "u1", email: "alice@example.com" },
        workspaces: [{ id: "w1", name: "Alice's workspace", role: "owner" }],
        csrf_token: "csrf-2",
      });

      await act(async () => {
        await handler();
      });

      expect(screen.getByTestId("csrf").textContent).toBe("csrf-2");
      expect(screen.getByTestId("workspace").textContent).toBe("w1");
      expect(apiMocks.configureRequestContext).toHaveBeenLastCalledWith({ workspaceId: "w1", csrfToken: "csrf-2" });
      expect(clearSpy).not.toHaveBeenCalled();
    });

    it("unregisters the handler when the provider unmounts", async () => {
      apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
      const { unmount } = mount();
      await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));

      unmount();

      expect(apiMocks.setCsrfRefreshHandler).toHaveBeenLastCalledWith(null);
    });
  });

  it("throws when useAuth() is called outside an AuthProvider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    function Bare() {
      useAuth();
      return null;
    }
    expect(() => render(<Bare />)).toThrow(/useAuth/);
    spy.mockRestore();
  });

  describe("analytics identity", () => {
    function mockAccount(overrides) {
      apiMocks.fetchMe.mockResolvedValueOnce({
        user: { id: "u1", email: "alice@example.com", display_name: "Alice A." },
        workspaces: [
          { id: "w1", name: "Alice's workspace", role: "owner" },
          { id: "w2", name: "Second workspace", role: "owner" },
        ],
        csrf_token: "csrf-1",
        ...overrides,
      });
    }

    it("identifies the opaque user id once the account is loaded and consent is accepted", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));
    });

    it("does not identify a signed-in user who has no workspace yet", async () => {
      mockAccount({ workspaces: [] });
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
      expect(adapter.identifiedId).toBeNull();
    });

    it("does not identify when consent is rejected", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "rejected" });
      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
      expect(adapter.identifiedId).toBeNull();
    });

    it("does not identify while consent is pending, but identifies once the visitor accepts", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "pending" });
      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("alice@example.com"));
      expect(adapter.identifiedId).toBeNull();

      await act(async () => {
        screen.getByRole("button", { name: "accept-consent" }).click();
      });

      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));
    });

    it("does not reset analytics merely because the initial /api/auth/me request is unauthenticated", async () => {
      apiMocks.fetchMe.mockRejectedValueOnce({ response: { status: 401 } });
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(screen.getByTestId("ready").textContent).toBe("true"));
      expect(adapter.resetCount).toBe(0);
    });

    it("resets analytics identity on logout", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));

      await act(async () => {
        screen.getByRole("button", { name: "logout" }).click();
      });

      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe(""));
      expect(adapter.resetCount).toBeGreaterThan(0);
      expect(adapter.identifiedId).toBeNull();
    });

    it("resets analytics identity on logout-all", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));

      await act(async () => {
        screen.getByRole("button", { name: "logout-all" }).click();
      });

      await waitFor(() => expect(screen.getByTestId("email").textContent).toBe(""));
      expect(adapter.resetCount).toBeGreaterThan(0);
      expect(adapter.identifiedId).toBeNull();
    });

    it("resets then re-identifies the same opaque user id after a workspace switch", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));
      const resetCountBefore = adapter.resetCount;

      await act(async () => {
        screen.getByRole("button", { name: "switch-workspace" }).click();
      });

      expect(screen.getByTestId("workspace").textContent).toBe("w2");
      await waitFor(() => expect(adapter.resetCount).toBe(resetCountBefore + 1));
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));
    });

    it("never leaks e-mail, display name, workspace id/name, or CSRF token to analytics", async () => {
      mockAccount();
      const { adapter } = mount({ initialConsent: "accepted" });
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));

      await act(async () => {
        screen.getByRole("button", { name: "switch-workspace" }).click();
      });
      await waitFor(() => expect(adapter.identifiedId).toBe("u1"));

      const serialized = JSON.stringify({ identifiedId: adapter.identifiedId, events: adapter.events });
      expect(serialized).not.toMatch(/alice@example\.com/);
      expect(serialized).not.toMatch(/Alice A\./);
      expect(serialized).not.toMatch(/Alice's workspace/);
      expect(serialized).not.toMatch(/Second workspace/);
      expect(serialized).not.toMatch(/csrf-1/);
      expect(serialized).not.toMatch(/\bw1\b/);
      expect(serialized).not.toMatch(/\bw2\b/);
    });
  });
});
