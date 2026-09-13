import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { InsiderTransactionsSection } from "./StockDetail";

const manyTransactions = Array.from({ length: 60 }, (_, i) => ({
  insider: `Person ${i}`,
  side: i % 2 === 0 ? "buy" : "sell",
  shares: 100,
  value: 10000,
  date: "2024-01-01",
  filerType: "director",
}));

describe("InsiderTransactionsSection pagination", () => {
  it("renders at most 25 rows per page", () => {
    render(
      <InsiderTransactionsSection
        transactions={manyTransactions}
        currencyCode="USD"
        currentPrice={100}
      />
    );
    expect(screen.getAllByText(/^Person \d+$/)).toHaveLength(25);
  });

  it("advancing to the next page shows the next 25 rows", () => {
    render(
      <InsiderTransactionsSection
        transactions={manyTransactions}
        currencyCode="USD"
        currentPrice={100}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("Person 25")).toBeInTheDocument();
  });

  it("changing the type filter resets to page 1", () => {
    render(
      <InsiderTransactionsSection
        transactions={manyTransactions}
        currencyCode="USD"
        currentPrice={100}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect(screen.getByText("Person 25")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /buy/i }));
    expect(screen.getByText("Person 0")).toBeInTheDocument();
  });
});
