import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import AuthAction, { safeContinueTarget } from "./AuthAction";

const firebaseMocks = vi.hoisted(() => ({
  applyEmailActionCode: vi.fn(() => Promise.resolve()),
  checkEmailActionCode: vi.fn(),
  verifyResetCode: vi.fn(),
  confirmNewPassword: vi.fn(() => Promise.resolve()),
  mapFirebaseAuthError: vi.fn((err) => err?.code || "Something went wrong. Please try again."),
}));
vi.mock("../auth/firebase", () => firebaseMocks);

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search}</output>;
}

function renderAction(search) {
  return render(
    <MemoryRouter initialEntries={[`/auth/action${search}`]}>
      <Routes>
        <Route path="/auth/action" element={<AuthAction />} />
        <Route path="/login" element={<p>login page</p>} />
      </Routes>
      <Where />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

test("verifies the e-mail once and cleans the address bar", async () => {
  renderAction("?mode=verifyEmail&oobCode=CODE1&apiKey=KEY&continueUrl=http%3A%2F%2Flocalhost%3A3000%2Flogin%3Fverified%3D1&lang=en");

  expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
  expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledTimes(1);
  expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledWith("CODE1");
  expect(screen.getByTestId("where")).toHaveTextContent(/^\/auth\/action$/);
  expect(screen.getByRole("link", { name: "Continue to Portfyl" })).toHaveAttribute("href", "/login?verified=1");
});

test("shows a friendly error for a used or expired link", async () => {
  firebaseMocks.applyEmailActionCode.mockRejectedValueOnce({ code: "auth/invalid-action-code" });
  renderAction("?mode=verifyEmail&oobCode=OLD");

  expect(await screen.findByRole("heading", { name: "This link didn't work" })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("auth/invalid-action-code");
});

test("a link without a code is rejected without calling Firebase", async () => {
  renderAction("?mode=verifyEmail");

  expect(await screen.findByRole("heading", { name: "This link didn't work" })).toBeInTheDocument();
  expect(firebaseMocks.applyEmailActionCode).not.toHaveBeenCalled();
});

test("resets the password with the code from the link", async () => {
  firebaseMocks.verifyResetCode.mockResolvedValueOnce("me@example.com");
  renderAction("?mode=resetPassword&oobCode=RESET1");

  expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
  expect(screen.getByText("me@example.com")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "short" } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "short" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("at least 8 characters");
  expect(firebaseMocks.confirmNewPassword).not.toHaveBeenCalled();

  fireEvent.change(screen.getByLabelText("New password"), { target: { value: "long-enough-1" } });
  fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "long-enough-1" } });
  fireEvent.click(screen.getByRole("button", { name: "Save new password" }));

  expect(await screen.findByRole("heading", { name: "Password changed" })).toBeInTheDocument();
  expect(firebaseMocks.confirmNewPassword).toHaveBeenCalledWith("RESET1", "long-enough-1");
});

test("restores the previous sign-in e-mail", async () => {
  firebaseMocks.checkEmailActionCode.mockResolvedValueOnce({ operation: "RECOVER_EMAIL", email: "old@example.com" });
  renderAction("?mode=recoverEmail&oobCode=REC1");

  expect(await screen.findByRole("heading", { name: "Your sign-in e-mail is restored" })).toBeInTheDocument();
  expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledWith("REC1");
  expect(screen.getByText("old@example.com")).toBeInTheDocument();
});

describe("safeContinueTarget", () => {
  const origin = "https://app.portfyl.com";

  test("keeps a same-origin continue URL as a path", () => {
    expect(safeContinueTarget("https://app.portfyl.com/login?verified=1", origin)).toBe("/login?verified=1");
  });

  test("allows a local dev server", () => {
    expect(safeContinueTarget("http://localhost:5173/login?verified=1", origin)).toBe("http://localhost:5173/login?verified=1");
  });

  test("never follows another site", () => {
    expect(safeContinueTarget("https://evil.example/login", origin)).toBe("/login?verified=1");
    expect(safeContinueTarget("javascript:alert(1)", origin)).toBe("/login?verified=1");
    expect(safeContinueTarget("https://localhost.evil.example/", origin)).toBe("/login?verified=1");
  });

  test("falls back to the login page without a continue URL", () => {
    expect(safeContinueTarget(null, origin)).toBe("/login?verified=1");
  });
});
