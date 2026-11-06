import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import MobileNavDrawer from "./MobileNavDrawer";
import { NAV_GROUPS } from "./navigation";
import { TRACKER_HOME } from "../../lib/routes";

vi.mock("../AccountMenu", () => ({ default: () => <div>Account menu</div> }));

function renderDrawer(open = true, onClose = vi.fn()) {
  return render(
    <MemoryRouter>
      <button>Menu trigger</button>
      <MobileNavDrawer groups={NAV_GROUPS} open={open} onClose={onClose} />
    </MemoryRouter>,
  );
}

describe("MobileNavDrawer", () => {
  it('preloads just the destination receiving focus or pointer intent', async () => {
    const first = vi.fn().mockResolvedValue({}), second = vi.fn().mockRejectedValue(new Error('offline'));
    // Cash and Search: neither is in the default bottom bar, so both are listed.
    const research = NAV_GROUPS.find((g) => g.id === 'research').items[0];
    const cash = NAV_GROUPS.find((g) => g.id === 'portfolio').items.find((i) => i.to === '/cash');
    render(<MemoryRouter><MobileNavDrawer open onClose={vi.fn()} groups={[{ id: 'test', label: 'Test', items: [
      { ...cash, preload: first }, { ...research, preload: second },
    ] }]} /></MemoryRouter>);
    expect(first).not.toHaveBeenCalled(); expect(second).not.toHaveBeenCalled();
    fireEvent.focus(screen.getByRole('link', { name: 'Cash' }));
    await waitFor(() => expect(first).toHaveBeenCalledTimes(1));
    expect(second).not.toHaveBeenCalled();
    fireEvent.mouseEnter(screen.getByRole('link', { name: 'Search' }));
    await waitFor(() => expect(second).toHaveBeenCalledTimes(1));
  });
  it("renders nothing when closed", () => {
    renderDrawer(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders as a labelled modal dialog when open", () => {
    renderDrawer();
    const dialog = screen.getByRole("dialog", { name: /navigation/i });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("calls onClose on Escape", () => {
    const onClose = vi.fn();
    renderDrawer(true, onClose);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    renderDrawer(true, onClose);
    fireEvent.mouseDown(screen.getByTestId("mobile-nav-backdrop"));
    expect(onClose).toHaveBeenCalled();
  });

  it("lists every nav item that is not already in the bottom bar", () => {
    renderDrawer();
    expect(screen.getByRole("link", { name: /cash/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /assistant/i })).not.toBeInTheDocument();
    // The default bar holds these four, so More does not repeat them.
    for (const name of [/dashboard/i, /allocation/i, /transactions/i, /dividends/i]) {
      expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
    }
  });

  it("lists a page again once the user takes it out of their bar", () => {
    localStorage.setItem("sb_bottom_nav_items", JSON.stringify([TRACKER_HOME, "/allocation"]));
    try {
      renderDrawer();
      expect(screen.getByRole("link", { name: /transactions/i })).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /dividends/i })).toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /dashboard/i })).not.toBeInTheDocument();
    } finally {
      localStorage.removeItem("sb_bottom_nav_items");
    }
  });

  it("keeps group headings at least 12px", () => {
    renderDrawer();
    expect(screen.getByRole("heading", { name: NAV_GROUPS[0].label })).toHaveClass("data-label");
  });

  it("closes after a navigation changes the route", () => {
    const onClose = vi.fn();
    renderDrawer(true, onClose);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: /cash/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("MobileNavDrawer surface", () => {
  it("is fully opaque over the page and keeps log out reachable", () => {
    renderDrawer();
    // Opacity lives in the .app-drawer rule (a solid page colour under the
    // translucent card token); the panel must not set its own see-through fill.
    const dialog = screen.getByRole("dialog", { name: /navigation/i });
    expect(dialog).toHaveClass("app-drawer");
    expect(dialog.className).not.toMatch(/bg-surface-card/);
    expect(within(dialog).getByText("Account menu")).toBeInTheDocument();
  });
});
