import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import Cash from "./Cash";
import { fetchCash, fetchCashReconciliation, fetchT212HistoryStatus, fetchT212Status } from "../api";
import { legacyColorClassesIn } from "../test/legacyClasses";

// Mock the API module so no network is hit. The App hooks below provide one
// active portfolio and a stable display currency, matching Cash's normal shell.
vi.mock("../api", () => ({
  fetchCash: vi.fn(),
  fetchCashBalance: () => Promise.resolve({ total: 0, total_accrued: 0, by_currency: {} }),
  fetchCashHistory: () => Promise.resolve({ currency: "USD", series: [] }),
  fetchCashReconciliation: vi.fn(),
  fetchT212Status: vi.fn(),
  fetchT212HistoryStatus: vi.fn(),
  fetchT212Positions: vi.fn(),
  syncT212: vi.fn(),
  retryT212History: vi.fn(),
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
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Cash />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Cash", () => {
  beforeEach(() => {
    fetchCash.mockReset().mockResolvedValue([]);
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

  describe("ledger", () => {
    const makeRows = (n) =>
      Array.from({ length: n }, (_, i) => ({
        id: `row-${i}`,
        date: `2024-03-${String((i % 28) + 1).padStart(2, "0")}`,
        type: "deposit",
        amount: 100 + i,
        currency: "USD",
        note: `Entry ${i}`,
      }));

    it("shows pagination only when rows exceed one page", async () => {
      const { unmount } = renderCash();
      expect(await screen.findByText(/No cash flows yet/i)).toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: /cash ledger pages/i })).not.toBeInTheDocument();
      unmount();

      fetchCash.mockResolvedValue(makeRows(25));
      const second = renderCash();
      expect(await screen.findByText("Entry 24", { selector: "td" })).toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: /cash ledger pages/i })).not.toBeInTheDocument();
      second.unmount();

      fetchCash.mockResolvedValue(makeRows(26));
      renderCash();
      expect(await screen.findByRole("navigation", { name: /cash ledger pages/i })).toBeInTheDocument();
      const table = screen.getByRole("table");
      expect(within(table).getAllByRole("row")).toHaveLength(1 + 25);
      expect(screen.queryByText("Entry 25", { selector: "td" })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Next" }));
      expect(await screen.findByText("Entry 25", { selector: "td" })).toBeInTheDocument();
    });

    it("ledger has a header row and separate amount and note cells", async () => {
      fetchCash.mockResolvedValue([
        { id: "a", date: "2024-03-05", type: "interest", amount: 1.5, currency: "USD", note: "T212 INTEREST_ON_FREE_CASH" },
      ]);
      renderCash();
      const table = await screen.findByRole("table");
      const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent.trim());
      expect(headers.slice(0, 4)).toEqual(["Date", "Type", "Amount", "Note"]);
      const note = within(table).getByText("T212 Interest on free cash");
      expect(note.tagName).toBe("TD");
      expect(within(table).queryByText(/INTEREST_ON_FREE_CASH/)).not.toBeInTheDocument();
    });

    it("cash type options are humanized", async () => {
      renderCash();
      await screen.findByText(/No cash flows yet/i);
      const option = screen.getByRole("option", { name: "Deposit" });
      expect(option).toHaveValue("deposit");
    });
  });

  it("uses no legacy color classes", async () => {
    expect(await legacyColorClassesIn(new URL("./Cash.jsx", import.meta.url))).toEqual([]);
  });
});
