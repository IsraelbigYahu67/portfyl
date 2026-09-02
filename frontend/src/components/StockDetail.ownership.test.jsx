import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ShibuiOwnershipFilingsSection } from "./StockDetail";
import { fetchShibuiActivistStakes, fetchShibuiStrategicInvestors, fetchShibuiOwnershipDetail } from "../api";

vi.mock("../api", () => ({
  fetchShibuiActivistStakes: vi.fn(),
  fetchShibuiStrategicInvestors: vi.fn(),
  fetchShibuiOwnershipDetail: vi.fn(),
}));

function renderSection(ticker = "NVDA") {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ShibuiOwnershipFilingsSection ticker={ticker} />
    </QueryClientProvider>
  );
}

describe("ShibuiOwnershipFilingsSection ownership detail", () => {
  beforeEach(() => {
    fetchShibuiStrategicInvestors.mockResolvedValue({ investors: [] });
  });

  it("shows the eagerly-fetched shares/percent for a stake without a click", async () => {
    fetchShibuiActivistStakes.mockResolvedValue({
      stakes: [{
        filer_name: "NVIDIA CORP", filer_canonical_name: "NVIDIA CORP",
        schedule_type: "13G", filing_date: "2026-01-26", filer_is_activist: false,
        accession_number: "0001045810-26-000001", filer_cik: "1045810", primary_document: "nvda-13g.htm",
        shares_owned: 24_000_000, percent_of_class: 6.2,
      }],
    });

    renderSection();

    // .toLocaleString()'s thousands separator is locale-dependent (comma,
    // space, dot, ...) -- match the digit groups, not a specific separator.
    expect(await screen.findByText(/24.000.000 ks/)).toBeInTheDocument();
    expect(screen.getByText(/6\.2 %/)).toBeInTheDocument();
    expect(fetchShibuiOwnershipDetail).not.toHaveBeenCalled();
  });

  it("lazily fetches and displays detail for a stake past the eager cutoff", async () => {
    fetchShibuiActivistStakes.mockResolvedValue({
      stakes: [{
        filer_name: "SMALL FUND LP", filer_canonical_name: "SMALL FUND LP",
        schedule_type: "13D", filing_date: "2025-11-03", filer_is_activist: true,
        accession_number: "0001045810-25-000099", filer_cik: "1045810", primary_document: "sf-13d.htm",
        // no shares_owned/percent_of_class -- past the backend's eager cutoff
      }],
    });
    fetchShibuiOwnershipDetail.mockResolvedValue({ shares_owned: 3_450_000, percent_of_class: 8.1 });

    renderSection();

    const trigger = await screen.findByRole("button", { name: /zobrazit podíl/i });
    fireEvent.click(trigger);

    expect(await screen.findByText(/3.450.000 ks/)).toBeInTheDocument();
    expect(screen.getByText(/8\.1 %/)).toBeInTheDocument();
    expect(fetchShibuiOwnershipDetail).toHaveBeenCalledWith("1045810", "0001045810-25-000099", "sf-13d.htm");
  });

  it("shows a fallback message when EDGAR parsing couldn't find the fields", async () => {
    fetchShibuiActivistStakes.mockResolvedValue({
      stakes: [{
        filer_name: "OLD FILER INC", filer_canonical_name: "OLD FILER INC",
        schedule_type: "13G", filing_date: "2020-05-01", filer_is_activist: false,
        accession_number: "0001045810-20-000001", filer_cik: "1045810", primary_document: "old.txt",
        shares_owned: null, percent_of_class: null,
      }],
    });

    renderSection();

    expect(await screen.findByText(/podíl nedostupný/i)).toBeInTheDocument();
  });
});
