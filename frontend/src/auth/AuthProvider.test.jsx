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
}));
vi.mock("../api", () => ({
  fetchMe: apiMocks.fetchMe,
  exchangeSession: apiMocks.exchangeSession,
  logoutSession: apiMocks.logoutSession,
  logoutAllSessions: apiMocks.logoutAllSessions,
  configureRequestContext: apiMocks.configureRequestContext,
}));

const firebaseMocks = vi.hoisted(() => ({
  signOutFirebaseClient: vi.fn(() => Promise.resolve()),
}));
vi.mock("./firebase", () => ({
  signOutFirebaseClient: firebaseMocks.signOutFirebaseClient,
}));

afterEach(() => localStorage.clear());

function Probe() {
  const auth = useAuth();
  return (
    <div>
      <span data-testid="ready">{String(auth.ready)}</span>
      <span data-testid="email">{auth.user?.email ?? ""}</span>
      <span data-testid="workspace">{auth.currentWorkspace?.id ?? ""}</span>
      <span data-testid="csrf">{auth.csrfToken ?? ""}</span>
      <button onClick={() => auth.loginWithIdToken("id-token-123")}>login</button>
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
  // Stable reference across the test's lifetime -- see useDemoAnalytics.test.jsx's
  // note on why an inline arrow here would cause AnalyticsProvider to reset on
  // every rerender (its effect depends on [consent, adapterFactory]).
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
