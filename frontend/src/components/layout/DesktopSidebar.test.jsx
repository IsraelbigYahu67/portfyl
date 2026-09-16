import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import DesktopSidebar from "./DesktopSidebar";
import { NAV_GROUPS } from "./navigation";

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

function renderSidebar(groups = NAV_GROUPS) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DesktopSidebar groups={groups} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DesktopSidebar", () => {
  it('preloads only the hovered or focused destination', async () => {
    const first = vi.fn().mockResolvedValue({}), second = vi.fn().mockRejectedValue(new Error('offline'));
    renderSidebar([{ id: 'test', label: 'Test', items: [
      { ...NAV_GROUPS[0].items[0], preload: first }, { ...NAV_GROUPS[0].items[1], preload: second },
    ] }]);
    expect(first).not.toHaveBeenCalled(); expect(second).not.toHaveBeenCalled();
    fireEvent.mouseEnter(screen.getByRole('link', { name: 'Dashboard' }));
    await waitFor(() => expect(first).toHaveBeenCalledTimes(1));
    expect(second).not.toHaveBeenCalled();
    fireEvent.focus(screen.getByRole('link', { name: 'Allocation' }));
    await waitFor(() => expect(second).toHaveBeenCalledTimes(1));
  });
  it("renders every group label as a heading", () => {
    renderSidebar();
    for (const group of NAV_GROUPS) {
      expect(screen.getByRole("heading", { name: group.label })).toBeInTheDocument();
    }
  });

  it("renders every item as an accessible nav link", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /ai assistant/i })).toBeInTheDocument();
  });

  it("does not render an Overview link", () => {
    renderSidebar();
    expect(screen.queryByRole("link", { name: /^overview$/i })).not.toBeInTheDocument();
  });

  it("renders the nav landmark with an accessible name", () => {
    renderSidebar();
    expect(screen.getByRole("navigation", { name: /primary/i })).toBeInTheDocument();
  });

  it("keeps portfolio and account controls but no longer renders device preferences", () => {
    renderSidebar();
    expect(screen.getByText("Portfolio switcher")).toBeInTheDocument();
    expect(screen.getByText("Account menu")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Theme style" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /display currency/i })).not.toBeInTheDocument();
  });
});
