import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Login from "./Login";
import Register from "./Register";
import ForgotPassword from "./ForgotPassword";
import { TRACKER_HOME } from "../lib/routes";

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

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/verify-email" element={<div>Verify email page</div>} />
        <Route path={TRACKER_HOME} element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );
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
    fireEvent.click(screen.getByRole("button", { name: /create beta account/i }));

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
    fireEvent.click(screen.getByRole("button", { name: /create beta account/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/don't match/i);
    expect(firebaseMocks.registerWithEmailPassword).not.toHaveBeenCalled();
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
