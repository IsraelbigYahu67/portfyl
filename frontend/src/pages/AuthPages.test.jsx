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
  isGoogleSignInEnabled: vi.fn(() => false),
  prepareGoogleSignIn: vi.fn(() => Promise.resolve()),
  signInWithGoogle: vi.fn(),
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

  it("requires the 18+ and Terms/Privacy confirmation before any sign-up path is enabled", () => {
    renderAt("/register");
    expect(screen.getByRole("button", { name: /create account/i })).toBeDisabled();
    const terms = screen.getByRole("link", { name: /terms of service/i });
    const privacy = screen.getByRole("link", { name: /privacy policy/i });
    expect(terms).toHaveAttribute("href", expect.stringMatching(/^\/terms\?lang=/));
    expect(privacy).toHaveAttribute("href", expect.stringMatching(/^\/privacy\?lang=/));
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
    expect(screen.getByRole("button", { name: /create account/i })).toBeEnabled();
  });

  it("sends a verification e-mail and navigates to /verify-email", async () => {
    const fakeUser = { email: "new@example.com" };
    firebaseMocks.registerWithEmailPassword.mockResolvedValueOnce(fakeUser);

    renderAt("/register");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "s3cret!123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
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
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
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

  it("captures signup_completed with source_surface and auth_method only, after registration succeeds and before navigation", async () => {
    const fakeUser = { email: "new@example.com" };
    firebaseMocks.registerWithEmailPassword.mockResolvedValueOnce(fakeUser);

    const { adapter } = renderAt("/register?source=demo");
    fireEvent.change(screen.getByLabelText(/e-mail/i), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "s3cret!123" } });
    fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "s3cret!123" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() =>
      expect(adapter.events).toContainEqual(["signup_completed", { source_surface: "demo", auth_method: "password" }])
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
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
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

describe("Continue with Google", () => {
  const googleUser = { email: "person@gmail.com", emailVerified: true };

  beforeEach(() => {
    vi.clearAllMocks();
    firebaseMocks.isGoogleSignInEnabled.mockReturnValue(true);
    firebaseMocks.signInWithGoogle.mockResolvedValue(googleUser);
    authMocks.loginWithIdToken.mockResolvedValue({ account_created: false });
  });

  afterEach(() => {
    firebaseMocks.isGoogleSignInEnabled.mockReturnValue(false);
    firebaseMocks.signInWithGoogle.mockReset();
    authMocks.loginWithIdToken.mockReset().mockImplementation(() => Promise.resolve({}));
  });

  it.each(["/login", "/register"])("is hidden on %s unless the build enables it", (path) => {
    firebaseMocks.isGoogleSignInEnabled.mockReturnValue(false);
    renderAt(path);
    expect(screen.queryByRole("button", { name: /continue with google/i })).not.toBeInTheDocument();
  });

  it.each(["/login", "/register"])("preloads the Firebase SDK on %s so the popup is not blocked", async (path) => {
    renderAt(path);
    expect(screen.getByRole("button", { name: /continue with google/i })).toBeInTheDocument();
    await waitFor(() => expect(firebaseMocks.prepareGoogleSignIn).toHaveBeenCalledTimes(1));
  });

  it("logs a returning Google user in and goes home without a signup event", async () => {
    const { adapter } = renderAt("/login");
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => expect(firebaseMocks.getIdToken).toHaveBeenCalledWith(googleUser));
    expect(authMocks.loginWithIdToken).toHaveBeenCalledWith("id-token-123");
    expect(await screen.findByText("Home")).toBeInTheDocument();
    expect(adapter.events.map(([name]) => name)).not.toContain("signup_completed");
  });

  it("records a first Google sign-in as a signup and skips e-mail verification", async () => {
    authMocks.loginWithIdToken.mockResolvedValue({ account_created: true });

    const { adapter } = renderAt("/register?source=demo");
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    expect(await screen.findByText("Home")).toBeInTheDocument();
    expect(adapter.events).toContainEqual(["signup_completed", { source_surface: "demo", auth_method: "google" }]);
    expect(firebaseMocks.sendVerificationEmail).not.toHaveBeenCalled();
    expect(JSON.stringify(adapter.events)).not.toMatch(/person@gmail\.com/);
  });

  it("does nothing when the Google popup is dismissed", async () => {
    firebaseMocks.signInWithGoogle.mockResolvedValue(null);

    renderAt("/login");
    const button = screen.getByRole("button", { name: /continue with google/i });
    fireEvent.click(button);

    await waitFor(() => expect(button).not.toBeDisabled());
    expect(authMocks.loginWithIdToken).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("explains a rejected Google sign-in and stays on the page", async () => {
    authMocks.loginWithIdToken.mockRejectedValue({
      response: { status: 403, data: { code: "beta_access_required" } },
    });
    firebaseMocks.mapFirebaseAuthError.mockImplementationOnce(
      () => "This e-mail does not have an active Portfyl private beta invitation."
    );

    renderAt("/register");
    fireEvent.click(screen.getByRole("checkbox", { name: /18 or older/i }));
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/private beta invitation/i);
    expect(screen.queryByText("Home")).not.toBeInTheDocument();
  });

  it("shows popup failures such as a blocked window", async () => {
    firebaseMocks.signInWithGoogle.mockRejectedValue({ code: "auth/popup-blocked" });

    renderAt("/login");
    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("auth/popup-blocked");
    expect(authMocks.loginWithIdToken).not.toHaveBeenCalled();
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
