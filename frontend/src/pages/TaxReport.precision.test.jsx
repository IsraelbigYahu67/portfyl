import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import TaxReport from "./TaxReport";


const localApi = vi.hoisted(() => ({ fetchTaxReport: vi.fn() }));

vi.mock("../editions/localApi", () => localApi);
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
}));
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ children }) => <span>{children}</span>,
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaxReport />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localApi.fetchTaxReport.mockReset().mockResolvedValue({
    gains: [{
      ticker: "DUST",
      buy_date: "2024-01-01",
      sell_date: "2024-02-01",
      shares: 0.00000002,
      cost_basis: 0.000002,
      proceeds: 0.000004,
      gain: 0.000002,
      gain_pct: null,
      holding_days: 31,
      term: "short",
      cz_exempt_time_test: false,
      cz_exempt_date: "2027-01-01",
      cost_basis_czk: 0.00004,
      proceeds_czk: 0.00008,
      gain_czk: 0.00004,
    }],
    summary: {
      total_realized: 0.000002,
      short_term_gains: 0.000002,
      long_term_gains: 0,
      short_term_count: 1,
      long_term_count: 0,
      total_dividends: 0,
    },
    dividend_income: [],
    unrealized: [],
    czech_tax: [],
    available_years: [2024],
  });
});

it("renders tiny realized lots without inventing a meaningful percentage", async () => {
  renderPage();

  const row = (await screen.findByText("DUST")).closest("tr");
  expect(within(row).getByText("0.00000002")).toBeInTheDocument();
  expect(within(row).getAllByText("<$0.01")).toHaveLength(3);
  expect(within(row).getByTitle("Percentage is not meaningful for a basis below one cent.")).toHaveTextContent("—");
});

it("exports API precision and leaves a null gain percentage cell empty", async () => {
  let exported;
  vi.spyOn(URL, "createObjectURL").mockImplementation((blob) => {
    exported = blob;
    return "blob:tax-report";
  });
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  renderPage();
  await screen.findByText("DUST");

  fireEvent.click(screen.getByRole("button", { name: /export csv/i }));

  const csv = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(exported);
  });
  expect(csv).toContain("Realized,DUST,2024-01-01,2024-02-01,0.00000002,0.000002,0.000004,0.000002");
  expect(csv).toContain("0.000040,0.000080,0.000040,,31,short");
  expect(csv).not.toContain("null%");
});
