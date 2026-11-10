import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { formatTableDate } from "../lib/format";
import { legacyColorClassesIn } from "../test/legacyClasses";
import { InsiderTransactionsSection } from "./StockDetail";

const api = vi.hoisted(() => ({}));
vi.mock("../api", () => api);

function withClient(ui) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("insider transactions", () => {
  const otherRow = {
    insider: "Jane Doe",
    side: "other",
    shares: 500,
    value: 0,
    date: "2026-10-13",
    transaction: "Stock Gift",
  };

  it("insider rows without a price show a dash", () => {
    render(<InsiderTransactionsSection transactions={[otherRow]} currencyCode="USD" currentPrice={100} />);
    const row = screen.getByText("Jane Doe").closest("li");
    expect(row.textContent).not.toMatch(/\$0/);
    // Price, Value and P&L are all unknown for a zero-value grant.
    expect(within(row).getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("insider dates use table format", () => {
    render(<InsiderTransactionsSection transactions={[otherRow]} currencyCode="USD" currentPrice={100} />);
    const row = screen.getByText("Jane Doe").closest("li");
    expect(within(row).getByText(formatTableDate("2026-10-13"))).toBeInTheDocument();
  });

  it("does not tint whole sell rows red", () => {
    const sell = { ...otherRow, insider: "Sam Seller", side: "sell", shares: 10, value: 1000 };
    render(<InsiderTransactionsSection transactions={[sell]} currencyCode="USD" currentPrice={100} />);
    const row = screen.getByText("Sam Seller").closest("li");
    expect(row.className).not.toMatch(/bg-(red|loss)/);
    expect(within(row).getByText("Sell").dataset.tone).toBe("loss");
  });
});

describe("Clay colors", () => {
  it("StockDetail.jsx uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./StockDetail.jsx", import.meta.url))).toEqual([]);
  });
});
