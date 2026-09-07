import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import Import from "./Import";


const mocks = vi.hoisted(() => ({
  previewImportCSV: vi.fn(),
  commitImportCSV: vi.fn(),
  fetchImportUndo: vi.fn(),
  undoLastImport: vi.fn(),
  clearAllTransactions: vi.fn(),
  confirm: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock("../api", () => ({
  previewImportCSV: mocks.previewImportCSV,
  commitImportCSV: mocks.commitImportCSV,
  fetchImportUndo: mocks.fetchImportUndo,
  undoLastImport: mocks.undoLastImport,
  clearAllTransactions: mocks.clearAllTransactions,
}));

vi.mock("../components/ui/ConfirmDialog", () => ({
  useConfirm: () => mocks.confirm,
}));

vi.mock("../components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.success, error: mocks.error }),
}));


function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <Import />
    </QueryClientProvider>
  );
}


function chooseCsv(container) {
  const file = new File([
    "date,ticker,type,shares,price,currency\n2026-01-02,AAPL,buy,1,100,USD\n",
  ], "portfolio.csv", { type: "text/csv" });
  fireEvent.change(container.querySelector('input[type="file"]'), {
    target: { files: [file] },
  });
  return file;
}


describe("Import preview and undo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.fetchImportUndo.mockResolvedValue({ available: false, reason: null });
    mocks.previewImportCSV.mockResolvedValue({
      preview_id: "preview-1",
      format: "Native",
      mode: "append",
      mandatory_replace: false,
      counts: {
        source_events: 3,
        recognized_rows: 3,
        unique_rows: 2,
        duplicates_in_file: 1,
        duplicates_existing: 1,
        current: 5,
        added: 1,
        removed: 0,
        unchanged: 5,
        projected: 6,
        skipped: 0,
      },
      sample: [{ date: "2026-01-02", ticker: "AAPL", type: "buy", shares: 1, price: 100, currency: "USD" }],
      sample_truncated: false,
    });
    mocks.commitImportCSV.mockResolvedValue({
      imported: 1,
      duplicates_skipped: 2,
      projected: 6,
      mode: "append",
      format: "Native",
      undo: { available: true, expires_at: "2026-09-08T12:00:00+00:00", imported: 1, mode: "append" },
    });
    mocks.undoLastImport.mockResolvedValue({ restored: 5, undone: true });
    mocks.confirm.mockResolvedValue(true);
  });

  it("does not offer commit until the selected file has been previewed", async () => {
    const { container } = mount();
    const file = chooseCsv(container);

    expect(screen.queryByRole("button", { name: /^import 1 transaction$/i })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));

    await waitFor(() => expect(mocks.previewImportCSV).toHaveBeenCalledWith(file, false));
    expect(await screen.findByText(/1 transaction will be added/i)).toBeInTheDocument();
    expect(screen.getByText(/2 exact duplicates will be skipped/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^import 1 transaction$/i }));
    await waitFor(() => expect(mocks.commitImportCSV).toHaveBeenCalledWith(file, "preview-1", false));
  });

  it("shows replacement removals before destructive commit", async () => {
    mocks.previewImportCSV.mockResolvedValueOnce({
      preview_id: "replace-1",
      format: "Trading 212",
      mode: "replace",
      mandatory_replace: true,
      counts: {
        source_events: 10, recognized_rows: 10, unique_rows: 10,
        duplicates_in_file: 0, duplicates_existing: 4,
        current: 8, added: 6, removed: 4, unchanged: 4, projected: 10, skipped: 0,
      },
      sample: [],
      sample_truncated: false,
    });
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));

    expect(await screen.findByText(/4 current transactions will be removed/i)).toBeInTheDocument();
    expect(screen.getByText(/Trading 212 exports replace the full portfolio/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /replace portfolio with 10 transactions/i })).toBeInTheDocument();
  });

  it("offers the persisted undo point and refreshes it after use", async () => {
    mocks.fetchImportUndo.mockResolvedValueOnce({
      available: true,
      mode: "replace",
      imported: 10,
      expires_at: "2026-09-08T12:00:00+00:00",
    });
    mount();

    fireEvent.click(await screen.findByRole("button", { name: /undo last import/i }));

    await waitFor(() => expect(mocks.undoLastImport).toHaveBeenCalledTimes(1));
    expect(mocks.success).toHaveBeenCalledWith("Last import undone");
  });
});
