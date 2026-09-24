import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import Allocation from "./Allocation";
import Transactions from "./Transactions";
import Dividends from "./Dividends";
import TaxReport from "./TaxReport";

const api = vi.hoisted(() => ({
  fetchAllHoldings: vi.fn(),
  fetchSectorBreakdown: vi.fn(),
  fetchTransactionsPage: vi.fn(),
  fetchAllTradeNotes: vi.fn(),
  createTransaction: vi.fn(),
  deleteTransaction: vi.fn(),
  fetchDividends: vi.fn(),
  fetchDividendForecast: vi.fn(),
  fetchDividendGrowth: vi.fn(),
}));
const localApi = vi.hoisted(() => ({ fetchTaxReport: vi.fn() }));

vi.mock("../api", () => api);
vi.mock("../editions/localApi", () => localApi);
vi.mock("../hooks/useT212Sync", () => ({
  useT212Sync: () => ({ connected: false, positionsQuery: {} }),
}));
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
  usePortfolio: () => ({ current: null }),
}));
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span>{children || ticker}</span>,
  useStockDetail: () => ({ openStock: vi.fn() }),
}));
vi.mock("../components/BreakdownChart", () => ({
  default: ({ title }) => <div>{title}</div>,
}));
vi.mock("../components/TradeNoteModal", () => ({ default: () => null }));
vi.mock("../components/ui/ConfirmDialog", () => ({ useConfirm: () => vi.fn() }));
vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));

function renderPage(Page) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Page />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const emptyTaxReport = {
  gains: [],
  summary: {},
  dividend_income: [],
  unrealized: [],
  czech_tax: [],
  available_years: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchAllHoldings.mockResolvedValue([]);
  api.fetchSectorBreakdown.mockResolvedValue({ sectors: [], countries: [], currencies: [], asset_types: [] });
  api.fetchTransactionsPage.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 });
  api.fetchAllTradeNotes.mockResolvedValue([]);
  api.fetchDividends.mockResolvedValue([]);
  api.fetchDividendForecast.mockResolvedValue({ months: [], total_paid: 0, total_estimated: 0 });
  api.fetchDividendGrowth.mockResolvedValue([]);
  localApi.fetchTaxReport.mockResolvedValue(emptyTaxReport);
});

it("distinguishes Allocation failure from an empty portfolio and retries", async () => {
  api.fetchAllHoldings
    .mockRejectedValueOnce({ response: { data: { detail: "Allocation unavailable" } } })
    .mockResolvedValue([]);
  renderPage(Allocation);

  expect(await screen.findByRole("alert")).toHaveTextContent("Allocation unavailable");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchAllHoldings).toHaveBeenCalledTimes(2));
});

it("keeps Allocation's legitimate empty copy", async () => {
  renderPage(Allocation);
  expect(await screen.findByText(/no holdings yet/i)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("distinguishes Transactions failure from an empty ledger and retries", async () => {
  api.fetchTransactionsPage
    .mockRejectedValueOnce({ response: { data: { detail: "Transactions unavailable" } } })
    .mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 });
  renderPage(Transactions);

  expect(await screen.findByRole("alert")).toHaveTextContent("Transactions unavailable");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchTransactionsPage).toHaveBeenCalledTimes(2));
});

it("keeps Transactions' legitimate empty copy", async () => {
  renderPage(Transactions);
  expect(await screen.findByText(/no transactions yet/i)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("distinguishes Dividends provider failure from no holdings and retries", async () => {
  api.fetchDividends
    .mockRejectedValueOnce({ response: { data: { detail: "Dividend provider unavailable" } } })
    .mockResolvedValue([]);
  renderPage(Dividends);

  expect(await screen.findByRole("alert")).toHaveTextContent("Dividend provider unavailable");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(api.fetchDividends).toHaveBeenCalledTimes(2));
});

it("keeps Dividends' legitimate empty copy", async () => {
  renderPage(Dividends);
  expect(await screen.findByText(/no holdings found/i)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("distinguishes Tax Report failure from an empty report and retries", async () => {
  localApi.fetchTaxReport
    .mockRejectedValueOnce({ response: { data: { detail: "Tax report unavailable" } } })
    .mockResolvedValue(emptyTaxReport);
  renderPage(TaxReport);

  expect(await screen.findByRole("alert")).toHaveTextContent("Tax report unavailable");
  fireEvent.click(screen.getByRole("button", { name: /retry/i }));
  await waitFor(() => expect(localApi.fetchTaxReport).toHaveBeenCalledTimes(2));
});

it("keeps Tax Report's legitimate empty copy", async () => {
  renderPage(TaxReport);
  expect(await screen.findByText(/no realized gains or losses/i)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
