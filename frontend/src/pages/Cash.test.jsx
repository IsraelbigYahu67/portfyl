import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Cash from "./Cash";

// Mock the api module so no network is hit. Cash.jsx reads the active display
// currency via useCurrency() from ../App, which returns null outside of
// CurrencyProvider — Cash.jsx already falls back to "USD" in that case, so no
// mock of ../App is needed here.
vi.mock("../api", () => ({
  fetchCash: () => Promise.resolve([]),
  fetchCashBalance: () => Promise.resolve({ total: 0, total_accrued: 0, by_currency: {} }),
  createCash: vi.fn(),
  deleteCash: vi.fn(),
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

describe("Cash", () => {
  it("mounts and shows the ledger empty state", async () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <Cash />
      </QueryClientProvider>
    );
    expect(await screen.findByText(/No cash flows yet/i)).toBeInTheDocument();
  });
});
