import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import VerifyEmail from "./VerifyEmail";
import Login from "./Login";
import { TRACKER_HOME } from "../lib/routes";

const navigateMock = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => navigateMock,
}));

const authMocks = vi.hoisted(() => ({
  loginWithIdToken: vi.fn(() => Promise.resolve({})),
}));
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ loginWithIdToken: authMocks.loginWithIdToken }),
}));

const firebaseMocks = vi.hoisted(() => ({
  getCurrentFirebaseUser: vi.fn(),
  reloadFirebaseUser: vi.fn(),
  getIdToken: vi.fn(() => Promise.resolve("fresh-token")),
  sendVerificationEmail: vi.fn(() => Promise.resolve()),
  mapFirebaseAuthError: vi.fn((err) => err?.code || "Something went wrong. Please try again."),
  signInWithEmailPassword: vi.fn(),
  isGoogleSignInEnabled: vi.fn(() => false),
  prepareGoogleSignIn: vi.fn(() => Promise.resolve()),
  signInWithGoogle: vi.fn(),
}));
vi.mock("../auth/firebase", () => firebaseMocks);

const USER = { email: "new@example.com" };

function renderVerify() {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/verify-email", state: { email: "new@example.com" } }]}>
      <Routes>
        <Route path="/verify-email" element={<VerifyEmail />} />
      </Routes>
    </MemoryRouter>,
  );
}

// Lets the awaited reload -> token -> login chain settle after a timer tick.
async function advance(ms) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  firebaseMocks.getCurrentFirebaseUser.mockReturnValue(USER);
  firebaseMocks.reloadFirebaseUser.mockResolvedValue(false);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("VerifyEmail", () => {
  test("continues into the app once the address is verified", async () => {
    firebaseMocks.reloadFirebaseUser.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    renderVerify();

    await advance(4000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(1);
    expect(authMocks.loginWithIdToken).not.toHaveBeenCalled();

    await advance(4000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledWith(USER);
    expect(firebaseMocks.getIdToken).toHaveBeenCalledWith(USER, true);
    expect(authMocks.loginWithIdToken).toHaveBeenCalledTimes(1);
    expect(authMocks.loginWithIdToken).toHaveBeenCalledWith("fresh-token");
    expect(navigateMock).toHaveBeenCalledWith(TRACKER_HOME, { replace: true });

    // Success stops the polling for good.
    await advance(60000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(2);
  });

  test("checks again when the tab regains focus", async () => {
    renderVerify();
    expect(firebaseMocks.reloadFirebaseUser).not.toHaveBeenCalled();

    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(1);
  });

  test("does not poll without an in-memory user", async () => {
    firebaseMocks.getCurrentFirebaseUser.mockReturnValue(null);
    renderVerify();

    await advance(60000);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(firebaseMocks.reloadFirebaseUser).not.toHaveBeenCalled();
    expect(screen.getByText("Sign in again to resend the verification e-mail.")).toBeInTheDocument();
  });

  test("stops polling on unmount and after the limit", async () => {
    const first = renderVerify();
    await advance(8000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(2);
    first.unmount();
    await advance(10 * 60 * 1000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(2);

    firebaseMocks.reloadFirebaseUser.mockClear();
    renderVerify();
    await advance(20 * 60 * 1000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(225);
  });

  test("shows the mapped error and stops polling when the session exchange fails", async () => {
    firebaseMocks.reloadFirebaseUser.mockResolvedValue(true);
    authMocks.loginWithIdToken.mockRejectedValueOnce({ code: "auth/network-request-failed" });
    renderVerify();

    await advance(4000);
    expect(screen.getByRole("alert")).toHaveTextContent("auth/network-request-failed");
    expect(navigateMock).not.toHaveBeenCalled();

    await advance(60000);
    expect(firebaseMocks.reloadFirebaseUser).toHaveBeenCalledTimes(1);
  });

  test("login shows the verified notice", () => {
    render(
      <MemoryRouter initialEntries={["/login?verified=1"]}>
        <Routes>
          <Route path="/login" element={<Login />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("E-mail verified. Log in to continue.");
  });

  test("login has no verified notice without the flag", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <Routes>
          <Route path="/login" element={<Login />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByText("E-mail verified. Log in to continue.")).not.toBeInTheDocument();
  });
});
