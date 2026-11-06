import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AppShell from "./AppShell";
import { resetRouteFocusAnnouncerForTests } from "../../hooks/useRouteFocusAnnouncer";
import { NAV_GROUPS } from "./navigation";

// The focus announcer remembers the last path across mounts; start each test fresh.
beforeEach(resetRouteFocusAnnouncerForTests);

vi.mock("../../App", () => ({
  useCurrency: () => ({ currency: "USD", setCurrency: vi.fn(), rate: 21, rateLoading: false }),
  usePalette: () => ({
    palette: "blue",
    setPalette: vi.fn(),
    theme: "light",
    setTheme: vi.fn(),
    themeStyle: "glass",
    setThemeStyle: vi.fn(),
  }),
}));
vi.mock("../PortfolioSwitcher", () => ({ default: () => <div>Portfolio switcher</div> }));
vi.mock("../AccountMenu", () => ({ default: () => <div>Account menu</div> }));

function renderShell(children = <h1>Test Page</h1>) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AppShell groups={NAV_GROUPS}>
          {children}
        </AppShell>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  it("renders a skip link targeting #main-content", () => {
    renderShell();
    expect(screen.getByRole("link", { name: /skip to main content/i }))
      .toHaveAttribute("href", "#main-content");
  });

  it("renders exactly one main landmark with the shared id", () => {
    renderShell();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
  });

  it("renders the page content inside main", () => {
    renderShell();
    expect(screen.getByRole("heading", { name: "Test Page" })).toBeInTheDocument();
  });

  it("opens and closes the mobile drawer from the bottom bar More button", () => {
    renderShell();
    const trigger = screen.getByRole("button", { name: /open navigation menu/i });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("dialog", { name: /navigation/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /close navigation menu/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps focus on page content after navigation from the drawer", () => {
    renderShell(
      <Routes>
        <Route path="/" element={<h1>Test Page</h1>} />
        <Route path="/cash" element={<h1>Cash Page</h1>} />
      </Routes>,
    );
    fireEvent.click(screen.getByRole("button", { name: /open navigation menu/i }));
    // Cash is not in the default bottom bar, so it is listed under More.
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("link", { name: /cash/i }));
    expect(screen.getByRole("heading", { name: "Cash Page" })).toHaveFocus();
  });

  it("does not render fixed viewport-height classes anywhere in the shell", () => {
    const { container } = renderShell();
    expect(container.innerHTML).not.toMatch(/\bh-screen\b/);
    expect(container.innerHTML).not.toMatch(/\bmax-h-screen\b/);
  });
});
