import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import Transactions from "./Transactions";
import { legacyColorClassesIn } from "../test/legacyClasses";

const api = vi.hoisted(() => ({
  fetchTransactionsPage: vi.fn(),
  createTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  fetchAllTradeNotes: vi.fn(),
}));

const currencyState = vi.hoisted(() => ({ currency: "USD" }));

vi.mock("../api", () => api);
vi.mock("../App", () => ({ useCurrency: () => ({ currency: currencyState.currency, rate: 22 }) }));
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
    currencyState.currency = "USD";
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
    expect((await screen.findAllByText("AAPL")).length).toBeGreaterThan(0);
  });

  it("resets offset to zero when the filter changes", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page({ total: 200 }));
    renderPage();
    await screen.findAllByText("AAPL");

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
    await screen.findAllByText("AAPL");

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
      await screen.findAllByText("AAPL");
      fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
      fireEvent.change(screen.getByPlaceholderText("e.g. AAPL"), { target: { value: "MSFT" } });
      fireEvent.change(screen.getByPlaceholderText("e.g. 10"), { target: { value: "5" } });
      fireEvent.change(screen.getByPlaceholderText("e.g. 185.50"), { target: { value: "100" } });
      fireEvent.submit(screen.getByPlaceholderText("e.g. AAPL").closest("form"));
    }

    it("requires a positive quantity and price in the browser", async () => {
      api.fetchTransactionsPage.mockResolvedValue(page());
      renderPage();
      await screen.findAllByText("AAPL");
      fireEvent.click(screen.getByRole("button", { name: /^add$/i }));

      for (const placeholder of ["e.g. 10", "e.g. 185.50"]) {
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
      fireEvent.submit(screen.getByPlaceholderText("e.g. AAPL").closest("form"));
      await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Failed to add transaction"));
    });
  });
});

describe("Transactions (Clay UI)", () => {
  const mixed = () =>
    page({
      items: [
        { id: "1", date: "2024-01-01", ticker: "AAPL", type: "buy", shares: 10, price: 150, currency: "USD", notes: null },
        { id: "2", date: "2024-02-01", ticker: "MSFT", type: "sell", shares: 5, price: 300, currency: "USD", notes: null },
        { id: "3", date: "2024-03-01", ticker: "KO", type: "dividend", shares: 20, price: 0.5, currency: "USD", notes: null },
      ],
      total: 3,
    });

  beforeEach(() => {
    vi.clearAllMocks();
    currencyState.currency = "USD";
    api.fetchAllTradeNotes.mockResolvedValue([]);
  });

  it("Add Transaction opens as an accessible dialog", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page());
    renderPage();
    await screen.findAllByText("AAPL");

    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    const dialog = screen.getByRole("dialog", { name: "Add Transaction" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByPlaceholderText("e.g. AAPL")).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("marks placeholders as examples", async () => {
    api.fetchTransactionsPage.mockResolvedValue(page());
    renderPage();
    await screen.findAllByText("AAPL");
    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));

    expect(screen.getByPlaceholderText("e.g. AAPL")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. 10")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. 185.50")).toBeInTheDocument();
  });

  it("filters by transaction type", async () => {
    api.fetchTransactionsPage.mockResolvedValue(mixed());
    renderPage();
    await screen.findAllByText("AAPL");

    const control = screen.getByRole("group", { name: "Filter by type" });
    fireEvent.click(within(control).getByRole("button", { name: "Dividend" }));

    expect(screen.getAllByText("KO").length).toBeGreaterThan(0);
    expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
    expect(screen.queryByText("MSFT")).not.toBeInTheDocument();

    fireEvent.click(within(control).getByRole("button", { name: "All" }));
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
  });

  it("renders the type as a badge", async () => {
    api.fetchTransactionsPage.mockResolvedValue(mixed());
    const { container } = renderPage();
    await screen.findAllByText("AAPL");

    const tone = (label) =>
      Array.from(container.querySelectorAll("[data-tone]"))
        .find((el) => el.textContent === label)
        ?.getAttribute("data-tone");
    expect(tone("Buy")).toBe("brand");
    expect(tone("Sell")).toBe("neutral");
    expect(tone("Dividend")).toBe("gain");
  });

  it("formats shares and dates with the display currency locale", async () => {
    currencyState.currency = "CZK";
    api.fetchTransactionsPage.mockResolvedValue(
      page({ items: [{ id: "1", date: "2020-01-05", ticker: "AAPL", type: "buy", shares: 1234.5, price: 150, currency: "USD", notes: null }] })
    );
    renderPage();
    await screen.findAllByText("AAPL");

    expect(screen.getAllByText(/1[\s ]234,5/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Jan 5, 2020/).length).toBeGreaterThan(0);
  });

  it("renders mobile cards beside the table", async () => {
    api.fetchTransactionsPage.mockResolvedValue(mixed());
    const { container } = renderPage();
    await screen.findAllByText("AAPL");

    const cards = container.querySelector("ul.md\\:hidden");
    expect(cards).not.toBeNull();
    expect(cards.querySelectorAll("li")).toHaveLength(3);
    expect(container.querySelector(".hidden.md\\:block table")).not.toBeNull();
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./Transactions.jsx", import.meta.url))).toEqual([]);
  });
});
