import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import Cash from "./Cash";
import { fetchCashReconciliation, fetchT212HistoryStatus, fetchT212Status } from "../api";

// Mock the API module so no network is hit. The App hooks below provide one
// active portfolio and a stable display currency, matching Cash's normal shell.
vi.mock("../api", () => ({
  fetchCash: () => Promise.resolve([]),
  fetchCashBalance: () => Promise.resolve({ total: 0, total_accrued: 0, by_currency: {} }),
  fetchCashHistory: () => Promise.resolve({ currency: "USD", series: [] }),
  fetchCashReconciliation: vi.fn(),
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  fetchT212Positions: vi.fn(),
  syncT212: vi.fn(),
  createCash: vi.fn(),
  deleteCash: vi.fn(),
  fetchInterestRates: () => Promise.resolve([]),
  saveInterestRates: vi.fn(),
}));

vi.mock("../App", () => ({
  useCurrency: () => ({ currency: "USD" }),
  usePortfolio: () => ({ current: { id: "portfolio-1", name: "Portfolio" } }),
}));

// Cash.jsx also calls useConfirm()/useToast(), which throw outside their
// providers. The empty-state assertion never exercises delete, so we just need
// the hooks to not throw on render: confirm resolves true, toast is a no-op.
vi.mock("../components/ui/ConfirmDialog", () => ({
  useConfirm: () => () => Promise.resolve(true),
}));
vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), dismiss: vi.fn() }),
}));

const UNAVAILABLE_RECONCILIATION = {
  currency: "USD",
  broker_amount: null,
  broker_currency: null,
  broker_as_of: null,
  broker_updated_at: null,
  ledger_amount: 0,
  difference: null,
  tolerance: 1,
  status: "unavailable",
};

function renderCash() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Cash />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Cash", () => {
  beforeEach(() => {
    fetchCashReconciliation.mockReset().mockResolvedValue(UNAVAILABLE_RECONCILIATION);
    fetchT212Status.mockReset().mockResolvedValue({ connected: false });
    fetchT212HistoryStatus.mockReset().mockResolvedValue({ connected: false, run: null });
  });

  it("mounts and shows the ledger empty state", async () => {
    renderCash();
    expect(await screen.findByText(/No cash flows yet/i)).toBeInTheDocument();
  });

  it("prompts to connect Trading 212 when no broker is linked", async () => {
    renderCash();
    expect(await screen.findByText(/No Trading 212 connected/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /connect trading 212/i })).toBeInTheDocument();
  });

  it("offers a sync action when connected but no snapshot exists yet", async () => {
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();
    expect(await screen.findByText(/No Trading 212 balance synced yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sync now/i })).toBeInTheDocument();
  });

  it("flags a reconciliation difference with sync and import actions, never auto-fixing", async () => {
    fetchCashReconciliation.mockResolvedValue({
      currency: "USD",
      broker_amount: 1500,
      broker_currency: "USD",
      broker_as_of: "2026-09-20",
      broker_updated_at: "2026-09-20T10:00:00",
      ledger_amount: 1000,
      difference: 500,
      tolerance: 1,
      status: "different",
    });
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();

    expect(await screen.findByText(/Differs from your recorded history/i)).toBeInTheDocument();
    expect(screen.getByText(/usually means your recorded history is incomplete/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sync now/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /import transactions/i })).toBeInTheDocument();
    expect(screen.queryByText(/fix automatically/i)).not.toBeInTheDocument();
  });

  it("shows a matched badge with no corrective action when balances agree", async () => {
    fetchCashReconciliation.mockResolvedValue({
      currency: "USD",
      broker_amount: 1000.5,
      broker_currency: "USD",
      broker_as_of: "2026-09-20",
      broker_updated_at: "2026-09-20T10:00:00",
      ledger_amount: 1000,
      difference: 0.5,
      tolerance: 1,
      status: "matched",
    });
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();

    expect(await screen.findByText(/Matches your recorded history/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sync now/i })).not.toBeInTheDocument();
  });

  it("shows the broker balance with an import prompt when no cash history is recorded yet", async () => {
    fetchCashReconciliation.mockResolvedValue({
      currency: "USD",
      broker_amount: 250,
      broker_currency: "USD",
      broker_as_of: "2026-09-20",
      broker_updated_at: "2026-09-20T10:00:00",
      ledger_amount: 0,
      difference: null,
      tolerance: 1,
      status: "no_ledger_history",
    });
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();

    expect(await screen.findByText(/No recorded cash history yet/i)).toBeInTheDocument();
    expect(screen.getByText(/250/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /import transactions/i })).toBeInTheDocument();
  });

  it("shows an error state with retry when the reconciliation call fails", async () => {
    fetchCashReconciliation.mockRejectedValue(new Error("network error"));
    fetchT212Status.mockResolvedValue({ connected: true });
    renderCash();

    expect(await screen.findByText(/Couldn't load your broker balance/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });
});
