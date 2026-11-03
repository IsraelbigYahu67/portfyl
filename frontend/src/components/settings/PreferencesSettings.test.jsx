import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import PreferencesSettings from "./PreferencesSettings";
import { legacyColorClassesIn } from "../../test/legacyClasses";

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

  expect(context.setThemeStyle).toHaveBeenCalledWith("neu");
  expect(context.setTheme).toHaveBeenCalledWith("dark");
  expect(context.setPalette).toHaveBeenCalledWith("purple");
  expect(context.setCurrency).toHaveBeenCalledWith("USD");
  expect(screen.getByText("1 USD = 22.75 Kc")).toBeInTheDocument();
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

  expect(screen.getByRole("link", { name: /replay onboarding/i })).toHaveAttribute("href", "/onboarding/preview");
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./PreferencesSettings.jsx", import.meta.url))).toEqual([]);
});
