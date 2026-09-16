import { fireEvent, render, screen } from "@testing-library/react";

import PreferencesSettings from "./PreferencesSettings";

const context = vi.hoisted(() => ({
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
    themeStyle: "glass",
    setThemeStyle: context.setThemeStyle,
  }),
}));

beforeEach(() => vi.clearAllMocks());

it("uses the existing context setters for every device preference", () => {
  render(<PreferencesSettings />);

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

