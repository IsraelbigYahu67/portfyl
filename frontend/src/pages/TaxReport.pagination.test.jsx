import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import TaxReport from "./TaxReport";

const localApi = vi.hoisted(() => ({ fetchTaxReport: vi.fn() }));
vi.mock("../editions/localApi", () => localApi);
vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD", rate: 22 }),
}));
vi.mock("../components/StockDetail", () => ({
  TickerLink: ({ ticker, children }) => <span data-testid="tax-ticker">{children || ticker}</span>,
}));

const gain = (i) => ({
  ticker: `T${i}`,
  buy_date: "2024-01-01",
  sell_date: "2024-06-01",
  shares: 1,
  cost_basis: 100,
  proceeds: 110,
  gain: 10,
  gain_pct: 10,
  holding_days: 150,
  term: "short",
  cz_exempt_time_test: false,
  cz_exempt_date: "2027-01-01",
});

const unrealizedRow = (i) => ({
  ticker: `T${i}`,
  buy_date: "2024-01-01",
  shares: 1,
  cost_basis: 100,
  market_value: 120,
  unrealized_gain: 20,
  gain_pct: 20,
  holding_days: 150,
  term: "short",
  cz_exempt_time_test: false,
  cz_exempt_date: "2027-01-01",
  cz_days_to_exemption: 400,
});

const report = (overrides = {}) => ({
  summary: {},
  gains: Array.from({ length: 120 }, (_, i) => gain(i)),
  unrealized: [],
  dividend_income: [],
  available_years: [2024],
  czech_tax: [],
  ...overrides,
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/tax-report"]}>
        <TaxReport />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TaxReport pagination", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders at most 50 realized-gain rows per page", async () => {
    localApi.fetchTaxReport.mockResolvedValue(report());
    renderPage();
    await screen.findAllByTestId("tax-ticker");
    // jsdom applies no CSS, so the desktop table and the mobile list both render.
    expect(within(screen.getByRole("table")).getAllByTestId("tax-ticker")).toHaveLength(50);
  });

  it("advancing to page 2 shows the next 50 rows", async () => {
    localApi.fetchTaxReport.mockResolvedValue(report());
    renderPage();
    await screen.findAllByTestId("tax-ticker");

    fireEvent.click(screen.getByRole("button", { name: /next/i }));

    expect((await screen.findAllByText("T50")).length).toBeGreaterThan(0);
    expect(screen.queryAllByText("T0")).toHaveLength(0);
  });

  it("switching tabs resets the page to 1", async () => {
    localApi.fetchTaxReport.mockResolvedValue(
      report({ unrealized: Array.from({ length: 120 }, (_, i) => unrealizedRow(i)) })
    );
    renderPage();
    await screen.findAllByTestId("tax-ticker");

    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    expect((await screen.findAllByText("T50")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /unrealized gains/i }));
    expect(await screen.findByText("T0")).toBeInTheDocument();
  });
});
