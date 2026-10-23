import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AllocationTargets from "./AllocationTargets";

const api = vi.hoisted(() => ({
  fetchAllocationTargetDrift: vi.fn(),
  saveAllocationTargets: vi.fn(),
}));
vi.mock("../api", () => api);

const DRIFT = {
  currency: "USD",
  total_value: 1000,
  target_total_pct: 90,
  is_complete: false,
  unassigned_pct: 30,
  rows: [
    { ticker: "AAPL", name: "Apple", group: "Core", held: true, target_pct: 60, current_pct: 70, drift_pct: 10, market_value: 700, value_to_target: -100 },
    { ticker: "MSFT", name: null, group: "Core", held: false, target_pct: 30, current_pct: 0, drift_pct: -30, market_value: 0, value_to_target: 300 },
    { ticker: "TSLA", name: "Tesla", group: null, held: true, target_pct: null, current_pct: 30, drift_pct: null, market_value: 300, value_to_target: null },
  ],
  groups: [{ group: "Core", target_pct: 90, current_pct: 70, drift_pct: -20 }],
  missing_price_tickers: [],
  warnings: ["targets_incomplete"],
};

function renderTargets() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AllocationTargets currency="USD" />
    </QueryClientProvider>
  );
}

describe("AllocationTargets", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchAllocationTargetDrift.mockResolvedValue(DRIFT);
    api.saveAllocationTargets.mockResolvedValue({});
  });

  it("shows target, current weight and drift per holding", async () => {
    renderTargets();
    const aapl = await screen.findByRole("row", { name: /AAPL/ });
    expect(within(aapl).getByText("60.00%")).toBeInTheDocument();
    expect(within(aapl).getByText("70.00%")).toBeInTheDocument();
    expect(within(aapl).getByText("+10.00%")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /MSFT/ })).getByText(/not held/i)).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /TSLA/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "1 holding without a target" }));
    expect(within(screen.getByRole("row", { name: /TSLA/ })).getByText(/no target/i)).toBeInTheDocument();
    expect(screen.getByText(/90.00% of 100% assigned/i)).toBeInTheDocument();
    expect(screen.getByText(/10.00% not assigned/i)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /target groups/i })).toHaveTextContent("Core");
  });

  it("collapses rows without a target into one summary row", async () => {
    const untargeted = Array.from({ length: 21 }, (_, i) => ({
      ticker: `UT${i}`, name: null, group: null, held: true, target_pct: null,
      current_pct: 1, drift_pct: null, market_value: 10, value_to_target: null,
    }));
    api.fetchAllocationTargetDrift.mockResolvedValue({
      ...DRIFT, rows: [DRIFT.rows[0], ...untargeted], groups: [],
    });
    renderTargets();

    const toggle = await screen.findByRole("button", { name: "21 holdings without a target" });
    expect(screen.getByRole("row", { name: /AAPL/ })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /UT0/ })).not.toBeInTheDocument();
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    for (let i = 0; i < 21; i += 1) {
      expect(screen.getByRole("row", { name: (accessibleName) => accessibleName.split(" ")[0] === `UT${i}` })).toBeInTheDocument();
    }
  });

  it("shows an empty state when no targets are set", async () => {
    api.fetchAllocationTargetDrift.mockResolvedValue({
      ...DRIFT, target_total_pct: 0, groups: [], rows: [DRIFT.rows[2]],
    });
    renderTargets();
    expect(await screen.findByText(/no target allocation yet/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /set targets/i }));
    expect(screen.getByLabelText("Target for TSLA")).toBeInTheDocument();
  });

  it("shows a missing-price notice", async () => {
    api.fetchAllocationTargetDrift.mockResolvedValue({
      ...DRIFT, missing_price_tickers: ["AAPL"], warnings: ["targets_incomplete", "missing_prices"],
    });
    renderTargets();
    expect(await screen.findByText(/no current price for AAPL/i)).toBeInTheDocument();
  });

  it("edits and saves targets", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.change(screen.getByLabelText("Target for AAPL"), { target: { value: "70" } });
    expect(screen.getByText(/total 100.00% of 100%/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));

    await waitFor(() => expect(api.saveAllocationTargets).toHaveBeenCalledWith([
      { ticker: "AAPL", target_pct: "70", group: "Core" },
      { ticker: "MSFT", target_pct: "30", group: "Core" },
    ]));
    await waitFor(() => expect(screen.queryByLabelText("Target for AAPL")).not.toBeInTheDocument());
  });

  it("blocks saving a total above 100%", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.change(screen.getByLabelText("Target for AAPL"), { target: { value: "80" } });
    expect(screen.getByRole("alert")).toHaveTextContent("more than 100%");
    expect(screen.getByRole("button", { name: /save targets/i })).toBeDisabled();
  });

  it("adds a ticker that is not held yet", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.click(screen.getByRole("button", { name: /add ticker/i }));
    fireEvent.change(screen.getByLabelText("Ticker for new row 1"), { target: { value: "nvda" } });
    fireEvent.change(screen.getByLabelText("Target for new row 1"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));
    await waitFor(() => expect(api.saveAllocationTargets).toHaveBeenCalledWith(
      expect.arrayContaining([{ ticker: "NVDA", target_pct: "10", group: null }]),
    ));
  });

  it("keeps the editor open and shows the server message when saving fails", async () => {
    api.saveAllocationTargets.mockRejectedValue({ response: { data: { detail: "MSFT has more than one target." } } });
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));
    expect(await screen.findByText("MSFT has more than one target.")).toBeInTheDocument();
    expect(screen.getByLabelText("Target for AAPL")).toBeInTheDocument();
  });

  it("pre-fills targets from current weights", async () => {
    renderTargets();
    fireEvent.click(await screen.findByRole("button", { name: /edit targets/i }));
    fireEvent.click(screen.getByRole("button", { name: /use current weights/i }));
    expect(screen.getByLabelText("Target for AAPL")).toHaveValue("70.00");
    expect(screen.getByLabelText("Target for TSLA")).toHaveValue("30.00");
    expect(screen.getByLabelText("Target for MSFT")).toHaveValue("");
  });
});
