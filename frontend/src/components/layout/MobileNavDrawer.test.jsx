import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import MobileNavDrawer from "./MobileNavDrawer";
import { NAV_GROUPS } from "./navigation";

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
    render(<MemoryRouter><MobileNavDrawer open onClose={vi.fn()} groups={[{ id: 'test', label: 'Test', items: [
      { ...NAV_GROUPS[0].items[0], preload: first }, { ...NAV_GROUPS[0].items[1], preload: second },
    ] }]} /></MemoryRouter>);
    expect(first).not.toHaveBeenCalled(); expect(second).not.toHaveBeenCalled();
    fireEvent.focus(screen.getByRole('link', { name: 'Dashboard' }));
    await waitFor(() => expect(first).toHaveBeenCalledTimes(1));
    expect(second).not.toHaveBeenCalled();
    fireEvent.mouseEnter(screen.getByRole('link', { name: 'Allocation' }));
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

  it("renders every nav item as a link", () => {
    renderDrawer();
    expect(screen.getByRole("link", { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /assistant/i })).not.toBeInTheDocument();
  });

  it("keeps group headings at least 12px", () => {
    renderDrawer();
    expect(screen.getByRole("heading", { name: NAV_GROUPS[0].label })).toHaveClass("data-label");
  });

  it("closes after a navigation changes the route", () => {
    const onClose = vi.fn();
    renderDrawer(true, onClose);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("link", { name: /allocation/i }));
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
