import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import WelcomePanel from "./WelcomePanel";

const items = () => [
  { id: "first_portfolio", done: true, to: "/import" },
  { id: "second_broker", done: false, to: "/import" },
  { id: "preferences", done: false, to: "/settings?section=preferences" },
  { id: "dividends", done: false, to: "/dividends" },
];

function renderPanel(props = {}) {
  const handlers = { onVisit: vi.fn(), onDismiss: vi.fn() };
  const view = render(
    <MemoryRouter>
      <WelcomePanel items={items()} insight="You hold 3 positions." {...handlers} {...props} />
    </MemoryRouter>,
  );
  return { ...handlers, ...view };
}

describe("WelcomePanel", () => {
  it("shows the heading, the progress and every item", () => {
    renderPanel();
    expect(screen.getByText("Getting started")).toBeInTheDocument();
    expect(screen.getByText("1 of 4 done")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Add another broker for one combined view/ })).toHaveAttribute("href", "/import");
    expect(screen.getByRole("link", { name: /Check language and currency/ })).toHaveAttribute("href", "/settings?section=preferences");
    expect(screen.getByRole("link", { name: /See your dividend calendar/ })).toHaveAttribute("href", "/dividends");
    expect(screen.getByText(/Add your first portfolio/)).toBeInTheDocument();
    expect(screen.getByText("You hold 3 positions.")).toBeInTheDocument();
  });

  it("reports a visit when an item is clicked", () => {
    const { onVisit } = renderPanel();
    fireEvent.click(screen.getByRole("link", { name: /See your dividend calendar/ }));
    expect(onVisit).toHaveBeenCalledWith("dividends");
  });

  it("hides on request", () => {
    const { onDismiss } = renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when every item is done", () => {
    const done = items().map((item) => ({ ...item, done: true }));
    const { container } = renderPanel({ items: done });
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing without items", () => {
    const { container } = renderPanel({ items: [] });
    expect(container).toBeEmptyDOMElement();
  });
});
