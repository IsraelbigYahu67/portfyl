import { act, fireEvent, render, screen } from "@testing-library/react";

import { MobilePreviewFrame, ViewModeSetting } from "./viewMode";

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("matchMedia", () => ({
    matches: true,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
});
afterEach(() => vi.unstubAllGlobals());

it("renders the app untouched in desktop mode", () => {
  render(<MobilePreviewFrame><p>App</p></MobilePreviewFrame>);

  expect(screen.getByText("App")).toBeInTheDocument();
  expect(screen.queryByTitle("Mobile preview")).not.toBeInTheDocument();
});

it("swaps the app for a phone-sized frame in mobile mode and back again", () => {
  localStorage.setItem("sb_view_mode", "mobile");
  render(<MobilePreviewFrame><p>App</p></MobilePreviewFrame>);

  expect(screen.queryByText("App")).not.toBeInTheDocument();
  expect(screen.getByTitle("Mobile preview")).toHaveStyle({ width: "390px" });

  fireEvent.click(screen.getByRole("button", { name: "Back to desktop" }));

  expect(screen.getByText("App")).toBeInTheDocument();
  expect(localStorage.getItem("sb_view_mode")).toBe("desktop");
});

it("does not frame an already narrow window", () => {
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  localStorage.setItem("sb_view_mode", "mobile");
  render(<MobilePreviewFrame><p>App</p></MobilePreviewFrame>);

  expect(screen.getByText("App")).toBeInTheDocument();
});

it("follows a preference change made in the framed copy", () => {
  render(<MobilePreviewFrame><p>App</p></MobilePreviewFrame>);

  act(() => {
    localStorage.setItem("sb_view_mode", "mobile");
    window.dispatchEvent(new StorageEvent("storage", { key: "sb_view_mode" }));
  });

  expect(screen.getByTitle("Mobile preview")).toBeInTheDocument();
});

it("the settings control persists the chosen mode", () => {
  render(<ViewModeSetting />);

  fireEvent.click(screen.getByRole("button", { name: "View mode: Mobile" }));

  expect(localStorage.getItem("sb_view_mode")).toBe("mobile");
});
