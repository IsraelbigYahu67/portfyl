import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import Register from "./Register";
import AnalyticsProvider from "../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../analytics/analyticsClient";
import { I18nProvider } from "../i18n/I18nProvider";
import { LANGUAGE_STORAGE_KEY, initialLanguage } from "../i18n/languages";
import { INTENDED_BROKER_KEY } from "../lib/signupIntent";
import de from "../i18n/messages/de.js";
import cs from "../i18n/messages/cs.js";

vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ loginWithIdToken: vi.fn() }),
}));

vi.mock("../auth/firebase", () => ({
  registerWithEmailPassword: vi.fn(),
  sendVerificationEmail: vi.fn(),
  mapFirebaseAuthError: vi.fn(() => "Something went wrong. Please try again."),
  isGoogleSignInEnabled: vi.fn(() => false),
  prepareGoogleSignIn: vi.fn(() => Promise.resolve()),
  signInWithGoogle: vi.fn(),
}));

const HEADING = "Create your Portfyl account";

function renderRegister(path, initial = "en") {
  const adapter = createMemoryAdapter();
  const adapterFactory = () => adapter;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <I18nProvider initial={initial}>
        <AnalyticsProvider initialConsent="accepted" adapterFactory={adapterFactory}>
          <Routes>
            <Route path="/register" element={<Register />} />
          </Routes>
        </AnalyticsProvider>
      </I18nProvider>
    </MemoryRouter>
  );
}

afterEach(() => localStorage.clear());

describe("Register signup intent", () => {
  test("stores the broker from the URL", () => {
    renderRegister("/register?broker=xtb&lang=de");
    expect(localStorage.getItem(INTENDED_BROKER_KEY)).toBe("xtb");
  });

  test("does not store an unsupported broker", () => {
    renderRegister("/register?broker=robinhood");
    expect(localStorage.getItem(INTENDED_BROKER_KEY)).toBeNull();
  });

  test("switches to the URL language when none is saved", async () => {
    renderRegister("/register?broker=xtb&lang=de");
    expect(await screen.findByRole("heading", { name: de[HEADING] })).toBeInTheDocument();
  });

  test("keeps a saved language over the URL", async () => {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, "cs");
    renderRegister("/register?broker=xtb&lang=de", initialLanguage);
    expect(await screen.findByRole("heading", { name: cs[HEADING] })).toBeInTheDocument();
    // Applying the URL's German would have saved it over the user's choice.
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("cs");
    expect(screen.queryByRole("heading", { name: de[HEADING] })).not.toBeInTheDocument();
  });
});
