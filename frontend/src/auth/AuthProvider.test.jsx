import { render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "./AuthProvider";

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
    </div>
  );
}

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const clearSpy = vi.spyOn(qc, "clear");
  const utils = render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>
  );
  return { ...utils, clearSpy };
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
});
