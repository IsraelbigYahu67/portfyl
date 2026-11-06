import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import MobileBottomNav from "./MobileBottomNav";
import MobileTopBar from "./MobileTopBar";
import { BOTTOM_NAV_ITEMS, NAV_GROUPS } from "./navigation";

vi.mock("../PortfolioSwitcher", () => ({ default: ({ compact }) => <div>Portfolio switcher{compact ? " (compact)" : ""}</div> }));
vi.mock("../AccountMenu", () => ({ default: ({ compact }) => <div>Account menu{compact ? " (compact)" : ""}</div> }));

function renderNav(props = {}, path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MobileBottomNav open={false} onOpenMenu={vi.fn()} {...props} />
    </MemoryRouter>,
  );
}

describe("MobileBottomNav", () => {
  it("links the four main pages and a More button", () => {
    renderNav();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(nav).toHaveClass("lg:hidden");
    for (const { label } of BOTTOM_NAV_ITEMS) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /open navigation menu/i })).toHaveTextContent("More");
  });

  it("only links pages that also exist in the full navigation", () => {
    const all = new Set(NAV_GROUPS.flatMap((g) => g.items.map((i) => i.to)));
    for (const { to } of BOTTOM_NAV_ITEMS) expect(all.has(to)).toBe(true);
  });

  it("marks the current page and leaves More inactive on a primary page", () => {
    renderNav({}, "/transactions");
    expect(screen.getByRole("link", { name: "Transactions" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /open navigation menu/i })).not.toHaveClass("text-brand");
  });

  it("highlights More on a page that is not in the bar", () => {
    renderNav({}, "/settings");
    expect(screen.getByRole("button", { name: /open navigation menu/i })).toHaveClass("text-brand");
  });

  it("opens the drawer and reports its expanded state", () => {
    const onOpenMenu = vi.fn();
    const { rerender } = renderNav({ onOpenMenu });
    const more = screen.getByRole("button", { name: /open navigation menu/i });
    expect(more).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(more);
    expect(onOpenMenu).toHaveBeenCalledTimes(1);
    rerender(<MemoryRouter><MobileBottomNav open onOpenMenu={onOpenMenu} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /open navigation menu/i })).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps each target at least 56px tall", () => {
    renderNav();
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveClass("min-h-14");
  });
});

describe("MobileTopBar", () => {
  it("is sticky and carries the portfolio switcher and the account menu", () => {
    render(<MemoryRouter><MobileTopBar /></MemoryRouter>);
    const bar = screen.getByRole("banner");
    expect(bar).toHaveClass("sticky", "lg:hidden");
    expect(screen.getByText("Portfolio switcher (compact)")).toBeInTheDocument();
    expect(screen.getByText("Account menu (compact)")).toBeInTheDocument();
  });
});
