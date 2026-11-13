import { readFileSync } from "node:fs";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import PreferencesSettings from "./PreferencesSettings";
import { I18nProvider } from "../../i18n/I18nProvider";
import { legacyColorClassesIn } from "../../test/legacyClasses";
import { sourcePath } from "../../test/sourcePath";

const context = vi.hoisted(() => ({
  themeStyle: "glass",
  setCurrency: vi.fn(),
  setPalette: vi.fn(),
  setTheme: vi.fn(),
  setThemeStyle: vi.fn(),
}));

vi.mock("../../App", () => ({
  useCurrency: () => ({ currency: "CZK", setCurrency: context.setCurrency, rate: 22.75, rateLoading: false }),
  usePalette: () => ({
    palette: "green",
    setPalette: context.setPalette,
    theme: "system",
    setTheme: context.setTheme,
    themeStyle: context.themeStyle,
    setThemeStyle: context.setThemeStyle,
  }),
}));

function renderPreferences() {
  return render(<MemoryRouter><PreferencesSettings /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  context.themeStyle = "glass";
});

it("uses the existing context setters for every device preference", () => {
  renderPreferences();

  fireEvent.click(screen.getByRole("button", { name: "Warm glass-hybrid theme" }));
  fireEvent.click(screen.getByRole("button", { name: "Dark" }));
  fireEvent.click(screen.getByRole("button", { name: "Theme: Soft Iris" }));
  fireEvent.click(screen.getByRole("button", { name: "Display currency: USD" }));
  fireEvent.click(screen.getByRole("button", { name: "Display currency: EUR" }));
  fireEvent.click(screen.getByRole("button", { name: "Display currency: PLN" }));

  expect(context.setThemeStyle).toHaveBeenCalledWith("neu");
  expect(context.setTheme).toHaveBeenCalledWith("dark");
  expect(context.setPalette).toHaveBeenCalledWith("purple");
  expect(context.setCurrency).toHaveBeenCalledWith("USD");
  expect(context.setCurrency).toHaveBeenCalledWith("EUR");
  expect(context.setCurrency).toHaveBeenCalledWith("PLN");
  expect(screen.getByText("1 USD = 22.75 Kč")).toBeInTheDocument();
});

it("offers Clay as a third theme style next to Premium", () => {
  renderPreferences();

  fireEvent.click(screen.getByRole("button", { name: "Soft clay theme" }));

  expect(context.setThemeStyle).toHaveBeenCalledWith("clay");
});

it("Clay hides appearance and accent palette", () => {
  context.themeStyle = "clay";
  renderPreferences();

  expect(screen.queryByRole("heading", { name: "Appearance" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Accent palette" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Theme: Soft Iris" })).not.toBeInTheDocument();
  expect(screen.getByText("Clay uses its own light palette.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Display currency" })).toBeInTheDocument();
});

it("keeps appearance and accent palette for Classic and Premium", () => {
  for (const style of ["glass", "neu"]) {
    context.themeStyle = style;
    const { unmount } = renderPreferences();
    expect(screen.getByRole("heading", { name: "Appearance" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Accent palette" })).toBeInTheDocument();
    expect(screen.queryByText("Clay uses its own light palette.")).not.toBeInTheDocument();
    unmount();
  }
});

it("renders the accent palette choices as pills", () => {
  renderPreferences();

  expect(screen.getByRole("button", { name: "Theme: Soft Iris" })).toHaveClass("rounded-full");
});

it("links to the local-only onboarding preview", () => {
  renderPreferences();

  const link = screen.getByRole("link", { name: /replay onboarding/i });
  expect(link).toHaveAttribute("href", "/onboarding/preview");
  // Secondary action: the shared ghost pill (raised in Clay), not a hand-built one.
  expect(link).toHaveClass("btn-ghost");
});

it("takes the preview path from lib/routes, not the lazy route registry that loads Settings", () => {
  const source = readFileSync(sourcePath(new URL("./PreferencesSettings.jsx", import.meta.url)), "utf8");
  expect(source).not.toMatch(/routes\/authenticatedRoutes/);
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./PreferencesSettings.jsx", import.meta.url))).toEqual([]);
});

it("changes the app language from the Language picker", async () => {
  render(<I18nProvider initial="en"><MemoryRouter><PreferencesSettings /></MemoryRouter></I18nProvider>);

  const picker = screen.getByRole("combobox", { name: "Language" });
  expect(picker).toHaveValue("en");
  expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
    "Čeština", "English", "Deutsch", "Français", "Español", "Italiano", "Português", "Polski", "Nederlands",
  ]);

  fireEvent.change(picker, { target: { value: "cs" } });

  expect(await screen.findByRole("heading", { name: "Preference" })).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Jazyk" })).toHaveValue("cs");
  expect(localStorage.getItem("portfyl_language")).toBe("cs");
  localStorage.clear();
});
