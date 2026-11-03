import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { sourcePath } from "../test/sourcePath";

import OnboardingPreview, { PREVIEW_EXIT_PATH } from "./OnboardingPreview";

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}{location.search}</output>;
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/onboarding/preview"]}>
      <Routes>
        <Route path="/onboarding/preview" element={<OnboardingPreview />} />
        <Route path="/settings" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>
  );
}

const PREVIEW_SOURCES = [
  new URL("./OnboardingPreview.jsx", import.meta.url),
  new URL("../components/onboarding/OnboardingView.jsx", import.meta.url),
];

describe("OnboardingPreview", () => {
  let fetchSpy;
  let xhrOpenSpy;
  let beaconSpy;

  beforeEach(() => {
    localStorage.clear();
    fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      throw new Error("preview must not fetch");
    });
    xhrOpenSpy = vi.spyOn(XMLHttpRequest.prototype, "open");
    if (!navigator.sendBeacon) navigator.sendBeacon = () => true;
    beaconSpy = vi.spyOn(navigator, "sendBeacon");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never imports the API client, portfolio context or analytics", () => {
    for (const url of PREVIEW_SOURCES) {
      const imports = readFileSync(sourcePath(url), "utf8").match(/from\s+["'][^"']+["']/g) || [];
      for (const statement of imports) {
        expect(statement).not.toMatch(/\/api["']|\/App["']|analytics|axios|firebase/);
      }
    }
  });

  it("walks every choice locally without any network request or stored state", () => {
    mount();

    expect(screen.getByText(/onboarding preview/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /add your first portfolio/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Import a CSV" }));
    expect(screen.getByRole("status")).toHaveTextContent(/opens the csv import/i);

    fireEvent.click(screen.getByRole("button", { name: "Explore sample portfolio" }));
    expect(screen.getByRole("status")).toHaveTextContent(/sample portfolio/i);

    fireEvent.click(screen.getByRole("button", { name: "Connect a broker" }));
    expect(screen.getByRole("status")).toHaveTextContent(/settings → connections/i);

    fireEvent.click(screen.getByRole("button", { name: /start with a blank portfolio/i }));
    expect(screen.getByRole("status")).toHaveTextContent(/empty portfolio/i);
    expect(screen.getByRole("status")).toHaveTextContent(/nothing was created/i);

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(xhrOpenSpy).not.toHaveBeenCalled();
    expect(beaconSpy).not.toHaveBeenCalled();
    expect(localStorage.length).toBe(0);
  });

  it("exits back to Settings preferences", () => {
    mount();

    fireEvent.click(screen.getByRole("link", { name: /exit preview/i }));

    expect(screen.getByLabelText("location")).toHaveTextContent(PREVIEW_EXIT_PATH);
  });
});
