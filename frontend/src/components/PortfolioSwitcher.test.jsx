import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { legacyColorClassesIn } from "../test/legacyClasses";
import PortfolioSwitcher from "./PortfolioSwitcher";

const PORTFOLIOS = [
  { id: "p-1", name: "Main", is_default: true, transaction_count: 3 },
  { id: "p-2", name: "Side", is_default: false, transaction_count: 0 },
];

vi.mock("../App", () => ({
  usePortfolio: () => ({
    activePortfolios: PORTFOLIOS,
    portfolios: PORTFOLIOS,
    current: PORTFOLIOS[0],
    setCurrentId: vi.fn(),
    refetchPortfolios: vi.fn().mockResolvedValue({}),
  }),
}));
vi.mock("../api", () => ({
  createPortfolio: vi.fn(),
  deletePortfolio: vi.fn(),
  updatePortfolio: vi.fn(),
}));
vi.mock("./ui/ConfirmDialog", () => ({ useConfirm: () => vi.fn() }));
vi.mock("./ui/Toast", () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

function renderInSidebar() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <aside data-testid="sidebar">
        <PortfolioSwitcher />
      </aside>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: /switch portfolio/i }));
}

describe("PortfolioSwitcher dialogs", () => {
  it("renders the New portfolio dialog outside the sidebar so it covers the page", () => {
    renderInSidebar();
    fireEvent.click(screen.getByRole("button", { name: "New portfolio" }));

    const dialog = screen.getByRole("dialog", { name: "New portfolio" });
    expect(screen.getByTestId("sidebar")).not.toContainElement(dialog);
    expect(dialog.parentElement.parentElement).toBe(document.body);
    expect(screen.getByRole("textbox", { name: "Portfolio name" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the Rename dialog outside the sidebar and closes on backdrop click", () => {
    renderInSidebar();
    fireEvent.click(screen.getByRole("button", { name: "Rename Side" }));

    const dialog = screen.getByRole("dialog", { name: 'Rename "Side"' });
    expect(screen.getByTestId("sidebar")).not.toContainElement(dialog);
    expect(screen.getByRole("textbox", { name: "Portfolio name" })).toHaveValue("Side");

    fireEvent.mouseDown(dialog.parentElement);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("PortfolioSwitcher rows", () => {
  it("switcher shows the default badge on its own line", () => {
    renderInSidebar();
    const meta = screen.getByText("Default · 3 transactions");
    expect(meta).toHaveClass("text-xs", "text-muted");
    const name = meta.previousElementSibling;
    expect(name).toHaveTextContent(/^Main$/);
    expect(name).toHaveClass("truncate");
    // The name and the meta line stack in a column; the name is not squeezed
    // into the same flex row as the badge.
    expect(meta.parentElement).toHaveClass("flex-col");
    expect(screen.getByText("0 transactions")).toBeInTheDocument();
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./PortfolioSwitcher.jsx", import.meta.url))).toEqual([]);
  });
});
