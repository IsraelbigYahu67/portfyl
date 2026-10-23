import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import TaxReport, { czRowStatus } from "./TaxReport";
import { legacyColorClassesIn } from "../test/legacyClasses";


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
      <MemoryRouter initialEntries={["/tax-report"]}>
        <TaxReport />
      </MemoryRouter>
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

  const row = (await screen.findAllByText("DUST")).map((n) => n.closest("tr")).find(Boolean);
  expect(within(row).getByText("0,00000002")).toBeInTheDocument();
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
  await screen.findAllByText("DUST");

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

describe("Czech row status", () => {
  const row = (patch = {}) => ({
    cz_exempt_time_test: false,
    sell_date: "2026-03-10",
    ...patch,
  });

  it("marks rows exempt when the sell year passed the value test", () => {
    expect(czRowStatus(row(), { 2026: { value_test_passed: true } })).toBe("exempt_value");
  });

  it("keeps Taxable when the sell year failed the value test", () => {
    expect(czRowStatus(row(), { 2026: { value_test_passed: false } })).toBe("taxable");
    expect(czRowStatus(row(), {})).toBe("taxable");
    expect(czRowStatus(row(), undefined)).toBe("taxable");
  });

  it("lets the time test win whatever the year says", () => {
    expect(czRowStatus(row({ cz_exempt_time_test: true }), { 2026: { value_test_passed: false } })).toBe("exempt_time");
    expect(czRowStatus(row({ cz_exempt_time_test: true }), { 2026: { value_test_passed: true } })).toBe("exempt_time");
  });

  it("renders row badges Exempt · 3y, Exempt · value test and Taxable with the right tones", async () => {
    const base = localApi.fetchTaxReport.getMockImplementation
      ? await localApi.fetchTaxReport()
      : null;
    const gain = (ticker, sell_date, time) => ({
      ...base.gains[0],
      ticker,
      sell_date,
      cz_exempt_time_test: time,
    });
    localApi.fetchTaxReport.mockResolvedValue({
      ...base,
      gains: [
        gain("TIME", "2026-02-01", true),
        gain("VALUE", "2026-02-02", false),
        gain("TAXED", "2025-02-03", false),
      ],
      czech_tax: [
        { tax_year: 2026, value_test_passed: true, trades: 2 },
        { tax_year: 2025, value_test_passed: false, trades: 1 },
      ],
    });
    renderPage();
    await screen.findAllByText("TIME");

    expect(screen.getAllByText("Exempt · 3y")[0].closest("[data-tone]")).toHaveAttribute("data-tone", "gain");
    expect(screen.getAllByText("Exempt · value test")[0].closest("[data-tone]")).toHaveAttribute("data-tone", "gain");
    expect(screen.getAllByText("Taxable")[0].closest("[data-tone]")).toHaveAttribute("data-tone", "warn");
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./TaxReport.jsx", import.meta.url))).toEqual([]);
  });
});
