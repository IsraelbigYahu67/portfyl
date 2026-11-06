import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import BottomNavSetting from "./BottomNavSetting";
import { NavGroupsContext } from "../layout/NavGroupsContext";
import { NAV_GROUPS } from "../layout/navigation";
import { TRACKER_HOME } from "../../lib/routes";

const KEY = "sb_bottom_nav_items";
const stored = () => JSON.parse(localStorage.getItem(KEY));
const chip = (label) => screen.getByRole("button", { name: `Bottom bar: ${label}` });

function renderSetting(groups = NAV_GROUPS) {
  return render(
    <MemoryRouter>
      <NavGroupsContext.Provider value={groups}>
        <BottomNavSetting />
      </NavGroupsContext.Provider>
    </MemoryRouter>,
  );
}

afterEach(() => localStorage.clear());

describe("BottomNavSetting", () => {
  it("starts on the default four pages", () => {
    renderSetting();
    for (const label of ["Dashboard", "Positions", "Transactions", "Dividends"]) {
      expect(chip(label)).toHaveAttribute("aria-pressed", "true");
    }
    expect(chip("Cash")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/4 of 5 pages/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled();
  });

  it("adds a page and keeps the stored list in navigation order", () => {
    renderSetting();
    fireEvent.click(chip("Cash"));
    expect(stored()).toEqual([TRACKER_HOME, "/allocation", "/transactions", "/cash", "/dividends"]);
    expect(chip("Cash")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/5 of 5 pages/)).toBeInTheDocument();
  });

  it("removes a page", () => {
    renderSetting();
    fireEvent.click(chip("Dividends"));
    expect(stored()).toEqual([TRACKER_HOME, "/allocation", "/transactions"]);
    expect(chip("Dividends")).toHaveAttribute("aria-pressed", "false");
  });

  it("stops at five pages: the rest are disabled until one is removed", () => {
    renderSetting();
    fireEvent.click(chip("Cash"));
    expect(chip("Search")).toBeDisabled();
    expect(chip("Search")).toHaveAttribute("title", expect.stringMatching(/up to 5/));
    fireEvent.click(chip("Cash"));
    expect(chip("Search")).toBeEnabled();
  });

  it("keeps at least two pages", () => {
    renderSetting();
    fireEvent.click(chip("Dividends"));
    fireEvent.click(chip("Transactions"));
    expect(stored()).toEqual([TRACKER_HOME, "/allocation"]);
    expect(chip("Dashboard")).toBeDisabled();
    expect(chip("Positions")).toBeDisabled();
    expect(chip("Dashboard")).toHaveAttribute("title", expect.stringMatching(/at least 2/));
  });

  it("resets to the default bar", () => {
    renderSetting();
    fireEvent.click(chip("Cash"));
    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(localStorage.getItem(KEY)).toBeNull();
    expect(chip("Cash")).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/4 of 5 pages/)).toBeInTheDocument();
  });

  it("previews the very bar the phone shows, and updates it live", () => {
    renderSetting();
    const preview = screen.getByTestId("bottom-nav-preview");
    expect(preview).toHaveAttribute("aria-hidden", "true");
    expect(within(preview).getByText("Positions")).toBeInTheDocument();
    expect(within(preview).queryByText("Cash")).not.toBeInTheDocument();

    fireEvent.click(chip("Cash"));
    expect(within(preview).getByText("Cash")).toBeInTheDocument();

    fireEvent.click(within(preview).getByText("Positions"));
    expect(preview.querySelector('[data-slot="/allocation"] [role="presentation"]')).toHaveClass("text-brand");
  });

  it("only offers pages this edition has", () => {
    const withoutCash = NAV_GROUPS.map((group) => ({
      ...group,
      items: group.items.filter(({ to }) => to !== "/cash"),
    }));
    renderSetting(withoutCash);
    expect(screen.queryByRole("button", { name: "Bottom bar: Cash" })).not.toBeInTheDocument();
    expect(chip("Dashboard")).toBeInTheDocument();
  });
});
