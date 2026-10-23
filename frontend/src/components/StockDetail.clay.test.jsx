import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { formatTableDate } from "../lib/format";
import { legacyColorClassesIn } from "../test/legacyClasses";
import { InsiderTransactionsSection, ShibuiFilingsSection } from "./StockDetail";
import { StockFilingsTab } from "./stock/StockFilingsTab";

const api = vi.hoisted(() => ({ fetchShibuiFilings: vi.fn() }));
vi.mock("../api", () => api);

const FILINGS = [
  { filing_date: "2025-02-01", raw_form_type: "10-Q", form_type: "10-Q", filing_url: "https://sec.example/a" },
  { filing_date: "2026-03-05", raw_form_type: "10-K", form_type: "10-K", filing_url: "https://sec.example/b" },
  { filing_date: "2025-11-20", raw_form_type: "8-K", form_type: "8-K", filing_url: "https://sec.example/c" },
  { filing_date: "2025-06-30", raw_form_type: "4", form_type: "4", filing_url: "https://sec.example/d" },
];

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
    expect(within(row).getByText("SELL").dataset.tone).toBe("loss");
  });
});

describe("filings", () => {
  it("filings are sorted newest first and explain form types", async () => {
    api.fetchShibuiFilings.mockResolvedValue({ filings: FILINGS });
    withClient(<StockFilingsTab ticker="AAPL" />);

    const rows = await screen.findAllByRole("listitem");
    expect(rows.map((row) => row.querySelector("time").textContent)).toEqual([
      formatTableDate("2026-03-05"),
      formatTableDate("2025-11-20"),
      formatTableDate("2025-06-30"),
      formatTableDate("2025-02-01"),
    ]);
    expect(within(rows[0]).getByText("Annual report")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Current report")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Insider transaction")).toBeInTheDocument();
    expect(within(rows[3]).getByText("Quarterly report")).toBeInTheDocument();
  });

  it("the expandable SEC filings list is also newest first", async () => {
    api.fetchShibuiFilings.mockResolvedValue({ filings: FILINGS });
    withClient(<ShibuiFilingsSection ticker="AAPL" />);

    fireEvent.click(await screen.findByRole("button", { name: /SEC Filings/i }));
    const dates = screen.getAllByRole("listitem").map((row) => row.querySelector("time").textContent);
    expect(dates).toEqual([
      formatTableDate("2026-03-05"),
      formatTableDate("2025-11-20"),
      formatTableDate("2025-06-30"),
      formatTableDate("2025-02-01"),
    ]);
  });
});

describe("Clay colors", () => {
  it("StockDetail.jsx uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./StockDetail.jsx", import.meta.url))).toEqual([]);
  });
});
