import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

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
  refetchPortfolios: vi.fn(),
  setCurrentId: vi.fn(),
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
vi.mock("../App", () => ({
  usePortfolio: () => ({
    current: { id: "portfolio-id", activation_state: "active" },
    pendingImportPortfolio: null,
    refetchPortfolios: mocks.refetchPortfolios,
    setCurrentId: mocks.setCurrentId,
  }),
}));


function LocationProbe() {
  const location = useLocation();
  return <output aria-label="location">{location.pathname}</output>;
}

function mount(props = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/import"]}><Import {...props} /><LocationProbe /></MemoryRouter>
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
    mocks.refetchPortfolios.mockResolvedValue({ data: [{ id: "portfolio-id", activation_state: "active" }] });
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
    fireEvent.click(screen.getByRole("button", { name: /continue to confirm/i }));
    fireEvent.click(screen.getByRole("button", { name: /^import 1 transaction$/i }));
    await waitFor(() => expect(mocks.commitImportCSV).toHaveBeenCalledWith(file, "preview-1", false));
    expect(await screen.findByRole("link", { name: /manage portfolio data/i })).toHaveAttribute("href", "/settings?section=data");
  });

  it("does not expose destructive portfolio clearing", async () => {
    mount();
    expect(await screen.findByRole("heading", { name: "Import CSV" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /clear portfolio/i })).not.toBeInTheDocument();
    expect(mocks.clearAllTransactions).not.toHaveBeenCalled();
  });

  it("leaves a focused onboarding import without activating it", async () => {
    mount({ focused: true });
    fireEvent.click(screen.getByRole("button", { name: /leave import/i }));
    expect(screen.getByLabelText("location")).toHaveTextContent("/onboarding");
    expect(mocks.commitImportCSV).not.toHaveBeenCalled();
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
    fireEvent.click(screen.getByRole("button", { name: /continue to confirm/i }));
    expect(screen.getByRole("button", { name: /replace portfolio with 10 transactions/i })).toBeInTheDocument();
  });

  it("shows the four import stages in order", () => {
    mount();
    const steps = screen.getByRole("list", { name: "Import progress" });
    expect(Array.from(steps.children).map((item) => item.textContent)).toEqual([
      "1.Select source",
      "2.Preview changes",
      "3.Confirm import",
      "4.Result / Undo",
    ]);
  });

  it("invalidates a preview when import mode changes", async () => {
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    await screen.findByText(/1 transaction will be added/i);
    fireEvent.click(screen.getByRole("button", { name: /cancel preview/i }));
    fireEvent.click(screen.getByRole("checkbox", { name: /replace existing portfolio/i }));
    expect(screen.queryByText(/1 transaction will be added/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /preview import/i })).toBeInTheDocument();
  });

  it("recovers from commit drift by requiring a fresh preview", async () => {
    mocks.commitImportCSV.mockRejectedValueOnce({ response: { status: 409, data: { detail: "stale" } } });
    const { container } = mount();
    chooseCsv(container);
    fireEvent.click(await screen.findByRole("button", { name: /preview import/i }));
    await screen.findByText(/1 transaction will be added/i);
    fireEvent.click(screen.getByRole("button", { name: /continue to confirm/i }));
    fireEvent.click(screen.getByRole("button", { name: /^import 1 transaction$/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The portfolio changed. Preview the file again.");
    expect(screen.getByRole("button", { name: /preview import/i })).toBeInTheDocument();
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
