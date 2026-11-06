import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BottomNavBar, { MORE_KEY } from "./BottomNavBar";
import MobileBottomNav, { activeBarKey } from "./MobileBottomNav";
import { bottomNavChoices } from "./navigation";
import { TRACKER_HOME } from "../../lib/routes";

// The dashboard is "/" in the local edition and "/dashboard" in the cloud one.
const HOME = TRACKER_HOME;
const choices = bottomNavChoices();
const pick = (...paths) => paths.map((to) => choices.find((choice) => choice.to === to));
const slot = (to) => document.querySelector(`[data-slot="${to}"]`);

const bar = (props) => (
  <MemoryRouter>
    <BottomNavBar {...props} />
  </MemoryRouter>
);
const renderBar = (props) => render(bar(props));

// jsdom has no layout: give every bar item a 100px-wide box in DOM order so the
// sliding pill has real, different geometry to move between.
let originals;
beforeEach(() => {
  originals = ["offsetLeft", "offsetWidth", "offsetTop", "offsetHeight", "clientWidth"].map((name) => [
    name,
    Object.getOwnPropertyDescriptor(HTMLElement.prototype, name),
  ]);
  const items = (el) => [...el.closest("div.relative").querySelectorAll("a, button, [role=presentation]")];
  Object.defineProperty(HTMLElement.prototype, "offsetLeft", { configurable: true, get() { return items(this).indexOf(this) * 100; } });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get() { return 100; } });
  Object.defineProperty(HTMLElement.prototype, "offsetTop", { configurable: true, get() { return 0; } });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, get() { return 56; } });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get() { return 600; } });
});
afterEach(() => {
  for (const [name, descriptor] of originals) {
    if (descriptor) Object.defineProperty(HTMLElement.prototype, name, descriptor);
    else delete HTMLElement.prototype[name];
  }
  vi.useRealTimers();
  localStorage.clear();
});

describe("MobileBottomNav with a saved pick", () => {
  it("draws the pages the user chose, in navigation order, plus More", () => {
    localStorage.setItem("sb_bottom_nav_items", JSON.stringify(["/settings", "/cash", "/search"]));
    render(
      <MemoryRouter>
        <MobileBottomNav open={false} onOpenMenu={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual(["Cash", "Search", "Settings"]);
    expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /open navigation menu/i })).toBeInTheDocument();
  });

  it("falls back to the default bar when the saved pick holds too few known pages", () => {
    localStorage.setItem("sb_bottom_nav_items", JSON.stringify(["/tax-report"]));
    render(
      <MemoryRouter>
        <MobileBottomNav open={false} onOpenMenu={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "Dashboard",
      "Positions",
      "Transactions",
      "Dividends",
    ]);
  });
});

describe("activeBarKey", () => {
  const items = pick(HOME, "/allocation", "/cash");

  it("matches the dashboard only on the exact root path", () => {
    expect(activeBarKey(items, HOME)).toBe(HOME);
    expect(activeBarKey(items, "/settings")).toBe(MORE_KEY);
  });

  it("matches nested routes by prefix", () => {
    expect(activeBarKey(items, "/allocation/anything")).toBe("/allocation");
  });

  it("hands the highlight to More while the drawer is open", () => {
    expect(activeBarKey(items, "/cash", true)).toBe(MORE_KEY);
  });
});

describe("BottomNavBar motion", () => {
  it("shows every page at full size without animating on first render", () => {
    renderBar({ items: pick(HOME, "/cash"), activeKey: HOME });
    expect(slot(HOME)).toHaveAttribute("data-phase", "idle");
    expect(slot(HOME).style.flexGrow).toBe("1");
    expect(screen.getByTestId("bottomnav-pill").style.transition).toBe("none");
  });

  it("slides the pill to the page that becomes active", () => {
    const items = pick(HOME, "/cash", "/search");
    const { rerender } = renderBar({ items, activeKey: HOME });
    const pill = screen.getByTestId("bottomnav-pill");
    expect(pill.style.left).toBe("0px");

    rerender(bar({ items, activeKey: "/search" }));

    expect(pill.style.left).toBe("200px");
    // An animated move transitions both edges (the leading one faster).
    expect(pill.style.transition).toMatch(/left .*right /);
    expect(pill.style.transition).not.toBe("none");
  });

  it("moves the pill onto More when the active page leaves the bar", () => {
    const { rerender } = renderBar({ items: pick(HOME, "/cash", "/search"), activeKey: "/search" });
    rerender(bar({ items: pick(HOME, "/cash"), activeKey: MORE_KEY }));
    // The removed page is still collapsing, so More sits after three slots.
    expect(document.querySelectorAll("[data-slot]")).toHaveLength(3);
    expect(screen.getByTestId("bottomnav-pill").style.left).toBe("300px");
  });

  it("collapses a removed page in place and only then unmounts it", () => {
    vi.useFakeTimers();
    const { rerender } = renderBar({ items: pick(HOME, "/allocation", "/cash"), activeKey: HOME });

    rerender(bar({ items: pick(HOME, "/cash"), activeKey: HOME }));

    const leaving = slot("/allocation");
    expect(leaving).toHaveAttribute("data-phase", "leave");
    expect(leaving).toHaveAttribute("aria-hidden", "true");
    expect(leaving).toHaveAttribute("inert");
    expect(leaving.style.flexGrow).toBe("0");
    expect(leaving.style.opacity).toBe("0");
    // It keeps its place between its old neighbours while it shrinks.
    expect([...document.querySelectorAll("[data-slot]")].map((el) => el.dataset.slot)).toEqual([HOME, "/allocation", "/cash"]);

    act(() => vi.advanceTimersByTime(600));
    expect(slot("/allocation")).toBeNull();
    expect(slot(HOME)).toHaveAttribute("data-phase", "idle");
  });

  it("grows an added page from nothing", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "requestAnimationFrame", "cancelAnimationFrame"] });
    const { rerender } = renderBar({ items: pick(HOME, "/cash"), activeKey: HOME });

    rerender(bar({ items: pick(HOME, "/cash", "/search"), activeKey: HOME }));

    expect(slot("/search")).toHaveAttribute("data-phase", "enter");
    expect(slot("/search").style.flexGrow).toBe("0");

    act(() => vi.advanceTimersByTime(100));
    expect(slot("/search")).toHaveAttribute("data-phase", "idle");
    expect(slot("/search").style.flexGrow).toBe("1");
  });

  it("brings back a page that is re-added while it is still collapsing", () => {
    vi.useFakeTimers();
    const full = pick(HOME, "/allocation", "/cash");
    const { rerender } = renderBar({ items: full, activeKey: HOME });
    rerender(bar({ items: pick(HOME, "/cash"), activeKey: HOME }));
    rerender(bar({ items: full, activeKey: HOME }));

    act(() => vi.advanceTimersByTime(600));
    expect(slot("/allocation")).toHaveAttribute("data-phase", "idle");
  });
});

describe("More", () => {
  const lastItem = () => {
    const row = document.querySelector("div.relative");
    return row.lastElementChild.querySelector("button, [role=presentation]");
  };

  it("is always the right-most item, also while pages are added or removed", () => {
    vi.useFakeTimers();
    const { rerender } = renderBar({ items: pick(HOME, "/cash"), activeKey: HOME });
    expect(lastItem()).toHaveTextContent("More");

    rerender(bar({ items: pick(HOME, "/cash", "/search", "/settings"), activeKey: HOME }));
    expect(lastItem()).toHaveTextContent("More");

    rerender(bar({ items: pick(HOME, "/settings"), activeKey: HOME }));
    // /cash and /search are still collapsing here; More stays after them.
    expect(lastItem()).toHaveTextContent("More");
    act(() => vi.advanceTimersByTime(600));
    expect(lastItem()).toHaveTextContent("More");
  });

  it("cannot be switched off in Preferences: it is never offered as a page", () => {
    expect(choices.map((choice) => choice.to)).not.toContain(MORE_KEY);
  });
});

describe("BottomNavBar preview", () => {
  it("is not navigation: no links, and tapping an item reports it", () => {
    const onSelect = vi.fn();
    renderBar({ items: pick(HOME, "/cash"), activeKey: HOME, preview: true, onSelect });
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);

    fireEvent.click(screen.getByText("Cash"));
    expect(onSelect).toHaveBeenCalledWith("/cash");
    fireEvent.click(screen.getByText("More"));
    expect(onSelect).toHaveBeenCalledWith(MORE_KEY);
  });
});
