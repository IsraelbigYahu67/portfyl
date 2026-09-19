import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Login from "./Login";
import Register from "./Register";
import ForgotPassword from "./ForgotPassword";
import { TRACKER_HOME } from "../lib/routes";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";

const authMocks = vi.hoisted(() => ({
  loginWithIdToken: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ loginWithIdToken: authMocks.loginWithIdToken }),
}));

const firebaseMocks = vi.hoisted(() => ({
  signInWithEmailPassword: vi.fn(),
  registerWithEmailPassword: vi.fn(),
  sendPasswordReset: vi.fn(() => Promise.resolve()),
  sendVerificationEmail: vi.fn(() => Promise.resolve()),
  getCurrentFirebaseUser: vi.fn(() => null),
  getIdToken: vi.fn(() => Promise.resolve("id-token-123")),
  mapFirebaseAuthError: vi.fn((err) => err?.code || "Something went wrong. Please try again."),
}));
vi.mock("../auth/firebase", () => firebaseMocks);

afterEach(() => localStorage.clear());

function renderAt(path, { initialConsent = "accepted" } = {}) {
  const adapter = createMemoryAdapter();
  // Stable reference across the test's lifetime -- see useDemoAnalytics.test.jsx's
  // note on why an inline arrow here would cause AnalyticsProvider to reset on
  // every rerender (its effect depends on [consent, adapterFactory]).
  const adapterFactory = () => adapter;
  const result = render(
    <MemoryRouter initialEntries={[path]}>
      <AnalyticsProvider initialConsent={initialConsent} adapterFactory={adapterFactory}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/verify-email" element={<div>Verify email page</div>} />
          <Route path={TRACKER_HOME} element={<div>Home</div>} />
        </Routes>
      </AnalyticsProvider>
    </MemoryRouter>
  );
  return { ...result, adapter };
}

describe("Register", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends a verification e-mail and navigates to /verify-email", async () => {
    const fakeUser = { email: "new@example.com" };
    firebaseMocks.registerWithEmailPassword.mockResolvedValueOnce(fakeUser);

    renderAt("/register");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "s3cret!123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(firebaseMocks.registerWithEmailPassword).toHaveBeenCalledWith("new@example.com", "s3cret!123")
    );
    await waitFor(() => expect(firebaseMocks.sendVerificationEmail).toHaveBeenCalledWith(fakeUser));
    expect(await screen.findByText("Verify email page")).toBeInTheDocument();
  });

  it("shows an error and does not navigate when passwords don't match", async () => {
    renderAt("/register");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "s3cret!123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "different!123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/don't match/i);
    expect(firebaseMocks.registerWithEmailPassword).not.toHaveBeenCalled();
  });

  it("captures signup_started with source_surface=direct when there is no ?source param", async () => {
    const { adapter } = renderAt("/register");
    await waitFor(() =>
      expect(adapter.events).toContainEqual(["signup_started", { source_surface: "direct", language: "en" }])
    );
  });

  it("captures signup_started with source_surface=demo for ?source=demo, and never forwards other params", async () => {
    const { adapter } = renderAt("/register?source=demo&utm_source=evil&foo=bar");
    await waitFor(() =>
      expect(adapter.events).toContainEqual(["signup_started", { source_surface: "demo", language: "en" }])
    );
    const [, properties] = adapter.events.find(([name]) => name === "signup_started");
    expect(Object.keys(properties).sort()).toEqual(["language", "source_surface"]);
  });

  it("falls back to direct for an unrecognized ?source value", async () => {
    const { adapter } = renderAt("/register?source=malicious");
    await waitFor(() =>
      expect(adapter.events).toContainEqual(["signup_started", { source_surface: "direct", language: "en" }])
    );
  });

  it("captures signup_completed with source_surface only, after registration succeeds and before navigation", async () => {
    const fakeUser = { email: "new@example.com" };
    firebaseMocks.registerWithEmailPassword.mockResolvedValueOnce(fakeUser);

    const { adapter } = renderAt("/register?source=demo");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "s3cret!123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(adapter.events).toContainEqual(["signup_completed", { source_surface: "demo" }])
    );
    expect(await screen.findByText("Verify email page")).toBeInTheDocument();

    const serialized = JSON.stringify(adapter.events);
    expect(serialized).not.toMatch(/new@example\.com/);
  });

  it("does not capture signup_completed when registration fails", async () => {
    firebaseMocks.registerWithEmailPassword.mockRejectedValueOnce({ code: "auth/email-already-in-use" });

    const { adapter } = renderAt("/register");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "taken@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "s3cret!123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(adapter.events.map(([name]) => name)).not.toContain("signup_completed");
  });
});

describe("Login", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows verification instructions for an unverified account and does not log in", async () => {
    firebaseMocks.signInWithEmailPassword.mockResolvedValueOnce({
      email: "x@example.com",
      emailVerified: false,
    });

    renderAt("/login");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "x@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByText(/verify your e-mail/i)).toBeInTheDocument();
    expect(authMocks.loginWithIdToken).not.toHaveBeenCalled();
  });

  it("exchanges the ID token and navigates home for a verified login", async () => {
    firebaseMocks.signInWithEmailPassword.mockResolvedValueOnce({
      email: "x@example.com",
      emailVerified: true,
    });

    renderAt("/login");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "x@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => expect(authMocks.loginWithIdToken).toHaveBeenCalledWith("id-token-123"));
    expect(await screen.findByText("Home")).toBeInTheDocument();
  });

  it("explains when the verified e-mail has no private-beta invitation", async () => {
    firebaseMocks.signInWithEmailPassword.mockResolvedValueOnce({
      email: "outsider@example.com",
      emailVerified: true,
    });
    authMocks.loginWithIdToken.mockRejectedValueOnce({
      response: { status: 403, data: { code: "beta_access_required" } },
    });
    firebaseMocks.mapFirebaseAuthError.mockImplementationOnce(
      () => "This e-mail does not have an active Portfyl private beta invitation."
    );

    renderAt("/login");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "outsider@example.com" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/private beta invitation/i);
  });
});

describe("ForgotPassword", () => {
  beforeEach(() => vi.clearAllMocks());

  it("always shows a neutral success message when the reset call succeeds", async () => {
    renderAt("/forgot-password");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "real@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/if an account exists/i)).toBeInTheDocument();
  });

  it("shows the same neutral success message even when the reset call fails", async () => {
    firebaseMocks.sendPasswordReset.mockRejectedValueOnce({ code: "auth/user-not-found" });

    renderAt("/forgot-password");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "ghost@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));

    expect(await screen.findByText(/if an account exists/i)).toBeInTheDocument();
  });
});
