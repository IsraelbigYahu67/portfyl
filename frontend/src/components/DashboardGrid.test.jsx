import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import DashboardGrid, { ALL_WIDGETS, normalizeWidgetOrder, swapLayoutPositions } from "./DashboardGrid";

const ORDER_KEY = "sb_dashboard_widget_order_v2";
const HIDDEN_KEY = "sb_dashboard_widgets_hidden";
const LAYOUT_KEY = "sb_dashboard_layout";

const children = Object.fromEntries(
  ALL_WIDGETS.map((w) => [
    w.id,
    <div key={w.id} data-testid={`child-${w.id}`}>{w.label} body</div>,
  ])
);

function renderGrid(props = {}) {
  return render(<DashboardGrid {...props}>{children}</DashboardGrid>);
}

function domOrder(container) {
  return Array.from(container.querySelectorAll('[data-testid^="child-"]'))
    .map((el) => el.getAttribute("data-testid").replace("child-", ""));
}

describe("normalizeWidgetOrder", () => {
  it("drops unknown ids, dedupes, and appends missing known ids", () => {
    expect(normalizeWidgetOrder(["retired", "movers", "movers", "performance"], ["performance", "movers", "attention"]))
      .toEqual(["movers", "performance", "attention"]);
  });
});

describe("DashboardGrid", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("discards a retired stored widget and keeps the saved order", () => {
    localStorage.setItem(ORDER_KEY, JSON.stringify(["retired-widget", "movers", "performance"]));
    const { container } = renderGrid();

    expect(screen.queryByTestId("child-retired-widget")).not.toBeInTheDocument();
    expect(domOrder(container)[0]).toBe("movers");
    expect(domOrder(container)[1]).toBe("performance");
  });

  it("moves a widget with a labelled control and persists the order", () => {
    localStorage.setItem(ORDER_KEY, JSON.stringify(["movers", "performance"]));
    const { container } = renderGrid({ editing: true });

    fireEvent.click(screen.getByRole("button", { name: /move performance up/i }));

    expect(JSON.parse(localStorage.getItem(ORDER_KEY))[0]).toBe("performance");
    expect(domOrder(container)[0]).toBe("performance");
  });

  it("moves a default-grid widget visually and keeps the new reading order", () => {
    const { container } = renderGrid({ editing: true });

    fireEvent.click(screen.getByRole("button", { name: /move concentration up/i }));

    expect(domOrder(container)[0]).toBe("concentration");
    expect(JSON.parse(localStorage.getItem(ORDER_KEY))[0]).toBe("concentration");
    const storedLayout = JSON.parse(localStorage.getItem(LAYOUT_KEY)).lg;
    expect(storedLayout.find((item) => item.i === "concentration").y).toBe(0);
    expect(storedLayout.find((item) => item.i === "performance").y).toBe(5);
  });

  it("hides and restores a widget via named, focusable buttons", () => {
    renderGrid({ editing: true });

    fireEvent.click(screen.getByRole("button", { name: /hide top movers/i }));
    expect(screen.queryByTestId("child-movers")).not.toBeInTheDocument();

    const restore = screen.getByRole("button", { name: /restore top movers/i });
    expect(restore).toBeEnabled();
    fireEvent.click(restore);

    expect(screen.getByTestId("child-movers")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(HIDDEN_KEY))).toEqual([]);
  });

  it("renders one DOM column/order in non-edit mode even with stored grid coordinates", () => {
    localStorage.setItem(
      LAYOUT_KEY,
      JSON.stringify({ lg: [{ i: "insiderBuys", x: 0, y: 0, w: 6, h: 5 }, { i: "performance", x: 0, y: 99, w: 6, h: 5 }] })
    );
    const { container } = renderGrid();

    expect(domOrder(container)).toEqual(ALL_WIDGETS.map((w) => w.id));
  });
});

describe("swapLayoutPositions", () => {
  it("swaps coordinates without changing widget dimensions", () => {
    const layouts = {
      lg: [
        { i: "performance", x: 0, y: 0, w: 6, h: 5 },
        { i: "attention", x: 0, y: 5, w: 6, h: 4 },
      ],
    };

    const swapped = swapLayoutPositions(layouts, "attention", "performance");

    expect(swapped.lg).toEqual([
      { i: "performance", x: 0, y: 5, w: 6, h: 5 },
      { i: "attention", x: 0, y: 0, w: 6, h: 4 },
    ]);
  });
});
