import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { I18nProvider } from "../i18n/I18nProvider";
import { LANGUAGE_STORAGE_KEY } from "../i18n/languages";
import AuthAction, { safeContinueTarget } from "./AuthAction";

const firebaseMocks = vi.hoisted(() => ({
  applyEmailActionCode: vi.fn(() => Promise.resolve()),
  checkEmailActionCode: vi.fn(),
  verifyResetCode: vi.fn(),
  confirmNewPassword: vi.fn(() => Promise.resolve()),
  mapFirebaseAuthError: vi.fn((err) => err?.code || "Something went wrong. Please try again."),
}));
vi.mock("../auth/firebase", () => firebaseMocks);

// Whether this device has a language the user chose is decided per test.
const languageMocks = vi.hoisted(() => ({ hasSavedLanguage: vi.fn(() => false) }));
vi.mock("../i18n/languages", async (importOriginal) => ({
  ...(await importOriginal()),
  hasSavedLanguage: languageMocks.hasSavedLanguage,
}));

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.pathname + location.search + location.hash}</output>;
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
  languageMocks.hasSavedLanguage.mockReturnValue(false);
  document.documentElement.lang = "en";
});

afterEach(() => localStorage.clear());

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

// Portfyl's own links carry the parameters in the fragment (#mode=…), which a
// browser never sends to a server; Firebase's fallback e-mails use the query.
describe("parameters in the URL fragment", () => {
  test("a fragment link verifies the e-mail and cleans the address bar", async () => {
    renderAction("#mode=verifyEmail&oobCode=FRAG1&continueUrl=http%3A%2F%2Flocalhost%3A3000%2Flogin%3Fverified%3D1&lang=en");

    expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
    expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledTimes(1);
    expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledWith("FRAG1");
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/auth\/action$/);
    expect(screen.getByRole("link", { name: "Continue to Portfyl" })).toHaveAttribute("href", "/login?verified=1");
  });

  test("a fragment link opens the reset form", async () => {
    firebaseMocks.verifyResetCode.mockResolvedValueOnce("me@example.com");
    renderAction("#mode=resetPassword&oobCode=FRAGRESET");

    expect(await screen.findByRole("heading", { name: "Choose a new password" })).toBeInTheDocument();
    expect(firebaseMocks.verifyResetCode).toHaveBeenCalledWith("FRAGRESET");
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/auth\/action$/);
  });

  test("with both present the fragment wins", async () => {
    renderAction("?mode=resetPassword&oobCode=QUERY#mode=verifyEmail&oobCode=FRAG");

    expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
    expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledWith("FRAG");
    expect(firebaseMocks.verifyResetCode).not.toHaveBeenCalled();
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/auth\/action$/);
  });

  test("a fragment with no known key falls back to the query", async () => {
    renderAction("?mode=verifyEmail&oobCode=QUERY#top");

    expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
    expect(firebaseMocks.applyEmailActionCode).toHaveBeenCalledWith("QUERY");
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/auth\/action$/);
  });

  test("a lone unknown fragment is rejected and removed", async () => {
    renderAction("#top");

    expect(await screen.findByRole("heading", { name: "This link didn't work" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/auth\/action$/);
  });
});

// The e-mail's language (?lang=) is shown for this visit only, and only on a
// device where nobody chose a language. These use the real provider, so the
// page's own language and what is saved are the observable result.
describe("the link's language", () => {
  function renderInApp(search) {
    return render(
      <I18nProvider initial="en">
        <MemoryRouter initialEntries={[`/auth/action${search}`]}>
          <Routes>
            <Route path="/auth/action" element={<AuthAction />} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>,
    );
  }

  test("is used on a device with no saved language, without saving it", async () => {
    renderInApp("?mode=verifyEmail&oobCode=CODE1&lang=cs");

    expect(await screen.findByRole("heading", { name: "Váš e-mail je ověřený" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("cs");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBeNull();
  });

  test("is read from the fragment too", async () => {
    renderInApp("#mode=verifyEmail&oobCode=CODE1&lang=cs");

    expect(await screen.findByRole("heading", { name: "Váš e-mail je ověřený" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("cs");
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBeNull();
  });

  test("never overrides a saved language", async () => {
    languageMocks.hasSavedLanguage.mockReturnValue(true);
    renderInApp("?mode=verifyEmail&oobCode=CODE1&lang=cs");

    expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });

  test.each([["xx"], [""], ["CS"], ["cs-CZ"]])("ignores a lang that is not an app language (%j)", async (lang) => {
    renderInApp(`?mode=verifyEmail&oobCode=CODE1&lang=${lang}`);

    expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });

  test("a link without lang leaves the language alone", async () => {
    renderInApp("?mode=verifyEmail&oobCode=CODE1");

    expect(await screen.findByRole("heading", { name: "Your e-mail is verified" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("en");
  });

  test("an error shown for the link is in that language too", async () => {
    renderInApp("?mode=verifyEmail&lang=cs");

    expect(await screen.findByRole("alert")).toHaveTextContent("Tento odkaz už neplatí. Možná už byl použit.");
  });

  test("a Firebase error is in that language too", async () => {
    // The mocked mapper returns the code, so a dictionary key stands in for
    // Firebase's message.
    firebaseMocks.applyEmailActionCode.mockRejectedValueOnce({ code: "Back to login" });
    renderInApp("?mode=verifyEmail&oobCode=OLD&lang=cs");

    expect(await screen.findByRole("alert")).toHaveTextContent("Zpět na přihlášení");
  });
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
