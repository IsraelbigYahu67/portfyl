import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import Transactions from "./Transactions";

const api = vi.hoisted(() => ({
  fetchTransactionsPage: vi.fn(),
  createTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  fetchAllTradeNotes: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
}));
vi.mock("../components/TradeNoteModal", () => ({ default: () => null }));
vi.mock("../components/ui/ConfirmDialog", () => ({ useConfirm: () => vi.fn() }));
vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/transactions"]}>
        <Transactions />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const page = (overrides = {}) => ({
  items: [
    {
      id: "1",
      date: "2024-01-01",
      ticker: "AAPL",
      type: "buy",
      shares: 10,
      price: 150,
      currency: "USD",
      notes: null,
    },
  ],
  total: 1,
  offset: 0,
  limit: 50,
  ...overrides,
});

describe("Transactions (server-side pagination)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchAllTradeNotes.mockResolvedValue([]);
  });

  it("names the ticker filter for assistive technology", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page());
    renderPage();
    expect(await screen.findByLabelText("Filter transactions by ticker")).toBeInTheDocument();
  });

  it("fetches the paged endpoint with default offset/limit and renders rows", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page());
    renderPage();

    await waitFor(() =>
      expect(api.fetchTransactionsPage).toHaveBeenCalledWith(
        expect.objectContaining({ offset: 0, limit: 50 })
      )
    );
    expect(await screen.findByText("AAPL")).toBeInTheDocument();
  });

  it("resets offset to zero when the filter changes", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page({ total: 200 }));
    renderPage();
    await screen.findByText("AAPL");

    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() =>
      expect(api.fetchTransactionsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 50 })
      )
    );

    fireEvent.change(screen.getByPlaceholderText(/filter by ticker/i), {
      target: { value: "msft" },
    });
    await waitFor(() =>
      expect(api.fetchTransactionsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 0, q: "msft" })
      )
    );
  });

  it("changing page size resets offset and refetches with the new limit", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page({ total: 200 }));
    renderPage();
    await screen.findByText("AAPL");

    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() =>
      expect(api.fetchTransactionsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 50 })
      )
    );

    fireEvent.change(screen.getByLabelText(/rows per page/i), {
      target: { value: "100" },
    });
    await waitFor(() =>
      expect(api.fetchTransactionsPage).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 0, limit: 100 })
      )
    );
  });

  it("shows a distinct message when a filter yields no matches", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page({ items: [], total: 0 }));
    renderPage();
    fireEvent.change(screen.getByPlaceholderText(/filter by ticker/i), {
      target: { value: "zzz" },
    });

    expect(await screen.findByText(/no transactions match/i)).toBeInTheDocument();
  });

  describe("add transaction form", () => {
    async function openAndSubmit() {
      api.fetchTransactionsPage.mockResolvedValue(page());
      renderPage();
      await screen.findByText("AAPL");
      fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
      fireEvent.change(screen.getByPlaceholderText("AAPL"), { target: { value: "MSFT" } });
      fireEvent.change(screen.getByPlaceholderText("10"), { target: { value: "5" } });
      fireEvent.change(screen.getByPlaceholderText("185.50"), { target: { value: "100" } });
      fireEvent.submit(screen.getByPlaceholderText("AAPL").closest("form"));
    }

    it("requires a positive quantity and price in the browser", async () => {
      api.fetchTransactionsPage.mockResolvedValue(page());
      renderPage();
      await screen.findByText("AAPL");
      fireEvent.click(screen.getByRole("button", { name: /^add$/i }));

      for (const placeholder of ["10", "185.50"]) {
        const input = screen.getByPlaceholderText(placeholder);
        fireEvent.change(input, { target: { value: "0" } });
        expect(input.validity.rangeUnderflow).toBe(true);
        fireEvent.change(input, { target: { value: "0.5" } });
        expect(input.validity.valid).toBe(true);
      }
    });

    it("shows a readable message for a 422 with a list of validation errors", async () => {
      api.createTransaction.mockRejectedValue({
        response: {
          status: 422,
          data: {
            detail: [
              { type: "greater_than", loc: ["body", "shares"], msg: "Input should be greater than 0", ctx: { gt: 0 } },
              { type: "string_pattern_mismatch", loc: ["body", "currency"], msg: "String should match pattern" },
            ],
          },
        },
      });
      await openAndSubmit();

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("Shares must be greater than 0");
      expect(alert).toHaveTextContent("Currency has an invalid format");
      expect(screen.getByRole("heading", { name: /add transaction/i })).toBeInTheDocument();
    });

    it("still shows a string detail and falls back when there is no response", async () => {
      api.createTransaction.mockRejectedValueOnce({ response: { data: { detail: "Portfolio not found" } } });
      await openAndSubmit();
      expect(await screen.findByRole("alert")).toHaveTextContent("Portfolio not found");

      api.createTransaction.mockRejectedValueOnce(new Error("Network Error"));
      fireEvent.submit(screen.getByPlaceholderText("AAPL").closest("form"));
      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Failed to add transaction"));
    });
  });
});
